import mimetypes
from pathlib import Path

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.api_utils import json_error
from app.auth import get_current_user_by_token, get_token_from_header, require_current_user
from app.module_data_manager import (
    clear_user_draft,
    create_compliance_record,
    create_firmware_record,
    ensure_module_data_tables,
    export_compliance_records_csv,
    export_firmware_records_csv,
    get_user_draft,
    list_compliance_records,
    list_firmware_records,
    list_shared_devices,
    peek_next_record_no,
    save_user_draft,
    upsert_shared_device,
)

router = APIRouter(prefix="/api/module-data", tags=["module-data"])


class SharedDevicePayload(BaseModel):
    sample_name: str = ""
    device_model: str = ""
    manufacturer: str = ""
    device_category: str = ""
    spec: str = ""
    remark: str = ""


class ComplianceDraftPayload(BaseModel):
    payload: dict = Field(default_factory=dict)


class ComplianceRecordPayload(BaseModel):
    record_no: str = ""
    standard: str = ""
    sample_name: str = ""
    device_model: str = ""
    manufacturer: str = ""
    device_category: str = ""
    check_item: str = ""
    result: str = ""
    issue_desc: str = ""
    rectification: str = ""
    check_date: str = ""
    inspector: str = ""
    remark: str = ""
    source_trace: str = ""


class FirmwareItemPayload(BaseModel):
    item_no: int = 0
    item_name: str = ""
    description: str = ""
    mode: str = ""
    method: str = ""
    process: str = ""
    result: str = ""


class FirmwareDraftPayload(BaseModel):
    payload: dict = Field(default_factory=dict)


class FirmwareRecordPayload(BaseModel):
    record_no: str = ""
    sample_name: str = ""
    device_model: str = ""
    manufacturer: str = ""
    check_date: str = ""
    inspector: str = ""
    remark: str = ""
    attachments: str = ""
    items: list[FirmwareItemPayload] = Field(default_factory=list)


def _module_user(current_user) -> tuple[int | None, str]:
    user_id = None
    username = ""
    if current_user:
        user_id = int(current_user["id"])
        username = str(current_user["username"] or "")
    return user_id, username


@router.get("/shared-devices")
def get_shared_devices(current_user=Depends(require_current_user)):
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)
    ensure_module_data_tables()
    return {"code": 200, "message": "查询成功", "data": list_shared_devices()}


@router.post("/shared-devices")
def save_shared_device(req: SharedDevicePayload, current_user=Depends(require_current_user)):
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)
    try:
        record = upsert_shared_device(req.model_dump())
    except ValueError as exc:
        return {"code": 400, "message": str(exc), "data": ""}
    return {"code": 200, "message": "保存成功", "data": record}


@router.get("/compliance/next-record-no")
def get_next_compliance_record_no(current_user=Depends(require_current_user)):
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)
    return {"code": 200, "message": "查询成功", "data": {"record_no": peek_next_record_no("compliance")}}


@router.get("/firmware/next-record-no")
def get_next_firmware_record_no(current_user=Depends(require_current_user)):
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)
    return {"code": 200, "message": "查询成功", "data": {"record_no": peek_next_record_no("firmware")}}


@router.get("/compliance/draft")
def get_compliance_draft(current_user=Depends(require_current_user)):
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)
    user_id, _ = _module_user(current_user)
    return {"code": 200, "message": "查询成功", "data": get_user_draft("compliance", user_id or 0)}


@router.post("/compliance/draft")
def save_compliance_draft(req: ComplianceDraftPayload, current_user=Depends(require_current_user)):
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)
    user_id, _ = _module_user(current_user)
    return {"code": 200, "message": "保存成功", "data": save_user_draft("compliance", user_id or 0, req.payload or {})}


@router.delete("/compliance/draft")
def delete_compliance_draft(current_user=Depends(require_current_user)):
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)
    user_id, _ = _module_user(current_user)
    clear_user_draft("compliance", user_id or 0)
    return {"code": 200, "message": "清除成功", "data": True}


@router.get("/firmware/draft")
def get_firmware_draft(current_user=Depends(require_current_user)):
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)
    user_id, _ = _module_user(current_user)
    return {"code": 200, "message": "查询成功", "data": get_user_draft("firmware", user_id or 0)}


@router.post("/firmware/draft")
def save_firmware_draft(req: FirmwareDraftPayload, current_user=Depends(require_current_user)):
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)
    user_id, _ = _module_user(current_user)
    return {"code": 200, "message": "保存成功", "data": save_user_draft("firmware", user_id or 0, req.payload or {})}


