import csv
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from app.auth import get_db_connection

BASE_DIR = Path(__file__).resolve().parent.parent
EXPORT_DIR = BASE_DIR / "data" / "module_data_exports"
MAX_PAGE_SIZE = 500

COMPLIANCE_PREFIX = "HC"
FIRMWARE_PREFIX = "FW"

COMPLIANCE_RECORD_FIELDS = [
    "record_no",
    "standard",
    "sample_name",
    "device_model",
    "manufacturer",
    "device_category",
    "check_item",
    "result",
    "issue_desc",
    "rectification",
    "check_date",
    "inspector",
    "remark",
    "source_trace",
    "payload_json",
    "created_by",
    "created_by_username",
]
FIRMWARE_RECORD_FIELDS = [
    "record_no",
    "sample_name",
    "device_model",
    "manufacturer",
    "check_date",
    "inspector",
    "remark",
    "attachments",
    "items_json",
    "payload_json",
    "created_by",
    "created_by_username",
]
FIRMWARE_ITEM_NAMES = [
    "固件提取",
    "固件元信息分析",
    "敏感文件提取",
    "供应链安全分析",
    "代码审计",
    "漏洞挖掘",
    "漏洞匹配",
    "恶意代码检测",
    "仿真测试",
]


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _today_key() -> str:
    return datetime.now().strftime("%Y%m%d")


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _json_loads(text: str, fallback: Any) -> Any:
    try:
        return json.loads(text or "")
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _row_to_dict(row) -> dict[str, Any]:
    return dict(row) if row else {}


def _safe_name(value: str, fallback: str) -> str:
    safe = re.sub(r"[^\w\u4e00-\u9fff\-]+", "_", _clean(value) or fallback).strip("_")
    return safe or fallback


def _serialize_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload or {}, ensure_ascii=False)


def _serialize_items(items: list[dict[str, Any]]) -> str:
    return json.dumps(items or [], ensure_ascii=False)


def _normalize_shared_device(payload: dict[str, Any]) -> dict[str, str]:
    return {
        "sample_name": _clean(payload.get("sample_name")),
        "device_model": _clean(payload.get("device_model")),
        "manufacturer": _clean(payload.get("manufacturer")),
        "device_category": _clean(payload.get("device_category")),
        "spec": _clean(payload.get("spec")),
        "remark": _clean(payload.get("remark")),
    }


def _normalize_compliance_payload(payload: dict[str, Any]) -> dict[str, str]:
    data = {
        "record_no": _clean(payload.get("record_no") or payload.get("compliance-record-no")),
        "standard": _clean(payload.get("standard") or payload.get("compliance-standard")),
        "sample_name": _clean(payload.get("sample_name") or payload.get("compliance-sample-name")),
        "device_model": _clean(payload.get("device_model") or payload.get("compliance-device-model")),
        "manufacturer": _clean(payload.get("manufacturer") or payload.get("compliance-manufacturer")),
        "device_category": _clean(payload.get("device_category") or payload.get("compliance-device-category")),
        "check_item": _clean(payload.get("check_item") or payload.get("compliance-check-item")),
        "result": _clean(payload.get("result") or payload.get("compliance-result")),
        "issue_desc": _clean(payload.get("issue_desc") or payload.get("compliance-issue-desc")),
        "rectification": _clean(payload.get("rectification") or payload.get("compliance-rectification")),
        "check_date": _clean(payload.get("check_date") or payload.get("compliance-check-date")),
        "inspector": _clean(payload.get("inspector") or payload.get("compliance-inspector")),
        "remark": _clean(payload.get("remark") or payload.get("compliance-remark")),
        "source_trace": _clean(payload.get("source_trace") or payload.get("compliance-source-trace")),
    }
    return data


