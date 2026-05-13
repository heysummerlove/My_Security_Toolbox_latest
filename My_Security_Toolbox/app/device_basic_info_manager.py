import io
import ipaddress
import re
import zipfile
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from app.auth import get_db_connection
from app.report_builder import TEMPLATE_FILES, TEMPLATE_SOURCE_DIRS

BASE_DIR = Path(__file__).resolve().parent.parent
EXPORT_DIR = BASE_DIR / "data" / "device_basic_info_exports"
SHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
XML_NS = "http://www.w3.org/XML/1998/namespace"
ROW_TEMPLATE_INDEX = 2
MAX_PAGE_SIZE = 200

ET.register_namespace("", SHEET_NS)

DEVICE_BASIC_INFO_FIELDS = [
    "device_name",
    "device_type",
    "department",
    "device_no",
    "device_level",
    "device_model",
    "device_status",
    "network_status",
    "manufacturer",
    "interface_type",
    "protocol",
    "software_version",
    "device_composition",
    "target_ip",
    "mac_address",
    "operating_system_choice",
    "operating_system_other",
    "operating_system",
    "open_ports",
    "support_software",
    "source_code_available",
    "notes",
    "record_status",
]

DB_FIELDS = ", ".join(DEVICE_BASIC_INFO_FIELDS)
HEADER_FIELD_MAP = {
    "设备名称": "device_name",
    "设备类型": "device_type",
    "设备部门": "department",
    "设备编号": "device_no",
    "设备等级": "device_level",
    "设备型号": "device_model",
    "设备状态": "device_status",
    "入网状态": "network_status",
    "设备厂商": "manufacturer",
    "接口类型": "interface_type",
    "通信协议": "protocol",
    "应用软件及版本": "software_version",
    "设备组成": "device_composition",
    "设备IP": "target_ip",
    "操作系统": "operating_system",
    "开放端口": "open_ports",
    "是否有特定配套软件且可进行拷贝": "support_software",
    "是否有源代码且可进行拷贝": "source_code_available",
}
EXPORT_COLUMNS = [
    ("B", "device_name"),
    ("C", "device_type"),
    ("D", "department"),
    ("E", "device_no"),
    ("F", "device_level"),
    ("G", "device_model"),
    ("H", "device_status"),
    ("I", "network_status"),
    ("J", "manufacturer"),
    ("K", "interface_type"),
    ("L", "protocol"),
    ("M", "software_version"),
    ("N", "device_composition"),
    ("O", "target_ip"),
    ("P", "operating_system"),
    ("Q", "open_ports"),
    ("R", "support_software"),
    ("S", "source_code_available"),
]
OPERATING_SYSTEM_OPTIONS = {
    "Windows",
    "Linux",
    "Android",
    "Ubuntu",
    "CentOS",
    "Debian",
    "麒麟",
    "统信UOS",
    "VxWorks",
    "FreeRTOS",
    "其他",
}
MAC_PATTERN = re.compile(r"^(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$")


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _row_to_dict(row) -> dict[str, Any]:
    return dict(row) if row else {}


def _normalize_record(payload: dict[str, Any]) -> dict[str, str]:
    data = {field: _clean(payload.get(field)) for field in DEVICE_BASIC_INFO_FIELDS}
    os_choice = data.get("operating_system_choice") or data.get("operating_system")
    os_other = data.get("operating_system_other")
    if os_choice and os_choice != "其他":
        data["operating_system"] = os_choice
        data["operating_system_other"] = ""
    elif os_other:
        data["operating_system_choice"] = "其他"
        data["operating_system"] = os_other
    else:
        data["operating_system"] = os_choice
    data["record_status"] = data.get("record_status") or "draft"
    return data


def _validate_ipv4(value: str) -> bool:
    try:
        return ipaddress.ip_address(value).version == 4
    except ValueError:
        return False


