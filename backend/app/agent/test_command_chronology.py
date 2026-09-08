"""Same-second command order follows durable request events, not random IDs."""
from datetime import datetime, timezone, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, update, delete
from app.models import User
from app.models.agent import AgentRunCommand, AgentEventRecord
from app.services import agent_runtime as runtime_module
from app.services.agent_runtime import AgentRuntimeService
from app.agent.command_recovery import AgentCommandRecovery
from app.agent.state_projection import AgentStateProjectionService


async def commands_in_one_second(session, monkeypatch):
    token = uuid4().hex
    user = User(username='chronology-'+token,email=token+'@example.com',hashed_password='x',is_active=True)
    session.add(user)
    await session.flush()
    uid = user.id
    service = AgentRuntimeService(session)
    chat = await service.create_session(user_id=uid)
    run = await service.create_run(session_id=chat.id,user_id=uid)
    instant = datetime(2026,9,7,4,0,0,tzinfo=timezone.utc)
    monkeypatch.setattr(AgentRuntimeService, '_now', staticmethod(lambda: instant))
    # Both command and event IDs descend; sequence allocation remains untouched.
    numbers = iter(range(1000,900,-1))
    monkeypatch.setattr(runtime_module,'uuid4',lambda: UUID(int=next(numbers)))
    commands = []
    for i,kind in enumerate(('pause','resume','cancel')):
        commands.append(await service.request_run_command(run_id=run.id,user_id=uid,
            command_type=kind,idempotency_key=f'chronology-{i}'))
    ids = [c.id for c in commands]
    assert ids == sorted(ids,reverse=True)
    assert len({c.requested_at for c in commands}) == 1
    return service,uid,run,commands


@pytest.mark.asyncio
async def test_same_second_runtime_lists_pages_and_projection_use_request_sequence(task_session,monkeypatch):
    service,uid,run,commands = await commands_in_one_second(task_session,monkeypatch)
    expected = [c.id for c in commands]
    assert [c.id for c in await service.list_run_commands(run_id=run.id,user_id=uid)] == expected
    assert [c.id for c in await service.list_run_commands_readable(run_id=run.id,user_id=uid)] == expected
    pages = []
    for offset in range(3):
        rows,total = await service.list_run_commands_readable_page(run_id=run.id,user_id=uid,limit=1,offset=offset)
        assert total == 3
        pages.extend(c.id for c in rows)
    assert pages == expected
    projection = await AgentStateProjectionService(task_session).get_run_state(run_id=run.id,user_id=uid)
    assert [c['id'] for c in projection['commands']] == expected
    assert projection['active_command']['id'] == expected[-1]


@pytest.mark.asyncio
async def test_same_second_worker_claims_follow_request_sequence(task_session,monkeypatch):
    _,uid,run,commands = await commands_in_one_second(task_session,monkeypatch)
    service = AgentCommandRecovery(task_session)
    claimed=[]
    for _ in range(3):
        command = await service.claim_next(lease_owner='chronology-worker')
        assert command is not None
        claimed.append(command.id)
    assert claimed == [c.id for c in commands]
    assert await service.claim_next(lease_owner='chronology-worker') is None


@pytest.mark.asyncio
async def test_missing_request_events_have_stable_legacy_fallback(task_session,monkeypatch):
    service,uid,run,commands = await commands_in_one_second(task_session,monkeypatch)
    await task_session.execute(delete(AgentEventRecord).where(AgentEventRecord.run_id==run.id))
    await task_session.commit()
    assert [c.id for c in await service.list_run_commands(run_id=run.id,user_id=uid)] == sorted(c.id for c in commands)


@pytest.mark.asyncio
@pytest.mark.parametrize('field', ['user_id','correlation_id','transaction_id','event_type','command_type','run_id'])
async def test_wrong_scope_request_event_never_controls_command_order(task_session,monkeypatch,field):
    service,uid,run,commands = await commands_in_one_second(task_session,monkeypatch)
    # First command loses its valid event; unrelated lookalike must not become ordering evidence.
    event=(await task_session.execute(select(AgentEventRecord).where(AgentEventRecord.run_id==run.id,
        AgentEventRecord.sequence==1))).scalar_one()
    if field == 'command_type':
        event.data_json = {**event.data_json, 'command_type': 'cancel'}
    elif field == 'run_id':
        other = await service.create_run(session_id=run.session_id,user_id=uid)
        event.run_id = other.id
    else:
        setattr(event,field,uid+100 if field=='user_id' else 'unrelated')
    await task_session.commit()
    expected=[commands[1].id,commands[2].id,commands[0].id]
    assert [c.id for c in await service.list_run_commands(run_id=run.id,user_id=uid)] == expected


@pytest.mark.asyncio
async def test_earlier_timestamp_precedes_same_second_sequence_tie_break(task_session,monkeypatch):
    service,uid,run,commands=await commands_in_one_second(task_session,monkeypatch)
    commands[-1].requested_at=commands[-1].requested_at-timedelta(seconds=1)
    await task_session.commit()
    assert [c.id for c in await service.list_run_commands(run_id=run.id,user_id=uid)] == [commands[2].id,commands[0].id,commands[1].id]


@pytest.mark.asyncio
async def test_null_legacy_transactions_still_match_request_events(task_session,monkeypatch):
    service,uid,run,commands=await commands_in_one_second(task_session,monkeypatch)
    await task_session.execute(update(AgentRunCommand).where(AgentRunCommand.run_id==run.id).values(transaction_id=None))
    await task_session.execute(update(AgentEventRecord).where(AgentEventRecord.run_id==run.id).values(transaction_id=None))
    await task_session.commit()
    assert [c.id for c in await service.list_run_commands(run_id=run.id,user_id=uid)] == [c.id for c in commands]


@pytest.mark.asyncio
async def test_same_expiry_recovery_preserves_request_event_order(task_session,monkeypatch):
    _,uid,run,commands=await commands_in_one_second(task_session,monkeypatch)
    recovery=AgentCommandRecovery(task_session)
    for command in commands:
        await recovery.claim(command_id=command.id,lease_owner='old-worker')
    expired=recovery.now()-timedelta(seconds=2)
    await task_session.execute(update(AgentRunCommand).where(AgentRunCommand.run_id==run.id).values(lease_expires_at=expired))
    await task_session.commit()
    recovered=await recovery.recover_stale_commands(limit=3)
    assert [c.id for c in recovered] == [c.id for c in commands]
    claimed=await recovery.claim_next(lease_owner='new-worker')
    assert claimed.id == commands[0].id


@pytest.mark.parametrize('dialect_name',['mysql','sqlite'])
def test_command_sequence_expression_compiles_with_full_scope(dialect_name):
    from sqlalchemy.dialects import mysql, sqlite
    from app.agent.command_ordering import command_order_by
    dialect=mysql.dialect() if dialect_name=='mysql' else sqlite.dialect()
    sql=str(select(AgentRunCommand.id).order_by(*command_order_by()).limit(1).compile(dialect=dialect))
    assert 'min(agent_events.sequence)' in sql
    for column in ('run_id','user_id','correlation_id','transaction_id'):
        assert f'agent_events.{column}' in sql and f'agent_run_commands.{column}' in sql
    assert 'JSON_EXTRACT' in sql
