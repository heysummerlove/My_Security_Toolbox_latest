import csv
import io
import json
import os
import sqlite3
from datetime import datetime
from typing import Any

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "toolbox.db")
MANAGED_TASK_FINAL_STATUSES = {"已完成", "已关闭", "COMPLETED", "CANCELED"}


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_ops_tables() -> None:
    conn = get_db_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS execution_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            related_task_id INTEGER DEFAULT NULL,
            managed_task_id INTEGER DEFAULT NULL,
            task_name TEXT NOT NULL DEFAULT '',
            executor TEXT NOT NULL DEFAULT '',
            execute_time TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT '',
            content TEXT NOT NULL DEFAULT '',
            operation_type TEXT NOT NULL DEFAULT '',
            source_module TEXT NOT NULL DEFAULT '',
            detail_data TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS managed_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_name TEXT NOT NULL,
            task_type TEXT NOT NULL,
            owner TEXT NOT NULL DEFAULT '',
            start_time TEXT NOT NULL DEFAULT '',
            due_time TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT '待开始',
            progress INTEGER NOT NULL DEFAULT 0,
            attachments TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            related_exec_task_id INTEGER DEFAULT NULL,
            priority TEXT NOT NULL DEFAULT '中',
            created_by TEXT NOT NULL DEFAULT '',
            create_time TEXT NOT NULL DEFAULT '',
            update_time TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.commit()
    conn.close()


def _encode_detail_data(detail_data: dict[str, Any] | None) -> str:
    return json.dumps(detail_data or {}, ensure_ascii=False)


