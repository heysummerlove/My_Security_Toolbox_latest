import re
import threading

from app.ops_manager import append_history_record
from app.task_manager import create_task, update_task


def json_error(message: str, code: int = 401):
    return {"code": code, "message": message, "data": ""}


def is_valid_target(target: str) -> bool:
    pattern = re.compile(r"^[a-zA-Z0-9\.\-/:_\s,=]+$")
    return bool(target) and bool(pattern.match(target))


def launch_background_task(task_id: int, runner, *args) -> None:
    def wrapped() -> None:
        try:
            runner(task_id, *args)
        except Exception as exc:
            update_task(task_id, "ERROR", f"ERROR: task crashed ({exc})")

    thread = threading.Thread(target=wrapped, daemon=True)
    thread.start()


def start_tool_task(
    tool: str,
    target: str,
    runner,
    *args,
    extra_data: dict | None = None,
    operator: str = "system",
    task_name: str = "",
    operation_type: str = "执行检测任务",
    source_module: str = "",
):
    final_extra_data = {
        **(extra_data or {}),
        "_history_operator": operator or "system",
        "_history_task_name": task_name or tool,
        "_history_operation_type": operation_type,
        "_history_source_module": source_module or tool,
    }
    task_id = create_task(
        tool,
        target,
        f"PENDING: {tool} task has been queued",
        extra_data=final_extra_data,
    )
    append_history_record(
        related_task_id=task_id,
        task_name=task_name or tool,
        executor=operator or "system",
        status="PENDING",
        content=f"任务已创建，目标：{target}",
        operation_type=operation_type,
        source_module=source_module or tool,
        detail_data={"tool": tool, "target": target, "extra_data": final_extra_data},
    )
    launch_background_task(task_id, runner, *args)
    return {
        "code": 200,
        "message": f"{tool} task started",
        "data": {"task_id": task_id},
    }
