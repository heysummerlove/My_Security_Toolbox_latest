import mimetypes
import os
import re
from collections.abc import Callable
from typing import Any

from app.api_utils import ApiError, is_valid_target, start_tool_task
from app.task_manager import get_task, get_task_logs, read_result_preview, request_cancel
from app.task_runners import (
    run_basic_task,
    run_evaluation_task,
    run_fscan_task,
    run_nmap_task,
    run_nsfocus_report_task,
    run_nsfocus_task,
)

UserLike = dict[str, Any]


def _require_valid_target(target: str) -> str:
    normalized = (target or "").strip()
    if not is_valid_target(normalized):
        raise ApiError("非法的目标地址。", 400)
    return normalized


def _require_non_empty(value: str, message: str) -> str:
    normalized = (value or "").strip()
    if not normalized:
        raise ApiError(message, 400)
    return normalized


def _require_task(task_id: int) -> dict[str, Any]:
    task = get_task(task_id)
    if not task:
        raise ApiError("任务不存在", 404)
    return task


def _start_task(
    *,
    tool: str,
    target: str,
    runner: Callable[..., Any],
    args: tuple[Any, ...],
    operator: str,
    task_name: str,
    operation_type: str,
    source_module: str,
    extra_data: dict[str, Any] | None = None,
):
    return start_tool_task(
        tool,
        target,
        runner,
        *args,
        extra_data=extra_data,
        operator=operator,
        task_name=task_name,
        operation_type=operation_type,
        source_module=source_module,
    )


def start_basic_tool(*, tool: str, target: str, current_user: UserLike):
    normalized_tool = (tool or "").strip().lower()
    if normalized_tool not in {"ping", "tracert"}:
        raise ApiError("不支持的基础工具", 400)
    normalized_target = _require_valid_target(target)
    return _start_task(
        tool="basic",
        target=normalized_target,
        runner=run_basic_task,
        args=(normalized_tool, normalized_target),
        extra_data={"tool": normalized_tool},
        operator=current_user["username"],
        task_name=f"{normalized_tool.upper()} 基础探测",
        operation_type="执行基础探测",
        source_module="vulnerability_basic",
    )


def start_nmap_scan(*, target_ip: str, task_name: str | None, current_user: UserLike):
    normalized_target = _require_valid_target(target_ip)
    normalized_task_name = (task_name or "").strip() or "Nmap 端口与服务识别"
    return _start_task(
        tool="nmap",
        target=normalized_target,
        runner=run_nmap_task,
        args=(normalized_target,),
        operator=current_user["username"],
        task_name=normalized_task_name,
        operation_type="执行Nmap扫描",
        source_module="vulnerability_nmap",
    )


def start_fscan_scan(*, args: str, current_user: UserLike):
    raw_args = _require_non_empty(args, "Fscan 参数不能为空。")
    return _start_task(
        tool="fscan",
        target=raw_args,
        runner=run_fscan_task,
        args=(raw_args,),
        extra_data={"args": raw_args},
        operator=current_user["username"],
        task_name="Fscan 综合漏洞巡检",
        operation_type="执行Fscan扫描",
        source_module="vulnerability_fscan",
    )


def start_nsfocus_scan(*, target_ip: str, task_name: str | None, current_user: UserLike):
    normalized_target = _require_valid_target(target_ip)
    normalized_task_name = (task_name or "").strip()
    return _start_task(
        tool="nsfocus",
        target=normalized_target,
        runner=run_nsfocus_task,
        args=(normalized_target, normalized_task_name),
        extra_data={"task_name": normalized_task_name},
        operator=current_user["username"],
        task_name=normalized_task_name or "Web 漏扫下发",
        operation_type="下发Web漏扫任务",
        source_module="vulnerability_nsfocus",
    )


def start_nsfocus_report_download(*, target_ip: str, task_name: str | None, current_user: UserLike):
    normalized_target = (target_ip or "").strip() or "latest_report"
    normalized_task_name = (task_name or "").strip()
    return _start_task(
        tool="nsfocus_report",
        target=normalized_target,
        runner=run_nsfocus_report_task,
        args=(normalized_task_name,),
        extra_data={"task_name": normalized_task_name, "source": "latest_report"},
        operator=current_user["username"],
        task_name=normalized_task_name or "下载最近报告",
        operation_type="下载最近报告",
        source_module="vulnerability_nsfocus_report",
    )


def start_evaluation(*, target_ip: str, task_name: str | None, current_user: UserLike):
    normalized_target = _require_valid_target(target_ip)
    normalized_task_name = (task_name or "").strip()
    return _start_task(
        tool="evaluation",
        target=normalized_target,
        runner=run_evaluation_task,
        args=(normalized_target, normalized_task_name),
        extra_data={"task_name": normalized_task_name},
        operator=current_user["username"],
        task_name=normalized_task_name or "综合评估",
        operation_type="执行综合评估",
        source_module="vulnerability_evaluation",
    )


def get_task_detail_data(task_id: int):
    task = _require_task(task_id)
    return {
        "code": 200,
        "message": "查询成功",
        "data": {
            "task": task,
            "logs": get_task_logs(task_id, 300),
            "result_preview": read_result_preview(task.get("result_path", "")),
        },
    }


def pause_task_by_id(task_id: int):
    _require_task(task_id)
    if not request_cancel(task_id):
        raise ApiError("任务不存在", 404)
    return {"code": 200, "message": f"已请求暂停任务 {task_id}", "data": {"task_id": task_id}}


def resolve_report_download(task_id: int) -> tuple[str, str, str]:
    task = _require_task(task_id)
    report_path = task.get("result_path", "")
    if not report_path or not os.path.exists(report_path):
        raise ApiError("报告文件不存在", 404)

    filename = os.path.basename(report_path)
    if task.get("tool") == "evaluation":
        task_name = ((task.get("extra_data") or {}).get("task_name") or "").strip()
        safe_name = re.sub(r"[^\w\-.]+", "_", task_name, flags=re.UNICODE).strip("_")
        filename = f"evaluation_{safe_name}_{task_id}.txt" if safe_name else f"evaluation_task_{task_id}.txt"
    elif task.get("tool") == "nsfocus_report":
        filename = os.path.basename(report_path)

    media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return report_path, media_type, filename
