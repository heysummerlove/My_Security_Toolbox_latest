import mimetypes
from pathlib import Path

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.api_utils import json_error
from app.auth import get_current_user_by_token, get_token_from_header, require_current_user
from app.basic_test_record_manager import (
    RESULT_OPTIONS,
    TEST_ITEM_OPTIONS,
    batch_delete_basic_test_records,
    batch_save_basic_test_records,
    create_basic_test_record,
    delete_basic_test_record,
    ensure_basic_test_record_table,
    export_basic_test_record_excel,
    get_basic_test_record,
    list_basic_test_records,
    list_device_refs,
    update_basic_test_record,
)

router = APIRouter(prefix="/api/basic-test-record", tags=["basic-test-record"])


class BasicTestRecordPayload(BaseModel):
    device_no: str = ""
    device_name: str = ""
    device_type: str = ""
    device_model: str = ""
    target_ip: str = ""
    test_item_key: str = ""
    test_item_label: str = ""
    test_method: str = ""
    test_result: str = ""
    problem_description: str = ""
    test_time: str = ""
    remarks: str = ""
    record_status: str = "draft"


class BasicTestRecordBatchRequest(BaseModel):
    records: list[BasicTestRecordPayload | dict] = Field(default_factory=list)
    submit: bool = False


class BatchDeleteRequest(BaseModel):
    ids: list[int] = Field(default_factory=list)


@router.get("/options")
def get_options(current_user=Depends(require_current_user)):
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)
    return {
        "code": 200,
        "message": "查询成功",
        "data": {
            "test_items": TEST_ITEM_OPTIONS,
            "result_options": RESULT_OPTIONS,
        },
    }


@router.get("/devices")
def get_devices(keyword: str = Query(default=""), current_user=Depends(require_current_user)):
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)
    return {"code": 200, "message": "查询成功", "data": list_device_refs(keyword=keyword)}


@router.get("")
def list_records(
    keyword: str = Query(default=""),
    result_filter: str = Query(default=""),
    page: int = Query(default=1),
    page_size: int = Query(default=20),
    current_user=Depends(require_current_user),
):
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)
    ensure_basic_test_record_table()
    data = list_basic_test_records(keyword=keyword, result_filter=result_filter, page=page, page_size=page_size)
    return {"code": 200, "message": "查询成功", "data": data}


@router.get("/{record_id}")
def get_record(record_id: int, current_user=Depends(require_current_user)):
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)
    record = get_basic_test_record(record_id)
    if not record:
        return {"code": 404, "message": "测试记录不存在", "data": ""}
    return {"code": 200, "message": "查询成功", "data": record}


@router.post("")
def create_record(req: BasicTestRecordPayload, current_user=Depends(require_current_user)):
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)
    try:
        record = create_basic_test_record(req.model_dump())
    except ValueError as exc:
        return {"code": 400, "message": str(exc), "data": ""}
    return {"code": 200, "message": "保存成功", "data": record}


@router.put("/{record_id}")
def update_record(record_id: int, req: BasicTestRecordPayload, current_user=Depends(require_current_user)):
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)
    try:
        record = update_basic_test_record(record_id, req.model_dump())
    except LookupError as exc:
        return {"code": 404, "message": str(exc), "data": ""}
    except ValueError as exc:
        return {"code": 400, "message": str(exc), "data": ""}
    return {"code": 200, "message": "更新成功", "data": record}


@router.delete("/{record_id}")
def delete_record(record_id: int, current_user=Depends(require_current_user)):
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)
    if not delete_basic_test_record(record_id):
        return {"code": 404, "message": "测试记录不存在", "data": ""}
    return {"code": 200, "message": "删除成功", "data": {"id": record_id}}


@router.post("/batch-save")
def batch_save(req: BasicTestRecordBatchRequest, current_user=Depends(require_current_user)):
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)
    try:
        saved = batch_save_basic_test_records(
            [item.model_dump() if hasattr(item, "model_dump") else dict(item) for item in req.records],
            submit=req.submit,
        )
    except ValueError as exc:
        return {"code": 400, "message": str(exc), "data": ""}
    return {"code": 200, "message": "批量保存成功", "data": {"items": saved, "count": len(saved)}}


@router.post("/batch-delete")
def batch_delete(req: BatchDeleteRequest, current_user=Depends(require_current_user)):
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)
    deleted_count = batch_delete_basic_test_records(req.ids)
    return {"code": 200, "message": "批量删除成功", "data": {"count": deleted_count}}


@router.get("/export-xlsx")
def export_records(
    keyword: str = Query(default=""),
    result_filter: str = Query(default=""),
    authorization: str | None = Header(default=None),
):
    current_user = get_current_user_by_token(get_token_from_header(authorization))
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)
    records = list_basic_test_records(keyword=keyword, result_filter=result_filter, page=1, page_size=200)["items"]
    try:
        export_path = export_basic_test_record_excel(records, export_name="附表2_基本信息测试项记录表")
    except FileNotFoundError as exc:
        return {"code": 404, "message": str(exc), "data": ""}
    media_type = mimetypes.guess_type(export_path.name)[0] or "application/octet-stream"
    return FileResponse(Path(export_path), media_type=media_type, filename=export_path.name)
