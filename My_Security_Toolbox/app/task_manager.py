import json
import os
import sqlite3
import subprocess
import threading
from datetime import datetime
from typing import Any

from app.ops_manager import append_history_record

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "toolbox.db")

FINAL_STATUSES = {"COMPLETED", "ERROR", "CANCELED"}
RUNNING_HANDLES: dict[int, Any] = {}
HANDLE_LOCK = threading.Lock()
_UNSET = object()


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_task_tables() -> None:
    conn = get_db_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target TEXT NOT NULL,
            tool TEXT NOT NULL,
            status TEXT NOT NULL,
            status_code TEXT NOT NULL DEFAULT 'PENDING',
            result_path TEXT NOT NULL DEFAULT '',
            pid INTEGER DEFAULT NULL,
            cancel_requested INTEGER NOT NULL DEFAULT 0,
            create_time TEXT NOT NULL DEFAULT '',
            update_time TEXT NOT NULL DEFAULT '',
            extra_data TEXT NOT NULL DEFAULT '{}'
        )
        """
    )

    columns = {row["name"] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()}
    if "status_code" not in columns:
        conn.execute("ALTER TABLE tasks ADD COLUMN status_code TEXT DEFAULT 'PENDING'")
    if "result_path" not in columns:
        conn.execute("ALTER TABLE tasks ADD COLUMN result_path TEXT DEFAULT ''")
    if "pid" not in columns:
        conn.execute("ALTER TABLE tasks ADD COLUMN pid INTEGER DEFAULT NULL")
    if "cancel_requested" not in columns:
        conn.execute("ALTER TABLE tasks ADD COLUMN cancel_requested INTEGER DEFAULT 0")
    if "create_time" not in columns:
        conn.execute("ALTER TABLE tasks ADD COLUMN create_time TEXT DEFAULT ''")
    if "extra_data" not in columns:
        conn.execute("ALTER TABLE tasks ADD COLUMN extra_data TEXT DEFAULT '{}'")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS task_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            log_time TEXT NOT NULL,
            message TEXT NOT NULL,
            FOREIGN KEY (task_id) REFERENCES tasks(id)
        )
        """
    )
    conn.commit()
    conn.close()


def _encode_extra_data(extra_data: dict[str, Any] | None) -> str:
    return json.dumps(extra_data or {}, ensure_ascii=False)


def _decode_extra_data(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def row_to_dict(row) -> dict[str, Any] | None:
    if row is None:
        return None
    data = dict(row)
    data["cancel_requested"] = bool(data.get("cancel_requested"))
    data["extra_data"] = _decode_extra_data(data.get("extra_data"))
    return data


def create_task(
    tool: str,
    target: str,
    initial_message: str,
    *,
    extra_data: dict[str, Any] | None = None,
) -> int:
    ensure_task_tables()
    conn = get_db_connection()
    timestamp = now_str()
    cur = conn.execute(
        """
        INSERT INTO tasks (target, tool, status, status_code, result_path, pid, cancel_requested, create_time, update_time, extra_data)
        VALUES (?, ?, ?, 'PENDING', '', NULL, 0, ?, ?, ?)
        """,
        (target, tool, initial_message, timestamp, timestamp, _encode_extra_data(extra_data)),
    )
    task_id = cur.lastrowid
    conn.commit()
    conn.close()
    append_log(task_id, initial_message)
    return task_id


def append_log(task_id: int, message: str) -> None:
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO task_logs (task_id, log_time, message) VALUES (?, ?, ?)",
        (task_id, now_str(), message),
    )
    conn.commit()
    conn.close()


def update_task(
    task_id: int,
    status_code: str,
    status_message: str,
    *,
    result_path: str | object = _UNSET,
    pid: int | None | object = _UNSET,
    extra_data: dict[str, Any] | object = _UNSET,
    append_status_log: bool = True,
) -> None:
    conn = get_db_connection()
    current_row = conn.execute(
        "SELECT tool, result_path, pid, extra_data FROM tasks WHERE id = ?",
        (task_id,),
    ).fetchone()
    if current_row is None:
        conn.close()
        return

    final_result_path = current_row["result_path"] if result_path is _UNSET else result_path
    final_pid = current_row["pid"] if pid is _UNSET else pid
    final_extra_data = (
        current_row["extra_data"]
        if extra_data is _UNSET
        else _encode_extra_data(extra_data)
    )

    conn.execute(
        """
        UPDATE tasks
        SET status = ?, status_code = ?, result_path = ?, pid = ?, extra_data = ?, update_time = ?
        WHERE id = ?
        """,
        (
            status_message,
            status_code,
            final_result_path,
            final_pid,
            final_extra_data,
            now_str(),
            task_id,
        ),
    )
    conn.commit()
    conn.close()

    if append_status_log:
        append_log(task_id, status_message)

    try:
        extra = _decode_extra_data(final_extra_data)
        operator = extra.get("_history_operator") or "system"
        task_name = extra.get("_history_task_name") or current_row["tool"] or f"task-{task_id}"
        operation_type = extra.get("_history_operation_type") or "执行检测任务"
        source_module = extra.get("_history_source_module") or current_row["tool"] or ""
        append_history_record(
            related_task_id=task_id,
            task_name=task_name,
            executor=operator,
            status=status_code,
            content=status_message,
            operation_type=operation_type,
            source_module=source_module,
            detail_data={"task_id": task_id, "status_code": status_code, "result_path": final_result_path or ""},
        )
    except Exception:
        pass