def _validate_record(data: dict[str, str]) -> None:
    required_fields = {
        "device_name": "设备名称",
        "device_type": "设备类型",
        "department": "设备部门",
        "device_no": "设备编号",
        "device_level": "设备等级",
        "device_model": "设备型号",
        "device_status": "设备状态",
        "network_status": "入网状态",
        "manufacturer": "设备厂商",
        "interface_type": "接口类型",
        "protocol": "通信协议",
        "software_version": "应用软件及版本",
        "device_composition": "设备组成",
        "target_ip": "设备IP",
        "operating_system": "操作系统",
    }
    for field, label in required_fields.items():
        if not data.get(field):
            raise ValueError(f"{label}不能为空")
    if not _validate_ipv4(data["target_ip"]):
        raise ValueError("设备IP格式不正确，请填写合法的 IPv4 地址")
    mac_value = data.get("mac_address", "")
    if mac_value and not MAC_PATTERN.match(mac_value):
        raise ValueError("MAC 地址格式不正确，请使用 00:11:22:33:44:55 或 00-11-22-33-44-55")
    if (data.get("operating_system_choice") or "") == "其他" and not data.get("operating_system_other"):
        raise ValueError("操作系统选择“其他”时必须补充说明")
    if data.get("record_status") not in {"draft", "submitted"}:
        raise ValueError("记录状态不合法")


