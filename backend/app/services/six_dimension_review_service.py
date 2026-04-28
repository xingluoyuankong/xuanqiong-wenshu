"""Six-dimension chapter review service."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from .constitution_service import ConstitutionService
from .writer_persona_service import WriterPersonaService
from .llm_service import LLMService
from .prompt_service import PromptService
from ..utils.json_utils import remove_think_tags, sanitize_json_like_text, unwrap_markdown_json

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReviewDimensionSpec:
    key: str
    label: str
    focus: List[str]
    severity_weight: float = 1.0


class SixDimensionReviewService:
    """Review a chapter from six dimensions and normalize the result for pipeline use."""

    DIMENSIONS: List[ReviewDimensionSpec] = [
        ReviewDimensionSpec(
            key='constitution_compliance',
            label='宪法/禁忌合规',
            focus=[
                '是否触碰项目禁忌、题材边界或用户明确禁止内容',
                '是否违背项目既定价值观、角色底线或世界规则',
                '是否出现不必要的擦边、暴力失控、猎奇内容',
            ],
            severity_weight=1.4,
        ),
        ReviewDimensionSpec(
            key='internal_consistency',
            label='章节内一致性',
            focus=[
                '同一章节内部的时间线、因果链、空间关系是否自洽',
                '人物行动、情绪、认知是否前后一致',
                '是否存在明显逻辑跳步或信息凭空出现',
            ],
            severity_weight=1.35,
        ),
        ReviewDimensionSpec(
            key='cross_chapter_consistency',
            label='跨章节连续性',
            focus=[
                '是否承接上一章结尾的事件、情绪和关系变化',
                '人物状态、伤势、线索、伏笔是否延续正确',
                '是否出现跨章设定遗失、人物失忆、剧情断裂',
            ],
            severity_weight=1.45,
        ),
        ReviewDimensionSpec(
            key='plan_compliance',
            label='章节规划符合度',
            focus=[
                '是否完成本章该完成的情节任务',
                '是否偏离章节计划、故事主线或当前卷目标',
                '推进速度是否过快/过慢导致计划执行失衡',
            ],
            severity_weight=1.2,
        ),
        ReviewDimensionSpec(
            key='style_compliance',
            label='文风符合度',
            focus=[
                '文风是否贴合当前项目人设、叙事口吻与题材气质',
                '是否有明显 AI 套话、空泛总结、解释性灌输',
                '语言是否具有现场感、画面感和角色味道',
            ],
            severity_weight=1.0,
        ),
        ReviewDimensionSpec(
            key='conflict_detection',
            label='冲突与风险检测',
            focus=[
                '当前章节的矛盾、压力、悬念是否成立',
                '是否存在削弱张力的提前和解、无代价解决、冲突失焦',
                '是否有会影响后续创作的重大风险点需要优先修正',
            ],
            severity_weight=1.15,
        ),
    ]

    SEVERITY_ORDER = {'critical': 0, 'major': 1, 'warning': 1, 'minor': 2, 'info': 3}

    def __init__(
        self,
        db: AsyncSession,
        llm_service: LLMService,
        prompt_service: PromptService,
        constitution_service: ConstitutionService,
        writer_persona_service: WriterPersonaService,
    ):
        self.db = db
        self.llm_service = llm_service
        self.prompt_service = prompt_service
        self.constitution_service = constitution_service
        self.writer_persona_service = writer_persona_service

    async def review_chapter(
        self,
        project_id: str,
        chapter_number: int,
        chapter_title: str,
        chapter_content: str,
        chapter_plan: Optional[str] = None,
        previous_summary: Optional[str] = None,
        character_profiles: Optional[str] = None,
        world_setting: Optional[str] = None,
    ) -> Dict[str, Any]:
        constitution = await self.constitution_service.get_constitution(project_id)
        persona = await self.writer_persona_service.get_active_persona(project_id)
        prompt_template = await self.prompt_service.get_prompt('six_dimension_review')

        prompt = self._build_prompt(
            chapter_number=chapter_number,
            chapter_title=chapter_title,
            chapter_content=chapter_content,
            constitution_context=self.constitution_service.get_constitution_context(constitution),
            persona_context=self.writer_persona_service.get_persona_context(persona),
            chapter_plan=chapter_plan,
            previous_summary=previous_summary,
            character_profiles=character_profiles,
            world_setting=world_setting,
            prompt_template=prompt_template,
        )

        try:
            response = await self.llm_service.generate(
                prompt=prompt,
                system_prompt=(
                    '你是一位严格的长篇连载小说总编审。'
                    '请从六个维度输出结构化 JSON，少而准地指出真正影响阅读和连载稳定性的问题。'
                ),
            )
            parsed = self._parse_response(response)
            if parsed:
                return parsed
        except Exception as exc:
            logger.warning('Six-dimension review failed for project=%s chapter=%s: %s', project_id, chapter_number, exc)

        return self._create_default_result('六维审查已回退到默认结果')

    async def quick_review(self, project_id: str, chapter_content: str) -> Dict[str, Any]:
        results: Dict[str, Any] = {
            'overall_score': 100,
            'quick_checks': [],
        }

        constitution = await self.constitution_service.get_constitution(project_id)
        if constitution and constitution.forbidden_content:
            for forbidden in constitution.forbidden_content:
                if forbidden and str(forbidden).lower() in chapter_content.lower():
                    results['quick_checks'].append({
                        'dimension': 'constitution_compliance',
                        'severity': 'critical',
                        'description': f'检测到禁忌内容：{forbidden}',
                    })
                    results['overall_score'] -= 20

        style_result = await self.writer_persona_service.check_style_compliance(project_id, chapter_content)
        if not style_result.get('compliance', True):
            for issue in style_result.get('issues', []) or []:
                if str(issue.get('severity') or '').lower() in {'warning', 'major'}:
                    results['quick_checks'].append({
                        'dimension': 'style_compliance',
                        'severity': issue.get('severity', 'warning'),
                        'description': issue.get('description', '发现文风偏移'),
                    })
                    results['overall_score'] -= 5

        results['overall_score'] = max(0, int(results['overall_score']))
        results['passed'] = results['overall_score'] >= 60
        return results

    def aggregate_issues(self, review_result: Dict[str, Any]) -> List[Dict[str, Any]]:
        issues: List[Dict[str, Any]] = []
        dimensions = review_result.get('dimensions', {}) or {}
        for dim_name, dim_data in dimensions.items():
            for raw_issue in dim_data.get('issues', []) or []:
                if not isinstance(raw_issue, dict):
                    continue
                issue = self._normalize_issue(raw_issue, dim_name)
                issues.append(issue)
        issues.sort(key=lambda item: self.SEVERITY_ORDER.get(str(item.get('severity') or 'info').lower(), 9))
        return issues

    def get_priority_fixes(self, review_result: Dict[str, Any], max_count: int = 5) -> List[str]:
        fixes: List[str] = []
        for issue in self.aggregate_issues(review_result):
            if str(issue.get('severity') or '').lower() not in {'critical', 'major', 'warning'}:
                continue
            suggestion = str(issue.get('suggestion') or issue.get('description') or '').strip()
            if suggestion and suggestion not in fixes:
                fixes.append(suggestion)
            if len(fixes) >= max_count:
                break
        return fixes

    def _build_prompt(
        self,
        *,
        chapter_number: int,
        chapter_title: str,
        chapter_content: str,
        constitution_context: str,
        persona_context: str,
        chapter_plan: Optional[str],
        previous_summary: Optional[str],
        character_profiles: Optional[str],
        world_setting: Optional[str],
        prompt_template: Optional[str],
    ) -> str:
        dimension_instructions = '\n'.join(
            f"[{spec.key}] {spec.label}\n- " + '\n- '.join(spec.focus)
            for spec in self.DIMENSIONS
        )
        default_prompt = f"""
