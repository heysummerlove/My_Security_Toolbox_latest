import io
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
EXPORT_DIR = BASE_DIR / "data" / "basic_test_record_exports"
SHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
XML_NS = "http://www.w3.org/XML/1998/namespace"
MAX_PAGE_SIZE = 200
DETAIL_HEADERS = [
    "记录ID",
    "设备编号",
    "设备名称",
    "设备类型",
    "设备型号",
    "设备IP",
    "测试项目",
    "测试方法",
    "测试结果",
    "问题描述",
    "测试时间",
    "备注",
    "状态",
]
ISSUE_HEADERS = [
    "记录ID",
    "设备编号",
    "设备名称",
    "测试项目",
    "测试结果",
    "问题描述",
    "测试时间",
]

ET.register_namespace("", SHEET_NS)

TEST_ITEM_OPTIONS = [
    {"key": "compliance_line", "label": "合规性检查 / 设备及产线基本情况摸排", "column": "U", "method": "核查设备台账、采购维修记录，并结合现场访谈确认设备来源、产线属性和使用背景。"},
    {"key": "compliance_physical", "label": "合规性检查 / 物理安全检测", "column": "V", "method": "检查设备外观、封签、防拆痕迹、部署位置和物理隔离状态，并拍照取证。"},
    {"key": "compliance_config", "label": "合规性检查 / 设备安全配置核查", "column": "W", "method": "核查账户、补丁、日志、防火墙、服务和安全基线配置。"},
    {"key": "wired_asset", "label": "有线网络流量安全检测 / 网络资产一致性验证", "column": "X", "method": "通过扫描、资产清单比对和现场核实验证网络资产一致性。"},
    {"key": "wired_threat", "label": "有线网络流量安全检测 / 威胁监测", "column": "Y", "method": "采集网络流量并结合告警日志分析异常通信、攻击痕迹和威胁行为。"},
    {"key": "wireless_physical", "label": "无线协议安全检测 / 物理层无线协议安全检测", "column": "Z", "method": "利用频谱仪、接收机等工具检测频率、功率、波形和信号异常。"},
    {"key": "wireless_link", "label": "无线协议安全检测 / 数据链路层无线协议安全检测", "column": "AA", "method": "抓取无线报文并验证链路层帧结构、加密、白名单和资源分配。"},
    {"key": "wireless_app", "label": "无线协议安全检测 / 应用层无线协议安全检测", "column": "AB", "method": "验证无线应用层认证、密钥协商、接口访问控制和业务指令安全。"},
    {"key": "firmware_extract", "label": "嵌入式设备固件提取及检测 / 固件提取", "column": "AC", "method": "通过官方升级包、调试口或芯片读取方式提取固件，并记录操作步骤。"},
    {"key": "firmware_meta", "label": "嵌入式设备固件提取及检测 / 固件元信息分析", "column": "AD", "method": "分析固件包结构、版本、哈希、文件系统及构建元信息。"},
    {"key": "firmware_sensitive", "label": "嵌入式设备固件提取及检测 / 敏感文件提取", "column": "AE", "method": "检查固件中的配置文件、证书、口令、密钥和敏感脚本。"},
    {"key": "firmware_supply_chain", "label": "嵌入式设备固件提取及检测 / 供应链安全分析", "column": "AF", "method": "识别第三方组件、版本依赖和已知风险，评估供应链暴露面。"},
    {"key": "firmware_code_audit", "label": "嵌入式设备固件提取及检测 / 代码审计", "column": "AG", "method": "对可获取源码或反编译结果进行静态审计，关注认证、输入处理和敏感调用。"},
    {"key": "firmware_vuln_mining", "label": "嵌入式设备固件提取及检测 / 漏洞挖掘", "column": "AH", "method": "结合静态分析、动态验证和模糊测试挖掘固件安全漏洞。"},
    {"key": "firmware_vuln_match", "label": "嵌入式设备固件提取及检测 / 漏洞匹配", "column": "AI", "method": "将组件版本、指纹和特征与公开漏洞库进行匹配确认。"},
    {"key": "firmware_malware", "label": "嵌入式设备固件提取及检测 / 恶意代码检测", "column": "AJ", "method": "使用规则特征与人工分析识别后门、恶意脚本和异常持久化逻辑。"},
    {"key": "firmware_simulation", "label": "嵌入式设备固件提取及检测 / 仿真测试", "column": "AK", "method": "在仿真或沙箱环境中启动固件，验证服务行为和潜在风险。"},
    {"key": "vuln_collect", "label": "漏洞检测 / 信息收集", "column": "AL", "method": "收集版本、指纹、开放服务、账号策略和外部暴露信息。"},
    {"key": "vuln_scan", "label": "漏洞检测 / 漏洞扫描", "column": "AM", "method": "使用扫描器对服务、组件和应用进行漏洞识别与验证。"},
    {"key": "vuln_code_audit", "label": "漏洞检测 / 代码审计", "column": "AN", "method": "围绕关键业务逻辑、认证授权、输入校验和敏感操作进行代码审查。"},
    {"key": "vuln_reverse", "label": "漏洞检测 / 逆向分析", "column": "AO", "method": "对可执行文件、协议或固件进行逆向分析，定位高风险实现缺陷。"},
    {"key": "vuln_fuzz", "label": "漏洞检测 / 模糊测试", "column": "AP", "method": "对接口、协议或文件格式执行模糊测试，观察崩溃与异常行为。"},
    {"key": "vuln_attack", "label": "漏洞检测 / 模拟攻击", "column": "AQ", "method": "在授权范围内进行利用验证，评估漏洞可利用性与影响面。"},
    {"key": "em_scan", "label": "设备电磁安全检测 / 扫描检测", "column": "AR", "method": "在目标频段内进行扫描检测，记录异常电磁辐射和信号特征。"},
    {"key": "em_induce_public", "label": "设备电磁安全检测 / 公共移动通信信号诱导检测", "column": "AS", "method": "构造公共移动通信诱导场景，观察设备响应与异常行为。"},
    {"key": "em_induce_wlan", "label": "设备电磁安全检测 / 无线局域网信号诱导检测", "column": "AT", "method": "构造 WLAN 诱导环境，检测设备连接、漫游与业务响应变化。"},
    {"key": "em_induce_iot", "label": "设备电磁安全检测 / 物联网信号诱导检测", "column": "AU", "method": "模拟物联网协议环境，验证设备在诱导信号下的连接与控制行为。"},
    {"key": "em_induce_gnss", "label": "设备电磁安全检测 / 卫星导航信号诱导检测", "column": "AV", "method": "搭建导航信号诱导场景，验证定位、授时与导航相关逻辑。"},
    {"key": "em_induce_satnet", "label": "设备电磁安全检测 / 卫星网络信号诱导检测", "column": "AW", "method": "模拟卫星网络诱导信号，观察通信链路和业务表现。"},
    {"key": "em_induce_noncoop", "label": "设备电磁安全检测 / 非合作卫星信号诱导检测", "column": "AX", "method": "在非合作卫星诱导环境下检测设备识别和响应能力。"},
    {"key": "peripheral_em_signal", "label": "设备周边电磁安全检测 / 电磁信号检测", "column": "AY", "method": "对周边环境的异常电磁信号进行扫描、定位和记录。"},
    {"key": "peripheral_ground_wireless", "label": "设备周边电磁安全检测 / 地面无线网络检测", "column": "AZ", "method": "检测地面无线网络环境中的可疑接入点、异常信道和信号覆盖。"},
    {"key": "peripheral_ir", "label": "设备周边电磁安全检测 / 红外热成像检测", "column": "BA", "method": "通过热成像识别异常热源、隐藏设备和可疑运行状态。"},
    {"key": "peripheral_nljd", "label": "设备周边电磁安全检测 / 非线性介质检测", "column": "BB", "method": "使用非线性结点探测方式识别疑似电子元件和隐蔽装置。"},
    {"key": "peripheral_ld", "label": "设备周边电磁安全检测 / LD成像检测", "column": "BC", "method": "使用 LD 成像或同类技术辅助发现隐蔽电子设备与反射异常。"},
    {"key": "peripheral_monitor_em", "label": "设备周边电磁安全检测 / 电磁信号监测", "column": "BD", "method": "对重点区域开展持续电磁监测，分析周期性和突发性异常信号。"},
    {"key": "peripheral_monitor_ground", "label": "设备周边电磁安全检测 / 地面无线网络监测", "column": "BE", "method": "对周边无线网络长期监测，记录异常 AP、客户端和链路变化。"},
    {"key": "peripheral_monitor_nav", "label": "设备周边电磁安全检测 / 导航干扰异常监测", "column": "BF", "method": "监测导航信号质量和干扰异常，定位异常发生时段与区域。"},
    {"key": "peripheral_monitor_satnet", "label": "设备周边电磁安全检测 / 卫星网络信号监测", "column": "BG", "method": "持续监测卫星网络链路相关信号，识别异常接入和通信行为。"},
    {"key": "peripheral_monitor_noncoop", "label": "设备周边电磁安全检测 / 非合作卫星信号监测", "column": "BH", "method": "对非合作卫星信号活动进行连续监测与告警分析。"},
    {"key": "peripheral_patrol_ground", "label": "设备周边电磁安全检测 / 地面机动巡检", "column": "BI", "method": "开展地面机动巡检，对可疑区域进行移动侦测和快速定位。"},
    {"key": "peripheral_patrol_air", "label": "设备周边电磁安全检测 / 空中机动巡检", "column": "BJ", "method": "在授权条件下执行空中巡检，补充地面难以覆盖的检测视角。"},
    {"key": "nondestructive_disassemble", "label": "设备无损拆解检测 / 设备拆解", "column": "BK", "method": "按无损拆解流程对设备外壳、接口和组件进行有序拆解。"},
    {"key": "nondestructive_detect", "label": "设备无损拆解检测 / 设备检测", "column": "BL", "method": "对拆解后的板卡、接口、芯片和连接关系进行检测分析。"},
    {"key": "nondestructive_restore", "label": "设备无损拆解检测 / 设备复原", "column": "BM", "method": "在检测完成后按记录步骤恢复设备结构并验证基本功能。"},
]
TEST_ITEM_MAP = {item["key"]: item for item in TEST_ITEM_OPTIONS}
RESULT_OPTIONS = ["合格", "不合格", "异常", "不涉及"]
REQUIRES_PROBLEM_RESULTS = {"不合格", "异常"}
BASIC_TEST_RECORD_FIELDS = [
    "device_no",
    "device_name",
    "device_type",
    "device_model",
    "target_ip",
    "test_item_key",
    "test_item_label",
    "test_method",
    "test_result",
    "problem_description",
    "test_time",
    "remarks",
    "record_status",
]
DB_FIELDS = ", ".join(BASIC_TEST_RECORD_FIELDS)


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_result(value: Any) -> str:
    text = _clean(value)
    mapping = {
        "pass": "合格",
        "fail": "不合格",
        "failed": "不合格",
        "error": "异常",
        "exception": "异常",
        "na": "不涉及",
        "n/a": "不涉及",
        "合格": "合格",
        "不合格": "不合格",
        "异常": "异常",
        "不涉及": "不涉及",
    }
    return mapping.get(text.lower(), text)


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _safe_name(value: str) -> str:
    safe = re.sub(r"[^\w\u4e00-\u9fff\-]+", "_", _clean(value) or "basic_test_record").strip("_")
    return safe or "basic_test_record"


