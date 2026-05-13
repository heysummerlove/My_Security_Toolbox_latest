import mimetypes
from pathlib import Path

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.api_utils import json_error
from app.auth import get_current_user_by_token, get_token_from_header, require_current_user
from app.issue_statistics_manager import (
    ISSUE_TYPE_OPTIONS,
    RECTIFICATION_STATUS_OPTIONS,
    SEVERITY_OPTIONS,
    create_issue_statistics,
    delete_issue_statistics,
    ensure_issue_statistics_table,
    export_issue_statistics_excel,
    get_issue_statistics,
    list_issue_device_refs,
    list_issue_statistics,
    update_issue_statistics,
)

router = APIRouter(prefix="/api/issue-statistics", tags=["issue-statistics"])


class IssueStatisticsPayload(BaseModel):
    issue_no: str = ""
    device_no: str = ""
    test_item: str = ""
    issue_type: str = ""
    severity_level: str = ""
    remediation_suggestion: str = ""
    rectification_status: str = ""


@router.get("/options")
def get_options(current_user=Depends(require_current_user)):
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)
    return {
        "code": 200,
        "message": "查询成功",
        "data": {
            "issue_type_options": ISSUE_TYPE_OPTIONS,
            "severity_options": SEVERITY_OPTIONS,
            "rectification_status_options": RECTIFICATION_STATUS_OPTIONS,
        },
    }


@router.get("/devices")
def get_devices(keyword: str = Query(default=""), current_user=Depends(require_current_user)):
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)
    return {"code": 200, "message": "查询成功", "data": list_issue_device_refs(keyword=keyword)}


@router.get("/export-xlsx")
def export_records(
    keyword: str = Query(default=""),
    severity_filter: str = Query(default=""),
    authorization: str | None = Header(default=None),
):
    current_user = get_current_user_by_token(get_token_from_header(authorization))
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)
    records = list_issue_statistics(keyword=keyword, severity_filter=severity_filter, page=1, page_size=200)["items"]
    try:
        export_path = export_issue_statistics_excel(records, export_name="附表3_设备检测问题统计表")
    except FileNotFoundError as exc:
        return {"code": 404, "message": str(exc), "data": ""}
    media_type = mimetypes.guess_type(export_path.name)[0] or "application/octet-stream"
    return FileResponse(Path(export_path), media_type=media_type, filename=export_path.name)


@router.get("")
def list_records(
    keyword: str = Query(default=""),
    severity_filter: str = Query(default=""),
    page: int = Query(default=1),
    page_size: int = Query(default=20),
    current_user=Depends(require_current_user),
):
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)
    ensure_issue_statistics_table()
    data = list_issue_statistics(keyword=keyword, severity_filter=severity_filter, page=page, page_size=page_size)
    return {"code": 200, "message": "查询成功", "data": data}


@router.get("/{record_id}")
def get_record(record_id: int, current_user=Depends(require_current_user)):
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)
    record = get_issue_statistics(record_id)
    if not record:
        return {"code": 404, "message": "记录不存在", "data": ""}
    return {"code": 200, "message": "查询成功", "data": record}


@router.post("")
def create_record(req: IssueStatisticsPayload, current_user=Depends(require_current_user)):
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)
    try:
        record = create_issue_statistics(req.model_dump())
    except ValueError as exc:
        return {"code": 400, "message": str(exc), "data": ""}
    return {"code": 200, "message": "保存成功", "data": record}


@router.put("/{record_id}")
def update_record(record_id: int, req: IssueStatisticsPayload, current_user=Depends(require_current_user)):
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)
    try:
        record = update_issue_statistics(record_id, req.model_dump())
    except LookupError as exc:
        return {"code": 404, "message": str(exc), "data": ""}
    except ValueError as exc:
        return {"code": 400, "message": str(exc), "data": ""}
    return {"code": 200, "message": "更新成功", "data": record}


@router.delete("/{record_id}")
def delete_record(record_id: int, current_user=Depends(require_current_user)):
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)
    if not delete_issue_statistics(record_id):
        return {"code": 404, "message": "记录不存在", "data": ""}
    return {"code": 200, "message": "删除成功", "data": {"id": record_id}}