请你对下面的章节执行六维审查，并输出 JSON。

[审查维度]
{dimension_instructions}

[章节信息]
- 章节序号：{chapter_number}
- 章节标题：{chapter_title or '未命名'}

[项目约束]
[宪法与禁忌]
{constitution_context or '（无）'}

[写作人格]
{persona_context or '（无）'}

[章节计划]
{chapter_plan or '（无章节计划）'}

[上一章摘要]
{previous_summary or '（无前文摘要）'}

[角色设定]
{character_profiles or '（无角色档案）'}

[世界设定]
{world_setting or '（无世界设定）'}

[待审查正文]
{chapter_content}

请输出 JSON：
{{
  "overall_score": 0,
  "summary": "一句话总结",
  "dimensions": {{
    "constitution_compliance": {{"score": 0, "issues": []}},
    "internal_consistency": {{"score": 0, "issues": []}},
    "cross_chapter_consistency": {{"score": 0, "issues": []}},
    "plan_compliance": {{"score": 0, "issues": []}},
    "style_compliance": {{"score": 0, "issues": []}},
    "conflict_detection": {{"score": 0, "issues": []}}
  }},
  "recommendations": [],
  "priority_fixes": []
}}

issue 字段尽量包含：severity、description、location、suggestion、confidence。
severity 仅允许：critical / major / minor / info。
""".strip()
        if not prompt_template:
            return default_prompt

        replacements = {
            '{{chapter_number}}': str(chapter_number),
            '{{chapter_title}}': chapter_title or '',
            '{{chapter_content}}': chapter_content,
            '{{constitution}}': constitution_context or '（无）',
            '{{writer_persona}}': persona_context or '（无）',
            '{{chapter_plan}}': chapter_plan or '（无章节计划）',
            '{{previous_summary}}': previous_summary or '（无前文摘要）',
            '{{character_profiles}}': character_profiles or '（无角色档案）',
            '{{world_setting}}': world_setting or '（无世界设定）',
            '{{dimension_instructions}}': dimension_instructions,
        }
        prompt = prompt_template
        for key, value in replacements.items():
            prompt = prompt.replace(key, value)
        if '{{dimension_instructions}}' not in prompt_template:
            prompt = f'{prompt}\n\n[审查维度]\n{dimension_instructions}'
        return prompt

    def _parse_response(self, response: Optional[str]) -> Optional[Dict[str, Any]]:
        content = sanitize_json_like_text(unwrap_markdown_json(remove_think_tags(response or '')))
        json_start = content.find('{')
        json_end = content.rfind('}') + 1
        if json_start < 0 or json_end <= json_start:
            return None
        try:
            payload = json.loads(content[json_start:json_end])
        except json.JSONDecodeError:
            return None
        return self._normalize_review_result(payload)

    def _normalize_review_result(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        dimensions_payload = payload.get('dimensions', {}) or {}
        normalized_dimensions: Dict[str, Dict[str, Any]] = {}
        aggregate_issues: List[Dict[str, Any]] = []
        weighted_score_sum = 0.0
        weight_sum = 0.0
        critical_count = 0
        warning_count = 0
        info_count = 0

        for spec in self.DIMENSIONS:
            raw = dimensions_payload.get(spec.key, {}) or {}
            score = self._normalize_score(raw.get('score'))
            issues = [self._normalize_issue(item, spec.key) for item in raw.get('issues', []) if isinstance(item, dict)]
            normalized_dimensions[spec.key] = {
                'label': spec.label,
                'score': score,
                'issues': issues,
            }
            aggregate_issues.extend(issues)
            weighted_score_sum += score * spec.severity_weight
            weight_sum += spec.severity_weight
            critical_count += sum(1 for item in issues if item['severity'] == 'critical')
            warning_count += sum(1 for item in issues if item['severity'] in {'major', 'warning'})
            info_count += sum(1 for item in issues if item['severity'] in {'minor', 'info'})

        overall_score = self._normalize_score(payload.get('overall_score'))
        if overall_score == 80 and weight_sum > 0:
            overall_score = round(weighted_score_sum / weight_sum, 1)

        recommendations = [str(item).strip() for item in payload.get('recommendations', []) if str(item).strip()]
        normalized = {
            'overall_score': overall_score,
            'dimensions': normalized_dimensions,
            'critical_issues_count': critical_count,
            'warning_issues_count': warning_count,
            'info_issues_count': info_count,
            'summary': str(payload.get('summary') or '六维审查完成').strip(),
            'priority_fixes': payload.get('priority_fixes') or self.get_priority_fixes({'dimensions': normalized_dimensions}),
            'recommendations': recommendations,
            'aggregated_issues': sorted(
                aggregate_issues,
                key=lambda item: self.SEVERITY_ORDER.get(item['severity'], 9),
            ),
        }
        return normalized

    def _normalize_issue(self, issue: Dict[str, Any], dimension: str) -> Dict[str, Any]:
        severity = str(issue.get('severity') or 'minor').strip().lower()
        if severity == 'warning':
            severity = 'major'
        if severity not in {'critical', 'major', 'minor', 'info'}:
            severity = 'minor'
        return {
            'dimension': dimension,
            'severity': severity,
            'description': str(issue.get('description') or issue.get('problem') or '').strip() or '发现待处理问题',
            'location': str(issue.get('location') or '').strip() or '未定位',
            'suggestion': str(issue.get('suggestion') or issue.get('fix') or '').strip(),
            'confidence': self._normalize_confidence(issue.get('confidence')),
            'example': str(issue.get('example') or '').strip(),
        }

    @staticmethod
    def _normalize_score(value: Any) -> float:
        try:
            score = float(value)
        except (TypeError, ValueError):
            return 80.0
        return max(0.0, min(100.0, round(score, 1)))

    @staticmethod
    def _normalize_confidence(value: Any) -> float:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            return 0.75
        return max(0.0, min(1.0, round(confidence, 2)))

    def _create_default_result(self, summary: str) -> Dict[str, Any]:
        return {
            'overall_score': 80,
            'dimensions': {
                spec.key: {'label': spec.label, 'score': 100, 'issues': []}
                for spec in self.DIMENSIONS
            },
            'critical_issues_count': 0,
            'warning_issues_count': 0,
            'info_issues_count': 0,
            'summary': summary,
            'priority_fixes': [],
            'recommendations': [],
            'aggregated_issues': [],
        }
