# AIMETA P=小说API_项目和章节管理|R=小说CRUD_章节管理|NR=不含内容生成|E=route:GET_POST_/api/novels/*|X=http|A=小说CRUD_章节|D=fastapi,sqlalchemy|S=db|RD=./README.ai
import json
import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Body, Depends, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.dependencies import get_current_user
from ...db.session import get_session
from ...schemas.novel import (
    Blueprint,
    BlueprintGenerationResponse,
    BlueprintPatch,
    Chapter as ChapterSchema,
    ConverseRequest,
    ConverseResponse,
    NovelProject as NovelProjectSchema,
    NovelProjectSummary,
    NovelSectionResponse,
    NovelSectionType,
)
from ...schemas.user import User as UserSchema, UserInDB
from ...services.export_service import ExportService
from ...services.import_service import ImportService
from ...services.llm_service import LLMService
from ...services.novel_service import NovelService
from ...services.prompt_service import PromptService
from ...utils.json_utils import remove_think_tags, sanitize_json_like_text, unwrap_markdown_json

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/novels", tags=["Novels"])

JSON_RESPONSE_INSTRUCTION = """
IMPORTANT: 你的回复必须是合法的 JSON 对象，并严格包含以下字段：
{
  "ai_message": "string",
  "ui_control": {
    "type": "single_choice | text_input",
    "options": [
      {"id": "option_1", "label": "string"}
    ],
    "placeholder": "string"
  },
  "conversation_state": {},
  "is_complete": false
}
不要输出额外的文本或解释。
"""


def _ensure_prompt(prompt: str | None, name: str) -> str:
    if not prompt:
        raise HTTPException(status_code=500, detail=f"未配置名为 {name} 的提示词，请联系管理员")
    return prompt


def _canonical_key(value: str) -> str:
    return "".join(ch for ch in str(value).strip().lower() if ch.isalnum() or ch == "_")


def _stringify_payload(value: Any, *, fallback: str = "") -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        labels = []
        for item in value:
            if isinstance(item, dict):
                label = str(item.get("label") or item.get("value") or item.get("id") or "").strip()
                if label:
                    labels.append(label)
            elif isinstance(item, str) and item.strip():
                labels.append(item.strip())
        if labels:
            return "；".join(labels)
    if isinstance(value, dict):
        for key in ("ai_message", "message", "content", "text", "value"):
            nested = value.get(key)
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
    return fallback.strip()


def _normalize_ui_control(raw_control: Any) -> Dict[str, Any]:
    default_placeholder = "请继续补充你的设定、冲突或写作方向。"
    if not isinstance(raw_control, dict):
        return {"type": "text_input", "placeholder": default_placeholder}

    normalized_control: Dict[str, Any] = {}
    control_type = str(raw_control.get("type") or "").strip().lower()
    raw_options = raw_control.get("options")
    options: List[Dict[str, str]] = []

    if isinstance(raw_options, list):
        for item in raw_options:
            if not isinstance(item, dict):
                continue
            option_id = str(item.get("id") or item.get("value") or "").strip()
            option_label = str(item.get("label") or item.get("value") or option_id).strip()
            if option_id and option_label:
                options.append({"id": option_id, "label": option_label})

    if control_type not in {"single_choice", "text_input"}:
        control_type = "single_choice" if options else "text_input"

    normalized_control["type"] = control_type
    if options and control_type == "single_choice":
        normalized_control["options"] = options

    placeholder = str(raw_control.get("placeholder") or "").strip()
    if placeholder:
        normalized_control["placeholder"] = placeholder
    elif control_type == "text_input":
        normalized_control["placeholder"] = default_placeholder

    return normalized_control


