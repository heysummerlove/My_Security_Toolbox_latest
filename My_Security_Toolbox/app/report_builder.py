import json
import shutil
import zipfile
from pathlib import Path
from typing import Callable
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
GENERATED_REPORTS_DIR = DATA_DIR / "generated_reports"
TEMPLATE_SOURCE_DIRS = [
    Path(r"D:\（非密）指南附件"),
    Path(r"C:\Users\32260\Desktop\网络安全\316检测\新建文件夹\指南附件\（非密）指南附件"),
]

TEMPLATE_FILES = {
    "device_survey": "1、设备调研表模板.docx",
    "detection_plan": "2、检测方案模板.docx",
    "detection_record": "3、安全检测记录表模板.docx",
    "detection_report": "4、检测报告模板.docx",
    "data_retention": "5、数据保留确认表模板.docx",
    "item_confirmation": "6、检测项确认表模板.docx",
    "device_basic_info": "7、附表1-设备基本信息表模板.xlsx",
    "basic_test_record": "8、附表2-基本信息测试项记录表.xlsx",
    "issue_statistics": "9、附表3-设备检测问题统计表.xlsx",
}

OUTPUT_NAMES = {
    "device_survey": "01_设备调研表_自动生成.docx",
    "detection_plan": "02_检测方案_自动生成.docx",
    "detection_record": "03_安全检测记录表_自动生成.docx",
    "detection_report": "04_检测报告_自动生成.docx",
    "data_retention": "05_数据保留确认表_自动生成.docx",
    "item_confirmation": "06_检测项确认表_自动生成.docx",
    "device_basic_info": "07_附表1_设备基本信息表_自动生成.xlsx",
    "basic_test_record": "08_附表2_基本信息测试项记录表_自动生成.xlsx",
    "issue_statistics": "09_附表3_设备检测问题统计表_自动生成.xlsx",
}

WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
SHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
XML_NS = "http://www.w3.org/XML/1998/namespace"

ET.register_namespace("", SHEET_NS)


def ensure_report_dirs() -> None:
    GENERATED_REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def _clean(value: object, fallback: str = "") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text if text else fallback


def _safe_name(value: str) -> str:
    text = _clean(value, "report")
    safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in text)
    return safe.strip("_.") or "report"


def _template_path(key: str) -> Path:
    filename = TEMPLATE_FILES[key]
    for root in TEMPLATE_SOURCE_DIRS:
        candidate = root / filename
        if candidate.exists():
            return candidate
    return TEMPLATE_SOURCE_DIRS[0] / filename


def _paragraph_xml(text: str, *, bold: bool = False, size: int | None = None) -> str:
    value = escape(text)
    run_props = []
    if bold:
        run_props.append("<w:b/>")
    if size is not None:
        run_props.append(f'<w:sz w:val="{size}"/>')
        run_props.append(f'<w:szCs w:val="{size}"/>')
    run_props_xml = f"<w:rPr>{''.join(run_props)}</w:rPr>" if run_props else ""
    return (
        "<w:p>"
        "<w:r>"
        f"{run_props_xml}"
        f'<w:t xml:space="preserve">{value}</w:t>'
        "</w:r>"
        "</w:p>"
    )


def _docx_document_xml(title: str, sections: list[tuple[str, str]]) -> str:
    body_parts = [_paragraph_xml(title, bold=True, size=32)]
    for heading, content in sections:
        body_parts.append(_paragraph_xml(""))
        body_parts.append(_paragraph_xml(heading, bold=True, size=26))
        for line in content.splitlines() or [""]:
            body_parts.append(_paragraph_xml(line))
    body_parts.append(
        "<w:sectPr>"
        '<w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1800" '
        'w:header="851" w:footer="992" w:gutter="0"/>'
        "</w:sectPr>"
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{WORD_NS}"><w:body>'
        + "".join(body_parts)
        + "</w:body></w:document>"
    )