def _normalize_firmware_payload(payload: dict[str, Any]) -> dict[str, Any]:
    items = payload.get("items")
    if not isinstance(items, list):
        items = []
    normalized_items: list[dict[str, str | int]] = []
    for index, raw_item in enumerate(items, start=1):
        item = raw_item if isinstance(raw_item, dict) else {}
        normalized_items.append(
            {
                "item_no": int(item.get("item_no") or index),
                "item_name": _clean(item.get("item_name")) or FIRMWARE_ITEM_NAMES[index - 1],
                "description": _clean(item.get("description")),
                "mode": _clean(item.get("mode")),
                "method": _clean(item.get("method")),
                "process": _clean(item.get("process")),
                "result": _clean(item.get("result")),
            }
        )
    return {
        "record_no": _clean(payload.get("record_no")),
        "sample_name": _clean(payload.get("sample_name")),
        "device_model": _clean(payload.get("device_model")),
        "manufacturer": _clean(payload.get("manufacturer")),
        "check_date": _clean(payload.get("check_date")),
        "inspector": _clean(payload.get("inspector")),
        "remark": _clean(payload.get("remark")),
        "attachments": _clean(payload.get("attachments")),
        "items": normalized_items,
    }


def _validate_shared_device(data: dict[str, str]) -> None:
    if not data["sample_name"]:
        raise ValueError("样品名称不能为空")
    if not data["device_model"]:
        raise ValueError("设备型号不能为空")


def _validate_compliance_record(data: dict[str, str]) -> None:
    required_fields = {
        "record_no": "检测编号",
        "sample_name": "样品名称",
        "device_model": "设备型号",
        "check_item": "检查项目",
        "result": "检查结果",
        "check_date": "检查日期",
        "inspector": "检查人",
    }
    for field, label in required_fields.items():
        if not data.get(field):
            raise ValueError(f"{label}不能为空")
    if data["result"] not in {"符合", "不符合", "待复测"}:
        raise ValueError("检查结果不合法")


def _validate_firmware_record(data: dict[str, Any]) -> None:
    required_fields = {
        "record_no": "检测编号",
        "sample_name": "样品名称",
        "device_model": "设备型号",
        "check_date": "检查日期",
        "inspector": "检查人",
    }
    for field, label in required_fields.items():
        if not data.get(field):
            raise ValueError(f"{label}不能为空")
    items = data.get("items") or []
    if len(items) != 9:
        raise ValueError("固件检测项数量不完整")
    for item in items:
        if not _clean(item.get("process")) or not _clean(item.get("result")):
            raise ValueError(f"{_clean(item.get('item_name')) or '检测项'}的检测过程和检测结果不能为空")


def _shared_device_from_row(row) -> dict[str, Any]:
    data = _row_to_dict(row)
    if not data:
        return {}
    return {
        "id": data.get("id"),
        "sample_name": data.get("sample_name", ""),
        "device_model": data.get("device_model", ""),
        "manufacturer": data.get("manufacturer", ""),
        "device_category": data.get("device_category", ""),
        "spec": data.get("spec", ""),
        "remark": data.get("remark", ""),
        "created_at": data.get("create_time", ""),
        "updated_at": data.get("update_time", ""),
    }


def _compliance_record_from_row(row) -> dict[str, Any]:
    data = _row_to_dict(row)
    if not data:
        return {}
    payload = _json_loads(data.get("payload_json", "{}"), {})
    payload.update(
        {
            "id": data.get("id"),
            "record_no": data.get("record_no", ""),
            "standard": data.get("standard", ""),
            "sample_name": data.get("sample_name", ""),
            "device_model": data.get("device_model", ""),
            "manufacturer": data.get("manufacturer", ""),
            "device_category": data.get("device_category", ""),
            "check_item": data.get("check_item", ""),
            "result": data.get("result", ""),
            "issue_desc": data.get("issue_desc", ""),
            "rectification": data.get("rectification", ""),
            "check_date": data.get("check_date", ""),
            "inspector": data.get("inspector", ""),
            "remark": data.get("remark", ""),
            "source_trace": data.get("source_trace", ""),
            "created_by": data.get("created_by"),
            "created_by_username": data.get("created_by_username", ""),
            "created_at": data.get("create_time", ""),
            "updated_at": data.get("update_time", ""),
        }
    )
    return payload