def _normalize_converse_response_payload(parsed: Any, raw_response: str) -> Dict[str, Any]:
    fallback_message = _stringify_payload(raw_response, fallback="我已经收到你的想法，请继续补充。")
    default_payload = {
        "ai_message": fallback_message,
        "ui_control": {"type": "text_input", "placeholder": "请继续补充你的设定、冲突或写作方向。"},
        "conversation_state": {},
        "is_complete": False,
    }
    if isinstance(parsed, str):
        default_payload["ai_message"] = parsed.strip() or fallback_message
        return default_payload
    if not isinstance(parsed, dict):
        return default_payload

    normalized_map = {_canonical_key(key): value for key, value in parsed.items()}

    ai_message_value = None
    for key in ("ai_message", "message", "assistant_message", "reply"):
        candidate = normalized_map.get(key)
        if candidate is not None:
            ai_message_value = candidate
            break
    ai_message = _stringify_payload(ai_message_value, fallback=fallback_message) or fallback_message

    ui_control_raw = normalized_map.get("ui_control") or normalized_map.get("control") or normalized_map.get("uicontrol")
    if ui_control_raw is None:
        ui_control_raw = {
            "type": normalized_map.get("type"),
            "options": normalized_map.get("options"),
            "placeholder": normalized_map.get("placeholder"),
        }
    ui_control = _normalize_ui_control(ui_control_raw)

    conversation_state = normalized_map.get("conversation_state")
    if not isinstance(conversation_state, dict):
        conversation_state = {}

    is_complete = bool(normalized_map.get("is_complete") or normalized_map.get("complete"))
    ready_for_blueprint = normalized_map.get("ready_for_blueprint")

    normalized_payload = {
        "ai_message": ai_message,
        "ui_control": ui_control,
        "conversation_state": conversation_state,
        "is_complete": is_complete,
    }
    if ready_for_blueprint is not None:
        normalized_payload["ready_for_blueprint"] = bool(ready_for_blueprint)
    return normalized_payload


async def _polish_chapter_outline_quality(
    *,
    llm_service: LLMService,
    blueprint_data: Dict[str, Any],
    user_id: int,
) -> Dict[str, Any]:
    chapter_outline = blueprint_data.get("chapter_outline")
    if not isinstance(chapter_outline, list) or not chapter_outline:
        return blueprint_data

    existing_lines: List[str] = []
    for item in chapter_outline:
        if not isinstance(item, dict):
            continue
        chapter_no = item.get("chapter_number")
        title = str(item.get("title") or "").strip()
        summary = str(item.get("summary") or "").strip()
        if chapter_no is None:
            continue
        existing_lines.append(f"第{chapter_no}章｜{title}｜{summary}")

    if not existing_lines:
        return blueprint_data

    one_sentence_summary = str(blueprint_data.get("one_sentence_summary") or "").strip()
    full_synopsis = str(blueprint_data.get("full_synopsis") or "").strip()
    characters = blueprint_data.get("characters") or []
    relationships = blueprint_data.get("relationships") or []

    polish_system_prompt = (
        "你是资深长篇网文总策划，擅长把粗糙大纲扩成可支撑长篇连载的高密度章节工程图。"
        "你只输出 JSON。"
    )
    polish_user_prompt = f"""
[作品定位]
一句话梗概：{one_sentence_summary or "暂无"}
长梗概：{full_synopsis or "暂无"}

[主要角色]
{json.dumps(characters, ensure_ascii=False)}

[主要关系]
{json.dumps(relationships, ensure_ascii=False)}

[现有章节大纲]
{chr(10).join(existing_lines)}

[改写目标]
1. 不改章节号，保持章节顺序与主线连续。
2. 每章 summary 必须有明确冲突、人物目标/阻碍、关键转折、章末钩子。
3. summary 长度控制在 180-360 字，避免空泛描述。
4. 补全每章承担的长线职责，保证前承后接，不允许只写“发生了什么”，还要写“推进了什么”。
5. 强制输出以下字段：narrative_phase、chapter_role、suspense_hook、emotional_progression、character_focus、conflict_escalation、continuity_notes、foreshadowing。
6. 语言要具体、可直接落地写作，避免模板腔。

[输出格式]
只输出 JSON：
{{
  "chapters": [
    {{
      "chapter_number": 1,
      "title": "标题",
      "summary": "摘要",
      "narrative_phase": "章节所处叙事阶段",
      "chapter_role": "本章在全书中的职责",
      "suspense_hook": "章末钩子",
      "emotional_progression": "情绪如何变化",
      "character_focus": ["角色A", "角色B"],
      "conflict_escalation": ["升级点1", "升级点2"],
      "continuity_notes": ["承接上一章的点", "为下一章预埋的点"],
      "foreshadowing": {{
        "plant": ["埋下的伏笔"],
        "payoff": ["本章回收的伏笔"]
      }}
    }}
  ]
}}
"""

    try:
        polished_raw = await llm_service.get_llm_response(
            system_prompt=polish_system_prompt,
            conversation_history=[{"role": "user", "content": polish_user_prompt}],
            temperature=0.35,
            user_id=user_id,
            timeout=360.0,
            response_format=None,
            allow_truncated_response=True,
        )
        polished_cleaned = remove_think_tags(polished_raw)
        polished_normalized = unwrap_markdown_json(polished_cleaned)
        polished_data = json.loads(polished_normalized)
    except Exception as exc:
        logger.warning("蓝图章节大纲润色失败，保留原始结果: %s", exc)
        return blueprint_data

    polished_items = []
    if isinstance(polished_data, dict):
        raw_items = polished_data.get("chapters", [])
        if isinstance(raw_items, list):
            polished_items = raw_items
    elif isinstance(polished_data, list):
        polished_items = polished_data

    polished_map: Dict[int, Dict[str, Any]] = {}
    for item in polished_items:
        if not isinstance(item, dict):
            continue
        try:
            chapter_no = int(item.get("chapter_number"))
        except (TypeError, ValueError):
            continue
        title = str(item.get("title") or "").strip()
        summary = str(item.get("summary") or "").strip()
        if not title or not summary or len("".join(summary.split())) < 150:
            continue
        polished_map[chapter_no] = item

    if not polished_map:
        return blueprint_data

    merged_outline: List[Dict[str, Any]] = []
    for item in chapter_outline:
        if not isinstance(item, dict):
            continue
        chapter_no_raw = item.get("chapter_number")
        try:
            chapter_no = int(chapter_no_raw)
        except (TypeError, ValueError):
            merged_outline.append(item)
            continue
        if chapter_no in polished_map:
            polished = dict(polished_map[chapter_no])
            merged_outline.append(
                {
                    **item,
                    **{k: v for k, v in polished.items() if k != "chapter_number" and v is not None},
                }
            )
        else:
            merged_outline.append(item)

    blueprint_data["chapter_outline"] = merged_outline
    return blueprint_data


