from fastapi import APIRouter, HTTPException, Request

from app.schemas import TaskResponse

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(task_id: str, request: Request) -> TaskResponse:
    state = request.app.state.task_manager.snapshot(task_id)
    if state is None:
        raise HTTPException(404, "任务不存在")
    return state
