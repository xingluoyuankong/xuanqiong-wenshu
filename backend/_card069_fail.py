from pathlib import Path
p=Path(r'D:\小说写作\xuanqiong-wenshu\backend\app\agent\test_execution_facts.py')
s=p.read_text(encoding='utf-8')
needle='''@pytest.mark.asyncio\nasync def test_execution_facts_are_scoped_to_the_run_owner(task_session):\n'''
test=r'''@pytest.mark.asyncio
async def test_provider_usage_summary_aggregates_attempt_outcomes_without_raw_output(task_session):
    user = User(id=6404, username='provider-summary-owner', email='provider-summary-owner@example.com', hashed_password='x', is_active=True)
    task_session.add(user)
    await task_session.flush()
    runtime = AgentRuntimeService(task_session)
    agent_session = await runtime.create_session(user_id=user.id)
    run = await runtime.create_run(session_id=agent_session.id, user_id=user.id)
    run.context_json = {
        'response_provider_attempts': {
            'provider_attempts': [
                {'attempt': 1, 'status': 'failed', 'error_category': 'TIMEOUT', 'first_token_at': '2026-09-02T10:00:00Z', 'output_digest': 'a' * 64},
                {'attempt': 2, 'status': 'failed', 'error_category': 'RATE_LIMIT', 'fallback_from_attempt': 1},
                {'attempt': 3, 'status': 'succeeded', 'first_token_at': '2026-09-02T10:01:00Z', 'output_digest': 'b' * 64},
            ],
            'selected_provider_attempt': 3,
            'fallback_used': True,
        },
        'planner_provider_attempts': {
            'provider_attempts': [{'attempt': 1, 'status': 'succeeded'}],
            'selected_provider_attempt': 1,
            'fallback_used': False,
        },
    }
    await task_session.commit()

    from app.agent.execution_facts import AgentExecutionFactService
    summary = await AgentExecutionFactService(task_session).provider_usage_summary(run_id=run.id, user_id=user.id)

    assert summary['total_attempts'] == 4
    assert summary['succeeded_attempts'] == 2
    assert summary['failed_attempts'] == 2
    assert summary['fallback_attempts'] == 1
    assert summary['first_token_attempts'] == 2
    assert summary['digest_attempts'] == 2
    assert summary['last_error_category'] == 'RATE_LIMIT'
    assert summary['selected_attempts'] == 2
    assert 'output' not in str(summary).lower()


'''
assert needle in s
p.write_text(s.replace(needle,test+needle,1),encoding='utf-8')