@router.post("", response_model=NovelProjectSchema, status_code=status.HTTP_201_CREATED)
async def create_novel(
    title: str = Body(...),
    initial_prompt: str = Body(...),
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    """为当前用户创建一个新的小说项目。"""
    novel_service = NovelService(session)
    project = await novel_service.create_project(current_user.id, title, initial_prompt)
    logger.info("用户 %s 创建项目 %s", current_user.id, project.id)
    return await novel_service.get_project_schema(project.id, current_user.id)


@router.post("/import", response_model=Dict[str, str], status_code=status.HTTP_201_CREATED)
async def import_novel(
    file: UploadFile,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> Dict[str, str]:
    """上传并导入小说文件。"""
    import_service = ImportService(session)
    project_id = await import_service.import_novel_from_file(current_user.id, file)
    logger.info("用户 %s 导入项目 %s", current_user.id, project_id)
    return {"id": project_id}


@router.get("", response_model=List[NovelProjectSummary])
async def list_novels(
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> List[NovelProjectSummary]:
    """列出用户的全部小说项目摘要信息。"""
    novel_service = NovelService(session)
    projects = await novel_service.list_projects_for_user(current_user.id)
    logger.info("用户 %s 获取项目列表，共 %s 个", current_user.id, len(projects))
    return projects


@router.get("/current-user", response_model=UserSchema)
async def get_current_user_profile(
    current_user: UserInDB = Depends(get_current_user),
) -> UserSchema:
    """返回当前运行态绑定的用户信息，供前端初始化用户态与诊断单用户绑定。"""
    logger.info("返回当前运行态用户：id=%s username=%s is_admin=%s", current_user.id, current_user.username, current_user.is_admin)
    return UserSchema.model_validate(current_user)


@router.get("/{project_id}", response_model=NovelProjectSchema)
async def get_novel(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    novel_service = NovelService(session)
    logger.info("用户 %s 查询项目 %s", current_user.id, project_id)
    return await novel_service.get_project_schema(project_id, current_user.id)


@router.get("/{project_id}/sections/{section}", response_model=NovelSectionResponse)
async def get_novel_section(
    project_id: str,
    section: NovelSectionType,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelSectionResponse:
    novel_service = NovelService(session)
    logger.info("用户 %s 获取项目 %s 的 %s 区段", current_user.id, project_id, section)
    return await novel_service.get_section_data(project_id, current_user.id, section)


@router.get("/{project_id}/chapters/{chapter_number}", response_model=ChapterSchema)
async def get_chapter(
    project_id: str,
    chapter_number: int,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> ChapterSchema:
    novel_service = NovelService(session)
    logger.info("用户 %s 获取项目 %s 第 %s 章", current_user.id, project_id, chapter_number)
    return await novel_service.get_chapter_schema(project_id, current_user.id, chapter_number)


@router.get("/{project_id}/export/txt")
async def export_novel_as_txt(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
):
    """导出小说为 TXT 格式"""
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    export_service = ExportService(session)
    content = await export_service.export_novel_as_txt(project_id)

    from fastapi.responses import Response
    filename = f"novel_{project_id}_{datetime.now().strftime('%Y%m%d')}.txt"
    return Response(
        content=content,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/{project_id}/export/docx")
async def export_novel_as_docx(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
):
    """导出小说为 DOCX 格式"""
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    export_service = ExportService(session)
    content = await export_service.export_novel_as_docx(project_id)

    from fastapi.responses import Response
    filename = f"novel_{project_id}_{datetime.now().strftime('%Y%m%d')}.docx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


from datetime import datetime


@router.delete("", status_code=status.HTTP_200_OK)
async def delete_novels(
    project_ids: List[str] = Body(...),
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> Dict[str, str]:
    novel_service = NovelService(session)
    await novel_service.delete_projects(project_ids, current_user.id)
    logger.info("用户 %s 删除项目 %s", current_user.id, project_ids)
    return {"status": "success", "message": f"成功删除 {len(project_ids)} 个项目"}


@router.post("/{project_id}/concept/converse", response_model=ConverseResponse)
async def converse_with_concept(
    project_id: str,
    request: ConverseRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> ConverseResponse:
    """与概念设计师（LLM）进行对话，引导蓝图筹备。"""
    novel_service = NovelService(session)
    prompt_service = PromptService(session)
    llm_service = LLMService(session)

    project = await novel_service.ensure_project_owner(project_id, current_user.id)

    history_records = await novel_service.list_conversations(project_id)
    logger.info(
        "项目 %s 概念对话请求，用户 %s，历史记录 %s 条",
        project_id,
        current_user.id,
        len(history_records),
    )
    conversation_history = [
        {"role": record.role, "content": record.content}
        for record in history_records
    ]
    user_content = json.dumps(request.user_input, ensure_ascii=False)
    conversation_history.append({"role": "user", "content": user_content})

    system_prompt = _ensure_prompt(await prompt_service.get_prompt("concept"), "concept")
    system_prompt = f"{system_prompt}\n{JSON_RESPONSE_INSTRUCTION}"

    llm_response = await llm_service.get_llm_response(
        system_prompt=system_prompt,
        conversation_history=conversation_history,
        temperature=0.8,
        user_id=current_user.id,
        timeout=240.0,
    )
    llm_response = remove_think_tags(llm_response)

    try:
        normalized = unwrap_markdown_json(llm_response)
        sanitized = sanitize_json_like_text(normalized)
        parsed: Any = json.loads(sanitized)
    except json.JSONDecodeError as exc:
        logger.warning(
            "Concept converse returned non-standard JSON, fallback to normalized text response: project_id=%s user_id=%s error=%s",
            project_id,
            current_user.id,
            exc,
        )
        normalized = llm_response
        parsed = llm_response

    normalized_payload = _normalize_converse_response_payload(parsed, llm_response)

    await novel_service.append_conversation(project_id, "user", user_content)
    await novel_service.append_conversation(
        project_id,
        "assistant",
        json.dumps(normalized_payload, ensure_ascii=False),
    )

    logger.info("项目 %s 概念对话完成，is_complete=%s", project_id, normalized_payload.get("is_complete"))

    if normalized_payload.get("is_complete"):
        normalized_payload["ready_for_blueprint"] = True

    normalized_payload.setdefault("conversation_state", normalized_payload.get("conversation_state", {}))
    return ConverseResponse(**normalized_payload)


@router.post("/{project_id}/blueprint/generate", response_model=BlueprintGenerationResponse)
async def generate_blueprint(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> BlueprintGenerationResponse:
    """根据完整对话生成可执行的小说蓝图。"""
    novel_service = NovelService(session)
    prompt_service = PromptService(session)
    llm_service = LLMService(session)

    project = await novel_service.ensure_project_owner(project_id, current_user.id)
    logger.info("项目 %s 开始生成蓝图", project_id)

    history_records = await novel_service.list_conversations(project_id)
    if not history_records:
        logger.warning("项目 %s 缺少对话历史，无法生成蓝图", project_id)
        raise HTTPException(status_code=400, detail="缺少对话历史，请先完成概念对话后再生成蓝图")

    formatted_history: List[Dict[str, str]] = []
    structured_dialogue: List[Dict[str, Any]] = []
    for record in history_records:
        role = record.role
        content = record.content
        if not role or not content:
            continue
        try:
            normalized = unwrap_markdown_json(content)
            data = json.loads(normalized)
            if role == "user":
                user_value = data.get("value", data)
                if isinstance(user_value, str):
                    formatted_history.append({"role": "user", "content": user_value})
                structured_dialogue.append({
                    "role": "user",
                    "value": user_value,
                    "raw": data,
                })
            elif role == "assistant":
                ai_message = data.get("ai_message") if isinstance(data, dict) else None
                if ai_message:
                    formatted_history.append({"role": "assistant", "content": ai_message})
                structured_dialogue.append({
                    "role": "assistant",
                    "ai_message": ai_message,
                    "ui_control": data.get("ui_control") if isinstance(data, dict) else None,
                    "conversation_state": data.get("conversation_state") if isinstance(data, dict) else None,
                    "ready_for_blueprint": data.get("ready_for_blueprint") if isinstance(data, dict) else None,
                    "raw": data,
                })
        except (json.JSONDecodeError, AttributeError):
            continue

    if not formatted_history:
        logger.warning("项目 %s 对话历史格式异常，无法提取有效内容", project_id)
        raise HTTPException(
            status_code=400,
            detail="无法从历史对话中提取有效内容，请检查对话历史格式或重新进行概念对话"
        )

    system_prompt = _ensure_prompt(await prompt_service.get_prompt("screenwriting"), "screenwriting")
    blueprint_context = {
        "conversation_transcript": formatted_history,
        "structured_dialogue": structured_dialogue,
        "requirements": {
            "must_build_longform_architecture": True,
            "must_output_detailed_chapter_outline": True,
            "must_include_multi_arc_progression": True,
        },
    }
    blueprint_raw = await llm_service.get_llm_response(
        system_prompt=system_prompt,
        conversation_history=[
            {
                "role": "user",
                "content": json.dumps(blueprint_context, ensure_ascii=False, indent=2),
            }
        ],
        temperature=0.25,
        user_id=current_user.id,
        timeout=480.0,
    )
    blueprint_raw = remove_think_tags(blueprint_raw)

    blueprint_normalized = unwrap_markdown_json(blueprint_raw)
    blueprint_sanitized = sanitize_json_like_text(blueprint_normalized)
    try:
        blueprint_data = json.loads(blueprint_sanitized)
    except json.JSONDecodeError as exc:
        logger.error(
            "项目 %s 蓝图生成 JSON 解析失败: %s\n原始响应: %s\n标准化后: %s\n清洗后: %s",
            project_id,
            exc,
            blueprint_raw[:500],
            blueprint_normalized[:500],
            blueprint_sanitized[:500],
        )
        raise HTTPException(
            status_code=500,
            detail=f"蓝图生成失败，AI 返回的内容格式不正确。请重试或联系管理员。错误详情: {str(exc)}"
        ) from exc

    blueprint_data = await _polish_chapter_outline_quality(
        llm_service=llm_service,
        blueprint_data=blueprint_data,
        user_id=current_user.id,
    )

    blueprint = Blueprint(**blueprint_data)
    await novel_service.replace_blueprint(project_id, blueprint)
    if blueprint.title:
        project.title = blueprint.title
        project.status = "blueprint_ready"
        await session.commit()
        logger.info("项目 %s 更新标题为 %s，并标记为 blueprint_ready", project_id, blueprint.title)

    ai_message = (
        "太棒了！我已经根据我们的对话整理出完整的小说蓝图。请确认是否进入写作阶段，或提出修改意见。"
    )
    return BlueprintGenerationResponse(blueprint=blueprint, ai_message=ai_message)


@router.post("/{project_id}/blueprint/save", response_model=NovelProjectSchema)
async def save_blueprint(
    project_id: str,
    blueprint_data: Blueprint | None = Body(None),
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    """保存蓝图信息，可用于手动覆盖自动生成结果。"""
    novel_service = NovelService(session)
    project = await novel_service.ensure_project_owner(project_id, current_user.id)

    if blueprint_data:
        await novel_service.replace_blueprint(project_id, blueprint_data)
        if blueprint_data.title:
            project.title = blueprint_data.title
            await session.commit()
        logger.info("项目 %s 手动保存蓝图", project_id)
    else:
        logger.warning("项目 %s 保存蓝图时未提供蓝图数据", project_id)
        raise HTTPException(status_code=400, detail="缺少蓝图数据，请提供有效的蓝图内容")

    return await novel_service.get_project_schema(project_id, current_user.id)


@router.patch("/{project_id}/blueprint", response_model=NovelProjectSchema)
async def patch_blueprint(
    project_id: str,
    payload: BlueprintPatch,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    """局部更新蓝图字段，对世界观或角色做微调。"""
    novel_service = NovelService(session)
    project = await novel_service.ensure_project_owner(project_id, current_user.id)

    update_data = payload.model_dump(exclude_unset=True)
    await novel_service.patch_blueprint(project_id, update_data)
    logger.info("项目 %s 局部更新蓝图字段：%s", project_id, list(update_data.keys()))
    return await novel_service.get_project_schema(project_id, current_user.id)
