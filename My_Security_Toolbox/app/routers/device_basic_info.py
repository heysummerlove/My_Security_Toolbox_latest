import base64
import mimetypes
from pathlib import Path

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.api_utils import json_error
from app.auth import get_current_user_by_token, get_token_from_header, require_current_user
from app.device_basic_info_manager import (
    create_device_basic_info,
    delete_device_basic_info,
    ensure_device_basic_info_table,
    export_device_basic_info_excel,
    get_device_basic_info,
    import_device_basic_info_rows,
    list_device_basic_info,
    parse_device_basic_info_template,
    update_device_basic_info,
)

router = APIRouter(prefix="/api/device-basic-info", tags=["device-basic-info"])


class DeviceBasicInfoPayload(BaseModel):
    device_name: str = ""
    device_type: str = ""
    department: str = ""
    device_no: str = ""
    device_level: str = ""
    device_model: str = ""
    device_status: str = ""
    network_status: str = ""
    manufacturer: str = ""
    interface_type: str = ""
    protocol: str = ""
    software_version: str = ""
    device_composition: str = ""
    target_ip: str = ""
    mac_address: str = ""
    operating_system_choice: str = ""
    operating_system_other: str = ""
    operating_system: str = ""
    open_ports: str = ""
    support_software: str = ""
    source_code_available: str = ""
    notes: str = ""
    record_status: str = "draft"


class DeviceBasicInfoImportRequest(BaseModel):
    file_name: str = ""
    file_content_base64: str = Field(default="", description="Excel 文件 Base64 内容")


@router.get("")
def list_records(
    keyword: str = Query(default=""),
    page: int = Query(default=1),
    page_size: int = Query(default=20),
    current_user=Depends(require_current_user),
):
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)
    ensure_device_basic_info_table()
    return {"code": 200, "message": "查询成功", "data": list_device_basic_info(keyword=keyword, page=page, page_size=page_size)}


@router.get("/{record_id}")
def get_record(record_id: int, current_user=Depends(require_current_user)):
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)
    record = get_device_basic_info(record_id)
    if not record:
        return {"code": 404, "message": "设备调研记录不存在", "data": ""}
    return {"code": 200, "message": "查询成功", "data": record}


@router.post("")
def create_record(req: DeviceBasicInfoPayload, current_user=Depends(require_current_user)):
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)
    try:
        record = create_device_basic_info(req.model_dump())
    except ValueError as exc:
        return {"code": 400, "message": str(exc), "data": ""}
    return {"code": 200, "message": "保存成功", "data": record}


@router.put("/{record_id}")
def update_record(record_id: int, req: DeviceBasicInfoPayload, current_user=Depends(require_current_user)):
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)
    try:
        record = update_device_basic_info(record_id, req.model_dump())
    except LookupError as exc:
        return {"code": 404, "message": str(exc), "data": ""}
    except ValueError as exc:
        return {"code": 400, "message": str(exc), "data": ""}
    return {"code": 200, "message": "更新成功", "data": record}


@router.delete("/{record_id}")
def delete_record(record_id: int, current_user=Depends(require_current_user)):
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)
    if not delete_device_basic_info(record_id):
        return {"code": 404, "message": "设备调研记录不存在", "data": ""}
    return {"code": 200, "message": "删除成功", "data": {"id": record_id}}


@router.post("/import")
def import_records(req: DeviceBasicInfoImportRequest, current_user=Depends(require_current_user)):
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)
    if not req.file_content_base64:
        return {"code": 400, "message": "请先上传 Excel 文件", "data": ""}
    try:
        file_bytes = base64.b64decode(req.file_content_base64)
        rows = parse_device_basic_info_template(file_bytes)
        result = import_device_basic_info_rows(rows)
    except ValueError as exc:
        return {"code": 400, "message": str(exc), "data": ""}
    except Exception as exc:
        return {"code": 400, "message": f"导入失败：{exc}", "data": ""}
    return {"code": 200, "message": "导入成功", "data": result}


@router.get("/export-xlsx")
def export_records(
    keyword: str = Query(default=""),
    authorization: str | None = Header(default=None),
):
    current_user = get_current_user_by_token(get_token_from_header(authorization))
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)
    records = list_device_basic_info(keyword=keyword, page=1, page_size=200)["items"]
    try:
        export_path = export_device_basic_info_excel(records, export_name="附表1_设备基本信息表")
    except FileNotFoundError as exc:
        return {"code": 404, "message": str(exc), "data": ""}
    media_type = mimetypes.guess_type(export_path.name)[0] or "application/octet-stream"
    return FileResponse(Path(export_path), media_type=media_type, filename=export_path.name)