def _firmware_record_from_row(row) -> dict[str, Any]:
    data = _row_to_dict(row)
    if not data:
        return {}
    payload = _json_loads(data.get("payload_json", "{}"), {})
    payload.update(
        {
            "id": data.get("id"),
            "record_no": data.get("record_no", ""),
            "sample_name": data.get("sample_name", ""),
            "device_model": data.get("device_model", ""),
            "manufacturer": data.get("manufacturer", ""),
            "check_date": data.get("check_date", ""),
            "inspector": data.get("inspector", ""),
            "remark": data.get("remark", ""),
            "attachments": data.get("attachments", ""),
            "items": _json_loads(data.get("items_json", "[]"), []),
            "created_by": data.get("created_by"),
            "created_by_username": data.get("created_by_username", ""),
            "created_at": data.get("create_time", ""),
            "updated_at": data.get("update_time", ""),
        }
    )
    return payload


def ensure_module_data_tables() -> None:
    conn = get_db_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS module_shared_devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sample_name TEXT NOT NULL COLLATE NOCASE,
            device_model TEXT NOT NULL COLLATE NOCASE,
            manufacturer TEXT NOT NULL DEFAULT '',
            device_category TEXT NOT NULL DEFAULT '',
            spec TEXT NOT NULL DEFAULT '',
            remark TEXT NOT NULL DEFAULT '',
            create_time TEXT NOT NULL,
            update_time TEXT NOT NULL,
            UNIQUE(sample_name, device_model)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS module_form_drafts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            module_type TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            create_time TEXT NOT NULL,
            update_time TEXT NOT NULL,
            UNIQUE(module_type, user_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS module_record_sequences (
            module_key TEXT NOT NULL,
            date_key TEXT NOT NULL,
            current_value INTEGER NOT NULL DEFAULT 0,
            update_time TEXT NOT NULL,
            PRIMARY KEY (module_key, date_key)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS module_compliance_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_no TEXT NOT NULL UNIQUE,
            standard TEXT NOT NULL DEFAULT '',
            sample_name TEXT NOT NULL,
            device_model TEXT NOT NULL,
            manufacturer TEXT NOT NULL DEFAULT '',
            device_category TEXT NOT NULL DEFAULT '',
            check_item TEXT NOT NULL,
            result TEXT NOT NULL,
            issue_desc TEXT NOT NULL DEFAULT '',
            rectification TEXT NOT NULL DEFAULT '',
            check_date TEXT NOT NULL,
            inspector TEXT NOT NULL,
            remark TEXT NOT NULL DEFAULT '',
            source_trace TEXT NOT NULL DEFAULT '',
            payload_json TEXT NOT NULL DEFAULT '{}',
            created_by INTEGER DEFAULT NULL,
            created_by_username TEXT NOT NULL DEFAULT '',
            create_time TEXT NOT NULL,
            update_time TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS module_firmware_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_no TEXT NOT NULL UNIQUE,
            sample_name TEXT NOT NULL,
            device_model TEXT NOT NULL,
            manufacturer TEXT NOT NULL DEFAULT '',
            check_date TEXT NOT NULL,
            inspector TEXT NOT NULL,
            remark TEXT NOT NULL DEFAULT '',
            attachments TEXT NOT NULL DEFAULT '',
            items_json TEXT NOT NULL DEFAULT '[]',
            payload_json TEXT NOT NULL DEFAULT '{}',
            created_by INTEGER DEFAULT NULL,
            created_by_username TEXT NOT NULL DEFAULT '',
            create_time TEXT NOT NULL,
            update_time TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def list_shared_devices() -> list[dict[str, Any]]:
    ensure_module_data_tables()
    conn = get_db_connection()
    rows = conn.execute(
        """
        SELECT id, sample_name, device_model, manufacturer, device_category, spec, remark, create_time, update_time
        FROM module_shared_devices
        ORDER BY sample_name COLLATE NOCASE ASC, device_model COLLATE NOCASE ASC, id ASC
        """
    ).fetchall()
    conn.close()
    return [_shared_device_from_row(row) for row in rows]


def upsert_shared_device(payload: dict[str, Any]) -> dict[str, Any]:
    ensure_module_data_tables()
    data = _normalize_shared_device(payload)
    _validate_shared_device(data)
    now = _now_text()
    conn = get_db_connection()
    existing = conn.execute(
        """
        SELECT id, sample_name, device_model, manufacturer, device_category, spec, remark, create_time, update_time
        FROM module_shared_devices
        WHERE sample_name = ? AND device_model = ?
        """,
        (data["sample_name"], data["device_model"]),
    ).fetchone()
    if existing:
        existing_data = _shared_device_from_row(existing)
        next_data = {
            "manufacturer": data["manufacturer"] or existing_data.get("manufacturer", ""),
            "device_category": data["device_category"] or existing_data.get("device_category", ""),
            "spec": data["spec"] or existing_data.get("spec", ""),
            "remark": data["remark"] or existing_data.get("remark", ""),
        }
        conn.execute(
            """
            UPDATE module_shared_devices
            SET manufacturer = ?, device_category = ?, spec = ?, remark = ?, update_time = ?
            WHERE id = ?
            """,
            (
                next_data["manufacturer"],
                next_data["device_category"],
                next_data["spec"],
                next_data["remark"],
                now,
                existing_data["id"],
            ),
        )
        record_id = int(existing_data["id"])
    else:
        cursor = conn.execute(
            """
            INSERT INTO module_shared_devices (
                sample_name,
                device_model,
                manufacturer,
                device_category,
                spec,
                remark,
                create_time,
                update_time
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["sample_name"],
                data["device_model"],
                data["manufacturer"],
                data["device_category"],
                data["spec"],
                data["remark"],
                now,
                now,
            ),
        )
        record_id = int(cursor.lastrowid)
    conn.commit()
    row = conn.execute(
        """
        SELECT id, sample_name, device_model, manufacturer, device_category, spec, remark, create_time, update_time
        FROM module_shared_devices
        WHERE id = ?
        """,
        (record_id,),
    ).fetchone()
    conn.close()
    return _shared_device_from_row(row)


def get_user_draft(module_type: str, user_id: int) -> dict[str, Any]:
    ensure_module_data_tables()
    conn = get_db_connection()
    row = conn.execute(
        """
        SELECT payload_json, create_time, update_time
        FROM module_form_drafts
        WHERE module_type = ? AND user_id = ?
        """,
        (_clean(module_type), int(user_id)),
    ).fetchone()
    conn.close()
    if not row:
        return {}
    return _json_loads(row["payload_json"], {})


def save_user_draft(module_type: str, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    ensure_module_data_tables()
    now = _now_text()
    data = payload or {}
    conn = get_db_connection()
    existing = conn.execute(
        "SELECT id FROM module_form_drafts WHERE module_type = ? AND user_id = ?",
        (_clean(module_type), int(user_id)),
    ).fetchone()
    if existing:
        conn.execute(
            """
            UPDATE module_form_drafts
            SET payload_json = ?, update_time = ?
            WHERE id = ?
            """,
            (_serialize_payload(data), now, int(existing["id"])),
        )
    else:
        conn.execute(
            """
            INSERT INTO module_form_drafts (module_type, user_id, payload_json, create_time, update_time)
            VALUES (?, ?, ?, ?, ?)
            """,
            (_clean(module_type), int(user_id), _serialize_payload(data), now, now),
        )
    conn.commit()
    conn.close()
    return data


def clear_user_draft(module_type: str, user_id: int) -> bool:
    ensure_module_data_tables()
    conn = get_db_connection()
    cursor = conn.execute(
        "DELETE FROM module_form_drafts WHERE module_type = ? AND user_id = ?",
        (_clean(module_type), int(user_id)),
    )
    conn.commit()
    conn.close()
    return cursor.rowcount > 0


def _record_prefix(module_key: str) -> str:
    module_key = _clean(module_key).lower()
    return COMPLIANCE_PREFIX if module_key == "compliance" else FIRMWARE_PREFIX


def peek_next_record_no(module_key: str) -> str:
    ensure_module_data_tables()
    module_key = _clean(module_key).lower()
    prefix = _record_prefix(module_key)
    date_key = _today_key()
    conn = get_db_connection()
    row = conn.execute(
        "SELECT current_value FROM module_record_sequences WHERE module_key = ? AND date_key = ?",
        (module_key, date_key),
    ).fetchone()
    conn.close()
    next_value = int(row["current_value"] or 0) + 1 if row else 1
    return f"{prefix}-{date_key}-{next_value:03d}"


def generate_next_record_no(module_key: str) -> str:
    ensure_module_data_tables()
    module_key = _clean(module_key).lower()
    prefix = _record_prefix(module_key)
    date_key = _today_key()
    now = _now_text()
    conn = get_db_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT current_value FROM module_record_sequences WHERE module_key = ? AND date_key = ?",
            (module_key, date_key),
        ).fetchone()
        if row:
            current_value = int(row["current_value"] or 0) + 1
            conn.execute(
                """
                UPDATE module_record_sequences
                SET current_value = ?, update_time = ?
                WHERE module_key = ? AND date_key = ?
                """,
                (current_value, now, module_key, date_key),
            )
        else:
            current_value = 1
            conn.execute(
                """
                INSERT INTO module_record_sequences (module_key, date_key, current_value, update_time)
                VALUES (?, ?, ?, ?)
                """,
                (module_key, date_key, current_value, now),
            )
        conn.commit()
    finally:
        conn.close()
    return f"{prefix}-{date_key}-{current_value:03d}"


def _save_shared_device_from_record(sample_name: str, device_model: str, manufacturer: str, device_category: str, remark: str) -> None:
    if not _clean(sample_name) or not _clean(device_model):
        return
    upsert_shared_device(
        {
            "sample_name": sample_name,
            "device_model": device_model,
            "manufacturer": manufacturer,
            "device_category": device_category,
            "remark": remark,
            "spec": "",
        }
    )


def create_compliance_record(payload: dict[str, Any], user_id: int | None = None, username: str = "") -> dict[str, Any]:
    ensure_module_data_tables()
    data = _normalize_compliance_payload(payload)
    if not data["record_no"]:
        data["record_no"] = generate_next_record_no("compliance")
    if not data["source_trace"]:
        source_segments = [part for part in [data["sample_name"], data["device_model"], data["manufacturer"]] if part]
        data["source_trace"] = " / ".join(source_segments)
    _validate_compliance_record(data)
    _save_shared_device_from_record(
        data["sample_name"],
        data["device_model"],
        data["manufacturer"],
        data["device_category"],
        data["remark"],
    )
    now = _now_text()
    values = [
        data["record_no"],
        data["standard"],
        data["sample_name"],
        data["device_model"],
        data["manufacturer"],
        data["device_category"],
        data["check_item"],
        data["result"],
        data["issue_desc"],
        data["rectification"],
        data["check_date"],
        data["inspector"],
        data["remark"],
        data["source_trace"],
        _serialize_payload(data),
        int(user_id) if user_id else None,
        _clean(username),
    ]
    conn = get_db_connection()
    try:
        cursor = conn.execute(
            f"""
            INSERT INTO module_compliance_records ({", ".join(COMPLIANCE_RECORD_FIELDS)}, create_time, update_time)
            VALUES ({", ".join(["?"] * len(COMPLIANCE_RECORD_FIELDS))}, ?, ?)
            """,
            [*values, now, now],
        )
        record_id = int(cursor.lastrowid)
        conn.commit()
    except Exception:
        conn.close()
        raise
    row = conn.execute(
        """
        SELECT *
        FROM module_compliance_records
        WHERE id = ?
        """,
        (record_id,),
    ).fetchone()
    conn.close()
    return _compliance_record_from_row(row)


def create_firmware_record(payload: dict[str, Any], user_id: int | None = None, username: str = "") -> dict[str, Any]:
    ensure_module_data_tables()
    data = _normalize_firmware_payload(payload)
    if not data["record_no"]:
        data["record_no"] = generate_next_record_no("firmware")
    _validate_firmware_record(data)
    _save_shared_device_from_record(
        data["sample_name"],
        data["device_model"],
        data["manufacturer"],
        "",
        data["remark"],
    )
    now = _now_text()
    payload_json = _serialize_payload(data)
    items_json = _serialize_items(data["items"])
    values = [
        data["record_no"],
        data["sample_name"],
        data["device_model"],
        data["manufacturer"],
        data["check_date"],
        data["inspector"],
        data["remark"],
        data["attachments"],
        items_json,
        payload_json,
        int(user_id) if user_id else None,
        _clean(username),
    ]
    conn = get_db_connection()
    try:
        cursor = conn.execute(
            f"""
            INSERT INTO module_firmware_records ({", ".join(FIRMWARE_RECORD_FIELDS)}, create_time, update_time)
            VALUES ({", ".join(["?"] * len(FIRMWARE_RECORD_FIELDS))}, ?, ?)
            """,
            [*values, now, now],
        )
        record_id = int(cursor.lastrowid)
        conn.commit()
    except Exception:
        conn.close()
        raise
    row = conn.execute(
        """
        SELECT *
        FROM module_firmware_records
        WHERE id = ?
        """,
        (record_id,),
    ).fetchone()
    conn.close()
    return _firmware_record_from_row(row)


def list_compliance_records(
    *,
    record_no: str = "",
    sample_name: str = "",
    device_model: str = "",
    inspector: str = "",
    result: str = "",
    date_from: str = "",
    date_to: str = "",
    page: int = 1,
    page_size: int = 200,
) -> dict[str, Any]:
    ensure_module_data_tables()
    safe_page = max(1, int(page or 1))
    safe_page_size = max(1, min(MAX_PAGE_SIZE, int(page_size or 200)))
    offset = (safe_page - 1) * safe_page_size
    conditions = []
    params: list[Any] = []
    if _clean(record_no):
        conditions.append("record_no LIKE ?")
        params.append(f"%{_clean(record_no)}%")
    if _clean(sample_name):
        conditions.append("sample_name LIKE ?")
        params.append(f"%{_clean(sample_name)}%")
    if _clean(device_model):
        conditions.append("device_model LIKE ?")
        params.append(f"%{_clean(device_model)}%")
    if _clean(inspector):
        conditions.append("inspector LIKE ?")
        params.append(f"%{_clean(inspector)}%")
    if _clean(result):
        conditions.append("result = ?")
        params.append(_clean(result))
    if _clean(date_from):
        conditions.append("check_date >= ?")
        params.append(_clean(date_from))
    if _clean(date_to):
        conditions.append("check_date <= ?")
        params.append(_clean(date_to))
    where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    conn = get_db_connection()
    total = conn.execute(f"SELECT COUNT(1) FROM module_compliance_records {where_sql}", params).fetchone()[0]
    rows = conn.execute(
        f"""
        SELECT *
        FROM module_compliance_records
        {where_sql}
        ORDER BY check_date DESC, create_time DESC, id DESC
        LIMIT ? OFFSET ?
        """,
        [*params, safe_page_size, offset],
    ).fetchall()
    conn.close()
    return {
        "items": [_compliance_record_from_row(row) for row in rows],
        "total": total,
        "page": safe_page,
        "page_size": safe_page_size,
    }


def list_firmware_records(
    *,
    record_no: str = "",
    sample_name: str = "",
    device_model: str = "",
    inspector: str = "",
    date_from: str = "",
    date_to: str = "",
    page: int = 1,
    page_size: int = 200,
) -> dict[str, Any]:
    ensure_module_data_tables()
    safe_page = max(1, int(page or 1))
    safe_page_size = max(1, min(MAX_PAGE_SIZE, int(page_size or 200)))
    offset = (safe_page - 1) * safe_page_size
    conditions = []
    params: list[Any] = []
    if _clean(record_no):
        conditions.append("record_no LIKE ?")
        params.append(f"%{_clean(record_no)}%")
    if _clean(sample_name):
        conditions.append("sample_name LIKE ?")
        params.append(f"%{_clean(sample_name)}%")
    if _clean(device_model):
        conditions.append("device_model LIKE ?")
        params.append(f"%{_clean(device_model)}%")
    if _clean(inspector):
        conditions.append("inspector LIKE ?")
        params.append(f"%{_clean(inspector)}%")
    if _clean(date_from):
        conditions.append("check_date >= ?")
        params.append(_clean(date_from))
    if _clean(date_to):
        conditions.append("check_date <= ?")
        params.append(_clean(date_to))
    where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    conn = get_db_connection()
    total = conn.execute(f"SELECT COUNT(1) FROM module_firmware_records {where_sql}", params).fetchone()[0]
    rows = conn.execute(
        f"""
        SELECT *
        FROM module_firmware_records
        {where_sql}
        ORDER BY check_date DESC, create_time DESC, id DESC
        LIMIT ? OFFSET ?
        """,
        [*params, safe_page_size, offset],
    ).fetchall()
    conn.close()
    return {
        "items": [_firmware_record_from_row(row) for row in rows],
        "total": total,
        "page": safe_page,
        "page_size": safe_page_size,
    }


def export_compliance_records_csv(records: list[dict[str, Any]], export_name: str | None = None) -> Path:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = EXPORT_DIR / f"{_safe_name(export_name or 'compliance_ledger', 'compliance_ledger')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    headers = [
        "检测编号",
        "合规标准依据",
        "样品名称",
        "设备型号",
        "设备生产厂家",
        "设备类别",
        "检查项目",
        "检查结果",
        "问题描述",
        "整改建议",
        "检查日期",
        "检查人",
        "备注",
        "溯源标识",
    ]
    with output_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(headers)
        for item in records:
            writer.writerow(
                [
                    _clean(item.get("record_no")),
                    _clean(item.get("standard")),
                    _clean(item.get("sample_name")),
                    _clean(item.get("device_model")),
                    _clean(item.get("manufacturer")),
                    _clean(item.get("device_category")),
                    _clean(item.get("check_item")),
                    _clean(item.get("result")),
                    _clean(item.get("issue_desc")),
                    _clean(item.get("rectification")),
                    _clean(item.get("check_date")),
                    _clean(item.get("inspector")),
                    _clean(item.get("remark")),
                    _clean(item.get("source_trace")),
                ]
            )
    return output_path


def export_firmware_records_csv(records: list[dict[str, Any]], export_name: str | None = None) -> Path:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = EXPORT_DIR / f"{_safe_name(export_name or 'firmware_ledger', 'firmware_ledger')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    headers = ["检测编号", "样品名称", "设备型号", "生产厂家", "检查日期", "检查人", "附件", "备注"]
    for item_name in FIRMWARE_ITEM_NAMES:
        headers.append(f"{item_name}-检测过程")
        headers.append(f"{item_name}-检测结果")
    with output_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(headers)
        for item in records:
            items = item.get("items")
            items_by_name = {}
            if isinstance(items, list):
                items_by_name = {_clean(entry.get("item_name")): entry for entry in items if isinstance(entry, dict)}
            row = [
                _clean(item.get("record_no")),
                _clean(item.get("sample_name")),
                _clean(item.get("device_model")),
                _clean(item.get("manufacturer")),
                _clean(item.get("check_date")),
                _clean(item.get("inspector")),
                _clean(item.get("attachments")),
                _clean(item.get("remark")),
            ]
            for item_name in FIRMWARE_ITEM_NAMES:
                current = items_by_name.get(item_name, {})
                row.append(_clean(current.get("process")))
                row.append(_clean(current.get("result")))
            writer.writerow(row)
    return output_path
