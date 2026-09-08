"""F5 composition tests: real Runtime, approval route and default registry."""
from copy import deepcopy

import pytest
from sqlalchemy import select

from app.agent.test_approval_context_contract import context_fixture, execute, reject
from app.models.agent_catalog import AgentCatalogRelease
from app.services.agent_execution_service import AgentExecutionService


@pytest.mark.asyncio
@pytest.mark.parametrize('part', ['catalog-tool', 'catalog-provider', 'resolver-request', 'resolver-tools', 'resolver-exclusions', 'relational-request', 'relational-scope', 'relational-exclusions'])
async def test_approval_route_rejects_changed_digest_material_before_handler(task_session, monkeypatch, part):
    f = await context_fixture(task_session, monkeypatch, reference='none')
    snapshot = await AgentExecutionService(task_session).get_run_snapshot(f.run.id)
    catalog = (await task_session.execute(select(AgentCatalogRelease).where(AgentCatalogRelease.id == snapshot.catalog_release_id))).scalar_one()
    context = deepcopy(f.run.context_json)
    if part.startswith('catalog-'):
        release = context['catalog_release']
        if part == 'catalog-tool': release['tools'][0]['description'] += ' changed-but-old-digest'
        else: release['providers'][0]['source'] = 'changed-but-old-digest'
        catalog.manifest_json = deepcopy(release)
        field = 'catalog_release.digest'
    elif part.startswith('resolver-'):
        resolution = context['capability_resolution']
        if part == 'resolver-request': resolution['request']['include_confirmation_required'] = False
        elif part == 'resolver-tools': resolution['tools'] = []
        else: resolution['exclusions'] = []
        field = 'capability_resolution.digest'
    elif part == 'relational-request':
        snapshot.request_json = {**snapshot.request_json, 'include_confirmation_required': False}
        field = 'snapshot.request_json'
    elif part == 'relational-scope':
        snapshot.resolved_scope_json = {**snapshot.resolved_scope_json, 'tool_names': []}
        field = 'snapshot.resolved_scope_json.tool_names'
    else:
        snapshot.exclusions_json = []
        field = 'snapshot.exclusions_json'
    f.run.context_json = context
    await task_session.commit()
    await reject(task_session, f, field)
