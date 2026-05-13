import re
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from app.auth import get_db_connection
from app.report_builder import TEMPLATE_FILES, TEMPLATE_SOURCE_DIRS

BASE_DIR = Path(__file__).resolve().parent.parent
EXPORT_DIR = BASE_DIR / "data" / "issue_statistics_exports"
SHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
XML_NS = "http://www.w3.org/XML/1998/namespace"
MAX_PAGE_SIZE = 200

ET.register_namespace("", SHEET_NS)

ISSUE_TYPE_OPTIONS = ["配置异常", "漏洞", "数据不符"]
SEVERITY_OPTIONS = ["高", "中", "低"]
RECTIFICATION_STATUS_OPTIONS = ["未整改", "整改中", "已完成"]

ISSUE_STATISTICS_FIELDS = [
    "issue_no",
    "device_no",
    "test_item",
    "issue_type",
    "severity_level",
    "remediation_suggestion",
    "rectification_status",
]
DB_FIELDS = ", ".join(ISSUE_STATISTICS_FIELDS)
EXPORT_HEADERS = [
    "问题编号",
    "设备编号",
    "检测项目",
    "问题类型",
    "严重等级",
    "整改建议",
    "整改状态",
]


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _row_to_dict(row) -> dict[str, Any]:
    return dict(row) if row else {}


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _safe_name(value: str) -> str:
    safe = re.sub(r"[^\w\u4e00-\u9fff\-]+", "_", _clean(value) or "issue_statistics").strip("_")
    return safe or "issue_statistics"


def ensure_issue_statistics_table() -> None:
    conn = get_db_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS issue_statistics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            issue_no TEXT NOT NULL UNIQUE,
            device_no TEXT NOT NULL,
            test_item TEXT NOT NULL,
            issue_type TEXT NOT NULL,
            severity_level TEXT NOT NULL,
            remediation_suggestion TEXT NOT NULL,
            rectification_status TEXT NOT NULL,
            create_time TEXT NOT NULL,
            update_time TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def _device_ref_by_no(conn, device_no: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT id, device_no, device_name
        FROM device_basic_info
        WHERE device_no = ?
        """,
        (device_no,),
    ).fetchone()
    return _row_to_dict(row) if row else None


def list_issue_device_refs(keyword: str = "") -> list[dict[str, Any]]:
    conn = get_db_connection()
    if _clean(keyword):
        kw = f"%{_clean(keyword)}%"
        rows = conn.execute(
            """
            SELECT id, device_no, device_name
            FROM device_basic_info
            WHERE device_no LIKE ? OR device_name LIKE ?
            ORDER BY id DESC
            LIMIT 200
            """,
            (kw, kw),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT id, device_no, device_name
            FROM device_basic_info
            ORDER BY id DESC
            LIMIT 200
            """
        ).fetchall()
    conn.close()
    return [_row_to_dict(row) for row in rows]


