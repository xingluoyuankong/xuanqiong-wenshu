import pytest

from app.services.generation_log_service import GenerationLogService


@pytest.mark.anyio
async def test_log_tasks_are_isolated_by_owner():
    service = GenerationLogService()
    task_id = service.create_task("task-owner-1", owner_user_id=1)
    await service.log(task_id, "secret", owner_user_id=1)

    await service.ensure_owner(task_id, 1)
    with pytest.raises(PermissionError):
        await service.ensure_owner(task_id, 2)
    with pytest.raises(LookupError):
        await service.ensure_owner("missing", 1)

    tasks = await service.get_all_tasks(owner_user_id=1)
    assert [item["task_id"] for item in tasks] == [task_id]
    assert await service.get_all_tasks(owner_user_id=2) == []


@pytest.mark.anyio
async def test_custom_task_id_cannot_be_rebound_to_another_owner():
    service = GenerationLogService()
    service.create_task("task-owner-1", owner_user_id=1)

    with pytest.raises(PermissionError):
        service.create_task("task-owner-1", owner_user_id=2)