def _parse_time(value: str) -> datetime:
    text = _clean(value)
    if not text:
        raise ValueError("测试时间不能为空")
    normalized = text.replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(normalized, fmt)
            if fmt == "%Y-%m-%d":
                return parsed.replace(hour=0, minute=0, second=0)
            return parsed
        except ValueError:
            continue
    raise ValueError("测试时间格式不正确，请使用日期或日期时间格式")


def _normalize_time(value: str) -> str:
    return _parse_time(value).strftime("%Y-%m-%d %H:%M:%S")


def ensure_basic_test_record_table() -> None:
    conn = get_db_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS basic_test_record (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_no TEXT NOT NULL,
            device_name TEXT NOT NULL,
            device_type TEXT NOT NULL,
            device_model TEXT NOT NULL,
            target_ip TEXT NOT NULL,
            test_item_key TEXT NOT NULL,
            test_item_label TEXT NOT NULL,
            test_method TEXT NOT NULL,
            test_result TEXT NOT NULL,
            problem_description TEXT NOT NULL DEFAULT '',
            test_time TEXT NOT NULL,
            remarks TEXT NOT NULL DEFAULT '',
            record_status TEXT NOT NULL DEFAULT 'draft',
            create_time TEXT NOT NULL,
            update_time TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def _row_to_dict(row) -> dict[str, Any]:
    return dict(row) if row else {}


def _device_snapshot_by_no(conn, device_no: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT id, device_no, device_name, device_type, device_level, device_model, device_status,
               network_status, manufacturer, interface_type, protocol, software_version,
               device_composition, target_ip, operating_system, open_ports,
               support_software, source_code_available, department
        FROM device_basic_info
        WHERE device_no = ?
        """,
        (device_no,),
    ).fetchone()
    return _row_to_dict(row) if row else None


def list_device_refs(keyword: str = "") -> list[dict[str, Any]]:
    conn = get_db_connection()
    if _clean(keyword):
        kw = f"%{_clean(keyword)}%"
        rows = conn.execute(
            """
            SELECT id, device_no, device_name, device_type, device_model, target_ip, manufacturer, department
            FROM device_basic_info
            WHERE device_no LIKE ? OR device_name LIKE ? OR target_ip LIKE ?
            ORDER BY id DESC
            LIMIT 200
            """,
            (kw, kw, kw),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT id, device_no, device_name, device_type, device_model, target_ip, manufacturer, department
            FROM device_basic_info
            ORDER BY id DESC
            LIMIT 200
            """
        ).fetchall()
    conn.close()
    return [_row_to_dict(row) for row in rows]


def _validate_record(conn, payload: dict[str, Any]) -> dict[str, str]:
    device_no = _clean(payload.get("device_no"))
    if not device_no:
        raise ValueError("设备编号不能为空")
    device = _device_snapshot_by_no(conn, device_no)
    if not device:
        raise ValueError("设备编号无效，请先在附表1中维护设备基础信息")

    test_item_key = _clean(payload.get("test_item_key"))
    item = TEST_ITEM_MAP.get(test_item_key)
    if not item:
        raise ValueError("测试项目无效，请从固定下拉列表中选择")

    test_result = _normalize_result(payload.get("test_result"))
    if test_result not in RESULT_OPTIONS:
        raise ValueError("测试结果无效")

    problem_description = _clean(payload.get("problem_description"))
    if test_result in REQUIRES_PROBLEM_RESULTS and not problem_description:
        raise ValueError("测试结果为不合格或异常时，必须填写问题描述")
    if test_result not in REQUIRES_PROBLEM_RESULTS:
        problem_description = ""

    parsed_time = _parse_time(payload.get("test_time"))
    now = datetime.now()
    if parsed_time > now:
        raise ValueError("测试时间不能晚于当前时间")
    if parsed_time.year < 2000:
        raise ValueError("测试时间早于 2000-01-01，不符合合理性要求")

    record_status = _clean(payload.get("record_status") or "draft")
    if record_status not in {"draft", "submitted"}:
        raise ValueError("记录状态无效")

    return {
        "device_no": device["device_no"],
        "device_name": _clean(payload.get("device_name") or device.get("device_name")),
        "device_type": _clean(payload.get("device_type") or device.get("device_type")),
        "device_model": _clean(payload.get("device_model") or device.get("device_model")),
        "target_ip": _clean(payload.get("target_ip") or device.get("target_ip")),
        "test_item_key": item["key"],
        "test_item_label": item["label"],
        "test_method": _clean(payload.get("test_method") or item["method"]),
        "test_result": test_result,
        "problem_description": problem_description,
        "test_time": parsed_time.strftime("%Y-%m-%d %H:%M:%S"),
        "remarks": _clean(payload.get("remarks")),
        "record_status": record_status,
    }

def _validate_record_v2(conn, payload: dict[str, Any]) -> dict[str, str]:
    device_no = _clean(payload.get("device_no"))
    if not device_no:
        raise ValueError("device_no is required")

    linked_device = _device_snapshot_by_no(conn, device_no) or {}

    test_item_key = _clean(payload.get("test_item_key"))
    item = TEST_ITEM_MAP.get(test_item_key)
    if not item:
        raise ValueError("invalid test_item_key")

    test_result = _normalize_result(payload.get("test_result"))
    if test_result not in RESULT_OPTIONS:
        raise ValueError("invalid test_result")

    problem_description = _clean(payload.get("problem_description"))
    if test_result in REQUIRES_PROBLEM_RESULTS and not problem_description:
        raise ValueError("problem_description is required when test_result is abnormal")
    if test_result not in REQUIRES_PROBLEM_RESULTS:
        problem_description = ""

    parsed_time = _parse_time(payload.get("test_time"))
    now = datetime.now()
    if parsed_time > now:
        raise ValueError("test_time cannot be in the future")
    if parsed_time.year < 2000:
        raise ValueError("test_time cannot be earlier than 2000-01-01")

    record_status = _clean(payload.get("record_status") or "draft")
    if record_status not in {"draft", "submitted"}:
        raise ValueError("invalid record_status")

    device_name = _clean(payload.get("device_name") or linked_device.get("device_name"))
    device_type = _clean(payload.get("device_type") or linked_device.get("device_type"))
    device_model = _clean(payload.get("device_model") or linked_device.get("device_model"))
    target_ip = _clean(payload.get("target_ip") or linked_device.get("target_ip"))
    if not device_name:
        raise ValueError("device_name is required")
    if not device_type:
        raise ValueError("device_type is required")
    if not device_model:
        raise ValueError("device_model is required")
    if not target_ip:
        raise ValueError("target_ip is required")

    return {
        "device_no": device_no,
        "device_name": device_name,
        "device_type": device_type,
        "device_model": device_model,
        "target_ip": target_ip,
        "test_item_key": item["key"],
        "test_item_label": item["label"],
        "test_method": _clean(payload.get("test_method") or item["method"]),
        "test_result": test_result,
        "problem_description": problem_description,
        "test_time": parsed_time.strftime("%Y-%m-%d %H:%M:%S"),
        "remarks": _clean(payload.get("remarks")),
        "record_status": record_status,
    }


def list_basic_test_records(keyword: str = "", result_filter: str = "", page: int = 1, page_size: int = 20) -> dict[str, Any]:
    ensure_basic_test_record_table()
    safe_page = max(1, int(page or 1))
    safe_page_size = max(1, min(MAX_PAGE_SIZE, int(page_size or 20)))
    offset = (safe_page - 1) * safe_page_size
    conditions = []
    params: list[Any] = []
    if _clean(keyword):
        kw = f"%{_clean(keyword)}%"
        conditions.append("(device_no LIKE ? OR device_name LIKE ? OR test_item_label LIKE ? OR target_ip LIKE ?)")
        params.extend([kw, kw, kw, kw])
    if _clean(result_filter):
        conditions.append("test_result = ?")
        params.append(_clean(result_filter))
    where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    conn = get_db_connection()
    total = conn.execute(f"SELECT COUNT(1) FROM basic_test_record {where_sql}", params).fetchone()[0]
    rows = conn.execute(
        f"""
        SELECT id, {DB_FIELDS}, create_time, update_time
        FROM basic_test_record
        {where_sql}
        ORDER BY test_time DESC, id DESC
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


def get_basic_test_record(record_id: int) -> dict[str, Any] | None:
    ensure_basic_test_record_table()
    conn = get_db_connection()
    row = conn.execute(
        f"SELECT id, {DB_FIELDS}, create_time, update_time FROM basic_test_record WHERE id = ?",
        (record_id,),
    ).fetchone()
    conn.close()
    return _row_to_dict(row) if row else None


def create_basic_test_record(payload: dict[str, Any]) -> dict[str, Any]:
    ensure_basic_test_record_table()
    conn = get_db_connection()
    try:
        data = _validate_record_v2(conn, payload)
        now = _now_text()
        placeholders = ", ".join(["?"] * len(BASIC_TEST_RECORD_FIELDS))
        values = [data[field] for field in BASIC_TEST_RECORD_FIELDS]
        cursor = conn.execute(
            f"""
            INSERT INTO basic_test_record ({DB_FIELDS}, create_time, update_time)
            VALUES ({placeholders}, ?, ?)
            """,
            [*values, now, now],
        )
        record_id = int(cursor.lastrowid)
        conn.commit()
    finally:
        conn.close()
    return get_basic_test_record(record_id) or {}


def update_basic_test_record(record_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    ensure_basic_test_record_table()
    existing = get_basic_test_record(record_id)
    if not existing:
        raise LookupError("测试记录不存在")
    conn = get_db_connection()
    try:
        data = _validate_record_v2(conn, {**existing, **payload})
        set_sql = ", ".join(f"{field} = ?" for field in BASIC_TEST_RECORD_FIELDS)
        values = [data[field] for field in BASIC_TEST_RECORD_FIELDS]
        conn.execute(
            f"UPDATE basic_test_record SET {set_sql}, update_time = ? WHERE id = ?",
            [*values, _now_text(), record_id],
        )
        conn.commit()
    finally:
        conn.close()
    return get_basic_test_record(record_id) or {}


def delete_basic_test_record(record_id: int) -> bool:
    ensure_basic_test_record_table()
    conn = get_db_connection()
    cursor = conn.execute("DELETE FROM basic_test_record WHERE id = ?", (record_id,))
    conn.commit()
    conn.close()
    return cursor.rowcount > 0


def batch_save_basic_test_records(records: list[dict[str, Any]], submit: bool = False) -> list[dict[str, Any]]:
    ensure_basic_test_record_table()
    if not records:
        return []
    saved_records: list[dict[str, Any]] = []
    conn = get_db_connection()
    try:
        for record in records:
            record_id = record.get("id")
            payload = {**record, "record_status": "submitted" if submit else _clean(record.get("record_status") or "draft")}
            data = _validate_record_v2(conn, payload)
            if record_id:
                set_sql = ", ".join(f"{field} = ?" for field in BASIC_TEST_RECORD_FIELDS)
                values = [data[field] for field in BASIC_TEST_RECORD_FIELDS]
                conn.execute(
                    f"UPDATE basic_test_record SET {set_sql}, update_time = ? WHERE id = ?",
                    [*values, _now_text(), int(record_id)],
                )
                saved_records.append({"id": int(record_id), **data})
            else:
                placeholders = ", ".join(["?"] * len(BASIC_TEST_RECORD_FIELDS))
                values = [data[field] for field in BASIC_TEST_RECORD_FIELDS]
                cursor = conn.execute(
                    f"""
                    INSERT INTO basic_test_record ({DB_FIELDS}, create_time, update_time)
                    VALUES ({placeholders}, ?, ?)
                    """,
                    [*values, _now_text(), _now_text()],
                )
                saved_records.append({"id": int(cursor.lastrowid), **data})
        conn.commit()
    finally:
        conn.close()
    return saved_records


def batch_delete_basic_test_records(ids: list[int]) -> int:
    ensure_basic_test_record_table()
    clean_ids = [int(item) for item in ids if int(item) > 0]
    if not clean_ids:
        return 0
    placeholders = ", ".join(["?"] * len(clean_ids))
    conn = get_db_connection()
    cursor = conn.execute(f"DELETE FROM basic_test_record WHERE id IN ({placeholders})", clean_ids)
    conn.commit()
    conn.close()
    return int(cursor.rowcount or 0)


def _template_path() -> Path:
    filename = TEMPLATE_FILES["basic_test_record"]
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


def _set_inline_value(cell: ET.Element, value: str) -> None:
    for child in list(cell):
        cell.remove(child)
    cell.set("t", "inlineStr")
    inline = ET.SubElement(cell, f"{{{SHEET_NS}}}is")
    text_node = ET.SubElement(inline, f"{{{SHEET_NS}}}t")
    if value != value.strip():
        text_node.set(f"{{{XML_NS}}}space", "preserve")
    text_node.text = value


def _clone_row(template_row: ET.Element, row_number: int) -> ET.Element:
    new_row = deepcopy(template_row)
    new_row.set("r", str(row_number))
    for cell in new_row.findall(f"{{{SHEET_NS}}}c"):
        column_name, _ = _split_cell_ref(cell.get("r", ""))
        cell.set("r", f"{column_name}{row_number}")
    return new_row


def _shift_merge_ref(ref: str, offset: int) -> str:
    parts = ref.split(":")
    shifted = []
    for part in parts:
        column_name, row_number = _split_cell_ref(part)
        shifted.append(f"{column_name}{row_number + offset}")
    return ":".join(shifted)


def _ensure_cell(row: ET.Element, cell_ref: str) -> ET.Element:
    for cell in row.findall(f"{{{SHEET_NS}}}c"):
        if cell.get("r") == cell_ref:
            return cell
    cell = ET.SubElement(row, f"{{{SHEET_NS}}}c", {"r": cell_ref})
    cells = row.findall(f"{{{SHEET_NS}}}c")
    cells.sort(key=lambda item: _column_name_to_number(_split_cell_ref(item.get("r", ""))[0]))
    row[:] = cells
    return cell


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


def export_basic_test_record_excel(records: list[dict[str, Any]], export_name: str | None = None) -> Path:
    template_path = _template_path()
    if not template_path.exists():
        raise FileNotFoundError(f"未找到模板文件：{template_path.name}")
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = EXPORT_DIR / f"{_safe_name(export_name or 'basic_test_record')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

    grouped: dict[str, list[dict[str, Any]]] = {}
    device_snapshots: dict[str, dict[str, Any]] = {}
    conn = get_db_connection()
    try:
        for record in records:
            device_no = _clean(record.get("device_no"))
            grouped.setdefault(device_no, []).append(record)
            if device_no and device_no not in device_snapshots:
                device_snapshots[device_no] = _device_snapshot_by_no(conn, device_no) or {}
    finally:
        conn.close()

    with zipfile.ZipFile(template_path, "r") as src, zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            if item.filename not in {"xl/worksheets/sheet1.xml", "xl/worksheets/sheet2.xml", "xl/worksheets/sheet3.xml"}:
                dst.writestr(item, src.read(item.filename))
                continue

            root = ET.fromstring(src.read(item.filename))
            if item.filename == "xl/worksheets/sheet1.xml":
                sheet_data = root.find(f"{{{SHEET_NS}}}sheetData")
                if sheet_data is None:
                    sheet_data = ET.SubElement(root, f"{{{SHEET_NS}}}sheetData")
                rows = sheet_data.findall(f"{{{SHEET_NS}}}row")
                template_rows = {int(row.get("r", "0")): deepcopy(row) for row in rows if 6 <= int(row.get("r", "0")) <= 8}
                keep_rows = [row for row in rows if int(row.get("r", "0")) < 6]
                sheet_data[:] = keep_rows

                merge_cells = root.find(f"{{{SHEET_NS}}}mergeCells")
                template_merges: list[str] = []
                if merge_cells is not None:
                    kept_merges = []
                    for merge_cell in merge_cells.findall(f"{{{SHEET_NS}}}mergeCell"):
                        ref = merge_cell.get("ref", "")
                        start_row = _split_cell_ref(ref.split(":", 1)[0])[1]
                        if 6 <= start_row <= 8:
                            template_merges.append(ref)
                        elif start_row < 6:
                            kept_merges.append(merge_cell)
                    merge_cells[:] = kept_merges

                device_nos = list(grouped.keys())
                for index, device_no in enumerate(device_nos, start=1):
                    start_row = 6 + (index - 1) * 3
                    for template_offset in range(3):
                        template_row = template_rows[6 + template_offset]
                        new_row = _clone_row(template_row, start_row + template_offset)
                        sheet_data.append(new_row)

                    if merge_cells is not None:
                        for ref in template_merges:
                            merge_cells.append(ET.Element(f"{{{SHEET_NS}}}mergeCell", {"ref": _shift_merge_ref(ref, (index - 1) * 3)}))

                    row_top = next(row for row in sheet_data.findall(f"{{{SHEET_NS}}}row") if int(row.get("r", "0")) == start_row)
                    row_mid = next(row for row in sheet_data.findall(f"{{{SHEET_NS}}}row") if int(row.get("r", "0")) == start_row + 1)
                    row_bottom = next(row for row in sheet_data.findall(f"{{{SHEET_NS}}}row") if int(row.get("r", "0")) == start_row + 2)
                    device = device_snapshots.get(device_no, {})

                    base_values = {
                        "A": str(index),
                        "B": str(index),
                        "C": _clean(device.get("device_name")),
                        "D": _clean(device.get("device_type")),
                        "E": _clean(device.get("department")),
                        "F": _clean(device.get("device_no")),
                        "G": _clean(device.get("device_level")),
                        "H": _clean(device.get("device_model")),
                        "I": _clean(device.get("device_status")),
                        "J": _clean(device.get("network_status")),
                        "K": _clean(device.get("manufacturer")),
                        "L": _clean(device.get("interface_type")),
                        "M": _clean(device.get("protocol")),
                        "N": _clean(device.get("support_software")),
                        "O": _clean(device.get("software_version")),
                        "P": _clean(device.get("source_code_available")),
                        "R": _clean(device.get("target_ip")),
                        "S": _clean(device.get("operating_system")),
                        "T": _clean(device.get("open_ports")),
                    }
                    for column_name, value in base_values.items():
                        cell = _ensure_cell(row_top, f"{column_name}{start_row}")
                        _set_inline_value(cell, value)

                    _set_inline_value(_ensure_cell(row_top, f"Q{start_row}"), _clean(device.get("device_composition")))
                    _set_inline_value(_ensure_cell(row_mid, f"Q{start_row + 1}"), "")
                    _set_inline_value(_ensure_cell(row_bottom, f"Q{start_row + 2}"), "")

                    for record in grouped[device_no]:
                        item_meta = TEST_ITEM_MAP.get(_clean(record.get("test_item_key")))
                        if not item_meta:
                            continue
                        cell = _ensure_cell(row_top, f"{item_meta['column']}{start_row}")
                        current = ""
                        for node in cell.findall(f".//{{{SHEET_NS}}}t"):
                            current += node.text or ""
                        next_value = _clean(record.get("test_result"))
                        if current and next_value and next_value not in current.split(" / "):
                            next_value = f"{current} / {next_value}"
                        _set_inline_value(cell, next_value)

                last_row = 5 + max(len(device_nos) * 3, 1)
                dimension = root.find(f"{{{SHEET_NS}}}dimension")
                if dimension is not None:
                    dimension.set("ref", f"A1:BM{last_row}")
                if merge_cells is not None:
                    merge_cells.set("count", str(len(merge_cells.findall(f'{{{SHEET_NS}}}mergeCell'))))

            elif item.filename == "xl/worksheets/sheet2.xml":
                detail_rows = [[
                    str(record.get("id", "")),
                    _clean(record.get("device_no")),
                    _clean(record.get("device_name")),
                    _clean(record.get("device_type")),
                    _clean(record.get("device_model")),
                    _clean(record.get("target_ip")),
                    _clean(record.get("test_item_label")),
                    _clean(record.get("test_method")),
                    _clean(record.get("test_result")),
                    _clean(record.get("problem_description")),
                    _clean(record.get("test_time")),
                    _clean(record.get("remarks")),
                    _clean(record.get("record_status")),
                ] for record in records]
                _fill_blank_sheet(root, DETAIL_HEADERS, detail_rows)

            elif item.filename == "xl/worksheets/sheet3.xml":
                issue_rows = [[
                    str(record.get("id", "")),
                    _clean(record.get("device_no")),
                    _clean(record.get("device_name")),
                    _clean(record.get("test_item_label")),
                    _clean(record.get("test_result")),
                    _clean(record.get("problem_description")),
                    _clean(record.get("test_time")),
                ] for record in records if _clean(record.get("test_result")) in REQUIRES_PROBLEM_RESULTS]
                _fill_blank_sheet(root, ISSUE_HEADERS, issue_rows)

            dst.writestr(item, ET.tostring(root, encoding="utf-8", xml_declaration=True))

    return output_path
