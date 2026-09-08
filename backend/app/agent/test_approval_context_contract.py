"""Approval context regressions through the real route and registry boundary."""
from copy import deepcopy
from functools import wraps
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update

from app.agent.execution import ApprovalRunContractError
from app.agent.registry import DEFAULT_TOOL_REGISTRY
from app.api.routers import agent as router
from app.models.agent import AgentArtifactRef
from app.models.agent_catalog import AgentCapabilityExecution
from app.models.agent_context import ContextSnapshot, ContextSnapshotRef
from app.models.novel import NovelProject, Chapter, ChapterVersion
from app.models.user import User
from app.services.agent_runtime import AgentRuntimeService
from app.services.agent_context_service import AgentContextService


async def context_fixture(session, monkeypatch, *, reference='chapter', approved_chapter=12, replan=False):
    key=uuid4().hex
    user=User(username=f'context-{key}',email=f'{key}@example.com',hashed_password='x',is_active=True)
    session.add(user); await session.flush()
    project=NovelProject(id=key,user_id=user.id,title='Approval context')
    session.add(project); await session.flush()
    chapters=[Chapter(project_id=key,chapter_number=number) for number in (12,99)]
    session.add_all(chapters); await session.flush()
    version=ChapterVersion(chapter_id=chapters[1].id,content='version for 99')
    session.add(version); await session.flush()
    refs=[]
    if reference == 'chapter': refs=[{'kind':'chapter','project_id':key,'chapter_number':12}]
    if reference == 'bad-version': refs=[{'kind':'chapter_version','project_id':key,'chapter_number':12,'version_id':version.id}]
    if reference == 'missing-artifact': refs=[{'kind':'artifact','project_id':key,'artifact_id':str(uuid4())}]
    if reference == 'malformed': refs={'secret':'not a reference array'}
    runtime=AgentRuntimeService(session)
    if reference in ('valid-artifact', 'cross-project-artifact'):
        artifact_project_id = key
        if reference == 'cross-project-artifact':
            artifact_project_id = uuid4().hex
            session.add(NovelProject(id=artifact_project_id, user_id=user.id, title='Other project'))
            await session.flush()
        artifact_chat = await runtime.create_session(user_id=user.id, project_id=artifact_project_id)
        artifact_run = await runtime.create_run(session_id=artifact_chat.id, user_id=user.id, project_id=artifact_project_id, context={})
        artifact = await runtime.add_artifact(run_id=artifact_run.id, user_id=user.id, project_id=artifact_project_id, kind='fixture', uri='fixture://context')
        refs = [{'kind': 'artifact', 'project_id': key, 'artifact_id': artifact.id}]
    chat=await runtime.create_session(user_id=user.id,project_id=key)
    run=await runtime.create_run(session_id=chat.id,user_id=user.id,project_id=key,context={'requested_tools':['chapter.generate'],'context_refs':refs})
    if replan:
        snapshot=await AgentContextService(session).create_snapshot(run=run,session=chat,context_json={'context_refs':refs},refs=refs,context_kind='replan_context')
        context=dict(run.context_json);context['relational_context_snapshot_id']=snapshot.id;context['relational_context_snapshot_key']=snapshot.snapshot_id
        await runtime.set_run_context(run_id=run.id,user_id=user.id,context=context)
    args={'chapter_number':approved_chapter}
    step=await runtime.ensure_step(run_id=run.id,user_id=user.id,step_order=1,tool_name='chapter.generate',idempotency_key=f'{run.id}:context',input_payload=args)
    step.status='awaiting_approval'; await session.commit()
    approval=await runtime.request_approval(run_id=run.id,user_id=user.id,step_id=step.id,tool_name='chapter.generate',project_id=key,arguments=args)
    await runtime.decide_approval(approval_id=approval.id,user_id=user.id,approved=True,reason='context regression')
    await session.refresh(run)
    snapshot=await AgentContextService(session).get_run_snapshot(run_id=run.id,snapshot_id=run.context_json['relational_context_snapshot_key'])
    calls=[]
    original=DEFAULT_TOOL_REGISTRY.get_handler('chapter.generate')
    @wraps(original)
    async def sentinel(**kwargs):
        calls.append(kwargs);return {'artifact':SimpleNamespace(id='context-artifact')}
    monkeypatch.setitem(DEFAULT_TOOL_REGISTRY._handlers,'chapter.generate',sentinel)
    return SimpleNamespace(run=run,user=user,approval=approval,snapshot=snapshot,chapters=chapters,version=version,calls=calls)


