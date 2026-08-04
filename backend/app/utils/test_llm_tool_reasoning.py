# -*- coding: utf-8 -*-
from app.utils.llm_tool import LLMClient


class _Msg:
    def __init__(self, content=None, reasoning_content=None, reasoning=None):
        self.content = content
        self.reasoning_content = reasoning_content
        self.reasoning = reasoning


def test_extract_message_prefers_content_over_reasoning():
    msg = _Msg(content="正文答案", reasoning_content="长推理过程")
    assert LLMClient._extract_message_text(msg, prefer_reasoning_fallback=True) == "正文答案"


def test_extract_message_falls_back_to_reasoning_when_content_empty():
    msg = _Msg(content="", reasoning_content="最终应输出的答案")
    assert LLMClient._extract_message_text(msg, prefer_reasoning_fallback=True) == "最终应输出的答案"


def test_extract_message_stream_mode_does_not_fallback_to_reasoning():
    msg = _Msg(content=None, reasoning_content="cot only")
    assert LLMClient._extract_message_text(msg, prefer_reasoning_fallback=False) == ""


def test_extract_message_supports_dict_payload():
    payload = {"content": "", "reasoning_content": "dict-answer"}
    assert LLMClient._extract_message_text(payload, prefer_reasoning_fallback=True) == "dict-answer"


def test_stream_parts_keep_reasoning_separate_for_service_aggregation():
    # stream path yields both fields; service may fallback after full stream
    delta = _Msg(content="", reasoning_content="流式推理片段")
    assert LLMClient._extract_message_text(delta, prefer_reasoning_fallback=False) == ""
    assert LLMClient._extract_reasoning_text(delta) == "流式推理片段"
    # non-stream path still fails closed to reasoning when content empty
    assert LLMClient._extract_message_text(delta, prefer_reasoning_fallback=True) == "流式推理片段"