def _decode_detail_data(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _parse_time(value: str) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
    return None


def _normalize_progress(progress: int | None) -> int:
    if progress is None:
        return 0
    return max(0, min(100, int(progress)))


def _row_to_history(row) -> dict[str, Any] | None:
    if row is None:
        return None
    data = dict(row)
    data["detail_data"] = _decode_detail_data(data.get("detail_data"))
    return data


def _row_to_managed_task(row) -> dict[str, Any] | None:
    if row is None:
        return None
    data = dict(row)
    due_dt = _parse_time(data.get("due_time", ""))
    is_overdue = bool(
        due_dt
        and due_dt < datetime.now()
        and (data.get("status") or "") not in MANAGED_TASK_FINAL_STATUSES
    )
    data["is_overdue"] = is_overdue
    data["attachments_list"] = [
        item.strip() for item in (data.get("attachments") or "").split(",") if item.strip()
    ]
    return data


def append_history_record(
    *,
    task_name: str,
    executor: str,
    status: str,
    content: str,
    operation_type: str,
    source_module: str = "",
    related_task_id: int | None = None,
    managed_task_id: int | None = None,
    detail_data: dict[str, Any] | None = None,
) -> int:
    ensure_ops_tables()
    conn = get_db_connection()
    cur = conn.execute(
        """
        INSERT INTO execution_history (
            related_task_id,
            managed_task_id,
            task_name,
            executor,
            execute_time,
            status,
            content,
            operation_type,
            source_module,
            detail_data
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            related_task_id,
            managed_task_id,
            task_name,
            executor or "system",
            now_str(),
            status,
            content,
            operation_type,
            source_module,
            _encode_detail_data(detail_data),
        ),
    )
    history_id = cur.lastrowid
    conn.commit()
    conn.close()
    return history_id


def list_execution_history(
    *,
    keyword: str = "",
    executor: str = "",
    status: str = "",
    operation_type: str = "",
    date_from: str = "",
    date_to: str = "",
    related_task_id: int | None = None,
    managed_task_id: int | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    ensure_ops_tables()
    clauses = ["1=1"]
    params: list[Any] = []
    if keyword:
        clauses.append("(task_name LIKE ? OR content LIKE ? OR source_module LIKE ?)")
        like = f"%{keyword.strip()}%"
        params.extend([like, like, like])
    if executor:
        clauses.append("executor LIKE ?")
        params.append(f"%{executor.strip()}%")
    if status:
        clauses.append("status = ?")
        params.append(status.strip())
    if operation_type:
        clauses.append("operation_type = ?")
        params.append(operation_type.strip())
    if date_from:
        clauses.append("execute_time >= ?")
        params.append(date_from.strip())
    if date_to:
        clauses.append("execute_time <= ?")
        params.append(date_to.strip())
    if related_task_id is not None:
        clauses.append("related_task_id = ?")
        params.append(related_task_id)
    if managed_task_id is not None:
        clauses.append("managed_task_id = ?")
        params.append(managed_task_id)

    where_sql = " AND ".join(clauses)
    safe_page = max(1, page)
    safe_page_size = max(1, min(200, page_size))
    offset = (safe_page - 1) * safe_page_size

    conn = get_db_connection()
    total = conn.execute(
        f"SELECT COUNT(1) AS total FROM execution_history WHERE {where_sql}",
        params,
    ).fetchone()["total"]
    rows = conn.execute(
        f"""
        SELECT *
        FROM execution_history
        WHERE {where_sql}
        ORDER BY id DESC
        LIMIT ? OFFSET ?
        """,
        [*params, safe_page_size, offset],
    ).fetchall()
    conn.close()
    return {
        "items": [_row_to_history(row) for row in rows],
        "total": total,
        "page": safe_page,
        "page_size": safe_page_size,
    }


def get_execution_history(record_id: int) -> dict[str, Any] | None:
    ensure_ops_tables()
    conn = get_db_connection()
    row = conn.execute(
        "SELECT * FROM execution_history WHERE id = ?",
        (record_id,),
    ).fetchone()
    conn.close()
    return _row_to_history(row)


def export_execution_history_csv(**filters) -> str:
    data = list_execution_history(page=1, page_size=5000, **filters)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["记录ID", "关联执行任务ID", "关联管理任务ID", "任务名称", "执行人", "执行时间", "状态", "内容", "操作类型", "来源模块"])
    for item in data["items"]:
        writer.writerow(
            [
                item.get("id"),
                item.get("related_task_id") or "",
                item.get("managed_task_id") or "",
                item.get("task_name") or "",
                item.get("executor") or "",
                item.get("execute_time") or "",
                item.get("status") or "",
                item.get("content") or "",
                item.get("operation_type") or "",
                item.get("source_module") or "",
            ]
        )
    return buffer.getvalue()


def create_managed_task(payload: dict[str, Any], operator: str) -> int:
    ensure_ops_tables()
    timestamp = now_str()
    task_name = (payload.get("task_name") or "").strip()
    task_type = (payload.get("task_type") or "").strip()
    owner = (payload.get("owner") or "").strip()
    start_time = (payload.get("start_time") or "").strip()
    due_time = (payload.get("due_time") or "").strip()
    status = (payload.get("status") or "待开始").strip()
    progress = _normalize_progress(payload.get("progress"))
    attachments = (payload.get("attachments") or "").strip()
    description = (payload.get("description") or "").strip()
    priority = (payload.get("priority") or "中").strip()
    related_exec_task_id = payload.get("related_exec_task_id")

    conn = get_db_connection()
    cur = conn.execute(
        """
        INSERT INTO managed_tasks (
            task_name,
            task_type,
            owner,
            start_time,
            due_time,
            status,
            progress,
            attachments,
            description,
            related_exec_task_id,
            priority,
            created_by,
            create_time,
            update_time
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            task_name,
            task_type,
            owner,
            start_time,
            due_time,
            status,
            progress,
            attachments,
            description,
            related_exec_task_id,
            priority,
            operator,
            timestamp,
            timestamp,
        ),
    )
    task_id = cur.lastrowid
    conn.commit()
    conn.close()

    append_history_record(
        task_name=task_name,
        executor=operator,
        status=status,
        content=f"创建检测任务，负责人：{owner or '未分配'}，进度：{progress}%",
        operation_type="创建检测任务",
        source_module="task_management",
        managed_task_id=task_id,
        related_task_id=related_exec_task_id,
        detail_data=payload,
    )
    return task_id


def get_managed_task(task_id: int) -> dict[str, Any] | None:
    ensure_ops_tables()
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM managed_tasks WHERE id = ?", (task_id,)).fetchone()
    conn.close()
    return _row_to_managed_task(row)


def list_managed_tasks(
    *,
    keyword: str = "",
    task_type: str = "",
    status: str = "",
    owner: str = "",
    overdue_only: bool = False,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    ensure_ops_tables()
    clauses = ["1=1"]
    params: list[Any] = []
    if keyword:
        clauses.append("(task_name LIKE ? OR description LIKE ? OR attachments LIKE ?)")
        like = f"%{keyword.strip()}%"
        params.extend([like, like, like])
    if task_type:
        clauses.append("task_type = ?")
        params.append(task_type.strip())
    if status:
        clauses.append("status = ?")
        params.append(status.strip())
    if owner:
        clauses.append("owner LIKE ?")
        params.append(f"%{owner.strip()}%")

    where_sql = " AND ".join(clauses)
    safe_page = max(1, page)
    safe_page_size = max(1, min(200, page_size))
    offset = (safe_page - 1) * safe_page_size

    conn = get_db_connection()
    rows = conn.execute(
        f"""
        SELECT *
        FROM managed_tasks
        WHERE {where_sql}
        ORDER BY id DESC
        """,
        params,
    ).fetchall()
    conn.close()

    items = [_row_to_managed_task(row) for row in rows]
    if overdue_only:
        items = [item for item in items if item.get("is_overdue")]

    total = len(items)
    overdue_count = sum(1 for item in items if item.get("is_overdue"))
    page_items = items[offset:offset + safe_page_size]
    return {
        "items": page_items,
        "total": total,
        "page": safe_page,
        "page_size": safe_page_size,
        "overdue_count": overdue_count,
    }


def _update_managed_task_fields(task_id: int, updates: dict[str, Any]) -> None:
    if not updates:
        return
    updates = {key: value for key, value in updates.items() if value is not None}
    if not updates:
        return
    updates["update_time"] = now_str()
    fields = ", ".join(f"{key} = ?" for key in updates.keys())
    values = list(updates.values())
    values.append(task_id)
    conn = get_db_connection()
    conn.execute(f"UPDATE managed_tasks SET {fields} WHERE id = ?", values)
    conn.commit()
    conn.close()


def update_managed_task(task_id: int, payload: dict[str, Any], operator: str, *, operation_type: str = "更新检测任务") -> bool:
    existing = get_managed_task(task_id)
    if not existing:
        return False
    updates = {
        "task_name": (payload.get("task_name") or existing["task_name"]).strip(),
        "task_type": (payload.get("task_type") or existing["task_type"]).strip(),
        "owner": (payload.get("owner") or existing["owner"]).strip(),
        "start_time": (payload.get("start_time") or existing["start_time"]).strip(),
        "due_time": (payload.get("due_time") or existing["due_time"]).strip(),
        "status": (payload.get("status") or existing["status"]).strip(),
        "progress": _normalize_progress(payload.get("progress") if payload.get("progress") is not None else existing["progress"]),
        "attachments": (payload.get("attachments") if payload.get("attachments") is not None else existing["attachments"]).strip(),
        "description": (payload.get("description") if payload.get("description") is not None else existing["description"]).strip(),
        "related_exec_task_id": payload.get("related_exec_task_id") if "related_exec_task_id" in payload else existing.get("related_exec_task_id"),
        "priority": (payload.get("priority") or existing["priority"]).strip(),
    }
    _update_managed_task_fields(task_id, updates)
    append_history_record(
        task_name=updates["task_name"],
        executor=operator,
        status=updates["status"],
        content=f"{operation_type}，负责人：{updates['owner'] or '未分配'}，进度：{updates['progress']}%",
        operation_type=operation_type,
        source_module="task_management",
        managed_task_id=task_id,
        related_task_id=updates.get("related_exec_task_id"),
        detail_data=updates,
    )
    return True


def batch_update_managed_tasks(task_ids: list[int], action: str, value: Any, operator: str) -> int:
    count = 0
    for task_id in task_ids:
        task = get_managed_task(task_id)
        if not task:
            continue
        if action == "assign_owner":
            success = update_managed_task(task_id, {"owner": str(value or "").strip()}, operator, operation_type="批量分配负责人")
        elif action == "update_status":
            success = update_managed_task(task_id, {"status": str(value or "").strip()}, operator, operation_type="批量更新状态")
        elif action == "update_progress":
            success = update_managed_task(task_id, {"progress": _normalize_progress(int(value))}, operator, operation_type="批量更新进度")
        elif action == "close_tasks":
            success = update_managed_task(task_id, {"status": "已关闭", "progress": 100}, operator, operation_type="批量关闭任务")
        else:
            success = False
        count += 1 if success else 0
    return count


def get_managed_task_detail(task_id: int) -> dict[str, Any] | None:
    task = get_managed_task(task_id)
    if not task:
        return None
    history_by_task = list_execution_history(managed_task_id=task_id, page=1, page_size=200)["items"]
    related_exec_task_id = task.get("related_exec_task_id")
    if related_exec_task_id:
        history_by_exec = list_execution_history(related_task_id=related_exec_task_id, page=1, page_size=200)["items"]
        seen_ids = {item["id"] for item in history_by_task}
        for item in history_by_exec:
            if item["id"] not in seen_ids:
                history_by_task.append(item)
        history_by_task.sort(key=lambda item: item.get("id", 0), reverse=True)
    return {
        "task": task,
        "history": history_by_task[:200],
    }


def export_managed_tasks_csv(**filters) -> str:
    data = list_managed_tasks(page=1, page_size=5000, **filters)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["任务ID", "任务名称", "任务类型", "负责人", "开始时间", "截止时间", "状态", "进度", "优先级", "附件", "关联执行任务ID", "是否逾期", "创建人", "创建时间", "更新时间"])
    for item in data["items"]:
        writer.writerow(
            [
                item.get("id"),
                item.get("task_name") or "",
                item.get("task_type") or "",
                item.get("owner") or "",
                item.get("start_time") or "",
                item.get("due_time") or "",
                item.get("status") or "",
                item.get("progress") or 0,
                item.get("priority") or "",
                item.get("attachments") or "",
                item.get("related_exec_task_id") or "",
                "是" if item.get("is_overdue") else "否",
                item.get("created_by") or "",
                item.get("create_time") or "",
                item.get("update_time") or "",
            ]
        )
    return buffer.getvalue()
