# AIMETA P=生成日志路由_实时流式API|R=日志查询_实时流|NR=不含业务逻辑|E=route:GET_/api/updates/*|X=http|A=日志路由|D=fastapi|S=db|RD=./README.ai
import json
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.session import get_session
from ...schemas.admin import UpdateLogRead
from ...services.update_log_service import UpdateLogService
from ...services.generation_log_service import get_generation_log_service, LogEntry

router = APIRouter(prefix="/api/updates", tags=["Updates"])

logger = logging.getLogger(__name__)


def get_update_log_service(session: AsyncSession = Depends(get_session)) -> UpdateLogService:
    return UpdateLogService(session)


@router.get("/latest", response_model=List[UpdateLogRead])
async def read_latest_updates(
    service: UpdateLogService = Depends(get_update_log_service),
) -> List[UpdateLogRead]:
    """获取最新的更新日志记录"""
    logs = await service.list_logs(limit=5)
    return [UpdateLogRead.model_validate(log) for log in logs]


# ==================== 实时流式日志 API ====================

@router.get("/stream/{task_id}")
async def stream_generation_logs(task_id: str):
    """
    SSE 实时流式输出生成日志
    
    使用方式:
        const evtSource = new EventSource('/api/updates/stream/{task_id}');
        evtSource.onmessage = (e) => console.log(JSON.parse(e.data));
    """
    log_service = get_generation_log_service()

    async def event_generator():
        async for entry in log_service.stream_logs(task_id):
            data = entry.to_dict()
            # 心跳事件不发送数据
            if data["level"] == "heartbeat":
                yield f": keepalive\n\n"
            else:
                yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/stream/{task_id}/log")
async def append_generation_log(
    task_id: str,
    message: str = Query(..., description="日志消息"),
    level: str = Query(default="info", description="日志级别"),
):
    """向指定任务追加一条日志（供内部服务调用）"""
    log_service = get_generation_log_service()
    entry = await log_service.log(task_id, message, level=level)
    return {"success": True, "entry": entry.to_dict()}


@router.get("/stream/tasks")
async def list_active_tasks():
    """列出所有活跃的日志任务"""
    log_service = get_generation_log_service()
    tasks = await log_service.get_all_tasks()
    return {"tasks": tasks, "total": len(tasks)}


@router.post("/stream/{task_id}/complete")
async def complete_generation_task(task_id: str):
    """标记生成任务完成"""
    log_service = get_generation_log_service()
    await log_service.complete_task(task_id)
    return {"success": True, "task_id": task_id, "status": "completed"}


@router.post("/stream/create")
async def create_generation_task(task_id: str = Query(default=None, description="可选自定义 task_id")):
    """创建新的生成日志任务"""
    log_service = get_generation_log_service()
    tid = log_service.create_task(task_id)
    return {"task_id": tid, "status": "created"}