async def execute(session, f):
    return await router._execute_registered_approval(approval_id=f.approval.id,session=session,user_id=f.user.id)


async def reject(session, f, field):
    before=[await session.scalar(select(func.count()).select_from(model).where(model.run_id==f.run.id)) for model in (AgentCapabilityExecution,AgentArtifactRef)]
    with pytest.raises(ApprovalRunContractError) as error:
        await execute(session,f)
    assert error.value.field == field or (field == 'context_snapshot' and error.value.field.startswith('context_snapshot.'))
    assert not f.calls
    after=[await session.scalar(select(func.count()).select_from(model).where(model.run_id==f.run.id)) for model in (AgentCapabilityExecution,AgentArtifactRef)]
    assert before==after==[0,0]


@pytest.mark.asyncio
@pytest.mark.parametrize('reference,replan',[('chapter',False),('chapter',True),('none',False),('valid-artifact',False)])
async def test_real_context_positive_explicit_and_replan(task_session,monkeypatch,reference,replan):
    f=await context_fixture(task_session,monkeypatch,reference=reference,replan=replan)
    assert (await execute(task_session,f)).id=='context-artifact'
    assert len(f.calls)==1
    assert f.calls[0]['arguments']['chapter_number']==12


@pytest.mark.asyncio
async def test_approved_argument_conflicts_with_real_selected_chapter(task_session,monkeypatch):
    f=await context_fixture(task_session,monkeypatch,approved_chapter=99)
    await reject(task_session,f,'approval.context_arguments')


@pytest.mark.asyncio
@pytest.mark.parametrize('reference',['bad-version','missing-artifact','malformed','cross-project-artifact'])
async def test_invalid_real_reference_fails_before_handler(task_session,monkeypatch,reference):
    f=await context_fixture(task_session,monkeypatch,reference=reference)
    await reject(task_session,f,'context_refs')


@pytest.mark.asyncio
async def test_selected_resource_deleted_since_approval(task_session,monkeypatch):
    f=await context_fixture(task_session,monkeypatch)
    await task_session.delete(f.chapters[0]);await task_session.commit()
    await reject(task_session,f,'context_refs')


@pytest.mark.asyncio
async def test_mutable_run_refs_must_match_frozen_user_refs(task_session,monkeypatch):
    f=await context_fixture(task_session,monkeypatch)
    context=deepcopy(f.run.context_json);context['context_refs'][0]['chapter_number']=99;f.run.context_json=context
    await task_session.commit()
    await reject(task_session,f,'context_refs')


@pytest.mark.asyncio
@pytest.mark.parametrize('change',['digest','ref-digest','id','key','drop-locators','null-id','project','transaction','ref-payload'])
async def test_context_snapshot_damage_rejected(task_session,monkeypatch,change):
    f=await context_fixture(task_session,monkeypatch)
    field='context_snapshot'
    if change in ('id','key','drop-locators','null-id'):
        context=deepcopy(f.run.context_json)
        if change=='id':context['relational_context_snapshot_id']=str(uuid4())
        elif change=='key':context['relational_context_snapshot_key']=str(uuid4())
        elif change=='null-id':context['relational_context_snapshot_id']=None
        else:
            context.pop('relational_context_snapshot_id');context.pop('relational_context_snapshot_key')
        f.run.context_json=context
    else:
        # Corrupt stored facts below ORM append-only events to exercise READ-time verification.
        if change=='ref-digest':
            await task_session.execute(update(ContextSnapshotRef).where(ContextSnapshotRef.id==f.snapshot.refs[0].id).values(digest='f'*64))
        elif change=='ref-payload':
            await task_session.execute(update(ContextSnapshotRef).where(ContextSnapshotRef.id==f.snapshot.refs[0].id).values(payload_json={'kind':'chapter','project_id':f.run.project_id,'chapter_number':99}))
        else:
            values={'digest': 'f'*64} if change=='digest' else {'project_id':'other-project'} if change=='project' else {'transaction_id':str(uuid4())}
            await task_session.execute(update(ContextSnapshot).where(ContextSnapshot.id==f.snapshot.id).values(**values))
    await task_session.commit()
    await reject(task_session,f,field)

