"""
US-006 端到端 harness：以 stubbed app 启动独立端口的 uvicorn 子进程。

原因：httpx 的 ASGITransport 会缓冲整个 StreamingResponse body，SSE 帧永远读不到。
要验证「SSE terminal event」，必须走真实 HTTP 长连接。

本模块在被 uvicorn 加载时先给 LLMService 打桩（本机无 OPENAI_API_KEY），
再导出 app，使整个 pipeline 可确定性跑通。
"""

import json
import os
from pathlib import Path

BACKEND_ROOT = Path("/run/csi/mount-root/nas/4079184d856ecc166ed19d4887083405/qwenpaw-data/xuanqiong-wenshu/backend")
REPO_ROOT = BACKEND_ROOT.parent
E2E_ENV = Path("/tmp/e2e_backend.env")


def load_env_file(path: Path):
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip()


load_env_file(E2E_ENV)
os.environ.setdefault("FILE_LOGGING_ENABLED", "false")

FIXED_CHAPTER_TEXT = (
    "第一章 山雨欲来\n\n"
    "林默站在青石阶上，望着远处翻涌的乌云。雨还没有落下，风却已经先一步穿过山谷，"
    "把他洗得发白的衣角掀起一角。他记得师父说过，山雨欲来的时候，最先变的不是天色，而是鸟鸣。\n\n"
    "此刻山谷里确实安静得异常。他握紧了手中的木匣，指节微微发白。"
)

import sys  # noqa: E402

sys.path.insert(0, str(REPO_ROOT))
os.chdir(BACKEND_ROOT)

from backend.app.services import llm_service as _llm_mod  # noqa: E402

_STUB_CALLS = {"text": 0, "json": 0, "embed": 0}


async def _fake_get_embedding(self, text, *, user_id=None, **kwargs):
    _STUB_CALLS["embed"] += 1
    return [0.0] * int(os.environ.get("EMBEDDING_MODEL_VECTOR_SIZE", "3072"))


async def _fake_get_llm_response(
    self, system_prompt, conversation_history, *, temperature=0.7, user_id=None,
    timeout=100.0, response_format=None, max_tokens=None, top_p=None,
    prompt_cache_key=None, allow_truncated_response=False, retry_same_model_once=True,
    **kwargs,
):
    _STUB_CALLS["text"] += 1
    blob = json.dumps(conversation_history, ensure_ascii=False)
    wants_prose = any(k in blob for k in ("正文", "章节", "写作", "续写", "草稿", "draft", "小说"))
    if wants_prose:
        return FIXED_CHAPTER_TEXT
    return json.dumps({}, ensure_ascii=False)


_llm_mod.LLMService.get_embedding = _fake_get_embedding
_llm_mod.LLMService.get_llm_response = _fake_get_llm_response

from backend.app.main import app  # noqa: E402


@app.get("/__e2e/stub_calls")
async def _stub_calls_endpoint():
    return _STUB_CALLS
