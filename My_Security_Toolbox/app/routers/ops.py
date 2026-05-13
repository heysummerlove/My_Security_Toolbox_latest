import io
from typing import Any

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api_utils import json_error
from app.auth import get_current_user_by_token, get_token_from_header, require_current_user
from app.ops_manager import (
    batch_update_managed_tasks,
    create_managed_task,
    export_execution_history_csv,
    export_managed_tasks_csv,
    get_execution_history,
    get_managed_task_detail,
    list_execution_history,
    list_managed_tasks,
    update_managed_task,
)

router = APIRouter(prefix="/api/ops", tags=["ops"])


class ManagedTaskPayload(BaseModel):
    task_name: str = Field(default="")
    task_type: str = Field(default="")
    owner: str = Field(default="")
    start_time: str = Field(default="")
    due_time: str = Field(default="")
    status: str = Field(default="待开始")
    progress: int = Field(default=0)
    attachments: str = Field(default="")
    description: str = Field(default="")
    related_exec_task_id: int | None = Field(default=None)
    priority: str = Field(default="中")


class ManagedTaskBatchPayload(BaseModel):
    task_ids: list[int] = Field(default_factory=list)
    action: str = Field(default="")
    value: Any = Field(default=None)


@router.get("/history")
def get_history_list(
    keyword: str = Query(default=""),
    executor: str = Query(default=""),
    status: str = Query(default=""),
    operation_type: str = Query(default=""),
    date_from: str = Query(default=""),
    date_to: str = Query(default=""),
    related_task_id: int | None = Query(default=None),
    managed_task_id: int | None = Query(default=None),
    page: int = Query(default=1),
    page_size: int = Query(default=20),
    current_user=Depends(require_current_user),
):
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)
    data = list_execution_history(
        keyword=keyword,
        executor=executor,
        status=status,
        operation_type=operation_type,
        date_from=date_from,
        date_to=date_to,
        related_task_id=related_task_id,
        managed_task_id=managed_task_id,
        page=page,
        page_size=page_size,
    )
    return {"code": 200, "message": "查询成功", "data": data}


@router.get("/history/export")
def export_history(
    keyword: str = Query(default=""),
    executor: str = Query(default=""),
    status: str = Query(default=""),
    operation_type: str = Query(default=""),
    date_from: str = Query(default=""),
    date_to: str = Query(default=""),
    authorization: str | None = Header(default=None),
):
    current_user = get_current_user_by_token(get_token_from_header(authorization))
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)
    csv_text = export_execution_history_csv(
        keyword=keyword,
        executor=executor,
        status=status,
        operation_type=operation_type,
        date_from=date_from,
        date_to=date_to,
    )
    filename = f"execution_history_{current_user['username']}.csv"
    return StreamingResponse(
        io.StringIO(csv_text),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/history/{record_id}")
def get_history_detail(record_id: int, current_user=Depends(require_current_user)):
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)
    record = get_execution_history(record_id)
    if not record:
        return {"code": 404, "message": "历史记录不存在", "data": ""}
    return {"code": 200, "message": "查询成功", "data": record}


@router.get("/managed-tasks")
def get_managed_tasks(
    keyword: str = Query(default=""),
    task_type: str = Query(default=""),
    status: str = Query(default=""),
    owner: str = Query(default=""),
    overdue_only: bool = Query(default=False),
    page: int = Query(default=1),
    page_size: int = Query(default=20),
    current_user=Depends(require_current_user),
):
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)
    data = list_managed_tasks(
        keyword=keyword,
        task_type=task_type,
        status=status,
        owner=owner,
        overdue_only=overdue_only,
        page=page,
        page_size=page_size,
    )
    return {"code": 200, "message": "查询成功", "data": data}


@router.post("/managed-tasks")
def create_managed_task_api(payload: ManagedTaskPayload, current_user=Depends(require_current_user)):
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)
    if not payload.task_name.strip():
        return {"code": 400, "message": "任务名称不能为空", "data": ""}
    if not payload.task_type.strip():
        return {"code": 400, "message": "任务类型不能为空", "data": ""}
    task_id = create_managed_task(payload.model_dump(), current_user["username"])
    return {"code": 200, "message": "任务创建成功", "data": {"task_id": task_id}}


@router.post("/managed-tasks/batch")
def batch_update_managed_tasks_api(payload: ManagedTaskBatchPayload, current_user=Depends(require_current_user)):
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)
    if not payload.task_ids:
        return {"code": 400, "message": "请至少选择一条任务", "data": ""}
    count = batch_update_managed_tasks(payload.task_ids, payload.action, payload.value, current_user["username"])
    return {"code": 200, "message": f"批量操作完成，共处理 {count} 条任务", "data": {"count": count}}


@router.get("/managed-tasks/export")
def export_managed_tasks(
    keyword: str = Query(default=""),
    task_type: str = Query(default=""),
    status: str = Query(default=""),
    owner: str = Query(default=""),
    overdue_only: bool = Query(default=False),
    authorization: str | None = Header(default=None),
):
    current_user = get_current_user_by_token(get_token_from_header(authorization))
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)
    csv_text = export_managed_tasks_csv(
        keyword=keyword,
        task_type=task_type,
        status=status,
        owner=owner,
        overdue_only=overdue_only,
    )
    filename = f"managed_tasks_{current_user['username']}.csv"
    return StreamingResponse(
        io.StringIO(csv_text),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/managed-tasks/{task_id}")
def get_managed_task_view(task_id: int, current_user=Depends(require_current_user)):
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)
    detail = get_managed_task_detail(task_id)
    if not detail:
        return {"code": 404, "message": "任务不存在", "data": ""}
    return {"code": 200, "message": "查询成功", "data": detail}


@router.put("/managed-tasks/{task_id}")
def update_managed_task_api(task_id: int, payload: ManagedTaskPayload, current_user=Depends(require_current_user)):
    if not current_user:
        return json_error("未登录或登录已过期，请重新登录。", 401)
    success = update_managed_task(task_id, payload.model_dump(), current_user["username"])
    if not success:
        return {"code": 404, "message": "任务不存在", "data": ""}
    return {"code": 200, "message": "任务更新成功", "data": {"task_id": task_id}}
