from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.api_utils import ApiError, json_error
from app.auth import require_authenticated_user
from app.task_service import (
    get_task_detail_data,
    pause_task_by_id,
    resolve_report_download,
    start_basic_tool,
    start_evaluation,
    start_fscan_scan,
    start_nmap_scan,
    start_nsfocus_report_download,
    start_nsfocus_scan,
)

router = APIRouter(tags=["tasks"])


class TargetRequest(BaseModel):
    target_ip: str
    task_name: str | None = None


class FscanRequest(BaseModel):
    args: str


class BasicToolRequest(BaseModel):
    tool: str
    target: str


def _handle_api_error(exc: ApiError):
    return json_error(exc.message, exc.code) if exc.data == "" else {"code": exc.code, "message": exc.message, "data": exc.data}


@router.post("/api/basic/run")
def run_basic_tool(req: BasicToolRequest, current_user=Depends(require_authenticated_user)):
    try:
        return start_basic_tool(tool=req.tool, target=req.target, current_user=current_user)
    except ApiError as exc:
        return _handle_api_error(exc)


@router.post("/api/nmap/scan")
def trigger_nmap(req: TargetRequest, current_user=Depends(require_authenticated_user)):
    try:
        return start_nmap_scan(target_ip=req.target_ip, task_name=req.task_name, current_user=current_user)
    except ApiError as exc:
        return _handle_api_error(exc)


@router.post("/api/fscan/scan")
def trigger_fscan(req: FscanRequest, current_user=Depends(require_authenticated_user)):
    try:
        return start_fscan_scan(args=req.args, current_user=current_user)
    except ApiError as exc:
        return _handle_api_error(exc)


@router.post("/api/nsfocus/scan")
def trigger_nsfocus(req: TargetRequest, current_user=Depends(require_authenticated_user)):
    try:
        return start_nsfocus_scan(target_ip=req.target_ip, task_name=req.task_name, current_user=current_user)
    except ApiError as exc:
        return _handle_api_error(exc)


@router.post("/api/nsfocus/report/download")
def trigger_nsfocus_report_download(req: TargetRequest, current_user=Depends(require_authenticated_user)):
    try:
        return start_nsfocus_report_download(target_ip=req.target_ip, task_name=req.task_name, current_user=current_user)
    except ApiError as exc:
        return _handle_api_error(exc)


@router.post("/api/evaluation/run")
def trigger_evaluation(req: TargetRequest, current_user=Depends(require_authenticated_user)):
    try:
        return start_evaluation(target_ip=req.target_ip, task_name=req.task_name, current_user=current_user)
    except ApiError as exc:
        return _handle_api_error(exc)


@router.get("/api/tasks/{task_id}")
def get_task_detail(task_id: int, current_user=Depends(require_authenticated_user)):
    try:
        return get_task_detail_data(task_id)
    except ApiError as exc:
        return _handle_api_error(exc)


@router.post("/api/tasks/{task_id}/pause")
def pause_task(task_id: int, current_user=Depends(require_authenticated_user)):
    try:
        return pause_task_by_id(task_id)
    except ApiError as exc:
        return _handle_api_error(exc)


@router.get("/api/tasks/{task_id}/report")
def download_task_report(task_id: int, current_user=Depends(require_authenticated_user)):
    try:
        report_path, media_type, filename = resolve_report_download(task_id)
    except ApiError as exc:
        return _handle_api_error(exc)
    return FileResponse(report_path, media_type=media_type, filename=filename)