def _generate_issue_no(conn) -> str:
    next_id = int(conn.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM issue_statistics").fetchone()[0])
    return f"WT-{datetime.now().strftime('%Y%m%d')}-{next_id:04d}"


def _validate_record(conn, payload: dict[str, Any], existing_issue_no: str = "") -> dict[str, str]:
    device_no = _clean(payload.get("device_no"))
    if not device_no:
        raise ValueError("device_no is required")
    if not _device_ref_by_no(conn, device_no):
        raise ValueError("device_no is invalid")

    issue_no = _clean(existing_issue_no) or _generate_issue_no(conn)
    test_item = _clean(payload.get("test_item"))
    issue_type = _clean(payload.get("issue_type"))
    severity_level = _clean(payload.get("severity_level"))
    remediation_suggestion = _clean(payload.get("remediation_suggestion"))
    rectification_status = _clean(payload.get("rectification_status"))

    if not test_item:
        raise ValueError("test_item is required")
    if issue_type not in ISSUE_TYPE_OPTIONS:
        raise ValueError("invalid issue_type")
    if severity_level not in SEVERITY_OPTIONS:
        raise ValueError("invalid severity_level")
    if not remediation_suggestion:
        raise ValueError("remediation_suggestion is required")
    if rectification_status not in RECTIFICATION_STATUS_OPTIONS:
        raise ValueError("invalid rectification_status")

    return {
        "issue_no": issue_no,
        "device_no": device_no,
        "test_item": test_item,
        "issue_type": issue_type,
        "severity_level": severity_level,
        "remediation_suggestion": remediation_suggestion,
        "rectification_status": rectification_status,
    }


def list_issue_statistics(keyword: str = "", severity_filter: str = "", page: int = 1, page_size: int = 20) -> dict[str, Any]:
    ensure_issue_statistics_table()
    safe_page = max(1, int(page or 1))
    safe_page_size = max(1, min(MAX_PAGE_SIZE, int(page_size or 20)))
    offset = (safe_page - 1) * safe_page_size
    conditions = []
    params: list[Any] = []
    if _clean(keyword):
        kw = f"%{_clean(keyword)}%"
        conditions.append("(issue_no LIKE ? OR device_no LIKE ? OR test_item LIKE ? OR remediation_suggestion LIKE ?)")
        params.extend([kw, kw, kw, kw])
    if _clean(severity_filter):
        conditions.append("severity_level = ?")
        params.append(_clean(severity_filter))
    where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    conn = get_db_connection()
    total = conn.execute(f"SELECT COUNT(1) FROM issue_statistics {where_sql}", params).fetchone()[0]
    rows = conn.execute(
        f"""
        SELECT id, {DB_FIELDS}, create_time, update_time
        FROM issue_statistics
        {where_sql}
        ORDER BY update_time DESC, id DESC
        LIMIT ? OFFSET ?
        """,
        [*params, safe_page_size, offset],
    ).fetchall()
    conn.close()
    return {
        "items": [_row_to_dict(row) for row in rows],
        "total": total,
        "page": safe_page,
        "page_size": safe_page_size,
    }


def get_issue_statistics(record_id: int) -> dict[str, Any] | None:
    ensure_issue_statistics_table()
    conn = get_db_connection()
    row = conn.execute(
        f"SELECT id, {DB_FIELDS}, create_time, update_time FROM issue_statistics WHERE id = ?",
        (record_id,),
    ).fetchone()
    conn.close()
    return _row_to_dict(row) if row else None


def create_issue_statistics(payload: dict[str, Any]) -> dict[str, Any]:
    ensure_issue_statistics_table()
    conn = get_db_connection()
    try:
        data = _validate_record(conn, payload)
        now = _now_text()
        placeholders = ", ".join(["?"] * len(ISSUE_STATISTICS_FIELDS))
        values = [data[field] for field in ISSUE_STATISTICS_FIELDS]
        cursor = conn.execute(
            f"""
            INSERT INTO issue_statistics ({DB_FIELDS}, create_time, update_time)
            VALUES ({placeholders}, ?, ?)
            """,
            [*values, now, now],
        )
        record_id = int(cursor.lastrowid)
        conn.commit()
    finally:
        conn.close()
    return get_issue_statistics(record_id) or {}


def update_issue_statistics(record_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    ensure_issue_statistics_table()
    existing = get_issue_statistics(record_id)
    if not existing:
        raise LookupError("record not found")
    conn = get_db_connection()
    try:
        data = _validate_record(conn, {**existing, **payload}, existing_issue_no=_clean(existing.get("issue_no")))
        set_sql = ", ".join(f"{field} = ?" for field in ISSUE_STATISTICS_FIELDS)
        values = [data[field] for field in ISSUE_STATISTICS_FIELDS]
        conn.execute(
            f"UPDATE issue_statistics SET {set_sql}, update_time = ? WHERE id = ?",
            [*values, _now_text(), record_id],
        )
        conn.commit()
    finally:
        conn.close()
    return get_issue_statistics(record_id) or {}


def delete_issue_statistics(record_id: int) -> bool:
    ensure_issue_statistics_table()
    conn = get_db_connection()
    cursor = conn.execute("DELETE FROM issue_statistics WHERE id = ?", (record_id,))
    conn.commit()
    conn.close()
    return cursor.rowcount > 0


def _template_path() -> Path:
    filename = TEMPLATE_FILES["issue_statistics"]
    for root in TEMPLATE_SOURCE_DIRS:
        candidate = root / filename
        if candidate.exists():
            return candidate
    return TEMPLATE_SOURCE_DIRS[0] / filename


def _set_inline_value(cell: ET.Element, value: str) -> None:
    for child in list(cell):
        cell.remove(child)
    cell.set("t", "inlineStr")
    inline = ET.SubElement(cell, f"{{{SHEET_NS}}}is")
    text_node = ET.SubElement(inline, f"{{{SHEET_NS}}}t")
    if value != value.strip():
        text_node.set(f"{{{XML_NS}}}space", "preserve")
    text_node.text = value


def _fill_blank_sheet(sheet_root: ET.Element, headers: list[str], rows: list[list[str]]) -> None:
    sheet_data = sheet_root.find(f"{{{SHEET_NS}}}sheetData")
    if sheet_data is None:
        sheet_data = ET.SubElement(sheet_root, f"{{{SHEET_NS}}}sheetData")
    sheet_data.clear()
    dimension = sheet_root.find(f"{{{SHEET_NS}}}dimension")
    if dimension is None:
        dimension = ET.Element(f"{{{SHEET_NS}}}dimension")
        sheet_root.insert(0, dimension)

    table_rows = [headers, *rows]
    max_col = 1
    for row_index, values in enumerate(table_rows, start=1):
        row = ET.SubElement(sheet_data, f"{{{SHEET_NS}}}row", {"r": str(row_index)})
        max_col = max(max_col, len(values))
        for col_index, value in enumerate(values, start=1):
            column_name = ""
            current = col_index
            while current > 0:
                current, rem = divmod(current - 1, 26)
                column_name = chr(65 + rem) + column_name
            cell = ET.SubElement(row, f"{{{SHEET_NS}}}c", {"r": f"{column_name}{row_index}"})
            _set_inline_value(cell, value)
    last_column = ""
    current = max_col
    while current > 0:
        current, rem = divmod(current - 1, 26)
        last_column = chr(65 + rem) + last_column
    dimension.set("ref", f"A1:{last_column}{len(table_rows)}")


def export_issue_statistics_excel(records: list[dict[str, Any]], export_name: str | None = None) -> Path:
    template_path = _template_path()
    if not template_path.exists():
        raise FileNotFoundError(f"未找到模板文件：{template_path.name}")
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = EXPORT_DIR / f"{_safe_name(export_name or 'issue_statistics')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

    rows = [[
        _clean(record.get("issue_no")),
        _clean(record.get("device_no")),
        _clean(record.get("test_item")),
        _clean(record.get("issue_type")),
        _clean(record.get("severity_level")),
        _clean(record.get("remediation_suggestion")),
        _clean(record.get("rectification_status")),
    ] for record in records]

    with zipfile.ZipFile(template_path, "r") as src, zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            if item.filename != "xl/worksheets/sheet1.xml":
                dst.writestr(item, src.read(item.filename))
                continue
            root = ET.fromstring(src.read(item.filename))
            _fill_blank_sheet(root, EXPORT_HEADERS, rows)
            dst.writestr(item, ET.tostring(root, encoding="utf-8", xml_declaration=True))
    return output_path