def ensure_device_basic_info_table() -> None:
    conn = get_db_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS device_basic_info (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_name TEXT NOT NULL,
            device_type TEXT NOT NULL,
            department TEXT NOT NULL,
            device_no TEXT NOT NULL UNIQUE,
            device_level TEXT NOT NULL,
            device_model TEXT NOT NULL,
            device_status TEXT NOT NULL,
            network_status TEXT NOT NULL,
            manufacturer TEXT NOT NULL,
            interface_type TEXT NOT NULL,
            protocol TEXT NOT NULL,
            software_version TEXT NOT NULL,
            device_composition TEXT NOT NULL,
            target_ip TEXT NOT NULL UNIQUE,
            mac_address TEXT NOT NULL DEFAULT '',
            operating_system_choice TEXT NOT NULL DEFAULT '',
            operating_system_other TEXT NOT NULL DEFAULT '',
            operating_system TEXT NOT NULL,
            open_ports TEXT NOT NULL DEFAULT '',
            support_software TEXT NOT NULL DEFAULT '',
            source_code_available TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            record_status TEXT NOT NULL DEFAULT 'draft',
            create_time TEXT NOT NULL,
            update_time TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def _ensure_unique(conn, device_no: str, target_ip: str, exclude_id: int | None = None) -> None:
    number_row = conn.execute(
        "SELECT id FROM device_basic_info WHERE device_no = ?",
        (device_no,),
    ).fetchone()
    if number_row and number_row["id"] != exclude_id:
        raise ValueError("设备编号已存在，请使用唯一的设备编号")
    ip_row = conn.execute(
        "SELECT id FROM device_basic_info WHERE target_ip = ?",
        (target_ip,),
    ).fetchone()
    if ip_row and ip_row["id"] != exclude_id:
        raise ValueError("设备IP已存在，请使用唯一的设备IP")


def list_device_basic_info(keyword: str = "", page: int = 1, page_size: int = 20) -> dict[str, Any]:
    ensure_device_basic_info_table()
    safe_page = max(1, int(page or 1))
    safe_page_size = max(1, min(MAX_PAGE_SIZE, int(page_size or 20)))
    offset = (safe_page - 1) * safe_page_size
    keyword_text = f"%{_clean(keyword)}%"
    conn = get_db_connection()
    if _clean(keyword):
        where_sql = """
            WHERE device_name LIKE ?
               OR device_no LIKE ?
               OR target_ip LIKE ?
               OR manufacturer LIKE ?
               OR department LIKE ?
        """
        params = [keyword_text] * 5
    else:
        where_sql = ""
        params = []
    total = conn.execute(f"SELECT COUNT(1) FROM device_basic_info {where_sql}", params).fetchone()[0]
    rows = conn.execute(
        f"""
        SELECT id, {DB_FIELDS}, create_time, update_time
        FROM device_basic_info
        {where_sql}
        ORDER BY id DESC
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


def get_device_basic_info(record_id: int) -> dict[str, Any] | None:
    ensure_device_basic_info_table()
    conn = get_db_connection()
    row = conn.execute(
        f"SELECT id, {DB_FIELDS}, create_time, update_time FROM device_basic_info WHERE id = ?",
        (record_id,),
    ).fetchone()
    conn.close()
    return _row_to_dict(row) if row else None


def create_device_basic_info(payload: dict[str, Any]) -> dict[str, Any]:
    ensure_device_basic_info_table()
    data = _normalize_record(payload)
    _validate_record(data)
    now = _now_text()
    conn = get_db_connection()
    _ensure_unique(conn, data["device_no"], data["target_ip"])
    placeholders = ", ".join(["?"] * len(DEVICE_BASIC_INFO_FIELDS))
    values = [data[field] for field in DEVICE_BASIC_INFO_FIELDS]
    cursor = conn.execute(
        f"""
        INSERT INTO device_basic_info ({DB_FIELDS}, create_time, update_time)
        VALUES ({placeholders}, ?, ?)
        """,
        [*values, now, now],
    )
    record_id = int(cursor.lastrowid)
    conn.commit()
    conn.close()
    return get_device_basic_info(record_id) or {}


def update_device_basic_info(record_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    ensure_device_basic_info_table()
    existing = get_device_basic_info(record_id)
    if not existing:
        raise LookupError("设备调研记录不存在")
    merged = {**existing, **payload}
    data = _normalize_record(merged)
    _validate_record(data)
    now = _now_text()
    conn = get_db_connection()
    _ensure_unique(conn, data["device_no"], data["target_ip"], exclude_id=record_id)
    set_sql = ", ".join(f"{field} = ?" for field in DEVICE_BASIC_INFO_FIELDS)
    values = [data[field] for field in DEVICE_BASIC_INFO_FIELDS]
    conn.execute(
        f"UPDATE device_basic_info SET {set_sql}, update_time = ? WHERE id = ?",
        [*values, now, record_id],
    )
    conn.commit()
    conn.close()
    return get_device_basic_info(record_id) or {}


def delete_device_basic_info(record_id: int) -> bool:
    ensure_device_basic_info_table()
    conn = get_db_connection()
    cursor = conn.execute("DELETE FROM device_basic_info WHERE id = ?", (record_id,))
    conn.commit()
    conn.close()
    return cursor.rowcount > 0


def _template_path() -> Path:
    filename = TEMPLATE_FILES["device_basic_info"]
    for root in TEMPLATE_SOURCE_DIRS:
        candidate = root / filename
        if candidate.exists():
            return candidate
    return TEMPLATE_SOURCE_DIRS[0] / filename


def _split_cell_ref(cell_ref: str) -> tuple[str, int]:
    letters = "".join(ch for ch in cell_ref if ch.isalpha())
    numbers = "".join(ch for ch in cell_ref if ch.isdigit())
    return letters, int(numbers or 0)


def _column_name_to_number(name: str) -> int:
    number = 0
    for char in name:
        number = number * 26 + (ord(char.upper()) - 64)
    return number


def _parse_shared_strings(shared_xml: bytes) -> list[str]:
    if not shared_xml:
        return []
    root = ET.fromstring(shared_xml)
    values: list[str] = []
    for si in root.findall(f"{{{SHEET_NS}}}si"):
        texts = [node.text or "" for node in si.iterfind(f".//{{{SHEET_NS}}}t")]
        values.append("".join(texts))
    return values


def _cell_text(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell.get("t", "")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(f".//{{{SHEET_NS}}}t")).strip()
    value_node = cell.find(f"{{{SHEET_NS}}}v")
    if value_node is None or value_node.text is None:
        return ""
    raw = value_node.text
    if cell_type == "s":
        try:
            return shared_strings[int(raw)].strip()
        except (ValueError, IndexError):
            return raw.strip()
    return raw.strip()


def _set_inline_value(cell: ET.Element, value: str) -> None:
    for child in list(cell):
        cell.remove(child)
    cell.set("t", "inlineStr")
    inline = ET.SubElement(cell, f"{{{SHEET_NS}}}is")
    text_node = ET.SubElement(inline, f"{{{SHEET_NS}}}t")
    if value != value.strip():
        text_node.set(f"{{{XML_NS}}}space", "preserve")
    text_node.text = value


def _ensure_row(sheet_data: ET.Element, row_number: int, template_row: ET.Element | None) -> ET.Element:
    for current_row in sheet_data.findall(f"{{{SHEET_NS}}}row"):
        if int(current_row.get("r", "0")) == row_number:
            current_row.set("r", str(row_number))
            return current_row
    attrs = {"r": str(row_number)}
    if template_row is not None:
        for key, value in template_row.attrib.items():
            if key != "r":
                attrs[key] = value
    row = ET.SubElement(sheet_data, f"{{{SHEET_NS}}}row", attrs)
    rows = sheet_data.findall(f"{{{SHEET_NS}}}row")
    rows.sort(key=lambda item: int(item.get("r", "0")))
    sheet_data[:] = rows
    return row


def _ensure_cell(row: ET.Element, cell_ref: str, template_cell: ET.Element | None) -> ET.Element:
    for current_cell in row.findall(f"{{{SHEET_NS}}}c"):
        if current_cell.get("r") == cell_ref:
            return current_cell
    attrs = {"r": cell_ref}
    if template_cell is not None:
        for key, value in template_cell.attrib.items():
            if key not in {"r", "t"}:
                attrs[key] = value
    cell = ET.SubElement(row, f"{{{SHEET_NS}}}c", attrs)
    cells = row.findall(f"{{{SHEET_NS}}}c")
    cells.sort(key=lambda item: _column_name_to_number(_split_cell_ref(item.get("r", ""))[0]))
    row[:] = cells
    return cell


def _collect_template_row_map(sheet_root: ET.Element, row_number: int) -> tuple[ET.Element | None, dict[str, ET.Element]]:
    sheet_data = sheet_root.find(f"{{{SHEET_NS}}}sheetData")
    if sheet_data is None:
        return None, {}
    for row in sheet_data.findall(f"{{{SHEET_NS}}}row"):
        if int(row.get("r", "0")) == row_number:
            template_cells = {}
            for cell in row.findall(f"{{{SHEET_NS}}}c"):
                column_name, _ = _split_cell_ref(cell.get("r", ""))
                template_cells[column_name] = deepcopy(cell)
            return deepcopy(row), template_cells
    return None, {}


def _remove_data_merge_cells(sheet_root: ET.Element) -> None:
    merge_cells = sheet_root.find(f"{{{SHEET_NS}}}mergeCells")
    if merge_cells is None:
        return
    kept = []
    for merge_cell in merge_cells.findall(f"{{{SHEET_NS}}}mergeCell"):
        start_ref = (merge_cell.get("ref", "").split(":", 1) or [""])[0]
        _, row_number = _split_cell_ref(start_ref)
        if row_number <= 4:
            kept.append(merge_cell)
    if kept:
        merge_cells[:] = kept
        merge_cells.set("count", str(len(kept)))
    else:
        sheet_root.remove(merge_cells)


def _update_dimension(sheet_root: ET.Element, max_row: int) -> None:
    dimension = sheet_root.find(f"{{{SHEET_NS}}}dimension")
    if dimension is None:
        dimension = ET.Element(f"{{{SHEET_NS}}}dimension")
        sheet_root.insert(0, dimension)
    dimension.set("ref", f"A1:S{max_row}")


def export_device_basic_info_excel(records: list[dict[str, Any]], export_name: str | None = None) -> Path:
    template_path = _template_path()
    if not template_path.exists():
        raise FileNotFoundError(f"未找到模板文件：{template_path.name}")
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = re.sub(r"[^\w\u4e00-\u9fff\-]+", "_", _clean(export_name) or "device_basic_info").strip("_")
    output_path = EXPORT_DIR / f"{safe_name or 'device_basic_info'}_{suffix}.xlsx"

    with zipfile.ZipFile(template_path, "r") as src, zipfile.ZipFile(
        output_path, "w", compression=zipfile.ZIP_DEFLATED
    ) as dst:
        for item in src.infolist():
            if item.filename != "xl/worksheets/sheet1.xml":
                dst.writestr(item, src.read(item.filename))
                continue
            sheet_root = ET.fromstring(src.read(item.filename))
            sheet_data = sheet_root.find(f"{{{SHEET_NS}}}sheetData")
            if sheet_data is None:
                sheet_data = ET.SubElement(sheet_root, f"{{{SHEET_NS}}}sheetData")
            _remove_data_merge_cells(sheet_root)
            template_row, template_cells = _collect_template_row_map(sheet_root, ROW_TEMPLATE_INDEX)
            max_row = max(ROW_TEMPLATE_INDEX, len(records) + 1)
            for row_index, record in enumerate(records, start=2):
                row = _ensure_row(sheet_data, row_index, template_row)
                serial_cell = _ensure_cell(row, f"A{row_index}", template_cells.get("A"))
                _set_inline_value(serial_cell, str(row_index - 1))
                for column_name, field_name in EXPORT_COLUMNS:
                    cell = _ensure_cell(row, f"{column_name}{row_index}", template_cells.get(column_name))
                    _set_inline_value(cell, _clean(record.get(field_name)))
            _update_dimension(sheet_root, max_row)
            dst.writestr(item, ET.tostring(sheet_root, encoding="utf-8", xml_declaration=True))
    return output_path


def parse_device_basic_info_template(file_bytes: bytes) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with zipfile.ZipFile(io.BytesIO(file_bytes), "r") as zf:
        sheet_xml = zf.read("xl/worksheets/sheet1.xml")
        shared_xml = zf.read("xl/sharedStrings.xml") if "xl/sharedStrings.xml" in zf.namelist() else b""
    shared_strings = _parse_shared_strings(shared_xml)
    root = ET.fromstring(sheet_xml)
    sheet_data = root.find(f"{{{SHEET_NS}}}sheetData")
    if sheet_data is None:
        return rows

    header_map: dict[str, str] = {}
    for row in sheet_data.findall(f"{{{SHEET_NS}}}row"):
        row_number = int(row.get("r", "0"))
        if row_number == 1:
            for cell in row.findall(f"{{{SHEET_NS}}}c"):
                column_name, _ = _split_cell_ref(cell.get("r", ""))
                header_text = _cell_text(cell, shared_strings)
                field_name = HEADER_FIELD_MAP.get(header_text)
                if field_name:
                    header_map[column_name] = field_name
            continue
        if row_number < 2:
            continue
        row_data: dict[str, str] = {}
        has_meaningful_value = False
        for cell in row.findall(f"{{{SHEET_NS}}}c"):
            column_name, _ = _split_cell_ref(cell.get("r", ""))
            field_name = header_map.get(column_name)
            if not field_name:
                continue
            cell_value = _cell_text(cell, shared_strings)
            row_data[field_name] = cell_value
            if cell_value:
                has_meaningful_value = True
        if has_meaningful_value:
            rows.append(row_data)
    return rows


def import_device_basic_info_rows(rows: list[dict[str, str]]) -> dict[str, Any]:
    ensure_device_basic_info_table()
    imported: list[dict[str, Any]] = []
    skipped = 0
    conn = get_db_connection()
    try:
        for row in rows:
            payload = {
                "device_name": row.get("device_name", ""),
                "device_type": row.get("device_type", ""),
                "department": row.get("department", ""),
                "device_no": row.get("device_no", ""),
                "device_level": row.get("device_level", ""),
                "device_model": row.get("device_model", ""),
                "device_status": row.get("device_status", ""),
                "network_status": row.get("network_status", ""),
                "manufacturer": row.get("manufacturer", ""),
                "interface_type": row.get("interface_type", ""),
                "protocol": row.get("protocol", ""),
                "software_version": row.get("software_version", ""),
                "device_composition": row.get("device_composition", ""),
                "target_ip": row.get("target_ip", ""),
                "mac_address": row.get("mac_address", ""),
                "operating_system": row.get("operating_system", ""),
                "operating_system_choice": row.get("operating_system", "") if row.get("operating_system", "") in OPERATING_SYSTEM_OPTIONS else "其他",
                "operating_system_other": "" if row.get("operating_system", "") in OPERATING_SYSTEM_OPTIONS else row.get("operating_system", ""),
                "open_ports": row.get("open_ports", ""),
                "support_software": row.get("support_software", ""),
                "source_code_available": row.get("source_code_available", ""),
                "notes": row.get("notes", ""),
                "record_status": "draft",
            }
            data = _normalize_record(payload)
            if not any(data.get(field) for field in DEVICE_BASIC_INFO_FIELDS if field not in {"record_status"}):
                skipped += 1
                continue
            _validate_record(data)
            existing = conn.execute(
                "SELECT id FROM device_basic_info WHERE device_no = ? OR target_ip = ?",
                (data["device_no"], data["target_ip"]),
            ).fetchone()
            if existing:
                _ensure_unique(conn, data["device_no"], data["target_ip"], exclude_id=existing["id"])
                set_sql = ", ".join(f"{field} = ?" for field in DEVICE_BASIC_INFO_FIELDS)
                values = [data[field] for field in DEVICE_BASIC_INFO_FIELDS]
                conn.execute(
                    f"UPDATE device_basic_info SET {set_sql}, update_time = ? WHERE id = ?",
                    [*values, _now_text(), existing["id"]],
                )
                imported.append({"id": existing["id"], **data})
            else:
                now = _now_text()
                placeholders = ", ".join(["?"] * len(DEVICE_BASIC_INFO_FIELDS))
                values = [data[field] for field in DEVICE_BASIC_INFO_FIELDS]
                cursor = conn.execute(
                    f"""
                    INSERT INTO device_basic_info ({DB_FIELDS}, create_time, update_time)
                    VALUES ({placeholders}, ?, ?)
                    """,
                    [*values, now, now],
                )
                imported.append({"id": int(cursor.lastrowid), **data})
        conn.commit()
    finally:
        conn.close()
    return {"items": imported, "imported_count": len(imported), "skipped_count": skipped}