def register_handle(task_id: int, handle: Any) -> None:
    with HANDLE_LOCK:
        RUNNING_HANDLES[task_id] = handle
    conn = get_db_connection()
    conn.execute(
        "UPDATE tasks SET pid = ?, update_time = ? WHERE id = ?",
        (getattr(handle, "pid", None), now_str(), task_id),
    )
    conn.commit()
    conn.close()


def unregister_handle(task_id: int) -> None:
    with HANDLE_LOCK:
        RUNNING_HANDLES.pop(task_id, None)
    conn = get_db_connection()
    conn.execute("UPDATE tasks SET pid = NULL WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()


def terminate_running_handles() -> None:
    with HANDLE_LOCK:
        items = list(RUNNING_HANDLES.items())
        RUNNING_HANDLES.clear()

    for task_id, handle in items:
        try:
            pid = getattr(handle, "pid", None)
            if pid and os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
            elif hasattr(handle, "terminate"):
                handle.terminate()
            elif hasattr(handle, "cancel"):
                handle.cancel()
        except Exception:
            try:
                if hasattr(handle, "kill"):
                    handle.kill()
            except Exception:
                pass

        try:
            conn = get_db_connection()
            conn.execute(
                "UPDATE tasks SET pid = NULL, cancel_requested = 1, status_code = 'CANCELED', status = ?, update_time = ? WHERE id = ?",
                ("CANCELED: server shutdown terminated the running task", now_str(), task_id),
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

        try:
            append_log(task_id, "CANCELED: server shutdown terminated the running task")
        except Exception:
            pass


def request_cancel(task_id: int) -> bool:
    conn = get_db_connection()
    row = conn.execute(
        "SELECT status_code FROM tasks WHERE id = ?",
        (task_id,),
    ).fetchone()
    if not row:
        conn.close()
        return False
    if row["status_code"] in FINAL_STATUSES:
        conn.close()
        return True

    conn.execute(
        "UPDATE tasks SET cancel_requested = 1, status_code = 'CANCEL_REQUESTED', status = ?, update_time = ? WHERE id = ?",
        ("CANCEL_REQUESTED: pause requested", now_str(), task_id),
    )
    conn.commit()
    conn.close()
    append_log(task_id, "CANCEL_REQUESTED: pause requested")

    try:
        task = get_task(task_id)
        extra = (task or {}).get("extra_data") or {}
        append_history_record(
            related_task_id=task_id,
            task_name=extra.get("_history_task_name") or (task or {}).get("tool") or f"task-{task_id}",
            executor=extra.get("_history_operator") or "system",
            status="CANCEL_REQUESTED",
            content="CANCEL_REQUESTED: pause requested",
            operation_type=extra.get("_history_operation_type") or "执行检测任务",
            source_module=extra.get("_history_source_module") or (task or {}).get("tool") or "",
            detail_data={"task_id": task_id},
        )
    except Exception:
        pass

    with HANDLE_LOCK:
        handle = RUNNING_HANDLES.get(task_id)

    if handle is None:
        return True

    try:
        pid = getattr(handle, "pid", None)
        if pid and os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        elif hasattr(handle, "terminate"):
            handle.terminate()
        elif hasattr(handle, "cancel"):
            handle.cancel()
    except Exception:
        try:
            if hasattr(handle, "kill"):
                handle.kill()
        except Exception:
            pass
    return True


def is_cancel_requested(task_id: int) -> bool:
    conn = get_db_connection()
    row = conn.execute(
        "SELECT cancel_requested FROM tasks WHERE id = ?",
        (task_id,),
    ).fetchone()
    conn.close()
    return bool(row and row["cancel_requested"])


def get_task(task_id: int):
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    conn.close()
    return row_to_dict(row)


def list_recent_tasks(limit: int = 20) -> list[dict[str, Any]]:
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT * FROM tasks ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [row_to_dict(row) for row in rows]


def get_task_logs(task_id: int, limit: int = 200) -> list[dict[str, str]]:
    conn = get_db_connection()
    rows = conn.execute(
        """
        SELECT log_time, message
        FROM task_logs
        WHERE task_id = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (task_id, limit),
    ).fetchall()
    conn.close()
    return [
        {"log_time": row["log_time"], "message": row["message"]}
        for row in reversed(rows)
    ]


def read_result_preview(result_path: str, max_chars: int = 12000) -> str:
    if not result_path or not os.path.exists(result_path):
        return ""
    ext = os.path.splitext(result_path)[1].lower()
    if ext in {".zip", ".docx", ".xlsx", ".xls", ".pdf", ".png", ".jpg", ".jpeg"}:
        return f"[binary file ready] {os.path.basename(result_path)}"
    try:
        with open(result_path, "r", encoding="utf-8", errors="replace") as fh:
            data = fh.read()
    except OSError:
        return ""
    if len(data) <= max_chars:
        return data
    return data[-max_chars:]
