import mimetypes
import os
import re

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.api_utils import is_valid_target, json_error, start_tool_task
from app.auth import get_current_user_by_token, get_token_from_header, require_current_user
from app.task_manager import get_task, get_task_logs, read_result_preview, request_cancel
from app.task_runners import (
    run_basic_task,
    run_evaluation_task,
    run_fscan_task,
    run_nmap_task,
    run_nsfocus_report_task,
    run_nsfocus_task,
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
@router.post("/api/basic/run")
def run_basic_tool(req: BasicToolRequest, current_user=Depends(require_current_user)):
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)
    if req.tool not in {"ping", "tracert"}:
        return {"code": 400, "message": "不支持的基础工具", "data": ""}
    if not is_valid_target(req.target):
        return {"code": 400, "message": "非法的目标地址。", "data": ""}

    return start_tool_task(
        "basic",
        req.target,
        run_basic_task,
        req.tool,
        req.target,
        extra_data={"tool": req.tool},
        operator=current_user["username"],
        task_name=f"{req.tool.upper()} 基础探测",
        operation_type="执行基础探测",
        source_module="vulnerability_basic",
    )


@router.post("/api/nmap/scan")
def trigger_nmap(req: TargetRequest, current_user=Depends(require_current_user)):
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)
    if not is_valid_target(req.target_ip):
        return {"code": 400, "message": "非法的目标地址。", "data": ""}

    return start_tool_task(
        "nmap",
        req.target_ip,
        run_nmap_task,
        req.target_ip,
        operator=current_user["username"],
        task_name=req.task_name or "Nmap 端口与服务识别",
        operation_type="执行Nmap扫描",
        source_module="vulnerability_nmap",
    )


@router.post("/api/fscan/scan")
def trigger_fscan(req: FscanRequest, current_user=Depends(require_current_user)):
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)
    raw_args = req.args.strip()
    if not raw_args:
        return {"code": 400, "message": "Fscan 参数不能为空。", "data": ""}

    return start_tool_task(
        "fscan",
        raw_args,
        run_fscan_task,
        raw_args,
        extra_data={"args": raw_args},
        operator=current_user["username"],
        task_name="Fscan 综合漏洞巡检",
        operation_type="执行Fscan扫描",
        source_module="vulnerability_fscan",
    )


@router.post("/api/nsfocus/scan")
def trigger_nsfocus(req: TargetRequest, current_user=Depends(require_current_user)):
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)
    if not is_valid_target(req.target_ip):
        return {"code": 400, "message": "非法的目标地址。", "data": ""}

    return start_tool_task(
        "nsfocus",
        req.target_ip,
        run_nsfocus_task,
        req.target_ip,
        req.task_name or "",
        extra_data={"task_name": (req.task_name or "").strip()},
        operator=current_user["username"],
        task_name=req.task_name or "Web 漏扫下发",
        operation_type="下发Web漏扫任务",
        source_module="vulnerability_nsfocus",
    )


@router.post("/api/nsfocus/report/download")
def trigger_nsfocus_report_download(req: TargetRequest, current_user=Depends(require_current_user)):
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)
    task_name = (req.task_name or "").strip()

    return start_tool_task(
        "nsfocus_report",
        req.target_ip or "latest_report",
        run_nsfocus_report_task,
        task_name,
        extra_data={"task_name": task_name, "source": "latest_report"},
        operator=current_user["username"],
        task_name=task_name or "下载最近报告",
        operation_type="下载最近报告",
        source_module="vulnerability_nsfocus_report",
    )


@router.post("/api/evaluation/run")
def trigger_evaluation(req: TargetRequest, current_user=Depends(require_current_user)):
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)
    if not is_valid_target(req.target_ip):
        return {"code": 400, "message": "非法的目标地址。", "data": ""}

    return start_tool_task(
        "evaluation",
        req.target_ip,
        run_evaluation_task,
        req.target_ip,
        req.task_name or "",
        extra_data={"task_name": (req.task_name or "").strip()},
        operator=current_user["username"],
        task_name=req.task_name or "综合评估",
        operation_type="执行综合评估",
        source_module="vulnerability_evaluation",
    )


@router.get("/api/tasks/{task_id}")
def get_task_detail(task_id: int, current_user=Depends(require_current_user)):
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)
    task = get_task(task_id)
    if not task:
        return {"code": 404, "message": "任务不存在", "data": ""}
    return {
        "code": 200,
        "message": "查询成功",
        "data": {
            "task": task,
            "logs": get_task_logs(task_id, 300),
            "result_preview": read_result_preview(task.get("result_path", "")),
        },
    }


@router.post("/api/tasks/{task_id}/pause")
def pause_task(task_id: int, current_user=Depends(require_current_user)):
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)
    if not request_cancel(task_id):
        return {"code": 404, "message": "任务不存在", "data": ""}
    return {"code": 200, "message": f"已请求暂停任务 {task_id}", "data": {"task_id": task_id}}


@router.get("/api/tasks/{task_id}/report")
def download_task_report(
    task_id: int,
    authorization: str | None = Header(default=None),
):
    current_user = get_current_user_by_token(get_token_from_header(authorization))
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)

    task = get_task(task_id)
    if not task:
        return {"code": 404, "message": "任务不存在", "data": ""}

    report_path = task.get("result_path", "")
    if not report_path or not os.path.exists(report_path):
        return {"code": 404, "message": "报告文件不存在", "data": ""}

    filename = os.path.basename(report_path)
    if task.get("tool") == "evaluation":
        task_name = ((task.get("extra_data") or {}).get("task_name") or "").strip()
        safe_name = re.sub(r"[^\w\-.]+", "_", task_name, flags=re.UNICODE).strip("_")
        filename = f"evaluation_{safe_name}_{task_id}.txt" if safe_name else f"evaluation_task_{task_id}.txt"
    elif task.get("tool") == "nsfocus_report":
        filename = os.path.basename(report_path)

    media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return FileResponse(report_path, media_type=media_type, filename=filename)
