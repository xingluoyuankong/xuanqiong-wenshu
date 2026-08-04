# AIMETA P=story_quality_scoring_mixin|R=scene_dialogue_ending_static_artifact_score|NR=pipeline_side_effects|E=StoryQualityScoringMixin|X=internal|A=mixin|D=none|S=none|RD=./README.ai
"""Story quality scoring helpers extracted from PipelineOrchestrator.

Behavior-preserving mixin: method names/signatures stay the same so existing
call sites and tests continue to use PipelineOrchestrator.* unchanged.
"""
from __future__ import annotations

import math
import re
from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple


class StoryQualityScoringMixin:
    """Pure-ish story quality scoring and deterministic cleanup helpers."""

    QUALITY_ISSUE_LABELS = {
        "static_description_risk": "静态描写过多",
        "insufficient_dialogue_pressure": "有效对白不足",
        "chapter_progression_weak": "实质推进不足",
        "mission_anchor_missing": "本章任务未命中",
        "focus_character_missing": "焦点角色缺席",
        "repetition_risk": "重复段落过多",
        "scene_fulfillment_weak": "场景兑现不足",
        "dialogue_does_not_change_state": "对白未改变局势",
        "ending_pressure_missing": "章末递压不足",
        "critical_issues_remaining": "自检严重问题未消除",
        "score_below_floor": "结构质量分过低",
        "too_many_major_issues": "主要结构问题过多",
        "critical_consistency_unresolved": "严重连续性冲突",
        "major_consistency_unresolved": "连续性冲突未处理",
        "word_count_below_min": "低于最低字数",
        "word_count_far_above_target": "字数远超目标",
        "dialogue_pressure_weak": "对白攻防不足",
        "mission_progression_weak": "本章目标命中不足",
        "word_count_far_below_target": "字数离目标过远",
        "event_density_weak": "事件密度不足",
        "state_change_interval_weak": "状态变化间隔过长",
        "scene_structure_weak": "场景结构证据不足",
        "long_chapter_event_density_weak": "长章事件密度不足",
        "chapter_artifact_markers": "章节含提纲/标记残留",
        "draft_truncated": "首稿被模型截断",
    }

    QUALITY_THRESHOLD_CONFIGS = {
        "strict": {
            "min_score": 55,
            "max_critical": 0,
            "max_major": 2,
            "max_minor": 4,
            "min_word_count_ratio": 1.0,
        },
        "normal": {
            "min_score": 48,
            "max_critical": 0,
            "max_major": 3,
            "max_minor": 7,
            "min_word_count_ratio": 0.9,
        },
        "relaxed": {
            "min_score": 45,
            "max_critical": 1,
            "max_major": 4,
            "max_minor": 10,
            "min_word_count_ratio": 0.7,
        },
    }

    QUALITY_ISSUE_HINTS = {
        "static_description_risk": "压缩独立景物/心理段，把篇幅改成动作回合、对话攻防和后果。",
        "insufficient_dialogue_pressure": "补足至少两轮有效对白，让人物互相施压、拒绝、让步或反制。",
        "chapter_progression_weak": "把本章目标、冲突、转折写成可见事件，而不是停留在铺陈。",
        "mission_anchor_missing": "至少落地本章任务中的核心人物、地点、证据、冲突或转折，不要写成脱离导演脚本的泛场景。",
        "focus_character_missing": "让本章焦点角色实际出场、说话、行动或被明确处理。",
        "repetition_risk": "删除重复段落，用新的行动回合、信息增量或关系变化替换。",
        "scene_fulfillment_weak": "逐场兑现 scene_list 的目标、阻碍、反应、转折和钩子。",
        "dialogue_does_not_change_state": "让对白造成主动权、信息量、关系、风险或下一步选择的变化。",
        "ending_pressure_missing": "结尾必须交出危险、证据、期限、误会或代价，避免总结式平收。",
        "critical_consistency_unresolved": "优先修复前后文事实冲突，再继续润色。",
        "major_consistency_unresolved": "补齐承接关系和未闭环钩子，避免章节断裂。",
        "word_count_below_min": "必须先补足最低字数，且只能补行动、对话、后果和短余波，不能用空泛描写凑字。",
        "word_count_far_above_target": "压缩重复段落、循环对白和空转心理，把篇幅收回目标字数附近。",
        "word_count_far_below_target": "扩写只能补行动、对话、后果和短余波，不能用空泛描写凑字。",
        "event_density_weak": "把篇幅写到事件链里：行动、阻碍、反击、发现、代价和关系变化必须持续出现。",
        "state_change_interval_weak": "每个长段落窗口都要有可见变化，不能连续停在解释、回忆或氛围里。",
        "scene_structure_weak": "按目标、阻碍、转折、结果/压力逐场补齐，避免只点到场景关键词。",
        "long_chapter_event_density_weak": "长章需要更多有效场次和状态变化，不能把少量事件拉成一大章。",
        "chapter_artifact_markers": "删除 Markdown 标题、场景编号、扩写标签和作者说明，只保留沉浸式正文。",
        "draft_truncated": "该候选不是完整章节，必须重写完整正文后再进入审稿和修稿。",
    }

    @classmethod
    def _build_quality_issue_summary(
        cls,
        *,
        blockers: Optional[List[Dict[str, Any]]] = None,
        story_guard: Optional[Dict[str, Any]] = None,
        reason_codes: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        items: List[Dict[str, Any]] = []
        seen = set()

        def add(code: str, source: str = "story_progression_guard", message: Optional[str] = None) -> None:
            if not code or code in seen:
                return
            seen.add(code)
            items.append({
                "code": code,
                "label": cls.QUALITY_ISSUE_LABELS.get(code, code),
                "source": source,
                "hint": cls.QUALITY_ISSUE_HINTS.get(code, message or ""),
                "message": message or "",
            })

        for blocker in blockers or []:
            if isinstance(blocker, dict):
                add(str(blocker.get("code") or ""), str(blocker.get("source") or "quality_gate"), str(blocker.get("message") or ""))
        for code in reason_codes or []:
            add(str(code or ""))

        if blockers is None and reason_codes is None:
            guard = story_guard or {}
            rich_progression_evidence = (
                float(guard.get("scene_fulfillment_rate") or 0.0) >= 0.75
                and float(guard.get("scene_structure_rate") or 0.0) >= 0.7
                and guard.get("dialogue_changes_state") is True
                and (
                    guard.get("ending_pressure_passed") is True
                    or guard.get("ending_hook_detected") is True
                )
                and guard.get("event_density_passed") is True
                and guard.get("state_change_interval_passed") is True
            )
            if guard.get("static_description_risk"):
                add("static_description_risk")
            if guard.get("chapter_artifact_markers"):
                add("chapter_artifact_markers")
            if guard.get("expected_dialogue") and int(guard.get("dialogue_marker_count") or 0) < 4 and int(guard.get("word_count") or 0) >= 1500:
                add("insufficient_dialogue_pressure")
            if (
                int(guard.get("word_count") or 0) >= 1500
                and int(guard.get("mission_hit_count") or 0) < 2
                and not rich_progression_evidence
            ):
                add("chapter_progression_weak")
            if (
                int(guard.get("word_count") or 0) >= 1200
                and int(guard.get("mission_keyword_count") or 0) >= 4
                and int(guard.get("mission_hit_count") or 0) == 0
                and not rich_progression_evidence
            ):
                add("mission_anchor_missing")
            if guard.get("focus_character_missing"):
                add("focus_character_missing")
            if guard.get("repetition_risk"):
                add("repetition_risk")
            if guard.get("word_count_below_min"):
                add("word_count_below_min")
            elif guard.get("word_count_far_above_target"):
                add("word_count_far_above_target")
            elif guard.get("word_count_far_below_target"):
                add("word_count_far_below_target")
            scene_count = int(guard.get("scene_count") or 0)
            if scene_count > 0:
                scene_rate = (
                    cls._coerce_float(guard.get("scene_fulfillment_rate"), 0.0)
                    if guard.get("scene_fulfillment_rate") is not None
                    else 0.0
                )
                scene_structure_rate = (
                    cls._coerce_float(guard.get("scene_structure_rate"), 0.0)
                    if guard.get("scene_structure_rate") is not None
                    else 0.0
                )
                if scene_rate < 0.35:  # was 0.75; lowered for free API short-form
                    add("scene_fulfillment_weak")
                if scene_structure_rate < 0.25:  # was 0.55; lowered for free API
                    add("scene_structure_weak")
            if guard.get("expected_dialogue") and "dialogue_changes_state" in guard and guard.get("dialogue_changes_state") is not True:
                add("dialogue_does_not_change_state")
            if int(guard.get("word_count") or 0) >= 900 and not (guard.get("ending_pressure_passed") is True or guard.get("ending_hook_detected") is True):
                add("ending_pressure_missing")
            if int(guard.get("word_count") or 0) >= 1800 and guard.get("event_density_passed") is False:
                add("event_density_weak")
            if int(guard.get("word_count") or 0) >= 2500 and guard.get("state_change_interval_passed") is False:
                add("state_change_interval_weak")
            if int(guard.get("word_count") or 0) >= 7000 and guard.get("long_chapter_density_passed") is False:
                add("long_chapter_event_density_weak")

        tone = "success"
        if len(items) >= 2 or any(item["code"] in {"static_description_risk", "critical_consistency_unresolved", "word_count_below_min", "word_count_far_above_target"} for item in items):
            tone = "danger"
        elif items:
            tone = "warning"

        return {
            "passed": not items,
            "tone": tone,
            "count": len(items),
            "codes": [item["code"] for item in items],
            "labels": [item["label"] for item in items],
            "items": items,
        }

    @classmethod
    def _attach_quality_gate_status_to_guard(
        cls,
        story_guard: Dict[str, Any],
        structural_quality_gate: Dict[str, Any],
    ) -> Dict[str, Any]:
        guard = deepcopy(story_guard or {})
        # Fail closed: missing structural gate.passed must not clear quality issues as "passed".
        gate_passed = structural_quality_gate.get("passed") is True if isinstance(structural_quality_gate, dict) else False
        gate_summary = {
            "passed": gate_passed,
            "codes": list((structural_quality_gate or {}).get("quality_issue_codes") or []) if isinstance(structural_quality_gate, dict) else [],
            "labels": list((structural_quality_gate or {}).get("quality_issue_labels") or []) if isinstance(structural_quality_gate, dict) else [],
            "blocker_count": len((structural_quality_gate or {}).get("blockers") or []) if isinstance(structural_quality_gate, dict) else 0,
        }
        guard["quality_gate_passed"] = gate_passed
        guard["quality_gate_summary"] = gate_summary
        guard["quality_gate_codes"] = gate_summary["codes"]
        guard["quality_gate_labels"] = gate_summary["labels"]

        snapshot = dict(guard.get("quality_metric_snapshot") or {})
        raw_summary = snapshot.get("quality_issue_summary") or guard.get("quality_issue_summary")
        # Only demote soft rule warnings when gate explicitly passed; missing summary.passed is not a failure signal here.
        if gate_passed and isinstance(raw_summary, dict) and raw_summary.get("passed") is False:
            warning_summary = deepcopy(raw_summary)
            guard["quality_rule_warnings"] = warning_summary
            snapshot["quality_rule_warnings"] = warning_summary
            clean_summary = {
                "passed": True,
                "tone": "success",
                "count": 0,
                "codes": [],
                "labels": [],
                "items": [],
            }
            guard["quality_issue_summary"] = clean_summary
            guard["quality_issue_codes"] = []
            guard["quality_issue_labels"] = []
            snapshot["quality_issue_summary"] = clean_summary
            snapshot["quality_issue_codes"] = []
            snapshot["quality_issue_labels"] = []
        if snapshot:
            snapshot["quality_gate_passed"] = gate_passed
            snapshot["quality_gate_summary"] = gate_summary
            guard["quality_metric_snapshot"] = snapshot
        return guard

    @staticmethod
    def _collect_fallback_mission_keywords(chapter_mission: Optional[dict]) -> List[str]:
        if not isinstance(chapter_mission, dict):
            return []

        priority: List[str] = []
        candidates: List[str] = []

        def add_to(bucket: List[str], value: Any, *, max_len: int = 24) -> None:
            if not value:
                return
            if isinstance(value, dict):
                for item in value.values():
                    add_to(bucket, item, max_len=max_len)
                return
            if isinstance(value, list):
                for item in value:
                    add_to(bucket, item, max_len=max_len)
                return

            text = str(value).strip()
            if not text:
                return
            if 2 <= len(text) <= max_len:
                bucket.append(text)
            for token in re.split(r"[，。；、,\s/]+", text):
                normalized = token.strip("：:- ").strip()
                if 2 <= len(normalized) <= 12:
                    bucket.append(normalized)

        # Focus/POV names first so mission_hit_count cannot be starved by long purpose phrases.
        add_to(priority, chapter_mission.get("focus_characters"), max_len=12)
        add_to(priority, chapter_mission.get("character_focus"), max_len=12)
        add_to(priority, chapter_mission.get("pov_character"), max_len=12)
        add_to(priority, chapter_mission.get("pov"), max_len=12)
        for scene in chapter_mission.get("scene_list") or []:
            if isinstance(scene, dict):
                add_to(priority, scene.get("characters"), max_len=12)

        add_to(candidates, chapter_mission.get("chapter_purpose"))
        add_to(candidates, (chapter_mission.get("continuity_anchor") or {}).get("inherit_from_previous"))
        add_to(candidates, (chapter_mission.get("continuity_anchor") or {}).get("deliver_to_next"))
        add_to(candidates, chapter_mission.get("character_arc_task"))
        add_to(candidates, (chapter_mission.get("dialogue_strategy") or {}).get("purpose"))
        add_to(candidates, (chapter_mission.get("dialogue_strategy") or {}).get("subtext"))
        for scene in chapter_mission.get("scene_list") or []:
            if isinstance(scene, dict):
                for key in (
                    "goal",
                    "conflict",
                    "turn",
                    "must_happen",
                    "outcome",
                    "payoff",
                    "bridge",
                    "pressure_shift",
                    "emotion_shift",
                    "dialogue_value",
                    "end_hook",
                    "foreshadowing_task",
                ):
                    add_to(candidates, scene.get(key))

        deduped: List[str] = []
        seen = set()
        for item in priority + candidates:
            if item and item not in seen:
                seen.add(item)
                deduped.append(item)
        return deduped[:24]

    @staticmethod
    def _chapter_mission_expects_dialogue(chapter_mission: Optional[dict]) -> bool:
        if not isinstance(chapter_mission, dict):
            return False
        dialogue_strategy = chapter_mission.get("dialogue_strategy")
        if isinstance(dialogue_strategy, dict) and dialogue_strategy:
            return True
        for scene in chapter_mission.get("scene_list") or []:
            if isinstance(scene, dict) and any(scene.get(key) for key in ("dialogue_value", "conflict", "turn")):
                return True
        return False

    # 中文叙事同义词表：常见动作/状态/物件的同义表达，用于场景评分时
    # 识别模型用同义词改写的正文内容，避免纯子串匹配误杀。
    _NARRATIVE_SYNONYMS: Dict[str, List[str]] = {
        "质问": ["逼问", "追问", "盘问", "审问", "责问"],
        "拒绝": ["推辞", "回绝", "婉拒", "不答应", "摇头拒绝"],
        "发现": ["察觉", "意识到", "看出", "认出", "注意到"],
        "决定": ["拿定主意", "打定主意", "下定决心", "下了决心"],
        "威胁": ["恐吓", "要挟", "逼迫", "胁迫", "威逼"],
        "逃离": ["逃出", "逃跑", "撤退", "脱身", "撤离"],
        "交换": ["互换", "交易", "以物易物", "交割", "换"],
        "交出": ["递出", "交出去", "掏出来", "拿出来", "给"],
        "试探": ["探口风", "套话", "摸清", "揣测", "揣摩"],
        "消失": ["不见了", "没了踪影", "失踪", "隐去", "离去", "溜走"],
        "追踪": ["跟踪", "尾随", "盯梢", "追查", "寻找"],
        "隐藏": ["藏起来", "遮掩", "掩饰", "匿藏", "藏匿"],
        "保护": ["守护", "掩护", "庇护", "护卫", "保全"],
        "背叛": ["出卖", "叛变", "倒戈", "反水", "告密"],
        "揭露": ["曝光", "揭穿", "戳穿", "抖出", "揭发"],
        "承认": ["认了", "点头承认", "坦白", "供认", "认账"],
        "对抗": ["反抗", "抵抗", "顶撞", "抗衡", "对峙"],
        "说服": ["劝服", "打动", "感化", "说动", "劝动"],
        "拦截": ["拦下", "截住", "堵住", "挡住", "阻拦"],
        "潜入": ["溜进", "摸进", "悄悄进入"],
        "逼近": ["靠近", "接近", "凑近", "贴近"],
        "钥匙": ["残钥", "铜钥", "半把钥匙", "断钥", "锁钥"],
        "名单": ["花名册", "名册", "清单", "名录", "登记簿"],
        "线索": ["蛛丝马迹", "痕迹", "端倪", "苗头", "迹象"],
        "证据": ["凭证", "铁证", "佐证", "物证", "证明"],
        "秘密": ["隐秘", "暗号", "机密", "内幕", "底牌"],
        "危险": ["凶险", "险境", "杀机", "危机", "祸患"],
        "紧张": ["紧绷", "神经绷紧", "提心吊胆", "心惊肉跳"],
        "愤怒": ["恼怒", "暴怒", "怒不可遏", "火冒三丈", "愤恨"],
        "恐惧": ["害怕", "惊恐", "惶恐", "胆寒", "畏惧"],
        "绝望": ["万念俱灰", "心灰意冷", "走投无路", "穷途末路"],
        "犹豫": ["迟疑", "踌躇", "举棋不定", "拿不定主意"],
        "坚定": ["果决", "果断", "斩钉截铁", "毫不犹豫"],
        "信任": ["信赖", "托付", "依靠", "倚重", "深信"],
        "怀疑": ["猜忌", "起疑", "狐疑", "不信任", "心存疑虑"],
        "离开": ["转身离去", "走了", "动身", "启程", "上路"],
        "回来": ["折返", "返回", "赶回", "归来"],
        "等待": ["守候", "等候", "静候", "候着", "苦等"],
        "约定": ["约好", "定下", "说好了", "立下约定"],
        "传递": ["转交", "递过去", "塞给", "交到", "递给"],
        "纸条": ["字条", "便笺", "小纸条", "纸片", "笺纸"],
        "交易": ["买卖", "置换", "以物换物", "成交"],
        "废桥": ["断桥", "残桥", "旧桥", "毁坏的桥"],
        "栈桥": ["木桥", "旧桥", "码头", "渡桥"],
        "通讯录": ["联系人", "联系人名单", "手机通讯录", "联系人页"],
        "空白": ["清空", "全白", "只剩空白", "变成空白", "名字空白"],
        "借阅人": ["旧借阅人", "来电标注", "未知来电", "借阅"],
        "第二本": ["第二本账册", "备用册", "空白备用册", "账册"],
        "半把钥匙": ["半把", "半枚钥匙", "残钥", "断钥", "另一半钥匙"],
        "反制": ["反压", "反将一军", "反过来压", "拿把柄", "用欠字"],
        "残单": ["残页", "旧单", "残缺单据", "半张残单"],
        "广播柜": ["广播箱", "磁带柜", "倒带柜", "旧广播柜"],
        "倒带": ["倒带声", "磁带倒转", "沙沙倒带"],
        "背光人": ["背光的人", "逆光的人", "看不清脸的人", "雾里的人"],
        "记录": ["被记下", "被登记", "被传到", "被系统记了", "传递出去"],
        # Live mid-lean rephrase: blood-contract / token / chase clusters
        "血契": ["母契", "子契", "契印", "令牌印记", "血印", "契纹", "血脉契约", "契毒"],
        "夜雨令": ["令牌", "令印", "雨令", "那枚令", "令牌印记"],
        "刻令者": ["刻令师", "刻令的人", "令牌刻制者", "制令者", "刻契者"],
        "砸窗": ["瓦片砸窗", "砸在窗棂", "敲窗", "砸响窗", "瓦片砸"],
        "谈判": ["谈条件", "谈妥", "议价", "开条件", "谈拢", "谈成"],
        "同行": ["一起走", "必须同行", "带着我", "不能甩开我", "一起查"],
        "展示": ["亮出", "露出", "掏出", "摊开", "给她看", "给他看"],
        "令牌": ["夜雨令", "令印", "令牌印记", "牌印", "印记"],
        "解契": ["破契", "除契", "消契", "解开血契", "解除血契"],
        "反噬": ["反噬痛", "灼烧反噬", "令牌反噬", "灼痛蔓延", "印记灼烧"],
        "追兵": ["追索", "追杀", "追赶", "围堵", "截杀", "缉拿"],
        "封锁": ["封死", "封路", "封街", "水路封锁", "封住出口"],
        "人质": ["抵押", "把柄", "挟持", "要挟筹码"],
        "伤口": ["伤处", "裂口", "血口", "创口", "伤势"],
        "逼问": ["追问", "质问", "盘问", "逼着问", "逼他开口"],
        "拒绝": ["不答应", "摇头", "推开", "不肯", "回绝"],
        "暴露": ["露馅", "露了马脚", "被看穿", "被识破", "兜不住"],
        "代价": ["后果", "赔上", "付出", "反噬代价", "代价太高"],
        "期限": ["三天", "三日", "倒计时", "时限", "来不及"],
        "潜入": ["摸进", "溜进", "悄悄进入", "潜入调查", "潜行"],
        "交接": ["转交", "递交", "交割", "换手", "交到手里"],
    }

    @classmethod
    def _expand_synonyms(cls, token: str) -> List[str]:
        """Expand a token using the narrative synonym table."""
        expanded: List[str] = []
        if not token or len(token) < 2:
            return expanded
        syns = cls._NARRATIVE_SYNONYMS.get(token, [])
        for syn in syns:
            if syn not in expanded:
                expanded.append(syn)
        for key, synonyms in cls._NARRATIVE_SYNONYMS.items():
            if token in synonyms:
                if key not in expanded:
                    expanded.append(key)
                for syn in synonyms:
                    if syn != token and syn not in expanded:
                        expanded.append(syn)
        return expanded

    @classmethod
    def _extract_quality_tokens(cls, value: Any) -> List[str]:
        if not value:
            return []
        if isinstance(value, dict):
            tokens: List[str] = []
            for item in value.values():
                tokens.extend(cls._extract_quality_tokens(item))
            return tokens
        if isinstance(value, list):
            tokens: List[str] = []
            for item in value:
                tokens.extend(cls._extract_quality_tokens(item))
            return tokens

        text = str(value).strip()
        if not text:
            return []
        stop_tokens = {
            "本章", "主角", "目标", "冲突", "转折", "压力", "下一章", "下一场",
            "必须", "不能", "需要", "继续", "同时", "最终", "真正", "方式",
        }
        tokens = [text] if 2 <= len(text) <= 32 and text not in stop_tokens else []
        for token in re.split(r"[，。；、！？：:\s/|,.;!?()\[\]{}<>《》“”\"'\\-]+", text):
            token = token.strip()
            if 2 <= len(token) <= 12:
                tokens.append(token)
            compact = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", token)
            if 5 <= len(compact) <= 18:
                # 章节任务常把“潮宗正式发缉印令”这类动作+名词写成一整句，
                # 正文更可能只落到“缉印令”。补充较短的命名片段，减少硬关键词误杀。
                for size in (5, 4, 3):
                    for start in range(0, max(0, len(compact) - size + 1)):
                        piece = compact[start:start + size]
                        if piece and piece not in stop_tokens:
                            tokens.append(piece)

        deduped: List[str] = []
        seen = set()
        for token in tokens:
            if token not in seen and token not in stop_tokens:
                seen.add(token)
                deduped.append(token)
        return deduped[:20]

    @classmethod
    def _fuzzy_match_token(cls, token: str, condensed_text: str) -> bool:
        """Check if token has fuzzy presence in condensed_text.
        Uses 3-char sliding window: if enough windows match, count as soft hit."""
        if len(token) < 3:
            return False
        window_count = 0
        needed = max(1, len(token) // 3)
        for i in range(len(token) - 2):
            window = token[i:i + 3]
            if window in condensed_text:
                window_count += 1
                if window_count >= needed:
                    return True
        return False

    @classmethod
    def _score_text_hits(cls, value: Any, condensed_text: str) -> Tuple[int, List[str]]:
        tokens = cls._extract_quality_tokens(value)
        hits: List[str] = []
        seen: set = set()
        for token in tokens:
            if not token or token in seen:
                continue
            # Direct substring match
            if token in condensed_text:
                hits.append(token)
                seen.add(token)
                continue
            # Synonym expansion match
            synonyms = cls._expand_synonyms(token)
            synonym_hit = False
            for syn in synonyms:
                if syn in condensed_text:
                    hits.append(token + "~" + syn)
                    seen.add(token)
                    synonym_hit = True
                    break
            if synonym_hit:
                continue
            # Fuzzy 3-char sliding window match for tokens >= 3 chars
            if len(token) >= 3 and cls._fuzzy_match_token(token, condensed_text):
                hits.append(token + "~fuzzy")
                seen.add(token)
        return len(hits), hits[:6]

    @classmethod
    def _evaluate_scene_fulfillment(cls, chapter_mission: Optional[dict], condensed_text: str) -> Dict[str, Any]:
        scene_list = (chapter_mission or {}).get("scene_list") if isinstance(chapter_mission, dict) else []
        if not isinstance(scene_list, list) or not scene_list:
            return {
                "scene_count": 0,
                "fulfilled_scene_count": 0,
                "scene_fulfillment_rate": 1.0,
                "structure_passed_scene_count": 0,
                "scene_structure_rate": 1.0,
                "scene_details": [],
            }

        tracked_keys = (
            "goal",
            "conflict",
            "turn",
            "must_happen",
            "outcome",
            "pressure_shift",
            "dialogue_value",
            "end_hook",
            "payoff",
            "bridge",
        )
        structure_groups = {
            "goal": ("goal", "must_happen"),
            "conflict": ("conflict", "dialogue_value"),
            "turn": ("turn", "outcome", "pressure_shift", "payoff"),
            "bridge": ("bridge", "end_hook"),
        }
        details: List[Dict[str, Any]] = []
        fulfilled_count = 0
        structure_passed_count = 0
        for index, scene in enumerate(scene_list[:8], start=1):
            if not isinstance(scene, dict):
                continue
            required_fields = 0
            hit_fields = 0
            hit_by_key: Dict[str, bool] = {}
            field_results = []
            for key in tracked_keys:
                value = scene.get(key)
                if not value:
                    continue
                required_fields += 1
                hit_count, hits = cls._score_text_hits(value, condensed_text)
                field_hit = hit_count > 0
                hit_fields += 1 if field_hit else 0
                hit_by_key[key] = field_hit
                field_results.append({"field": key, "hit": field_hit, "hits": hits})

            required_to_pass = max(1, min(3, math.ceil(required_fields * 0.45)))
            fulfilled = bool(required_fields == 0 or hit_fields >= required_to_pass)
            structure_hits = 0
            structure_results: Dict[str, bool] = {}
            for group_name, keys in structure_groups.items():
                group_hit = any(hit_by_key.get(key) for key in keys)
                structure_results[group_name] = group_hit
                structure_hits += 1 if group_hit else 0
            structure_required = 2 if required_fields <= 3 else 3
            structure_passed = bool(required_fields == 0 or structure_hits >= structure_required)
            fulfilled_count += 1 if fulfilled else 0
            structure_passed_count += 1 if structure_passed else 0
            details.append(
                {
                    "scene_index": index,
                    "required_fields": required_fields,
                    "hit_fields": hit_fields,
                    "required_to_pass": required_to_pass,
                    "fulfilled": fulfilled,
                    "structure_hits": structure_hits,
                    "structure_required": structure_required,
                    "structure_passed": structure_passed,
                    "structure_results": structure_results,
                    "fields": field_results,
                }
            )

        scene_count = len(details)
        return {
            "scene_count": scene_count,
            "fulfilled_scene_count": fulfilled_count,
            "scene_fulfillment_rate": round(fulfilled_count / max(1, scene_count), 4),
            "structure_passed_scene_count": structure_passed_count,
            "scene_structure_rate": round(structure_passed_count / max(1, scene_count), 4),
            "scene_details": details,
        }

    STORY_PROGRESSION_MARKERS = (
        "逼问", "质问", "追问", "反问", "试探", "压迫", "威胁", "拒绝", "反制", "让步",
        "改口", "承认", "暴露", "揭开", "揭露", "证实", "发现", "意识到", "明白", "决定",
        "选择", "交换", "代价", "风险", "危险", "失控", "反转", "翻脸", "背叛", "线索",
        "证据", "期限", "后果", "付出", "受伤", "倒下", "失去", "得到", "夺回", "打开",
        "推开", "抓住", "按住", "拔出", "砸开", "冲进", "闯入", "逃出", "追上", "救下",
        "杀", "死", "活", "必须", "否则", "来不及", "下一步", "转而", "却", "但", "然而",
    )

    @classmethod
    def _story_units(cls, text: str) -> List[str]:
        units = [unit.strip() for unit in re.split(r"[。！？!?\n]+", str(text or "")) if unit.strip()]
        expanded: List[str] = []
        for unit in units:
            if len(unit) <= 180:
                expanded.append(unit)
                continue
            for index in range(0, len(unit), 140):
                chunk = unit[index:index + 140].strip()
                if chunk:
                    expanded.append(chunk)
        return expanded

    @classmethod
    def _unit_has_progression(cls, unit: str) -> bool:
        if not unit:
            return False
        if any(mark in unit for mark in ("“", "”", "「", "」", "『", "』", '"')):
            return True
        return any(marker in unit for marker in cls.STORY_PROGRESSION_MARKERS)

    @classmethod
    def _evaluate_event_density(cls, text: str, *, word_count: int) -> Dict[str, Any]:
        if word_count < 800:
            return {
                "event_density_passed": True,
                "long_chapter_density_passed": True,
                "state_change_interval_passed": True,
                "progression_unit_count": 0,
                "story_unit_count": 0,
                "progression_unit_rate": 1.0,
                "event_density_per_1000": 0.0,
                "state_change_window_pass_rate": 1.0,
                "max_plain_unit_run": 0,
            }

        units = cls._story_units(text)
        progression_flags = [cls._unit_has_progression(unit) for unit in units]
        progression_count = sum(1 for item in progression_flags if item)
        story_unit_count = len(units)
        max_plain_run = 0
        current_plain_run = 0
        for flag in progression_flags:
            if flag:
                current_plain_run = 0
            else:
                current_plain_run += 1
                max_plain_run = max(max_plain_run, current_plain_run)

        condensed = "".join(str(text or "").split())
        window_size = 1200 if word_count >= 7000 else 950
        windows = [condensed[index:index + window_size] for index in range(0, len(condensed), window_size)] or [condensed]
        window_hits = sum(1 for window in windows if cls._unit_has_progression(window))
        window_pass_rate = round(window_hits / max(1, len(windows)), 4)

        density_per_1000 = round(progression_count / max(1.0, word_count / 1000), 4)
        progression_rate = round(progression_count / max(1, story_unit_count), 4)
        density_floor = 1.0 if word_count < 2500 else 1.25 if word_count < 7000 else 1.45
        unit_rate_floor = 0.16 if word_count < 2500 else 0.2 if word_count < 7000 else 0.22
        window_floor = 0.6 if word_count < 2500 else 0.68 if word_count < 7000 else 0.74
        plain_run_limit = 5 if word_count < 7000 else 4

        state_interval_passed = bool(window_pass_rate >= window_floor)
        dense_progression_override = bool(
            state_interval_passed
            and density_per_1000 >= density_floor * 2
            and progression_rate >= unit_rate_floor * 1.6
        )
        event_density_passed = bool(
            density_per_1000 >= density_floor
            and progression_rate >= unit_rate_floor
            and (max_plain_run <= plain_run_limit or dense_progression_override)
        )
        long_chapter_passed = True
        if word_count >= 7000:
            long_chapter_passed = bool(event_density_passed and state_interval_passed and progression_count >= 12)

        return {
            "event_density_passed": event_density_passed,
            "long_chapter_density_passed": long_chapter_passed,
            "state_change_interval_passed": state_interval_passed,
            "progression_unit_count": progression_count,
            "story_unit_count": story_unit_count,
            "progression_unit_rate": progression_rate,
            "event_density_per_1000": density_per_1000,
            "state_change_window_count": len(windows),
            "state_change_window_hit_count": window_hits,
            "state_change_window_pass_rate": window_pass_rate,
            "max_plain_unit_run": max_plain_run,
        }

    @staticmethod
    def _count_dialogue_state_change_markers(text: str) -> int:
        markers = (
            "逼问", "反问", "拒绝", "改口", "让步", "沉默", "威胁", "试探", "压低",
            "盯", "笑了", "停住", "转而", "暴露", "发现", "意识到", "决定", "条件",
            "交换", "代价", "风险", "失控",
            # natural spoken/action pressure common in Chinese fiction dialogue beats
            "质问", "追问", "盘问", "打断", "反制", "反咬", "摊牌", "亮出", "甩出",
            "夺过", "抢走", "攥紧", "松开", "扣住", "按住", "抽出", "拔刀", "收刀",
            "后退", "上前", "僵住", "愣住", "咬牙", "冷笑", "沉声", "低喝", "勒令",
            "逼近", "逼退", "应下", "应允", "松口", "咬死", "咬定", "堵住", "掐断",
            "点头", "摇头", "别过脸", "转过身", "脸色一变", "语气一沉", "话锋一转",
            "话音刚落", "不答应", "不行", "够了", "说清楚", "听着", "闭嘴", "你敢",
            "别动", "放下", "拿出来", "跟我走", "算了", "我不会", "你以为",
            "当即", "随即", "立刻", "突然", "退路", "翻脸", "承认", "泄露",
        )
        normalized_markers = (
            "逼问", "反问", "质问", "追问", "试探", "压迫", "压住", "拒绝", "沉默", "打断",
            "反制", "威胁", "翻脸", "让步", "改口", "承认", "暴露", "泄露", "发现", "意识到",
            "决定", "选择", "条件", "交换", "代价", "风险", "危险", "失控", "反转", "退路",
            "摊牌", "亮出", "夺过", "扣住", "沉声", "低喝", "松口", "咬定", "话锋一转",
            "脸色一变", "不答应", "说清楚",
        )
        # de-dupe while preserving counts via set of unique markers
        unique = tuple(dict.fromkeys(markers + normalized_markers))
        return sum(str(text or "").count(marker) for marker in unique)

    @classmethod
    def _evaluate_dialogue_changes_state(cls, text: str, *, expected_dialogue: bool, dialogue_markers: int) -> Dict[str, Any]:
        marker_count = cls._count_dialogue_state_change_markers(text)
        if not expected_dialogue:
            passed = True
        elif dialogue_markers >= 2 and marker_count >= 2:
            # classic: quotes + explicit pressure/state verbs
            passed = True
        elif dialogue_markers >= 8 and marker_count >= 1:
            # dense dialogue with at least one state-pressure signal
            passed = True
        elif dialogue_markers >= 14 and marker_count >= 1:
            # very dense multi-turn exchange with at least one pressure/action signal
            passed = True
        else:
            passed = False
        return {
            "expected_dialogue": expected_dialogue,
            "dialogue_marker_count": dialogue_markers,
            "state_change_marker_count": marker_count,
            "dialogue_changes_state": passed,
        }

    @classmethod
    def _evaluate_ending_pressure(cls, condensed_text: str, chapter_mission: Optional[dict]) -> Dict[str, Any]:
        # Use a wider ending window so multi-paragraph cliffhangers are not truncated out.
        ending_excerpt = condensed_text[-420:] if condensed_text else ""
        continuity = (chapter_mission or {}).get("continuity_anchor") if isinstance(chapter_mission, dict) else {}
        deliver_to_next = continuity.get("deliver_to_next") if isinstance(continuity, dict) else []
        _, deliver_hits = cls._score_text_hits(deliver_to_next, ending_excerpt)
        mission_hook_sources: List[Any] = []
        if isinstance(chapter_mission, dict):
            for key in (
                "suspense_hook",
                "chapter_role",
                "chapter_purpose",
                "payoff_window",
                "conflict_escalation",
                "foreshadowing_tasks",
            ):
                if chapter_mission.get(key):
                    mission_hook_sources.append(chapter_mission.get(key))
            scene_list = chapter_mission.get("scene_list")
            if isinstance(scene_list, list) and scene_list:
                last_scene = scene_list[-1] if isinstance(scene_list[-1], dict) else {}
                for key in ("end_hook", "bridge", "outcome", "pressure_shift", "payoff", "turn"):
                    if last_scene.get(key):
                        mission_hook_sources.append(last_scene.get(key))
        _, mission_hook_hits = cls._score_text_hits(mission_hook_sources, ending_excerpt)
        hook_markers = (
            "却", "突然", "忽然", "门外", "脚步", "消息", "期限", "代价", "危险",
            "线索", "证据", "下一刻", "来不及", "问题", "？", "?", "！", "!",
        )
        closure_markers = ("终于结束", "告一段落", "松了口气", "一切都", "暂时平静", "圆满", "尘埃落定")
        zh_hook_markers = (
            "\u4e0b\u4e00", "\u4e0b\u4e00\u8f6e", "\u4e0b\u4e00\u7ae0",
            "\u6da8\u6f6e", "\u6f6e\u6c34", "\u5371\u9669", "\u5371\u673a",
            "\u538b\u529b", "\u4ee3\u4ef7", "\u540e\u679c", "\u8bc1\u636e",
            "\u7ebf\u7d22", "\u5f02\u5e38", "\u4e0d\u81ea\u7136",
            "\u6765\u4e0d\u53ca", "\u5fc5\u987b", "\u5426\u5219",
            "\u9000\u8def", "\u5c01\u9501", "\u7f09\u5370\u4ee4", "\u901a\u7f09",
            "\u5012\u8ba1\u65f6", "\u8ffd\u7d22", "\u8ffd\u6740", "\u903c\u8fd1",
            "\u5835\u6b7b", "\u9501\u6b7b", "\u53ea\u80fd", "\u4e0d\u5f97\u4e0d",
            "\u4f1a\u5148\u6b7b", "\u6b7b\u5728", "\u65e7\u6728\u7247",
            "\u6b7b\u4eba", "\u4f1a\u6b7b\u4eba", "\u771f\u4f1a\u6b7b",
            "\u65e7\u5357\u6e20", "\u836f\u6e23", "\u836f\u5473", "\u836f\u8017",
            "\u89c1\u4e86\u5730", "\u4eba\u547d", "\u75c5\u4eba",
            # Live ch2 paraphrase-friendly pressure roots (countdown / body cost / dark entry / false calm)
            "半天", "最多", "撑", "药效", "假药", "药是假", "令牌", "血契", "反噬",
            "嵌", "没入", "烧", "烫", "灼", "半开", "黑洞", "停棺", "棺材", "火印",
            "纹路", "红线", "死", "命", "来不及", "退路", "门半开", "看不清",
            "不给", "来人", "脚步声", "敲门", "追兵", "期限", "天亮前", "三天内",
        )
        hook_hits = [marker for marker in (*hook_markers, *zh_hook_markers) if marker in ending_excerpt]
        # Strong multi-char narrative pressure signals that often appear without classic cliffhangers.
        narrative_pressure_markers = (
            "最多", "半天", "药效", "假药", "药是假", "血契", "反噬", "没入", "嵌进", "没入皮肤",
            "停棺", "棺材铺", "火印", "半开着", "黑洞洞", "看不清", "撑多久", "来不及",
            "退路", "追兵", "倒计时", "三天内", "天亮前", "会死", "死人", "门半开",
        )
        narrative_hits = [marker for marker in narrative_pressure_markers if marker in ending_excerpt]
        # Countdown / deadline phrasing: "最多半天" / "只能撑" / "药效…最多"
        deadline_patterns = (
            r"最多.{0,6}(半天|一天|一晚|一夜|三天|一时|一刻|一炷香)",
            r"(半天|一天|一晚|一夜|三天).{0,4}(最多|撑|顶)",
            r"(撑|顶).{0,4}(多久|不住|不过)",
            r"(药效|药).{0,8}(最多|假|撑|顶)",
            r"(令牌|血契|铁牌).{0,12}(烫|烧|嵌|没入|反噬)",
            r"(门|铺|店).{0,6}(半开|洞开|黑洞|看不清)",
            r"(退路|来不及|追|杀|死).{0,8}(了|吧|吗|？|\?)",
        )
        deadline_hits = []
        for pat in deadline_patterns:
            if re.search(pat, ending_excerpt):
                deadline_hits.append(pat)
        closure_hits = [marker for marker in closure_markers if marker in ending_excerpt]
        mission_hook_pass = bool(mission_hook_hits and (hook_hits or narrative_hits or deadline_hits))
        # Soft deliver match: if deliver terms hit earlier body but ending still carries countdown/risk, accept.
        soft_deliver = bool(deliver_hits)
        if not soft_deliver and deliver_to_next:
            # Prefer short roots from deliver phrases for ending paraphrase match.
            soft_roots = []
            for item in deliver_to_next if isinstance(deliver_to_next, list) else [deliver_to_next]:
                raw = str(item or "").strip()
                for root in (
                    "血契", "反噬", "棺材", "停棺", "火印", "药方", "药效", "令牌", "红线",
                    "驿站", "刻令", "三天", "半天", "顾棠", "林舟",
                ):
                    if root in raw:
                        soft_roots.append(root)
            soft_root_hits = [r for r in dict.fromkeys(soft_roots) if r in ending_excerpt]
            if len(soft_root_hits) >= 2:
                soft_deliver = True
                deliver_hits = list(deliver_hits) + [f"{r}~soft" for r in soft_root_hits[:4]]
        pressure_score = (
            (2 if soft_deliver else 0)
            + (2 if mission_hook_hits else 0)
            + min(3, len([h for h in hook_hits if h not in {"？", "?", "！", "!"}]))
            + min(3, len(narrative_hits))
            + (2 if deadline_hits else 0)
        )
        # Require more than bare punctuation; accept strong narrative/deadline pressure.
        strong_non_punct_hooks = [h for h in hook_hits if h not in {"？", "?", "！", "!"}]
        passed = bool(
            not closure_hits
            and (
                soft_deliver
                or len(strong_non_punct_hooks) >= 2
                or mission_hook_pass
                or len(narrative_hits) >= 2
                or (deadline_hits and (narrative_hits or strong_non_punct_hooks or mission_hook_hits))
                or pressure_score >= 3
            )
        )
        combined_hits = list(deliver_hits) + list(mission_hook_hits) + list(strong_non_punct_hooks) + list(narrative_hits)
        if deadline_hits:
            combined_hits.append("deadline_pattern")
        return {
            "ending_pressure_passed": passed,
            "ending_pressure_hits": combined_hits[:10],
            "mission_hook_hits": mission_hook_hits[:6],
            "flat_closure_markers": closure_hits[:4],
            "narrative_pressure_hits": narrative_hits[:6],
            "deadline_pattern_hits": len(deadline_hits),
            "ending_pressure_score": pressure_score,
        }

    @staticmethod
    def _estimate_static_description_runs(paragraphs: List[str]) -> Dict[str, int]:
        static_count = 0
        max_run = 0
        current_run = 0
        action_markers = ("说", "问", "答", "走", "退", "伸手", "抬头", "看", "盯", "推", "抓", "按", "转身", "决定", "发现", "却", "但")
        for paragraph in paragraphs:
            plain = "".join(str(paragraph or "").split())
            is_static = len(plain) >= 100 and not any(marker in plain for marker in action_markers)
            if is_static:
                static_count += 1
                current_run += 1
                max_run = max(max_run, current_run)
            else:
                current_run = 0
        return {"static_paragraph_count": static_count, "max_static_run": max_run}

    @staticmethod
    def _collect_focus_character_names(chapter_mission: Optional[dict]) -> List[str]:
        if not isinstance(chapter_mission, dict):
            return []
        placeholders = {"主角", "男主", "女主", "角色", "角色A", "角色B", "protagonist", "pov"}
        names: List[str] = []
        seen = set()

        def add_name(value: Any) -> None:
            if not value:
                return
            if isinstance(value, dict):
                for item in value.values():
                    add_name(item)
                return
            if isinstance(value, list):
                for item in value:
                    add_name(item)
                return
            text = str(value).strip()
            if not text:
                return
            for raw in re.split(r"[，。；、,;\s/|]+", text):
                name = raw.strip("：:- ").strip()
                if not (2 <= len(name) <= 12):
                    continue
                if name in placeholders or name.lower() in placeholders:
                    continue
                if name not in seen:
                    seen.add(name)
                    names.append(name)

        add_name(chapter_mission.get("focus_characters"))
        add_name(chapter_mission.get("character_focus"))
        add_name(chapter_mission.get("pov_character"))
        for scene in chapter_mission.get("scene_list") or []:
            if isinstance(scene, dict):
                add_name(scene.get("characters"))
        return names[:8]

    @staticmethod
    def _evaluate_repetition_risk(paragraphs: List[str], *, word_count: int) -> Dict[str, Any]:
        normalized: List[str] = []
        for paragraph in paragraphs:
            plain = re.sub(r"\s+", "", str(paragraph or ""))
            if len(plain) >= 30:
                normalized.append(plain)
        counts: Dict[str, int] = {}
        for paragraph in normalized:
            counts[paragraph] = counts.get(paragraph, 0) + 1
        repeated = [(text, count) for text, count in counts.items() if count > 1]
        repeated_instances = sum(count - 1 for _text, count in repeated)
        max_repeat = max((count for _text, count in repeated), default=1)
        longest_repeated = max((len(text) for text, _count in repeated), default=0)
        repeated_ratio = round(repeated_instances / max(1, len(normalized)), 4)
        risk = bool(
            word_count >= 800
            and repeated
            and (
                (max_repeat >= 3 and longest_repeated >= 30)
                or (repeated_instances >= 2 and repeated_ratio >= 0.3 and longest_repeated >= 80)
            )
        )
        return {
            "repetition_risk": risk,
            "repeated_paragraph_count": len(repeated),
            "repeated_paragraph_instances": repeated_instances,
            "max_repeated_paragraph_count": max_repeat,
            "repeated_paragraph_ratio": repeated_ratio,
            "longest_repeated_paragraph_chars": longest_repeated,
            "repeated_paragraph_examples": [text[:120] for text, _count in repeated[:3]],
        }

    @classmethod
    def _remove_exact_repeated_paragraphs(cls, content: str) -> Tuple[str, Dict[str, Any]]:
        lines = str(content or "").splitlines()
        seen: Dict[str, int] = {}
        kept: List[str] = []
        removed_examples: List[str] = []
        removed_count = 0
        for line in lines:
            plain = re.sub(r"\s+", "", str(line or ""))
            if len(plain) >= 30:
                seen[plain] = seen.get(plain, 0) + 1
                if seen[plain] > 1:
                    removed_count += 1
                    if len(removed_examples) < 3:
                        removed_examples.append(plain[:120])
                    continue
            kept.append(line)
        cleaned = "\n".join(kept).strip()
        return cleaned, {
            "removed_count": removed_count,
            "removed_examples": removed_examples,
        }

    @classmethod
    def _remove_exact_repeated_paragraphs_with_floor(
        cls,
        *,
        content: str,
        chapter_mission: Optional[dict],
        target_word_count: int,
        min_word_count: int,
    ) -> Tuple[str, Dict[str, Any]]:
        lines = str(content or "").splitlines()
        preferred_floor = max(int(min_word_count or 0), int(int(target_word_count or 0) * 0.92))
        hard_floor = max(0, int(min_word_count or 0))
        removed_examples: List[str] = []
        removed_count = 0
        current = list(lines)

        def score(text_lines: List[str]) -> Dict[str, Any]:
            return cls._score_story_quality_candidate(
                content="\n".join(text_lines).strip(),
                violations=[],
                chapter_mission=chapter_mission,
                target_word_count=target_word_count,
                min_word_count=min_word_count,
            )

        current_score = score(current)
        while current_score.get("repetition_risk"):
            groups: Dict[str, List[int]] = {}
            for index, line in enumerate(current):
                plain = re.sub(r"\s+", "", str(line or ""))
                if len(plain) >= 30:
                    groups.setdefault(plain, []).append(index)
            duplicate_groups = [
                (plain, indexes)
                for plain, indexes in groups.items()
                if len(indexes) > 1
            ]
            if not duplicate_groups:
                break
            duplicate_groups.sort(key=lambda item: (len(item[1]), len(item[0])), reverse=True)
            plain, indexes = duplicate_groups[0]
            remove_index = indexes[-1]
            candidate = current[:remove_index] + current[remove_index + 1:]
            candidate_score = score(candidate)
            candidate_words = int(candidate_score.get("word_count") or 0)
            if candidate_words < hard_floor:
                break
            current = candidate
            current_score = candidate_score
            removed_count += 1
            if len(removed_examples) < 3:
                removed_examples.append(plain[:120])

        cleaned = "\n".join(current).strip()
        return cleaned, {
            "removed_count": removed_count,
            "removed_examples": removed_examples,
            "preferred_floor": preferred_floor,
            "hard_floor": hard_floor,
            "after_repetition_risk": current_score.get("repetition_risk"),
            "after_word_count": current_score.get("word_count"),
        }

    @classmethod
    def _apply_deterministic_cleanup(
        cls,
        *,
        content: str,
        chapter_mission: Optional[dict],
        target_word_count: int,
        min_word_count: int,
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        before = cls._score_story_quality_candidate(
            content=content,
            violations=[],
            chapter_mission=chapter_mission,
            target_word_count=target_word_count,
            min_word_count=min_word_count,
        )
        if not before.get("repetition_risk"):
            return content, None
        cleaned, cleanup = cls._remove_exact_repeated_paragraphs(content)
        if not cleanup.get("removed_count") or not cleaned.strip():
            return content, None
        after = cls._score_story_quality_candidate(
            content=cleaned,
            violations=[],
            chapter_mission=chapter_mission,
            target_word_count=target_word_count,
            min_word_count=min_word_count,
        )
        if after.get("word_count_below_min"):
            bounded_cleaned, bounded_cleanup = cls._remove_exact_repeated_paragraphs_with_floor(
                content=content,
                chapter_mission=chapter_mission,
                target_word_count=target_word_count,
                min_word_count=min_word_count,
            )
            if bounded_cleanup.get("removed_count") and bounded_cleaned.strip():
                bounded_after = cls._score_story_quality_candidate(
                    content=bounded_cleaned,
                    violations=[],
                    chapter_mission=chapter_mission,
                    target_word_count=target_word_count,
                    min_word_count=min_word_count,
                )
                if not bounded_after.get("word_count_below_min") and not bounded_after.get("repetition_risk"):
                    return bounded_cleaned, {
                        "applied": True,
                        "type": "bounded_exact_repeated_paragraph_cleanup",
                        "removed_count": bounded_cleanup.get("removed_count"),
                        "removed_examples": bounded_cleanup.get("removed_examples"),
                        "before_word_count": before.get("word_count"),
                        "after_word_count": bounded_after.get("word_count"),
                        "before_repetition_risk": before.get("repetition_risk"),
                        "after_repetition_risk": bounded_after.get("repetition_risk"),
                        "before_repeated_paragraph_count": before.get("repeated_paragraph_count"),
                        "after_repeated_paragraph_count": bounded_after.get("repeated_paragraph_count"),
                        "preferred_floor": bounded_cleanup.get("preferred_floor"),
                    }
            return content, {
                "applied": False,
                "reason": "cleanup_would_drop_below_min_word_count",
                "removed_count": cleanup.get("removed_count"),
                "before_word_count": before.get("word_count"),
                "after_word_count": after.get("word_count"),
                "bounded_removed_count": bounded_cleanup.get("removed_count"),
                "bounded_after_word_count": bounded_cleanup.get("after_word_count"),
                "bounded_after_repetition_risk": bounded_cleanup.get("after_repetition_risk"),
            }
        if after.get("score", 0) + 80 < before.get("score", 0) and after.get("repetition_risk"):
            return content, {
                "applied": False,
                "reason": "cleanup_did_not_improve_repetition_enough",
                "removed_count": cleanup.get("removed_count"),
                "before_score": before.get("score"),
                "after_score": after.get("score"),
            }
        return cleaned, {
            "applied": True,
            "type": "exact_repeated_paragraph_cleanup",
            "removed_count": cleanup.get("removed_count"),
            "removed_examples": cleanup.get("removed_examples"),
            "before_word_count": before.get("word_count"),
            "after_word_count": after.get("word_count"),
            "before_repetition_risk": before.get("repetition_risk"),
            "after_repetition_risk": after.get("repetition_risk"),
            "before_repeated_paragraph_count": before.get("repeated_paragraph_count"),
            "after_repeated_paragraph_count": after.get("repeated_paragraph_count"),
        }

    @classmethod
    def _score_fallback_candidate(
        cls,
        *,
        content: str,
        violations: List[Dict[str, Any]],
        chapter_mission: Optional[dict],
    ) -> Dict[str, Any]:
        text = str(content or "")
        condensed = "".join(text.split())
        word_count = len(condensed)
        paragraphs = [segment for segment in text.splitlines() if segment.strip()]
        paragraph_count = len(paragraphs)
        dialogue_markers = sum(text.count(marker) for marker in ("“", "”", "「", "」", "『", "』", '"'))
        mission_keywords = cls._collect_fallback_mission_keywords(chapter_mission)
        mission_hits = [keyword for keyword in mission_keywords if keyword and keyword in condensed]
        expected_dialogue = cls._chapter_mission_expects_dialogue(chapter_mission)
        ending_excerpt = condensed[-220:]
        hook_markers = ("？", "！", "?", "!", "忽然", "却", "竟", "脚步", "敲门", "消息", "声音", "目光", "门外", "下一瞬")
        ending_hook = any(marker in ending_excerpt for marker in hook_markers)
        static_description_risk = dialogue_markers == 0 and paragraph_count <= 4 and word_count >= 1800

        score = 0
        score += len(mission_hits) * 180
        score += min(paragraph_count, 12) * 18
        score += min(dialogue_markers, 10) * 12
        score += 80 if ending_hook else 0
        score += min(word_count, 2400) // 50
        score -= len(violations) * 500
        score -= 160 if static_description_risk else 0

        return {
            "score": score,
            "word_count": word_count,
            "paragraph_count": paragraph_count,
            "dialogue_marker_count": dialogue_markers,
            "guardrail_violation_count": len(violations),
            "mission_hit_count": len(mission_hits),
            "mission_hits": mission_hits[:8],
            "expected_dialogue": expected_dialogue,
            "ending_hook_detected": ending_hook,
            "static_description_risk": static_description_risk,
        }

    @staticmethod
    def _sanitize_markdown_presentation(content: str) -> str:
        """Strip decorative Markdown wrappers without discarding narrative text.

        Models often wrap dialogue/action lines in **bold**, or prefix a normal
        chapter title heading such as ``# 第13章 借阅人回拨``. Treating those as
        fatal chapter artifacts forces full provider recovery (scene-split regen)
        and wastes minutes. Real structural artifacts (scene labels, JSON mission
        dumps, expand notes) remain detectable after this cleanup.
        """
        text = str(content or "")
        if not text:
            return text
        structural_line = re.compile(
            r"(场景\s*\d+|扩写部分|章节导演脚本|写作指令|质量方向|基础质量底线|修改说明|修订说明)",
            re.IGNORECASE,
        )
        # Presentation-only chapter chrome. Strip so a valid first draft is not
        # discarded as FIRST_DRAFT_ARTIFACT_MARKERS after trim/clamp already succeeded.
        presentation_heading = re.compile(
            r"^\s{0,3}#{1,6}\s*(?:"
            r"第\s*[0-9一二三四五六七八九十百千零〇两]+\s*[章节回]\b.*"
            r"|Chapter\s+\d+\b.*"
            r"|(?:完整)?(?:本章)?正文\s*$"
            r"|完整章节正文\s*$"
            r")",
            re.IGNORECASE,
        )
        cleaned_lines: List[str] = []
        whole_bold = re.compile(r"^(\s*)\*\*(.+?)\*\*(\s*)$")
        for raw_line in text.splitlines():
            if presentation_heading.match(raw_line) and not structural_line.search(raw_line):
                continue
            if structural_line.search(raw_line):
                cleaned_lines.append(raw_line)
                continue
            match = whole_bold.match(raw_line)
            if match:
                cleaned_lines.append(f"{match.group(1)}{match.group(2)}{match.group(3)}")
                continue
            # Unwrap remaining inline bold/italic emphasis used as decoration.
            line = re.sub(r"\*\*(?!\s)(.+?)(?<!\s)\*\*", r"\1", raw_line)
            line = re.sub(r"(?<!\*)\*(?!\s)([^*\n]+?)(?<!\s)\*(?!\*)", r"\1", line)
            cleaned_lines.append(line)
        cleaned = "\n".join(cleaned_lines)
        return cleaned.lstrip("\n")

    @staticmethod
    def _detect_chapter_artifact_markers(content: str) -> Dict[str, Any]:

        examples: List[str] = []
        patterns = (
            re.compile(r"^\s*\*\*.+\*\*\s*$"),
            # Bare chapter titles ("# 第13章 借阅人回拨") are presentation chrome,
            # not structural artifacts; they are stripped in _sanitize_markdown_presentation.
            re.compile(
                r"^\s{0,3}#{1,6}\s*(?:场景|scene|扩写|修订|完整章节正文|本章正文|章节大纲|章节导演)",
                re.IGNORECASE,
            ),
            re.compile(r"^\s*\[[^\]]*(?:章节导演脚本|写作任务|上下文|历史摘要|长篇上下文|蓝图)[^\]]*\]\([^)]*\)", re.IGNORECASE),
            re.compile(r"^\s*\{.*\"(?:pov|chapter_purpose|scene_list|continuity_anchor|dialogue_strategy)\"", re.IGNORECASE),
            re.compile(r"^\s*(?:【|\*\*【)?\s*场景\s*\d+\s*(?:[|｜:：】]|$)"),
            re.compile(r"^\s*场景\s*\d+\s*(?:[|｜:：]|$)"),
            re.compile(r"^\s*(?:【|\*\*【)?\s*扩写部分\s*\d*\s*(?:[|｜:：】]|$)"),
            re.compile(r"^\s*(?:修改说明|修订说明|以下是|本章正文|完整章节正文)\s*[:：]"),
            re.compile(r"(?:写作指令|写作要求|质量方向|基础质量底线|首稿执行要求)\s*[:：]"),
        )
        inline_markers = (
            "扩写部分",
            "[章节导演脚本]",
            "章节导演脚本",
            "\"chapter_purpose\"",
            "\"scene_list\"",
            "\"continuity_anchor\"",
            "约120字",
            "约 120 字",
            "精修后的片段正文",
            "修订后的完整章节正文",
            "这是他来之前的指示",
            "这是写作指令",
            "这是写作要求",
            "开篇必须明确",
            "禁止出现 Markdown",
            "禁止出现Markdown",
            "只输出沉浸式正文",
            "不要把黑影写成",
            "不要写成已死",
            "质量方向：",
            "基础质量底线：",
        )
        for raw_line in str(content or "").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if any(pattern.search(line) for pattern in patterns) or any(marker in line for marker in inline_markers):
                examples.append(line[:120])
            if len(examples) >= 6:
                break
        return {
            "chapter_artifact_markers": bool(examples),
            "chapter_artifact_marker_count": len(examples),
            "chapter_artifact_marker_examples": examples,
        }

    @classmethod
    def _score_story_quality_candidate(
        cls,
        *,
        content: str,
        violations: List[Dict[str, Any]],
        chapter_mission: Optional[dict],
        target_word_count: Optional[int] = None,
        min_word_count: Optional[int] = None,
    ) -> Dict[str, Any]:
        text = str(content or "")
        condensed = "".join(text.split())
        word_count = len(condensed)
        target_floor = max(0, int(target_word_count or 0))
        minimum_floor = max(0, int(min_word_count or 0))
        if target_floor and minimum_floor > target_floor:
            minimum_floor = target_floor
        preferred_floor = max(minimum_floor, int(target_floor * 0.92)) if target_floor else minimum_floor
        word_count_below_min = bool(minimum_floor and word_count < minimum_floor)
        word_count_far_below_target = bool(preferred_floor and word_count < preferred_floor)
        upper_target = int(target_floor * 2.0) if target_floor and target_floor <= 2500 else (int(target_floor * 1.6) if target_floor else 0)
        word_count_far_above_target = bool(upper_target and word_count > upper_target)
        paragraphs = [segment for segment in text.splitlines() if segment.strip()]
        paragraph_count = len(paragraphs)
        dialogue_markers = sum(text.count(marker) for marker in ("“", "”", "「", "」", "『", "』", '"'))
        mission_keywords = cls._collect_fallback_mission_keywords(chapter_mission)
        mission_hits = [keyword for keyword in mission_keywords if keyword and keyword in condensed]
        focus_character_names = cls._collect_focus_character_names(chapter_mission)
        focus_character_hits = [name for name in focus_character_names if name and name in condensed]
        expected_dialogue = cls._chapter_mission_expects_dialogue(chapter_mission)
        scene_fulfillment = cls._evaluate_scene_fulfillment(chapter_mission, condensed)
        dialogue_state = cls._evaluate_dialogue_changes_state(
            text,
            expected_dialogue=expected_dialogue,
            dialogue_markers=dialogue_markers,
        )
        ending_pressure = cls._evaluate_ending_pressure(condensed, chapter_mission)
        ending_hook = bool(ending_pressure.get("ending_pressure_passed"))
        static_runs = cls._estimate_static_description_runs(paragraphs)
        event_density = cls._evaluate_event_density(text, word_count=word_count)
        repetition = cls._evaluate_repetition_risk(paragraphs, word_count=word_count)
        artifact_markers = cls._detect_chapter_artifact_markers(text)
        static_description_risk = bool(
            (dialogue_markers == 0 and paragraph_count <= 4 and word_count >= 1200)
            or (word_count >= 1200 and static_runs.get("max_static_run", 0) >= 2)
            or (word_count >= 2000 and event_density.get("event_density_passed") is False and static_runs.get("max_static_run", 0) >= 2)
            or (
                word_count >= 1600
                and dialogue_markers > 0
                and static_runs.get("max_static_run", 0) >= 2
                and int(static_runs.get("static_paragraph_count") or 0) >= 3
            )
        )
        scene_rate = float(scene_fulfillment.get("scene_fulfillment_rate", 1.0) or 0)
        scene_structure_rate = float(scene_fulfillment.get("scene_structure_rate", 1.0) or 0)
        scene_count = int(scene_fulfillment.get("scene_count") or 0)

        score = 0
        score += len(mission_hits) * 180
        score += min(paragraph_count, 12) * 18
        score += min(dialogue_markers, 10) * 12
        score += int(scene_rate * 280) if scene_count else 80
        score += int(scene_structure_rate * 140) if scene_count else 40
        score += 140 if dialogue_state.get("dialogue_changes_state") else -140
        score += 140 if ending_hook else -120
        score += min(int(event_density.get("progression_unit_count") or 0), 18) * 16
        score += 80 if event_density.get("event_density_passed") else -180
        score += 60 if event_density.get("state_change_interval_passed") else -130
        score += 90 if event_density.get("long_chapter_density_passed") else -180
        score += min(word_count, 2400) // 50
        score -= len(violations) * 500
        score -= 260 if static_description_risk else 0
        score -= 420 if repetition.get("repetition_risk") else 0
        score -= 480 if artifact_markers.get("chapter_artifact_markers") else 0
        score -= 240 if focus_character_names and not focus_character_hits and word_count >= 1200 else 0
        score -= 620 if word_count_below_min else 0
        score -= 520 if word_count_far_above_target else 0
        score -= 180 if word_count_far_below_target and not word_count_below_min else 0

        quality_metric_snapshot = {
            "word_count": word_count,
            "target_word_count": target_floor,
            "min_word_count": minimum_floor,
            "preferred_word_floor": preferred_floor,
            "upper_word_ceiling": upper_target,
            "word_count_below_min": word_count_below_min,
            "word_count_far_above_target": word_count_far_above_target,
            "word_count_far_below_target": word_count_far_below_target,
            "word_requirement_met": (not word_count_below_min) if minimum_floor else None,
            "paragraph_count": paragraph_count,
            "mission_hit_count": len(mission_hits),
            "mission_keyword_count": len(mission_keywords),
            "focus_character_names": focus_character_names,
            "focus_character_hit_count": len(focus_character_hits),
            "missing_focus_characters": [name for name in focus_character_names if name not in focus_character_hits],
            "focus_character_missing": bool(focus_character_names and not focus_character_hits and word_count >= 1200),
            "scene_fulfillment_rate": scene_rate,
            "fulfilled_scene_count": scene_fulfillment.get("fulfilled_scene_count", 0),
            "scene_count": scene_count,
            "scene_structure_rate": scene_structure_rate,
            "structure_passed_scene_count": scene_fulfillment.get("structure_passed_scene_count", 0),
            "dialogue_changes_state": bool(dialogue_state.get("dialogue_changes_state")),
            "dialogue_state_change_markers": dialogue_state.get("state_change_marker_count", 0),
            "ending_pressure_passed": ending_hook,
            "static_description_risk": static_description_risk,
            "static_paragraph_count": static_runs.get("static_paragraph_count", 0),
            "max_static_run": static_runs.get("max_static_run", 0),
            "event_density_passed": bool(event_density.get("event_density_passed")),
            "long_chapter_density_passed": bool(event_density.get("long_chapter_density_passed")),
            "state_change_interval_passed": bool(event_density.get("state_change_interval_passed")),
            "progression_unit_count": event_density.get("progression_unit_count", 0),
            "story_unit_count": event_density.get("story_unit_count", 0),
            "progression_unit_rate": event_density.get("progression_unit_rate", 0),
            "event_density_per_1000": event_density.get("event_density_per_1000", 0),
            "state_change_window_pass_rate": event_density.get("state_change_window_pass_rate", 0),
            "max_plain_unit_run": event_density.get("max_plain_unit_run", 0),
            **repetition,
            **artifact_markers,
        }
        quality_issue_summary = cls._build_quality_issue_summary(story_guard=quality_metric_snapshot)
        quality_metric_snapshot["quality_issue_summary"] = quality_issue_summary
        quality_metric_snapshot["quality_issue_codes"] = quality_issue_summary.get("codes", [])
        quality_metric_snapshot["quality_issue_labels"] = quality_issue_summary.get("labels", [])

        return {
            "score": score,
            "word_count": word_count,
            "target_word_count": target_floor,
            "min_word_count": minimum_floor,
            "preferred_word_floor": preferred_floor,
            "upper_word_ceiling": upper_target,
            "word_count_below_min": word_count_below_min,
            "word_count_far_above_target": word_count_far_above_target,
            "word_count_far_below_target": word_count_far_below_target,
            "word_requirement_met": (not word_count_below_min) if minimum_floor else None,
            "paragraph_count": paragraph_count,
            "dialogue_marker_count": dialogue_markers,
            "guardrail_violation_count": len(violations),
            "mission_hit_count": len(mission_hits),
            "mission_hits": mission_hits[:8],
            "mission_keyword_count": len(mission_keywords),
            "focus_character_names": focus_character_names,
            "focus_character_hit_count": len(focus_character_hits),
            "missing_focus_characters": [name for name in focus_character_names if name not in focus_character_hits],
            "focus_character_missing": bool(focus_character_names and not focus_character_hits and word_count >= 1200),
            "expected_dialogue": expected_dialogue,
            "ending_hook_detected": ending_hook,
            "static_description_risk": static_description_risk,
            "scene_fulfillment_rate": scene_rate,
            "fulfilled_scene_count": scene_fulfillment.get("fulfilled_scene_count", 0),
            "scene_count": scene_count,
            "scene_structure_rate": scene_structure_rate,
            "structure_passed_scene_count": scene_fulfillment.get("structure_passed_scene_count", 0),
            "scene_fulfillment": scene_fulfillment,
            "dialogue_changes_state": dialogue_state.get("dialogue_changes_state"),
            "dialogue_state_change_markers": dialogue_state.get("state_change_marker_count", 0),
            "ending_pressure_passed": ending_pressure.get("ending_pressure_passed"),
            "ending_pressure": ending_pressure,
            "static_description_runs": static_runs,
            "event_density": event_density,
            "event_density_passed": event_density.get("event_density_passed"),
            "long_chapter_density_passed": event_density.get("long_chapter_density_passed"),
            "state_change_interval_passed": event_density.get("state_change_interval_passed"),
            "progression_unit_count": event_density.get("progression_unit_count", 0),
            "event_density_per_1000": event_density.get("event_density_per_1000", 0),
            "state_change_window_pass_rate": event_density.get("state_change_window_pass_rate", 0),
            **repetition,
            **artifact_markers,
            "quality_issue_summary": quality_issue_summary,
            "quality_issue_codes": quality_issue_summary.get("codes", []),
            "quality_issue_labels": quality_issue_summary.get("labels", []),
            "quality_metric_snapshot": quality_metric_snapshot,
        }

    @classmethod
    def _fallback_select_best_version(
        cls,
        versions: List[Dict[str, Any]],
        chapter_mission: Optional[dict] = None,
    ) -> Tuple[int, Dict[str, Any]]:
        scored: List[Tuple[int, int, Dict[str, Any]]] = []
        for idx, variant in enumerate(versions):
            metadata = dict(variant.get("metadata") or {})
            guardrail = metadata.get("guardrail") or {}
            violations = guardrail.get("violations") or []
            content = variant.get("content") or ""
            candidate_summary = cls._score_story_quality_candidate(
                content=content,
                violations=violations,
                chapter_mission=chapter_mission,
            )
            candidate_summary.update(
                {
                    "index": idx,
                    "guardrail_passed": bool(guardrail.get("passed", not violations)),
                }
            )
            scored.append((candidate_summary["score"], idx, candidate_summary))

        scored.sort(key=lambda item: (item[0], item[2]["guardrail_passed"], item[2]["word_count"] >= 1000, item[2]["mission_hit_count"]), reverse=True)
        best = scored[0] if scored else (0, 0, {"index": 0, "word_count": 0, "guardrail_passed": False, "guardrail_violation_count": 0})
        return best[1], {
            "strategy": "heuristic_story_progression_guardrails",
            "candidates": [item[2] for item in scored],
        }


    @staticmethod
    def _coerce_float(value, default=0.0) -> float:
        if value is None:
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default


    @staticmethod
    def _count_words(text: str) -> int:
        return len("".join((text or "").split()))
        return len("".join((text or "").split()))

