from __future__ import annotations

import json

from app.agent.runner import _tool_context
from app.agent.tool_result_digest import build_tool_result_digests


def test_tool_result_digest_retains_structured_findings_and_redacts_hidden_or_prose_fields():
    results = [
        {
            "tool_name": "quality.inspect",
            "result": {
                "score": 91,
                "summary": "章节冲突已定位",
                "content": "不应进入后续模型上下文的完整章节正文",
                "reasoning": "hidden",
                "nested": {"api_key": "secret", "blocker_count": 2},
            },
        }
    ]

    digests = build_tool_result_digests(results)

    assert digests == [
        {
            "tool_name": "quality.inspect",
            "result_keys": ["content", "nested", "reasoning", "score", "summary"],
            "summary": {
                "score": 91,
                "summary": "章节冲突已定位",
                "content": "[omitted-prose]",
                "nested": {"blocker_count": 2},
            },
        }
    ]


def test_runner_tool_context_uses_digest_not_only_keys_and_stays_bounded():
    results = [
        {
            "tool_name": "chapter.inspect",
            "result": {
                "quality_score": 88,
                "summary": "人物动机存在跳跃",
                "chapter_content": "x" * 10000,
                "provider_secret": "never-visible",
            },
        }
    ]

    context = _tool_context(results)
    payload = json.loads(context)

    assert payload[0]["summary"]["quality_score"] == 88
    assert payload[0]["summary"]["summary"] == "人物动机存在跳跃"
    assert payload[0]["summary"]["chapter_content"] == "[omitted-prose]"
    assert "provider_secret" not in payload[0]["summary"]
    assert len(context) <= 6000


def test_tool_result_digest_total_context_is_bounded_by_dropping_tail_entries():
    results = [
        {"tool_name": f"tool-{index}", "result": {"summary": "x" * 360}}
        for index in range(40)
    ]

    digests = build_tool_result_digests(results)

    assert len(json.dumps(digests, ensure_ascii=False, separators=(",", ":"))) <= 6000
    assert len(digests) < len(results)