@pytest.mark.asyncio
@pytest.mark.parametrize('shape', ['different-row', 'missing-row', 'row-metadata', 'unsupported-schema', 'invalid-json'])
async def test_self_consistent_snapshot_must_match_user_reference_contract(task_session, monkeypatch, shape):
    f = await context_fixture(task_session, monkeypatch)
    runtime = AgentRuntimeService(task_session)
    chat = await runtime.get_session(f.run.session_id, f.run.user_id)
    user_refs = deepcopy(f.run.context_json['context_refs'])
    row_refs = deepcopy(user_refs)
    context_json = {'context_refs': user_refs}
    if shape == 'different-row':
        row_refs[0]['chapter_number'] = 99
    elif shape == 'missing-row':
        row_refs = []
    elif shape == 'row-metadata':
        row_refs[0]['ref_type'] = 'artifact'
    if shape == 'invalid-json':
        # Valid service-created fact, then corrupt/reseal context below immutable ORM events.
        context_json = {}
    snapshot = await AgentContextService(task_session).create_snapshot(
        run=f.run, session=chat, context_json=context_json, refs=row_refs,
        context_kind='replan_context', schema_version=2 if shape == 'unsupported-schema' else 1,
    )
    context = deepcopy(f.run.context_json)
    context['relational_context_snapshot_id'] = snapshot.id
    context['relational_context_snapshot_key'] = snapshot.snapshot_id
    f.run.context_json = context
    await task_session.commit()
    if shape == 'invalid-json':
        from app.services.agent_context_service import canonical_digest, context_snapshot_material
        material = context_snapshot_material(snapshot, snapshot.refs)
        material['context_json'] = []
        await task_session.execute(update(ContextSnapshot).where(ContextSnapshot.id == snapshot.id).values(context_json=[], digest=canonical_digest(material)))
        await task_session.commit()
    field = 'context_refs' if shape == 'invalid-json' else 'context_snapshot'
    await reject(task_session, f, field)


@pytest.mark.asyncio
async def test_approval_context_error_does_not_expose_reference_identifiers(task_session, monkeypatch):
    f = await context_fixture(task_session, monkeypatch)
    secret = 'PRIVATE-REFERENCE-SENTINEL-DO-NOT-ECHO'
    context = deepcopy(f.run.context_json)
    context['context_refs'][0]['project_id'] = secret
    f.run.context_json = context
    await task_session.commit()
    with pytest.raises(ApprovalRunContractError) as error:
        await execute(task_session, f)
    assert secret not in str(error.value)
    assert secret not in str(error.value.detail)
    assert error.value.field == 'context_refs'
    assert not f.calls


@pytest.mark.asyncio
@pytest.mark.parametrize('value', [True, '12'])
async def test_persisted_reference_numeric_fields_are_strict(task_session, monkeypatch, value):
    f = await context_fixture(task_session, monkeypatch)
    context = deepcopy(f.run.context_json)
    context['context_refs'][0]['chapter_number'] = value
    f.run.context_json = context
    await task_session.commit()
    await reject(task_session, f, 'context_refs')


@pytest.mark.asyncio
async def test_context_boundary_requires_real_session_even_without_locators():
    from app.agent.approval_context_contract import ApprovalContextContractError, validate_approval_context_contract
    run = SimpleNamespace(context_json={'capability_resolution': {}})
    with pytest.raises(ApprovalContextContractError) as error:
        await validate_approval_context_contract(session=None, run=run, approval=None, manifest=None, require_snapshot=True)
    assert error.value.field == 'context_snapshot'