@router.delete("/firmware/draft")
def delete_firmware_draft(current_user=Depends(require_current_user)):
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)
    user_id, _ = _module_user(current_user)
    clear_user_draft("firmware", user_id or 0)
    return {"code": 200, "message": "清除成功", "data": True}


@router.get("/compliance/records")
def get_compliance_records(
    record_no: str = Query(default=""),
    sample_name: str = Query(default=""),
    device_model: str = Query(default=""),
    inspector: str = Query(default=""),
    result: str = Query(default=""),
    date_from: str = Query(default=""),
    date_to: str = Query(default=""),
    page: int = Query(default=1),
    page_size: int = Query(default=200),
    current_user=Depends(require_current_user),
):
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)
    return {
        "code": 200,
        "message": "查询成功",
        "data": list_compliance_records(
            record_no=record_no,
            sample_name=sample_name,
            device_model=device_model,
            inspector=inspector,
            result=result,
            date_from=date_from,
            date_to=date_to,
            page=page,
            page_size=page_size,
        ),
    }


@router.post("/compliance/records")
def save_compliance_record(req: ComplianceRecordPayload, current_user=Depends(require_current_user)):
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)
    user_id, username = _module_user(current_user)
    try:
        record = create_compliance_record(req.model_dump(), user_id=user_id, username=username)
    except ValueError as exc:
        return {"code": 400, "message": str(exc), "data": ""}
    except Exception as exc:
        return {"code": 400, "message": f"保存失败：{exc}", "data": ""}
    return {"code": 200, "message": "提交成功", "data": record}


@router.get("/firmware/records")
def get_firmware_records(
    record_no: str = Query(default=""),
    sample_name: str = Query(default=""),
    device_model: str = Query(default=""),
    inspector: str = Query(default=""),
    date_from: str = Query(default=""),
    date_to: str = Query(default=""),
    page: int = Query(default=1),
    page_size: int = Query(default=200),
    current_user=Depends(require_current_user),
):
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)
    return {
        "code": 200,
        "message": "查询成功",
        "data": list_firmware_records(
            record_no=record_no,
            sample_name=sample_name,
            device_model=device_model,
            inspector=inspector,
            date_from=date_from,
            date_to=date_to,
            page=page,
            page_size=page_size,
        ),
    }


@router.post("/firmware/records")
def save_firmware_record(req: FirmwareRecordPayload, current_user=Depends(require_current_user)):
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)
    user_id, username = _module_user(current_user)
    try:
        record = create_firmware_record(req.model_dump(), user_id=user_id, username=username)
    except ValueError as exc:
        return {"code": 400, "message": str(exc), "data": ""}
    except Exception as exc:
        return {"code": 400, "message": f"保存失败：{exc}", "data": ""}
    return {"code": 200, "message": "提交成功", "data": record}


@router.get("/compliance/export")
def export_compliance_records(
    record_no: str = Query(default=""),
    sample_name: str = Query(default=""),
    device_model: str = Query(default=""),
    inspector: str = Query(default=""),
    result: str = Query(default=""),
    date_from: str = Query(default=""),
    date_to: str = Query(default=""),
    authorization: str | None = Header(default=None),
):
    current_user = get_current_user_by_token(get_token_from_header(authorization))
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)
    records = list_compliance_records(
        record_no=record_no,
        sample_name=sample_name,
        device_model=device_model,
        inspector=inspector,
        result=result,
        date_from=date_from,
        date_to=date_to,
        page=1,
        page_size=500,
    )["items"]
    export_path = export_compliance_records_csv(records, export_name="compliance_ledger")
    media_type = mimetypes.guess_type(export_path.name)[0] or "text/csv"
    return FileResponse(Path(export_path), media_type=media_type, filename=export_path.name)


@router.get("/firmware/export")
def export_firmware_records(
    record_no: str = Query(default=""),
    sample_name: str = Query(default=""),
    device_model: str = Query(default=""),
    inspector: str = Query(default=""),
    date_from: str = Query(default=""),
    date_to: str = Query(default=""),
    authorization: str | None = Header(default=None),
):
    current_user = get_current_user_by_token(get_token_from_header(authorization))
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)
    records = list_firmware_records(
        record_no=record_no,
        sample_name=sample_name,
        device_model=device_model,
        inspector=inspector,
        date_from=date_from,
        date_to=date_to,
        page=1,
        page_size=500,
    )["items"]
    export_path = export_firmware_records_csv(records, export_name="firmware_ledger")
    media_type = mimetypes.guess_type(export_path.name)[0] or "text/csv"
    return FileResponse(Path(export_path), media_type=media_type, filename=export_path.name)
