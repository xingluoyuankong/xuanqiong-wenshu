from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.agent.write_executor import _ARTIFACT_ROOT, build_rewrite_instructions, diff_artifact_with_chapter_version, diff_artifacts, list_artifact_quality_blockers, list_artifact_rewrite_instructions
from app.api.routers.agent import diff_agent_artifact
from app.models import Chapter, ChapterVersion, NovelProject, User
from app.services.agent_runtime import AgentRuntimeService


async def _user(session, user_id: int, username: str) -> User:
    user = User(id=user_id, username=username, email=username + '@example.com', hashed_password='x', is_active=True)
    session.add(user)
    await session.flush()
    return user


@pytest.mark.asyncio
async def test_artifact_diff_is_line_level_and_project_scoped(task_session):
    owner = await _user(task_session, 1301, 'artifact-diff-owner')
    other = await _user(task_session, 1302, 'artifact-diff-other')
    task_session.add(NovelProject(id='artifact-diff-project', user_id=owner.id, title='Artifact Diff'))
    task_session.add(NovelProject(id='artifact-diff-other-project', user_id=other.id, title='Artifact Diff Other'))
    await task_session.flush()

    runtime = AgentRuntimeService(task_session)
    agent_session = await runtime.create_session(user_id=owner.id, project_id='artifact-diff-project')
    run = await runtime.create_run(session_id=agent_session.id, user_id=owner.id, project_id='artifact-diff-project')
    keys = [str(uuid4()) + '.md', str(uuid4()) + '.md']
    contents = ['第一行\n保留行\n旧行\n', '第一行\n保留行\n新行\n增加行\n']
    artifacts = []
    try:
        for key, content in zip(keys, contents):
            _ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
            (_ARTIFACT_ROOT / key).write_text(content, encoding='utf-8')
            artifacts.append(await runtime.add_artifact(
                run_id=run.id,
                user_id=owner.id,
                project_id='artifact-diff-project',
                kind='chapter_candidate',
                uri='agent-artifact://' + key,
                sha256=hashlib.sha256(content.encode('utf-8')).hexdigest(),
                metadata={'storage_key': key, 'status': 'candidate'},
            ))
        result = await diff_artifacts(artifact_id=artifacts[0].id, against_artifact_id=artifacts[1].id, user_id=owner.id, session=task_session)
        assert result['summary']['unchanged'] == 2
        assert result['summary']['modified'] == 1
        assert result['summary']['added'] == 1
        assert any(item['change_type'] == 'modified' and item['patched_line'] == '新行' for item in result['diff_lines'])
        api_result = await diff_agent_artifact(
            artifact_id=artifacts[0].id,
            against_artifact_id=artifacts[1].id,
            current_user=SimpleNamespace(id=owner.id),
            session=task_session,
        )
        assert api_result.artifact_id == artifacts[0].id
        assert api_result.against_artifact_id == artifacts[1].id
        with pytest.raises(Exception):
            await diff_artifacts(artifact_id=artifacts[0].id, against_artifact_id=artifacts[1].id, user_id=other.id, session=task_session)
    finally:
        for key in keys:
            (_ARTIFACT_ROOT / key).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_artifact_diff_against_chapter_version_returns_writing_desk_deep_link(task_session):
    owner = await _user(task_session, 1303, 'artifact-version-owner')
    task_session.add(NovelProject(id='artifact-version-project', user_id=owner.id, title='Artifact Version'))
    chapter = Chapter(project_id='artifact-version-project', chapter_number=7, status='successful', word_count=6)
    task_session.add(chapter)
    await task_session.flush()
    version = ChapterVersion(chapter_id=chapter.id, content='基准行\n新内容\n增加行\n', status='selected')
    task_session.add(version)
    await task_session.flush()
    key = str(uuid4()) + '.md'
    content = '基准行\n旧内容\n'
    try:
        _ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
        (_ARTIFACT_ROOT / key).write_text(content, encoding='utf-8')
        runtime = AgentRuntimeService(task_session)
        agent_session = await runtime.create_session(user_id=owner.id, project_id='artifact-version-project')
        run = await runtime.create_run(session_id=agent_session.id, user_id=owner.id, project_id='artifact-version-project')
        artifact = await runtime.add_artifact(run_id=run.id, user_id=owner.id, project_id='artifact-version-project', kind='chapter_candidate', uri='agent-artifact://' + key, sha256=hashlib.sha256(content.encode('utf-8')).hexdigest(), metadata={'storage_key': key, 'chapter_number': 7, 'status': 'candidate'})
        result = await diff_artifact_with_chapter_version(artifact_id=artifact.id, project_id='artifact-version-project', chapter_number=7, version_id=version.id, user_id=owner.id, session=task_session)
        assert result['version_id'] == version.id
        assert result['summary']['modified'] == 1
        assert result['summary']['added'] == 1
        assert result['deep_link'] == '/novel/artifact-version-project?chapter=7&version_id=' + str(version.id) + '&focus=version'
    finally:
        (_ARTIFACT_ROOT / key).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_quality_blocker_projection_locates_snippet(task_session):
    owner = await _user(task_session, 1304, 'blocker-owner')
    task_session.add(NovelProject(id='blocker-project', user_id=owner.id, title='Blocker'))
    await task_session.flush()
    content = '开场内容\n需要修复的句子\n结尾内容\n'
    key = str(uuid4()) + '.md'
    try:
        _ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
        (_ARTIFACT_ROOT / key).write_text(content, encoding='utf-8')
        runtime = AgentRuntimeService(task_session)
        agent_session = await runtime.create_session(user_id=owner.id, project_id='blocker-project')
        run = await runtime.create_run(session_id=agent_session.id, user_id=owner.id, project_id='blocker-project')
        artifact = await runtime.add_artifact(run_id=run.id, user_id=owner.id, project_id='blocker-project', kind='chapter_candidate', uri='agent-artifact://' + key, sha256=hashlib.sha256(content.encode('utf-8')).hexdigest(), metadata={'storage_key': key, 'chapter_number': 2, 'status': 'candidate', 'quality_gate': {'blockers': [{'code': 'dialogue_does_not_change_state', 'message': '对话没有改变状态', 'source': 'story_progression_guard', 'snippet': '需要修复的句子'}]}})
        rows = await list_artifact_quality_blockers(artifact_id=artifact.id, user_id=owner.id, session=task_session)
        assert len(rows) == 1
        assert rows[0]['anchor_status'] == 'located'
        assert rows[0]['start_char'] is not None
        assert rows[0]['end_char'] == rows[0]['start_char'] + len('需要修复的句子')
        assert rows[0]['deep_link'] == '/novel/blocker-project?chapter=2&focus=quality-blocker'
    finally:
        (_ARTIFACT_ROOT / key).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_quality_blocker_projection_builds_safe_rewrite_instruction(task_session):
    owner = await _user(task_session, 1305, 'rewrite-instruction-owner')
    task_session.add(NovelProject(id='rewrite-instruction-project', user_id=owner.id, title='Rewrite Instructions'))
    await task_session.flush()
    content = '开场内容\n需要修复的句子\n结尾内容\n'
    key = str(uuid4()) + '.md'
    try:
        _ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
        (_ARTIFACT_ROOT / key).write_text(content, encoding='utf-8')
        runtime = AgentRuntimeService(task_session)
        agent_session = await runtime.create_session(user_id=owner.id, project_id='rewrite-instruction-project')
        run = await runtime.create_run(session_id=agent_session.id, user_id=owner.id, project_id='rewrite-instruction-project')
        artifact = await runtime.add_artifact(
            run_id=run.id, user_id=owner.id, project_id='rewrite-instruction-project',
            kind='chapter_candidate', uri='agent-artifact://' + key,
            sha256=hashlib.sha256(content.encode('utf-8')).hexdigest(),
            metadata={'storage_key': key, 'chapter_number': 2, 'source_version_id': 7, 'status': 'candidate', 'quality_gate': {'blockers': [{'code': 'dialogue_does_not_change_state', 'message': '对话没有改变状态', 'source': 'story_progression_guard', 'snippet': '需要修复的句子'}]}},
        )
        rows = await list_artifact_rewrite_instructions(artifact_id=artifact.id, user_id=owner.id, session=task_session)
        assert len(rows) == 1
        assert rows[0]['anchor_status'] == 'located'
        assert rows[0]['source_version_id'] == 7
        assert 'dialogue_does_not_change_state' in rows[0]['instruction']
        assert rows[0]['rewrite_arguments']['source_version_id'] == 7
        direct = build_rewrite_instructions([{'code': 'x', 'message': '无锚点', 'source': 'test', 'anchor_status': 'unavailable'}], artifact_id=artifact.id, project_id=artifact.project_id, chapter_number=2, source_version_id=None)
        assert '未能安全定位' in direct[0]['instruction']
    finally:
        (_ARTIFACT_ROOT / key).unlink(missing_ok=True)