def _write_docx_from_template(template_path: Path, output_path: Path, document_xml: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(template_path, "r") as src, zipfile.ZipFile(
        output_path, "w", compression=zipfile.ZIP_DEFLATED
    ) as dst:
        for item in src.infolist():
            if item.filename == "word/document.xml":
                dst.writestr(item, document_xml.encode("utf-8"))
            else:
                dst.writestr(item, src.read(item.filename))


def _set_inline_cell(sheet_root: ET.Element, cell_ref: str, value: str) -> None:
    row_number = "".join(ch for ch in cell_ref if ch.isdigit())
    if not row_number:
        return

    sheet_data = sheet_root.find(f"{{{SHEET_NS}}}sheetData")
    if sheet_data is None:
        sheet_data = ET.SubElement(sheet_root, f"{{{SHEET_NS}}}sheetData")

    row = None
    for current in sheet_data.findall(f"{{{SHEET_NS}}}row"):
        if current.get("r") == row_number:
            row = current
            break
    if row is None:
        row = ET.SubElement(sheet_data, f"{{{SHEET_NS}}}row", {"r": row_number})

    cell = None
    for current in row.findall(f"{{{SHEET_NS}}}c"):
        if current.get("r") == cell_ref:
            cell = current
            break
    if cell is None:
        cell = ET.SubElement(row, f"{{{SHEET_NS}}}c", {"r": cell_ref})

    for child in list(cell):
        cell.remove(child)
    cell.set("t", "inlineStr")
    cell.attrib.pop("cm", None)
    inline = ET.SubElement(cell, f"{{{SHEET_NS}}}is")
    text_node = ET.SubElement(inline, f"{{{SHEET_NS}}}t")
    if value != value.strip():
        text_node.set(f"{{{XML_NS}}}space", "preserve")
    text_node.text = value


def _fill_sheet(template_path: Path, output_path: Path, cell_map: dict[str, str]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(template_path, "r") as src, zipfile.ZipFile(
        output_path, "w", compression=zipfile.ZIP_DEFLATED
    ) as dst:
        for item in src.infolist():
            if item.filename != "xl/worksheets/sheet1.xml":
                dst.writestr(item, src.read(item.filename))
                continue

            root = ET.fromstring(src.read(item.filename))
            for cell_ref, value in cell_map.items():
                _set_inline_cell(root, cell_ref, value)
            dst.writestr(item, ET.tostring(root, encoding="utf-8", xml_declaration=True))


def _copy_if_exists(source: Path, target: Path) -> bool:
    if not source.exists():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return True


def _selected_items_text(payload: dict[str, object], key: str = "selected_items") -> str:
    items = payload.get(key) or []
    if not isinstance(items, list):
        return "-"
    cleaned = [str(item).strip() for item in items if str(item).strip()]
    return "、".join(cleaned) if cleaned else "-"


def _item_confirmation_rows(payload: dict[str, object]) -> list[dict[str, str]]:
    try:
        sections = json.loads(_clean(payload.get("item_confirmation_sections_json"), "[]"))
    except json.JSONDecodeError:
        sections = []

    rows: list[dict[str, str]] = []
    for section in sections:
        for item in section.get("items", []):
            rows.append({
                "major": _clean(item.get("major")),
                "minor": _clean(item.get("minor")),
                "detail": _clean(item.get("detail")),
                "check": _clean(item.get("check")),
                "reason": _clean(item.get("final_reason")),
            })
    return rows


def _data_retention_rows(payload: dict[str, object]) -> list[dict[str, str]]:
    try:
        sections = json.loads(_clean(payload.get("data_retention_sections_json"), "[]"))
    except json.JSONDecodeError:
        sections = []

    rows: list[dict[str, str]] = []
    for section in sections:
        for item in section.get("items", []):
            rows.append({
                "major": _clean(item.get("major")),
                "minor": _clean(item.get("minor")),
                "detail": _clean(item.get("detail")),
                "keep": _clean(item.get("keep")),
                "reason": _clean(item.get("final_reason")),
            })
    return rows


def _record_item_block(
    payload: dict[str, object],
    prefix: str,
    title: str,
    auto_description: str,
    auto_method: str,
    auto_way: str = "系统自动带出"
) -> str:
    return "\n".join([
        f"检测项：{title}",
        f"检测项描述：{auto_description}",
        f"检测方式：{auto_way}",
        f"检测方法：{auto_method}",
        f"检测过程：{_clean(payload.get(f'{prefix}_process'))}",
        f"检测结果：{_clean(payload.get(f'{prefix}_result'))}",
        f"结果说明：{_clean(payload.get(f'{prefix}_result_note'))}",
        f"附件上传：{_clean(payload.get(f'{prefix}_files'))}",
    ])


def _detection_record_sections(payload: dict[str, object]) -> list[tuple[str, str]]:
    selected_text = _clean(payload.get("selected_items_text")) or _selected_items_text(payload)
    sections: list[tuple[str, str]] = [
        ("一、基础信息", "\n".join([
            f"项目名称：{_clean(payload.get('project_name'))}",
            f"报告标题：{_clean(payload.get('report_title') or payload.get('project_name'))}",
            f"报告编号：{_clean(payload.get('report_no'))}",
            f"样品名称：{_clean(payload.get('sample_name'))}",
            f"设备名称：{_clean(payload.get('device_name') or payload.get('sample_name'))}",
            f"设备型号：{_clean(payload.get('sample_model'))}",
            f"设备编号：{_clean(payload.get('device_no'))}",
            f"生产厂商：{_clean(payload.get('manufacturer'))}",
            f"委托单位：{_clean(payload.get('commissioning_org'))}",
            f"使用部门：{_clean(payload.get('department'))}",
            f"检测地点：{_clean(payload.get('test_location'))}",
            f"检测日期：{_clean(payload.get('test_date'))}",
            f"本次涵盖检测类别：{selected_text}",
            f"总体检测结果：{_clean(payload.get('detection_conclusion'))}",
            f"记录摘要：{_clean(payload.get('record_summary'))}",
            f"风险汇总：{_clean(payload.get('risk_summary'))}",
            f"补充说明：{_clean(payload.get('notes'))}",
        ])),
        ("二、通用填写规则", "\n".join([
            f"填写规则：{_clean(payload.get('record_common_rule'), '检测项描述、检测方式、检测方法系统自动带出；检测过程按步骤记录现场操作、工具使用、时间、人员；检测结果填写合格/不合格/异常/不涉及并附说明。')}",
            f"统一附件格式规范：{_clean(payload.get('record_attachment_rule'), '图片：JPG/PNG；文档：PDF/DOCX；数据：XLSX/CSV/BIN/PCAP；视频：MP4。')}",
        ])),
        ("三、合规性检查", "\n\n".join([
            _record_item_block(payload, "record_compliance_1", "设备及产线基本情况摸排", "系统自动带出，无需填写。", "进口渠道、产线属性、物防人防、采购与维修记录核查。"),
            _record_item_block(payload, "record_compliance_2", "设备物理安全检测", "系统自动带出，无需填写。", "品牌型号、外观、改装痕迹、物理隔离情况检查。"),
            _record_item_block(payload, "record_compliance_3", "设备安全配置核查", "系统自动带出，无需填写。", "补丁、服务、账户、防火墙、日志、杀毒软件状态核查。"),
        ])),
        ("四、有线网络流量安全检测", "\n\n".join([
            _record_item_block(payload, "record_wired_1", "网络资产一致性验证", "系统自动带出，无需填写。", "扫描工具采集、资产清单比对与一致性验证。"),
            _record_item_block(payload, "record_wired_2", "威胁检测", "系统自动带出，无需填写。", "特征集部署、攻击识别与溯源分析。"),
        ])),
        ("五、无线协议安全检测", "\n\n".join([
            _record_item_block(payload, "record_wireless_1", "物理层无线协议安全", "系统自动带出，无需填写。", "频谱仪参数设置、频率/功率/波形测试。"),
            _record_item_block(payload, "record_wireless_2", "数据链路层无线协议安全", "系统自动带出，无需填写。", "帧解析、白名单测试、资源分配与加密检测。"),
            _record_item_block(payload, "record_wireless_3", "应用层无线协议安全", "系统自动带出，无需填写。", "加密验证、白名单、双向认证与实时监测。"),
        ])),
        ("六、嵌入式设备固件提取及检测", "\n\n".join([
            _record_item_block(payload, "record_firmware_1", "固件提取", "系统自动带出，无需填写。", "官方/漏洞/调试口等提取方式与操作步骤记录。"),
            _record_item_block(payload, "record_firmware_2", "固件元信息分析", "系统自动带出，无需填写。", "完整性、哈希、解包、厂商型号识别分析。"),
            _record_item_block(payload, "record_firmware_3", "敏感文件提取", "系统自动带出，无需填写。", "文件系统、配置、权限、弱口令扫描。"),
            _record_item_block(payload, "record_firmware_4", "供应链安全分析", "系统自动带出，无需填写。", "第三方组件、版本、漏洞匹配分析。"),
            _record_item_block(payload, "record_firmware_5", "代码审计", "系统自动带出，无需填写。", "源码审查、加密与密钥存储检查。"),
            _record_item_block(payload, "record_firmware_6", "漏洞挖掘", "系统自动带出，无需填写。", "反编译、内存漏洞、内核漏洞、Web漏洞分析。"),
            _record_item_block(payload, "record_firmware_7", "漏洞匹配", "系统自动带出，无需填写。", "与 CVE/CNVD/CNNVD 比对并标注危害等级。"),
            _record_item_block(payload, "record_firmware_8", "恶意代码检测", "系统自动带出，无需填写。", "后门检查、特征匹配、YARA 检测。"),
            _record_item_block(payload, "record_firmware_9", "仿真测试", "系统自动带出，无需填写。", "环境搭建、服务启动与风险检测。"),
        ])),
        ("七、漏洞检测", "\n\n".join([
            _record_item_block(payload, "record_vulnerability_1", "信息收集", "系统自动带出，无需填写。", "资料收集、工具探测与人工核对。"),
            _record_item_block(payload, "record_vulnerability_2", "漏洞扫描", "系统自动带出，无需填写。", "静态比对、动态扫描、策略与验证。"),
            _record_item_block(payload, "record_vulnerability_3", "漏洞挖掘（代码审计/逆向分析/模糊测试）", "系统自动带出，无需填写。", "环境搭建、工具分析、验证确认。"),
            _record_item_block(payload, "record_vulnerability_4", "模拟攻击（渗透测试）", "系统自动带出，无需填写。", "接入点、利用过程、验证与痕迹清理。"),
        ])),
        ("八、设备电磁安全检测", "\n\n".join([
            _record_item_block(payload, "record_electromagnetic_device_1", "扫描检测", "系统自动带出，无需填写。", "频段、参数、频谱与 IQ 数据采集。"),
            _record_item_block(payload, "record_electromagnetic_device_2", "诱导检测", "系统自动带出，无需填写。", "公网/局域网/物联网/导航/卫星等制式诱导检测。"),
        ])),
        ("九、设备周边电磁安全检测", "\n\n".join([
            _record_item_block(payload, "record_electromagnetic_peripheral_1", "现场检测（电磁/无线网络/红外/非线性/雷达成像）", "系统自动带出，无需填写。", "检测范围、参数、可疑目标定位。"),
            _record_item_block(payload, "record_electromagnetic_peripheral_2", "常态监测（固定/机动巡检）", "系统自动带出，无需填写。", "背景采集、扫描、参数提取、IQ、测向。"),
        ])),
        ("十、设备无损拆解检测", "\n\n".join([
            _record_item_block(payload, "record_nondestructive_1", "设备拆解", "系统自动带出，无需填写。", "步骤、标记、录像、部件检查。"),
            _record_item_block(payload, "record_nondestructive_2", "设备检测", "系统自动带出，无需填写。", "外观、接口、PCB、元件、供应链、测试。"),
            _record_item_block(payload, "record_nondestructive_3", "设备复原", "系统自动带出，无需填写。", "逆序复原、紧固、功能测试。"),
        ])),
        ("十一、签署与建议", "\n".join([
            f"检测人员：{_clean(payload.get('testers'))}",
            f"审核人员：{_clean(payload.get('reviewer'))}",
            f"批准人员：{_clean(payload.get('approver'))}",
            f"整改或处置建议：{_clean(payload.get('recommendations'))}",
        ])),
    ]
    return sections


def _build_sections_for_template(template_type: str, payload: dict[str, object]) -> list[tuple[str, str]]:
    if template_type == "device_survey":
        return [
            ("一、设备概述", "\n".join([
                f"项目名称：{_clean(payload.get('project_name'))}",
                f"设备名称：{_clean(payload.get('device_name') or payload.get('sample_name'))}",
                f"设备型号：{_clean(payload.get('sample_model'))}",
                f"设备编号：{_clean(payload.get('device_no'))}",
                f"设备等级：{_clean(payload.get('device_level'))}",
                f"设备简介：{_clean(payload.get('notes'))}",
            ])),
            ("二、网络与环境", "\n".join([
                f"设备IP：{_clean(payload.get('target_ip'))}",
                f"接口类型：{_clean(payload.get('interface_type'))}",
                f"通信协议：{_clean(payload.get('protocol'))}",
                f"检测地点：{_clean(payload.get('test_location'))}",
                f"检测日期：{_clean(payload.get('test_date'))}",
            ])),
        ]
    if template_type == "detection_plan":
        return [
            ("一、方案概述", "\n".join([
                f"项目名称：{_clean(payload.get('project_name'))}",
                f"报告编号：{_clean(payload.get('report_no'))}",
                f"委托单位：{_clean(payload.get('commissioning_org'))}",
                f"检测地点：{_clean(payload.get('test_location'))}",
                f"检测依据：{_clean(payload.get('basis_document'))}",
            ])),
            ("二、检测对象", "\n".join([
                f"样品名称：{_clean(payload.get('sample_name'))}",
                f"设备名称：{_clean(payload.get('device_name'))}",
                f"设备型号：{_clean(payload.get('sample_model'))}",
                f"设备厂商：{_clean(payload.get('manufacturer'))}",
            ])),
            ("三、检测安排", "\n".join([
                f"检测项：{_selected_items_text(payload)}",
                f"环境温度：{_clean(payload.get('environment_temperature'))}",
                f"环境湿度：{_clean(payload.get('environment_humidity'))}",
                f"补充说明：{_clean(payload.get('notes'))}",
            ])),
        ]
    if template_type == "detection_record":
        return _detection_record_sections(payload)
    if template_type == "detection_report":
        return [
            ("封面信息", "\n".join([
                f"标识：{_clean(payload.get('document_identifier'))}",
                f"密级：{_clean(payload.get('classification'))}",
                f"报告编号：{_clean(payload.get('report_no'))}",
                f"样品名称：{_clean(payload.get('sample_name'))}",
                f"型号：{_clean(payload.get('sample_model'))}",
                f"序列号：{_clean(payload.get('sample_serial'))}",
                f"被检单位：{_clean(payload.get('inspected_unit'))}",
                f"报告时间：{_clean(payload.get('report_date'))}",
                f"出具单位：{_clean(payload.get('issuing_unit'))}",
            ])),
            ("有效性声明", "系统固定展示，不可编辑。"),
            ("检测基本信息表", "\n".join([
                f"样品名称 / 型号：{_clean(payload.get('sample_name'))} / {_clean(payload.get('sample_model'))}",
                f"设备编号：{_clean(payload.get('device_no'))}",
                f"委托单位：{_clean(payload.get('commissioning_org'))}",
                f"委托单位地址：{_clean(payload.get('commissioning_org_address'))}",
                f"联系人：{_clean(payload.get('contact_name'))}",
                f"联系电话：{_clean(payload.get('contact_phone'))}",
                f"联系邮箱：{_clean(payload.get('contact_email'))}",
                f"检测单位：{_clean(payload.get('testing_unit'))}",
                f"检测地点：{_clean(payload.get('test_location'))}",
                f"样品接收日期：{_clean(payload.get('receive_date'))}",
                f"检测日期：{_clean(payload.get('detection_date_start'))} 至 {_clean(payload.get('detection_date_end'))}",
                f"依据文件：{_clean(payload.get('basis_document'))}",
                f"检测结论：{_clean(payload.get('detection_conclusion'))}",
                f"检测人员：{_clean(payload.get('testers'))}",
                f"审核人员：{_clean(payload.get('reviewer'))}",
                f"批准人员：{_clean(payload.get('approver'))}",
                f"日期：{_clean(payload.get('signature_date'))}",
            ])),
            ("1 检测目的", _clean(payload.get("test_purpose"))),
            ("2 检测依据", "\n".join([
                f"依据表格：{_clean(payload.get('basis_documents_table'))}",
                f"依据文件附件：{_clean(payload.get('basis_attachments'))}",
            ])),
            ("3 被测样品清单", _clean(payload.get("sample_list_table"))),
            ("4 检测环境", _clean(payload.get("test_environment"))),
            ("5 检测工具", "\n".join([
                f"工具表格：{_clean(payload.get('test_tools_table'))}",
                f"校准证书：{_clean(payload.get('tool_calibration_attachments'))}",
            ])),
            ("6 检测结果汇总", _clean(payload.get("result_summary_table"))),
            ("7 总体风险研判", "\n".join([
                f"风险研判：{_clean(payload.get('overall_risk_assessment'))}",
                f"风险汇总：{_clean(payload.get('risk_summary'))}",
            ])),
            ("8 处置建议", "\n".join([
                f"处置建议：{_clean(payload.get('disposal_recommendations'))}",
                f"整改或处置建议补充：{_clean(payload.get('recommendations'))}",
            ])),
        ]
    if template_type == "data_retention":
        rows = _data_retention_rows(payload)
        return [
            ("一、保留确认", "\n".join([
                f"项目名称：{_clean(payload.get('project_name'))}",
                f"样品名称：{_clean(payload.get('sample_name'))}",
                f"留存项：{_selected_items_text(payload, 'retained_items')}",
                f"留存理由：{_clean(payload.get('retained_reason'))}",
            ])),
            ("二、留存明细", "\n".join([
                f"检测大项={row['major']}；检测小项={row['minor']}；检测细项={row['detail']}；是否留存={row['keep'] or '-'}；留存理由={row['reason'] or '-'}"
                for row in rows
            ])),
            ("三、签署信息", "\n".join([
                f"检测机构：{_clean(payload.get('data_retention_testing_agency') or payload.get('testers'))}",
                f"被测机构：{_clean(payload.get('data_retention_tested_agency') or payload.get('commissioning_org'))}",
                f"日期：{_clean(payload.get('data_retention_date') or payload.get('report_date') or payload.get('test_date'))}",
            ])),
        ]
    if template_type == "item_confirmation":
        rows = _item_confirmation_rows(payload)
        selected_items = [row["detail"] for row in rows if row["check"] == "是"]
        unselected_items = [f"{row['detail']}：{row['reason'] or '未填写'}" for row in rows if row["check"] == "否"]
        return [
            ("一、检测项确认", "\n".join([
                f"项目名称：{_clean(payload.get('project_name'))}",
                f"样品名称：{_clean(payload.get('sample_name'))}",
                f"确认检测项：{_clean(payload.get('item_confirmation_selected_text')) or ('、'.join(selected_items) if selected_items else '-')}",
                f"不开展理由：{_clean(payload.get('item_confirmation_unselected_text')) or ('；'.join(unselected_items) if unselected_items else '-')}",
            ])),
            ("二、明细确认结果", "\n".join([
                f"检测大项={row['major']}；检测小项={row['minor']}；检测细项={row['detail']}；是否检测={row['check'] or '-'}；裁剪理由={(row['reason'] if row['check'] == '否' else '-') or '-'}"
                for row in rows
            ])),
            ("三、签署信息", "\n".join([
                f"检测机构：{_clean(payload.get('testers'))}",
                f"被测机构：{_clean(payload.get('commissioning_org'))}",
            ])),
        ]
    return [("自动生成", json.dumps(payload, ensure_ascii=False, indent=2))]


def _build_docx(template_type: str, payload: dict[str, object]) -> str:
    title_map = {
        "device_survey": "设备调研表（自动生成）",
        "detection_plan": "检测方案（自动生成）",
        "detection_record": "安全检测记录表（自动生成）",
        "detection_report": "检测报告（自动生成）",
        "data_retention": "数据保留确认表（自动生成）",
        "item_confirmation": "检测项确认表（自动生成）",
    }
    return _docx_document_xml(title_map.get(template_type, "报告文档（自动生成）"), _build_sections_for_template(template_type, payload))


def _generate_device_basic_info(template_path: Path, output_path: Path, payload: dict[str, object]) -> None:
    _fill_sheet(template_path, output_path, {
        "A2": "1",
        "B2": _clean(payload.get("device_name") or payload.get("sample_name")),
        "C2": _clean(payload.get("device_type")),
        "D2": _clean(payload.get("department")),
        "E2": _clean(payload.get("device_no")),
        "F2": _clean(payload.get("device_level")),
        "G2": _clean(payload.get("sample_model")),
        "H2": _clean(payload.get("device_status")),
        "I2": _clean(payload.get("network_status")),
        "J2": _clean(payload.get("manufacturer")),
        "K2": _clean(payload.get("interface_type")),
        "L2": _clean(payload.get("protocol")),
        "M2": _clean(payload.get("software_version")),
        "N2": _clean(payload.get("other_devices")),
        "O2": _clean(payload.get("target_ip")),
        "P2": _clean(payload.get("operating_system")),
        "Q2": _clean(payload.get("open_ports")),
        "R2": _clean(payload.get("support_software")),
        "S2": _clean(payload.get("source_code_available")),
    })


def _generate_basic_test_record(template_path: Path, output_path: Path, payload: dict[str, object]) -> None:
    _fill_sheet(template_path, output_path, {
        "A2": "1",
        "B2": _clean(payload.get("device_name") or payload.get("sample_name")),
        "C2": _clean(payload.get("device_department") or payload.get("department")),
        "D2": _clean(payload.get("device_level")),
        "E2": _clean(payload.get("device_type")),
        "F2": _clean(payload.get("manufacturer")),
        "G2": _clean(payload.get("sample_model")),
        "H2": _clean(payload.get("upper_machine")),
        "I2": _clean(payload.get("lower_machine")),
        "J2": _clean(payload.get("support_software")),
        "K2": _clean(payload.get("source_code_available")),
        "L2": _clean(payload.get("other_devices")),
        "M2": _clean(payload.get("target_ip")),
        "N2": _clean(payload.get("open_ports")),
        "O2": _selected_items_text(payload),
        "P2": _clean(payload.get("record_summary")),
    })


def _generate_issue_statistics(template_path: Path, output_path: Path, payload: dict[str, object]) -> None:
    _fill_sheet(template_path, output_path, {
        "A2": "1",
        "B2": _clean(payload.get("device_no")),
        "C2": _clean(payload.get("device_name") or payload.get("sample_name")),
        "D2": _clean(payload.get("device_type")),
        "E2": _clean(payload.get("department")),
        "F2": _clean(payload.get("device_level")),
        "G2": _clean(payload.get("sample_model")),
        "H2": _clean(payload.get("network_status")),
        "I2": _clean(payload.get("manufacturer")),
        "J2": _clean(payload.get("interface_type")),
        "K2": _clean(payload.get("support_software")),
        "L2": _clean(payload.get("source_code_available")),
        "M2": _clean(payload.get("other_devices")),
        "N2": _clean(payload.get("target_ip")),
        "O2": _clean(payload.get("open_ports")),
        "P2": _clean(payload.get("upper_machine")),
        "Q2": _clean(payload.get("lower_machine")),
        "R2": _clean(payload.get("other_devices")),
        "S2": _clean(payload.get("problem_1")),
        "T2": _clean(payload.get("problem_2")),
        "U2": _clean(payload.get("problem_3")),
        "V2": _clean(payload.get("software_version")),
        "W2": _clean(payload.get("operating_system")),
        "X2": _clean(payload.get("issue_description")),
        "Y2": _clean(payload.get("issue_test_item")),
        "Z2": _clean(payload.get("issue_fixable")),
        "AA2": _clean(payload.get("issue_fix_action")),
        "AB2": _clean(payload.get("issue_fix_plan")),
        "AC2": _clean(payload.get("issue_unfixable_reason")),
    })


def _generate_single_artifact(template_type: str, payload: dict[str, object], output_dir: Path) -> tuple[Path | None, Path | None]:
    template_path = _template_path(template_type)
    if not template_path.exists():
        return None, template_path

    output_path = output_dir / OUTPUT_NAMES[template_type]
    if template_type in {"device_survey", "detection_plan", "detection_record", "detection_report", "data_retention", "item_confirmation"}:
        _write_docx_from_template(template_path, output_path, _build_docx(template_type, payload))
        return output_path, None
    if template_type == "device_basic_info":
        _generate_device_basic_info(template_path, output_path, payload)
        return output_path, None
    if template_type == "basic_test_record":
        _generate_basic_test_record(template_path, output_path, payload)
        return output_path, None
    if template_type == "issue_statistics":
        _generate_issue_statistics(template_path, output_path, payload)
        return output_path, None
    return None, template_path


def _build_summary_text(template_type: str, payload: dict[str, object], included_files: list[str], missing_files: list[str]) -> str:
    lines = [
        "报告编纂结果",
        "=" * 60,
        f"模板类型：{template_type}",
        f"项目名称：{_clean(payload.get('project_name'))}",
        f"报告编号：{_clean(payload.get('report_no'))}",
        f"样品名称：{_clean(payload.get('sample_name'))}",
        "",
        "已打包文件：",
    ]
    lines.extend(f"- {name}" for name in included_files)
    if missing_files:
        lines.append("")
        lines.append("缺失模板：")
        lines.extend(f"- {name}" for name in missing_files)
    return "\n".join(lines)


def generate_report_package(task_id: int, payload: dict[str, object], log: Callable[[str], None] | None = None) -> Path:
    ensure_report_dirs()
    template_type = _clean(payload.get("template_type"), "device_survey")
    report_name = _safe_name(
        f"{template_type}_{_clean(payload.get('report_no'))}_{_clean(payload.get('sample_name') or payload.get('project_name') or payload.get('device_name'))}"
    )
    work_dir = GENERATED_REPORTS_DIR / f"report_task_{task_id}_{report_name}"
    generated_dir = work_dir / "generated"
    templates_dir = work_dir / "templates"
    if work_dir.exists():
        shutil.rmtree(work_dir)
    generated_dir.mkdir(parents=True, exist_ok=True)
    templates_dir.mkdir(parents=True, exist_ok=True)

    included_files: list[str] = []
    missing_files: list[str] = []

    payload_path = work_dir / "report_data.json"
    payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    included_files.append(payload_path.name)

    if log:
        log(f"开始生成模板：{template_type}")

    generated_file, missing_template = _generate_single_artifact(template_type, payload, generated_dir)
    if generated_file:
        included_files.append(str(generated_file.relative_to(work_dir)))
    if missing_template:
        missing_files.append(missing_template.name)

    source_template = _template_path(template_type)
    if _copy_if_exists(source_template, templates_dir / f"原始模板_{TEMPLATE_FILES[template_type]}"):
        included_files.append(str((templates_dir / f"原始模板_{TEMPLATE_FILES[template_type]}").relative_to(work_dir)))

    summary_path = work_dir / "README.txt"
    summary_path.write_text(_build_summary_text(template_type, payload, included_files, missing_files), encoding="utf-8")
    included_files.append(summary_path.name)

    zip_path = GENERATED_REPORTS_DIR / f"report_task_{task_id}_{report_name}.zip"
    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(work_dir.rglob("*")):
            if file_path.is_file():
                zf.write(file_path, file_path.relative_to(work_dir))

    if log:
        log(f"报告包已生成：{zip_path.name}")
    return zip_path
