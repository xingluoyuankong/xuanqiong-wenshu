# AIMETA P=章节扩写服务_字数不足自动扩写|R=字数检测_扩写生成|NR=不含生成逻辑|E=EnrichmentService|X=internal|A=扩写_字数控制|D=llm_service|S=none|RD=./README.ai
"""
章节扩写服务 (EnrichmentService)

融合自 AI_NovelGenerator 的 enrich_chapter_text 设计，提供：
1. 字数检测：检查是否低于目标字数的70%
2. 智能扩写：加戏不加线（只扩写感官、对话潜台词、余波Sequel，不推进主线）
3. 质量控制：确保扩写后的内容与原文风格一致

这对起点风格的网文很实用，可以稳定保持每章2k~4k字。
"""
import logging
import re
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

from sqlalchemy.orm import Session

from .generation_call_service import GenerationCallPolicy, call_generation_text
from .llm_service import LLMService
from ..utils.json_utils import remove_think_tags

logger = logging.getLogger(__name__)


@dataclass
class EnrichmentResult:
    """扩写结果"""
    original_word_count: int
    enriched_word_count: int
    enriched_content: str
    enrichment_ratio: float  # 扩写比例
    enrichment_type: str  # detail/dialogue/sequel


# ==================== 提示词模板 ====================

ENRICH_CHAPTER_PROMPT = """\
以下章节文本较短，请在保持剧情连贯的前提下进行扩写，使其更充实。

## 原始内容：
{chapter_text}

## 目标字数：{target_word_count}字（当前约{current_word_count}字，仍需补足约{needed_word_count}字）

## 本次长度要求（务必遵守）：
- 最终全文尽量控制在 {target_word_count_floor}~{target_word_count_ceiling} 字之间，优先贴近 {target_word_count} 字
- 不要为了凑字数整章重写，也不要只在开头或结尾硬塞大段描写
- 建议采用：{expansion_plan}

## 质量硬红线（新增内容必须遵守）：
- 新增篇幅只能主要落在：行动回合、对话攻防、因果后果、短余波决断。
- 禁止把“感官/环境/心理描写”当作独立扩写材料；它们只能嵌在动作、对话、风险变化里，每次不超过两三句。
- 每新增一段都必须回答：这一段让人物做了什么、对方如何反应、局势或信息发生了什么变化。
- 如果某段新增内容删掉后剧情完全不变，说明它是水分，必须改成动作/对话/后果。
- 章末只能加强压力交接，不能写总结、感悟、平静落幕或空泛抒情。
- 保留原文开头、结尾、关键物件、关键地点、角色认知边界和事件顺序；只能在原有桥段之间补写。
- 每补 900~1500 字，至少要有一次具体状态变化：信息变化、主动权变化、风险升级、关系变化、行动结果或伏笔回收/强化。

## 扩写原则（重要！）：
1. **补足不补水**：优先补足当前章节里已经存在的冲突推进、试探压迫、动作过程、因果衔接与余波，不要把篇幅浪费在独立景物铺陈上。
2. **加戏不加线**：只在当前章既有冲突内扩写，不推进主线到新阶段。
3. **可扩写内容**：
   - 对话潜台词（人物内心活动、言外之意、试探/压迫/回避）
   - 动作细节（肢体语言、微表情、动作回合）
   - 余波 Sequel（事件发生后的情绪反应、思考、决断前摇）
   - 感官/环境只允许作为动作与冲突的承压细节，不能独立成段
4. **禁止内容**：
   - 不要引入新的剧情转折
   - 不要添加新的重要角色
   - 不要改变已有的人物关系
   - 不要提前揭示任何伏笔
   - 不要用纯景物描写、重复心理独白或同义反复来凑字数
   - 不要把一句话反复换说法
   - 不要长段静态环境铺陈，除非它正在给人物施压或给动作落点

## 本章优先焦点：
{focus_guidance}

## 扩写技巧：
- 优先补足场景里的目标、阻碍、反应、余波，写成“你来我往”的过程
- 在对话之间插入必要的内心活动和动作回合，让试探、压迫、回避、反击更清楚
- 把“为什么这样说/这样做”以及“说完做完造成了什么后果”补成连续因果链
- 在情感高潮或碰撞后增加短余波：呼吸、疼痛、停顿、判断、下一步选择压力
- 感官和环境只作为增压器使用，服务冲突、动作和情绪落点，不单独撑篇幅

## 新增内容配比建议：
- 对话攻防、动作回合、因果衔接、短余波应占新增内容的 85% 以上
- 纯心理独白尽量短，且必须推动判断、误判、试探或决断
- 景物和气氛描写只点到为止，避免连续多段铺陈

## 风格要求：
- 保持原文的叙事视角
- 保持原文的语言风格
- 保持原文的节奏感
- 保留原文骨架，在原有桥段之间补足，不要改写成另一章

## 输出前自检：
1. 新增字数是否主要落在对话攻防、动作回合、因果链和短余波，而不是景物或重复心理描写？
2. 是否至少补出了若干个“反应 -> 应对 -> 新反应”的来回？
3. 最终全文字数是否接近目标区间？

请返回扩写后的完整章节内容，不要解释修改内容。
"""

ENRICH_DIALOGUE_PROMPT = """\
请扩写以下对话场景，增加人物的内心活动和潜台词：

## 原始对话：
{dialogue_text}

## 人物信息：
{character_info}

## 扩写要求：
1. 在对话之间插入说话者的内心活动
2. 描写人物的微表情和肢体语言
3. 增加对话的言外之意和潜台词
4. 保持对话的原有含义不变

请返回扩写后的对话内容。
"""

ENRICH_SCENE_PROMPT = """\
请扩写以下场景描写，增加感官细节和氛围：

## 原始场景：
{scene_text}

## 场景信息：
- 地点：{location}
- 时间：{time}
- 氛围：{atmosphere}

## 扩写要求：
1. 增加视觉细节（光影、色彩、形状）
2. 增加听觉细节（声音、静默、回响）
3. 增加触觉/嗅觉细节（温度、气味、质感）
4. 通过环境细节暗示人物情绪

请返回扩写后的场景描写。
"""


ENRICH_DIALOGUE_PROMPT = """\
请扩写以下对话场景，把它改成能改变局势的对话攻防：

## 原始对话：
{dialogue_text}

## 人物信息：
{character_info}

## 扩写要求：
1. 每新增一轮对话都必须带来逼问、拒绝、让步、暴露、误导、决断或风险升级。
2. 动作和心理只能服务于对话攻防，不能独立铺陈气氛或反复抒情。
3. 必须写清“说完之后局势发生了什么变化”，例如主动权、信息量、关系、风险或下一步选择改变。
4. 保持对话的原有含义不变，不新增重要角色或新主线。

请返回扩写后的对话内容。
"""

ENRICH_SCENE_PROMPT = """\
请扩写以下场景，把静态场景改成行动、对话、后果驱动的场面：

## 原始场景：
{scene_text}

## 场景信息：
- 地点：{location}
- 时间：{time}
- 氛围：{atmosphere}

## 扩写要求：
1. 优先补人物做了什么、对方如何反应、局势因此如何变化。
2. 如需环境/感官细节，只能嵌入动作承压或对话攻防中，不能独立成段。
3. 至少补出一个明确后果：信息暴露、风险升级、关系改变、选择受限或章末压力增强。
4. 保持与原文风格一致，不新增重要角色或新主线。

请返回扩写后的场景内容。
"""


class EnrichmentService:
    """
    章节扩写服务
    
    负责检测字数不足并进行智能扩写。
    """
    
    def __init__(
        self,
        db: Session,
        llm_service: LLMService
    ):
        self.db = db
        self.llm_service = llm_service
    
    async def check_and_enrich(
        self,
        chapter_text: str,
        target_word_count: int,
        user_id: int,
        threshold: float = 0.92
    ) -> Optional[EnrichmentResult]:
        """
        检查字数并在需要时进行扩写

        Args:
            chapter_text: 章节内容
            target_word_count: 目标字数
            user_id: 用户ID
            threshold: 触发扩写的阈值（默认85%）

        Returns:
            如果进行了扩写返回EnrichmentResult，否则返回None
        """
        with LLMService.daily_limit_scope(f"enrichment_check:{user_id}:{target_word_count}:{len(chapter_text or '')}"):
            current_count = self._count_words(chapter_text)

            # 检查是否需要扩写
            if current_count >= target_word_count * threshold:
                logger.info(f"字数充足 ({current_count}/{target_word_count})，无需扩写")
                return None

            logger.info(f"字数不足 ({current_count}/{target_word_count})，开始扩写")

            # 执行扩写
            enriched = await self._enrich_chapter(
                chapter_text=chapter_text,
                target_word_count=target_word_count,
                current_word_count=current_count,
                user_id=user_id
            )

            if not enriched:
                return None

            enriched_count = self._count_words(enriched)

            return EnrichmentResult(
                original_word_count=current_count,
                enriched_word_count=enriched_count,
                enriched_content=enriched,
                enrichment_ratio=enriched_count / current_count if current_count > 0 else 1.0,
                enrichment_type="detail"
            )
    
    async def enrich_to_target(
        self,
        chapter_text: str,
        target_word_count: int,
        user_id: int,
        max_iterations: int = 3
    ) -> str:
        """
        迭代扩写直到达到目标字数

        Args:
            chapter_text: 章节内容
            target_word_count: 目标字数
            user_id: 用户ID
            max_iterations: 最大迭代次数

        Returns:
            扩写后的内容
        """
        with LLMService.daily_limit_scope(f"enrichment_target:{user_id}:{target_word_count}:{len(chapter_text or '')}"):
            current_text = (chapter_text or "").strip()
            if not current_text:
                return ""

            previous_growth = None
            for i in range(max_iterations):
                current_count = self._count_words(current_text)

                if current_count >= target_word_count:
                    break

                logger.info(f"扩写迭代 {i+1}: {current_count}/{target_word_count}")

                threshold = 0.95
                if target_word_count >= 5500:
                    threshold = 0.99
                elif target_word_count >= 4500:
                    threshold = 0.97

                result = await self.check_and_enrich(
                    chapter_text=current_text,
                    target_word_count=target_word_count,
                    user_id=user_id,
                    threshold=threshold
                )

                if not result or not result.enriched_content:
                    logger.info("扩写迭代 %s 未返回有效内容，停止扩写", i + 1)
                    break

                candidate_text = result.enriched_content.strip()
                candidate_count = self._count_words(candidate_text)
                growth = candidate_count - current_count
                # 避免在“几乎无增量”或增量持续衰减的情况下反复调用导致章节生成超时
                target_gap = max(0, target_word_count - current_count)
                min_expected_growth = 80
                if target_word_count >= 5500:
                    min_expected_growth = 180
                elif target_word_count >= 4500:
                    min_expected_growth = 120

                if growth <= min_expected_growth:
                    logger.warning(
                        "扩写迭代 %s 增量不足（%s -> %s, 目标缺口=%s, 最低期望增量=%s），停止继续重试",
                        i + 1,
                        current_count,
                        candidate_count,
                        target_gap,
                        min_expected_growth,
                    )
                    break
                if previous_growth is not None and target_gap <= 1200 and growth < min(120, previous_growth * 0.35):
                    logger.warning(
                        "扩写迭代 %s 增量衰减过快（上一轮 +%s，本轮 +%s），停止继续重试",
                        i + 1,
                        previous_growth,
                        growth,
                    )
                    break

                previous_growth = growth
                current_text = candidate_text

            return current_text
    
    async def enrich_dialogue(
        self,
        dialogue_text: str,
        character_info: str,
        user_id: int
    ) -> Optional[str]:
        """
        扩写对话场景
        
        专门针对对话进行扩写，增加潜台词和内心活动。
        """
        prompt = ENRICH_DIALOGUE_PROMPT.format(
            dialogue_text=dialogue_text,
            character_info=character_info
        )
        
        try:
            text_result = await call_generation_text(
                llm_service=self.llm_service,
                system_prompt="你是一位擅长对话攻防扩写的小说编辑，只扩写当前片段，不改变剧情事实。",
                conversation_history=[{"role": "user", "content": prompt}],
                temperature=0.6,
                user_id=user_id,
                timeout=150.0,
                policy=GenerationCallPolicy(
                    stage_label="对话局部扩写",
                    progress_stage="enrichment",
                    retry_attempts=2,
                    response_format=None,
                    max_tokens=4000,
                    retry_same_model_once=True,
                ),
            )
            cleaned = remove_think_tags(text_result.text) if text_result.text else ""
            return cleaned.strip() if cleaned else None
        except Exception as e:
            logger.error(f"对话扩写失败: {e}")
            return None
    
    async def enrich_scene(
        self,
        scene_text: str,
        location: str,
        time: str,
        atmosphere: str,
        user_id: int
    ) -> Optional[str]:
        """
        扩写场景描写
        
        专门针对场景进行扩写，增加感官细节。
        """
        prompt = ENRICH_SCENE_PROMPT.format(
            scene_text=scene_text,
            location=location,
            time=time,
            atmosphere=atmosphere
        )
        
        try:
            text_result = await call_generation_text(
                llm_service=self.llm_service,
                system_prompt="你是一位擅长场景细节补强的小说编辑，只做局部补写，不改变人物状态和事件顺序。",
                conversation_history=[{"role": "user", "content": prompt}],
                temperature=0.6,
                user_id=user_id,
                timeout=150.0,
                policy=GenerationCallPolicy(
                    stage_label="场景局部扩写",
                    progress_stage="enrichment",
                    retry_attempts=2,
                    response_format=None,
                    max_tokens=3000,
                    retry_same_model_once=True,
                ),
            )
            cleaned = remove_think_tags(text_result.text) if text_result.text else ""
            return cleaned.strip() if cleaned else None
        except Exception as e:
            logger.error(f"场景扩写失败: {e}")
            return None
    
    async def _enrich_chapter(
        self,
        chapter_text: str,
        target_word_count: int,
        current_word_count: int,
        user_id: int
    ) -> Optional[str]:
        """执行章节扩写"""
        enrichment_context = self._build_enrichment_context(
            chapter_text=chapter_text,
            target_word_count=target_word_count,
            current_word_count=current_word_count
        )
        prompt = ENRICH_CHAPTER_PROMPT.format(
            chapter_text=chapter_text,
            target_word_count=target_word_count,
            current_word_count=current_word_count,
            needed_word_count=enrichment_context["needed_word_count"],
            target_word_count_floor=enrichment_context["target_word_count_floor"],
            target_word_count_ceiling=enrichment_context["target_word_count_ceiling"],
            expansion_plan=enrichment_context["expansion_plan"],
            focus_guidance=enrichment_context["focus_guidance"]
        )
        
        try:
            gap = max(0, target_word_count - current_word_count)
            enrichment_max_tokens = max(4000, min(14000, gap * 4 or 4000))
            enrichment_timeout = 180.0
            if gap >= 2500:
                enrichment_timeout = 420.0
            elif gap >= 1200:
                enrichment_timeout = 300.0

            text_result = await call_generation_text(
                llm_service=self.llm_service,
                system_prompt="你是一位长篇小说补写编辑。保持整章事件链、前后锚点和角色状态，只把缺的回合补进正文。",
                conversation_history=[{"role": "user", "content": prompt}],
                temperature=0.55,
                user_id=user_id,
                timeout=enrichment_timeout,
                policy=GenerationCallPolicy(
                    stage_label="章节连续性扩写",
                    progress_stage="enrichment",
                    retry_attempts=2,
                    response_format=None,
                    max_tokens=enrichment_max_tokens,
                    allow_truncated_response=False,
                    retry_same_model_once=True,
                ),
            )
            normalized = remove_think_tags(text_result.text) if text_result.text else ""
            if not normalized:
                return None
            guard_failure = self._enrichment_continuity_guard_failure(chapter_text, normalized)
            if guard_failure:
                logger.warning("扩写结果未通过连续性保护，已放弃本次扩写: %s", guard_failure)
                return None
            if self._count_words(normalized) <= current_word_count:
                logger.warning("扩写结果未明显增长（%s -> %s）", current_word_count, self._count_words(normalized))
            return normalized
        except Exception as e:
            logger.error(f"章节扩写失败: {e}")
            return None

    def _build_enrichment_context(
        self,
        chapter_text: str,
        target_word_count: int,
        current_word_count: int
    ) -> Dict[str, Any]:
        """根据当前章节特征构造更聚焦的扩写提示。"""
        gap = max(0, target_word_count - current_word_count)

        lower_tolerance = max(60, min(220, gap // 6 if gap else 60))
        upper_tolerance = max(40, min(140, gap // 8 if gap else 40))
        target_floor = max(current_word_count + 1, target_word_count - lower_tolerance)
        target_ceiling = target_word_count + upper_tolerance

        if gap <= 250:
            expansion_plan = "补 1 处关键回合，每处约 80~180 字，直接补在最该增压的位置"
        elif gap <= 700:
            expansion_plan = "补 2~3 处关键回合，每处约 120~220 字，分散插入现有桥段之间"
        elif gap <= 1500:
            expansion_plan = "补 3~5 处关键回合，每处约 150~300 字，优先照顾冲突最紧的段落"
        else:
            expansion_plan = "补 5~7 处关键回合，每处约 180~320 字，拆散到整章的冲突链里"

        dialogue_markers = ["“", "”", "\"", "说", "问", "道", "答", "冷笑", "沉声", "开口"]
        action_markers = [
            "抬手", "抬脚", "逼近", "后退", "冲", "扑", "砸", "劈", "斩", "挥", "攥", "按",
            "扣", "闪", "避", "躲", "退", "撞", "拦", "抓", "拔", "踢", "打"
        ]
        sequel_markers = ["沉默", "呼吸", "胸口", "心头", "一滞", "顿了顿", "片刻", "僵", "发麻", "冷汗", "迟疑"]
        causal_markers = ["于是", "所以", "却", "但", "随即", "立刻", "顿时", "便", "才", "因为"]

        dialogue_score = sum(chapter_text.count(marker) for marker in dialogue_markers)
        action_score = sum(chapter_text.count(marker) for marker in action_markers)
        sequel_score = sum(chapter_text.count(marker) for marker in sequel_markers)
        causal_score = sum(chapter_text.count(marker) for marker in causal_markers)

        focus_items: List[str] = []
        if dialogue_score >= 2:
            focus_items.append(
                "- 对话攻防：把已有对话拆成更清楚的试探、追问、顶回去、停顿和让步，不要只补抒情。"
            )
        if action_score >= 2:
            focus_items.append(
                "- 动作回合：补足起手、应对、变招、命中或落空后的即时反馈，让动作形成回合感。"
            )
        if causal_score >= 2 or not focus_items:
            focus_items.append(
                "- 因果链：把人物为何这么说、为何这么做、对方如何接招，补成连续反应链。"
            )
        if sequel_score >= 1 or gap >= 500:
            focus_items.append(
                "- 短余波：在关键碰撞后补一小段身体反应、情绪回弹或决断前摇，但不要拖成长篇独白。"
            )
        focus_items.append(
            "- 环境只做配角：只写能强化压迫、暴露距离、承接动作或映照情绪的细节，不单列成景。"
        )

        return {
            "needed_word_count": gap,
            "target_word_count_floor": target_floor,
            "target_word_count_ceiling": target_ceiling,
            "expansion_plan": expansion_plan,
            "focus_guidance": "\n".join(focus_items),
        }

    def _enrichment_continuity_guard_failure(self, original: str, enriched: str) -> Optional[str]:
        """Reject expansions that look like a fresh rewrite instead of anchored supplementation."""
        original_clean = (original or "").strip()
        enriched_clean = (enriched or "").strip()
        if not original_clean or not enriched_clean:
            return "empty_content"
        if self._count_words(enriched_clean) < max(1, int(self._count_words(original_clean) * 0.9)):
            return "shrinks_original"
        original_paragraphs = [part.strip() for part in re.split(r"\n\s*\n", original_clean) if part.strip()]
        enriched_paragraphs = [part.strip() for part in re.split(r"\n\s*\n", enriched_clean) if part.strip()]
        if len(original_paragraphs) >= 3 and len(enriched_paragraphs) < max(2, len(original_paragraphs) // 2):
            return "collapses_paragraph_structure"
        anchors = []
        if original_paragraphs:
            anchors.append(original_paragraphs[0][:36])
            anchors.append(original_paragraphs[-1][-36:])
        missing = [anchor for anchor in anchors if anchor and anchor not in enriched_clean]
        if len(missing) == len(anchors) and len(anchors) >= 2:
            return "lost_front_and_back_anchors"
        missing_motifs = self._missing_required_motifs(original_clean, enriched_clean)
        if missing_motifs:
            return "lost_required_motifs:" + ",".join(missing_motifs[:4])
        anchor_failure = self._anchor_sequence_guard_failure(original_paragraphs, enriched_clean)
        if anchor_failure:
            return anchor_failure
        original_progression = self._count_progression_markers(original_clean)
        enriched_progression = self._count_progression_markers(enriched_clean)
        growth = self._count_words(enriched_clean) - self._count_words(original_clean)
        if growth >= 500 and enriched_progression < max(original_progression, 3):
            return "enriched_without_new_progression_markers"
        enriched_density = enriched_progression / max(1.0, self._count_words(enriched_clean) / 1000)
        if self._count_words(enriched_clean) >= 1800 and enriched_density < 0.85:
            return "enriched_event_density_too_low"
        return None

    @staticmethod
    def _count_progression_markers(text: str) -> int:
        markers = (
            "逼问", "质问", "追问", "反问", "试探", "压迫", "威胁", "拒绝", "反制", "让步",
            "改口", "承认", "暴露", "揭开", "证实", "发现", "意识到", "决定", "选择", "交换",
            "代价", "风险", "危险", "失控", "反转", "翻脸", "线索", "证据", "期限", "后果",
            "抓住", "按住", "推开", "冲进", "闯入", "逃出", "追上", "救下", "必须", "否则",
        )
        source = str(text or "")
        dialogue_marks = sum(source.count(mark) for mark in ("“", "”", "「", "」", "『", "』", '"'))
        return dialogue_marks + sum(source.count(marker) for marker in markers)

    @staticmethod
    def _missing_required_motifs(original: str, enriched: str) -> List[str]:
        motif_groups = EnrichmentService._extract_required_motifs(original)
        missing: List[str] = []
        for label, markers in motif_groups:
            if any(marker in original for marker in markers) and not any(marker in enriched for marker in markers):
                missing.append(label)
        return missing

    @staticmethod
    def _extract_required_motifs(text: str) -> List[tuple[str, tuple[str, ...]]]:
        """Extract project-specific continuity motifs from the original text.

        The guard must work for any story world, so it cannot know about a
        particular sample project's locations, props, medicines, or artifacts.
        Instead it derives compact motif candidates from quoted terms, named
        places/factions/objects, numeric commitments, and repeated short terms.
        """

        source = str(text or "")
        if not source.strip():
            return []

        motif_suffixes = (
            "城", "镇", "村", "寨", "岛", "山", "岭", "谷", "河", "江", "湖", "海", "渠", "桥", "井", "塔", "碑", "墓", "坟",
            "门", "宗", "派", "阁", "院", "府", "宫", "殿", "司", "局", "盟", "会", "帮", "堂", "楼", "馆", "铺", "坊", "行",
            "军", "营", "队", "卫", "盟", "族", "国", "朝", "域", "界",
            "剑", "刀", "枪", "弓", "珠", "戒", "镜", "鼎", "炉", "灯", "书", "册", "卷", "页", "图", "符", "印", "玺", "令", "牌",
            "标", "药", "丹", "毒", "血", "骨", "契", "钥", "锁", "矿", "晶", "石", "阵", "术", "法", "诀", "经",
        )
        stopwords = {
            "他们", "她们", "我们", "你们", "这里", "那里", "这个", "那个", "什么", "自己", "已经", "只是", "还是",
            "因为", "所以", "但是", "然而", "必须", "立刻", "不能", "没有", "所有", "当前", "之后", "之前", "一页",
        }
        cjk = r"\u4e00-\u9fff"
        candidates: Dict[str, tuple[str, ...]] = {}

        def add_candidate(raw: str) -> None:
            token = re.sub(r"\s+", "", str(raw or "")).strip("，。！？；：、,.!?;:（）()[]【】《》“”\"' ")
            if len(token) < 2 or len(token) > 12 or token in stopwords:
                return
            if re.fullmatch(rf"[{cjk}]+", token) and len(token) > 8:
                return
            variants = {token}
            if re.search(rf"[{cjk}]", token):
                for size in (2, 3, 4, 5, 6):
                    if len(token) >= size:
                        variants.add(token[-size:])
                for size in (2, 3, 4):
                    if len(token) >= size:
                        variants.add(token[:size])
            candidates.setdefault(token, tuple(sorted(variants, key=lambda item: (-len(item), item))))

        for match in re.finditer(r"[《“「『\"]([^》”」』\"]{2,16})[》”」』\"]", source):
            add_candidate(match.group(1))

        for match in re.finditer(r"\b[A-Za-z][A-Za-z0-9_-]{2,}\b", source):
            add_candidate(match.group(0))

        for match in re.finditer(r"\d{1,5}\s*(?:年|月|日|天|夜|章|回|层|阶|次|枚|块|页|卷|人|军|里|丈|息|刻|个)", source):
            add_candidate(match.group(0))

        suffix_pattern = "|".join(re.escape(item) for item in sorted(set(motif_suffixes), key=len, reverse=True))
        for match in re.finditer(rf"[{cjk}]{{0,5}}(?:{suffix_pattern})", source):
            add_candidate(match.group(0))
        suffix_set = set(motif_suffixes)
        for index, char in enumerate(source):
            if char in suffix_set:
                add_candidate(source[max(0, index - 5):index + 1])

        compact = re.sub(r"\s+", "", source)
        repeated_counts: Dict[str, int] = {}
        for size in (2, 3, 4):
            for index in range(0, max(0, len(compact) - size + 1)):
                token = compact[index:index + size]
                if not re.fullmatch(rf"[{cjk}]{{{size}}}", token) or token in stopwords:
                    continue
                repeated_counts[token] = repeated_counts.get(token, 0) + 1
        for token, count in repeated_counts.items():
            if count >= 2 and any(token.endswith(suffix) for suffix in motif_suffixes):
                add_candidate(token)

        return list(candidates.items())[:18]

    @staticmethod
    def _anchor_sequence_guard_failure(original_paragraphs: List[str], enriched: str) -> Optional[str]:
        if len(original_paragraphs) < 4:
            return None
        anchors: List[str] = []
        for paragraph in original_paragraphs:
            compact = "".join(paragraph.split())
            if len(compact) >= 14:
                anchors.append(compact[:14])
        if len(anchors) < 4:
            return None
        hit_positions: List[int] = []
        compact_enriched = "".join(enriched.split())
        for anchor in anchors[:10]:
            position = compact_enriched.find(anchor)
            if position >= 0:
                hit_positions.append(position)
        if len(hit_positions) < max(2, len(anchors[:10]) // 2):
            return "lost_too_many_original_sequence_anchors"
        if hit_positions != sorted(hit_positions):
            return "original_sequence_reordered"
        return None
    
    def _count_words(self, text: str) -> int:
        """计算中文字数"""
        # 移除空白字符
        text = re.sub(r'\s+', '', text)
        # 计算字符数（中文一个字符算一个字）
        return len(text)
    
    def get_enrichment_suggestions(
        self,
        chapter_text: str,
        target_word_count: int
    ) -> Dict[str, Any]:
        """
        获取扩写建议
        
        分析章节内容，给出具体的扩写建议。
        """
        current_count = self._count_words(chapter_text)
        needed = target_word_count - current_count
        
        suggestions = {
            "current_word_count": current_count,
            "target_word_count": target_word_count,
            "needed": max(0, needed),
            "ratio": current_count / target_word_count if target_word_count > 0 else 1.0,
            "recommendations": []
        }
        
        if needed <= 0:
            suggestions["status"] = "sufficient"
            return suggestions
        
        suggestions["status"] = "needs_enrichment"
        
        # 分析内容，给出建议
        if "说" in chapter_text or "道" in chapter_text or '"' in chapter_text:
            suggestions["recommendations"].append({
                "type": "dialogue",
                "description": "检测到对话场景，建议增加人物内心活动和潜台词",
                "estimated_words": min(needed // 2, 500)
            })
        
        # 检测场景描写
        scene_keywords = ["走进", "来到", "站在", "坐在", "看着"]
        if any(kw in chapter_text for kw in scene_keywords):
            suggestions["recommendations"].append({
                "type": "scene",
                "description": "检测到场景转换，建议增加环境细节描写",
                "estimated_words": min(needed // 3, 300)
            })
        
        # 检测动作场景
        action_keywords = ["打", "踢", "跑", "跳", "攻击", "防御"]
        if any(kw in chapter_text for kw in action_keywords):
            suggestions["recommendations"].append({
                "type": "action",
                "description": "检测到动作场景，建议增加动作细节和感官描写",
                "estimated_words": min(needed // 3, 400)
            })
        
        # 通用建议
        suggestions["recommendations"].append({
            "type": "general",
            "description": "建议在情节转折处增加人物的情绪反应和思考",
            "estimated_words": min(needed // 4, 300)
        })
        
        return suggestions
