"""
增强型写作流程服务

集成所有新功能到写作流程中：
- 小说宪法系统
- Writer 人格系统
- 六维度审查
- 伏笔追踪
- 势力关系网络
"""
from typing import Optional, Dict, Any, List
import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from .constitution_service import ConstitutionService
from .writer_persona_service import WriterPersonaService
from .six_dimension_review_service import SixDimensionReviewService
from .foreshadowing_tracker_service import ForeshadowingTrackerService
from .faction_service import FactionService
from .llm_service import LLMService
from .prompt_service import PromptService

logger = logging.getLogger(__name__)


class EnhancedWritingFlow:
    """增强型写作流程服务"""

    def __init__(self, db: AsyncSession, llm_service: LLMService, prompt_service: PromptService):
        self.db = db
        self.llm_service = llm_service
        self.prompt_service = prompt_service
        
        # 初始化子服务
        self.constitution_service = ConstitutionService(db, llm_service, prompt_service)
        self.writer_persona_service = WriterPersonaService(db, llm_service, prompt_service)
        self.foreshadowing_service = ForeshadowingTrackerService(db, llm_service, prompt_service)
        self.faction_service = FactionService(db, prompt_service)
        
        # 六维度审查服务需要其他服务
        self.review_service = SixDimensionReviewService(
            db, llm_service, prompt_service,
            self.constitution_service, self.writer_persona_service
        )

    async def prepare_writing_context(
        self,
        project_id: str,
        chapter_number: int,
        chapter_outline: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        准备写作上下文，包含所有增强功能的上下文信息
        """
        context = {
            "constitution": None,
            "writer_persona": None,
            "foreshadowing_reminders": None,
            "faction_context": None,
            "version_style_hints": []
        }
        
        # 1. 获取小说宪法上下文
        try:
            constitution = await self.constitution_service.get_constitution(project_id)
            context["constitution"] = self.constitution_service.get_constitution_context(constitution)
            context["constitution_obj"] = constitution
        except Exception as e:
            logger.warning(f"获取小说宪法失败: {e}")
        
        # 2. 获取 Writer 人格上下文
        try:
            persona = await self.writer_persona_service.ensure_default_persona(project_id)
            context["writer_persona"] = self.writer_persona_service.get_persona_context(persona)
            context["writer_persona_obj"] = persona
            
            # 生成版本差异化风格提示
            for i in range(3):
                hint = self.writer_persona_service.get_version_style_hint(persona, i)
                context["version_style_hints"].append(hint)
        except Exception as e:
            logger.warning(f"获取 Writer 人格失败: {e}")
        
        # 3. 获取伏笔提醒
        try:
            reminders = await self.foreshadowing_service.get_foreshadowing_reminders(
                project_id,
                chapter_number,
                chapter_outline,
                user_id=user_id,
            )
            context["foreshadowing_reminders"] = reminders
        except Exception as e:
            logger.warning(f"获取伏笔提醒失败: {e}")
        
        # 4. 获取势力关系上下文
        try:
            faction_context = await self.faction_service.get_faction_context(project_id)
            context["faction_context"] = faction_context
        except Exception as e:
            logger.warning(f"获取势力关系失败: {e}")
        
        return context

    def build_enhanced_prompt_sections(
        self,
        base_sections: List[tuple],
        enhanced_context: Dict[str, Any]
    ) -> List[tuple]:
        """
        构建增强的提示词段落
        """
        sections = list(base_sections)
        
        # 添加小说宪法
        if enhanced_context.get("constitution"):
            sections.insert(0, ("[小说宪法](必须遵守)", enhanced_context["constitution"]))
        
        # 添加 Writer 人格
        if enhanced_context.get("writer_persona"):
            sections.insert(1, ("[Writer 人格](写作风格指导)", enhanced_context["writer_persona"]))
        
        # 添加伏笔提醒
        if enhanced_context.get("foreshadowing_reminders"):
            reminders = enhanced_context["foreshadowing_reminders"]
            if reminders.get("foreshadowings_to_develop"):
                reminder_text = self._format_foreshadowing_reminders(reminders)
                sections.append(("[伏笔提醒](本章需要发展的伏笔)", reminder_text))
        
        # 添加势力关系
        if enhanced_context.get("faction_context") and enhanced_context["faction_context"] != "（无势力设定）":
            sections.append(("[势力关系](参考信息)", enhanced_context["faction_context"]))
        
        return sections

    def _format_foreshadowing_reminders(self, reminders: Dict[str, Any]) -> str:
        """格式化伏笔提醒"""
        lines = []
        
        for fs in reminders.get("foreshadowings_to_develop", []):
            urgency_emoji = "🔴" if fs.get("urgency") == "high" else ("🟡" if fs.get("urgency") == "medium" else "🟢")
            lines.append(f"{urgency_emoji} {fs.get('name', '未命名')}")
            lines.append(f"   - 原因: {fs.get('reason', '无')}")
            lines.append(f"   - 建议: {fs.get('suggested_development', '无')}")
        
        return "\n".join(lines) if lines else "无需特别处理的伏笔"

    async def post_generation_review(
        self,
        project_id: str,
        chapter_number: int,
        chapter_title: str,
        chapter_content: str,
        chapter_plan: Optional[str] = None,
        previous_summary: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        生成后的审查流程
        """
        results = {
            "six_dimension_review": None,
            "constitution_compliance": None,
            "style_compliance": None,
            "overall_passed": True,
            "critical_issues": []
        }
        
        # 1. 六维度审查
        try:
            review_result = await self.review_service.review_chapter(
                project_id=project_id,
                chapter_number=chapter_number,
                chapter_title=chapter_title,
                chapter_content=chapter_content,
                chapter_plan=chapter_plan,
                previous_summary=previous_summary
            )
            results["six_dimension_review"] = review_result
            
            # 检查是否有严重问题
            if review_result.get("critical_issues_count", 0) > 0:
                results["overall_passed"] = False
                results["critical_issues"].extend(review_result.get("priority_fixes", []))
        except Exception as e:
            logger.warning(f"六维度审查失败: {e}")
        
        # 2. 宪法合规检查
        try:
            compliance_result = await self.constitution_service.check_compliance(
                project_id=project_id,
                chapter_number=chapter_number,
                chapter_title=chapter_title,
                chapter_content=chapter_content
            )
            results["constitution_compliance"] = compliance_result
            
            if not compliance_result.get("overall_compliance", True):
                results["overall_passed"] = False
                for violation in compliance_result.get("violations", []):
                    if violation.get("severity") == "critical":
                        results["critical_issues"].append(violation.get("description"))
        except Exception as e:
            logger.warning(f"宪法合规检查失败: {e}")
        
        # 3. 风格合规检查
        try:
            style_result = await self.writer_persona_service.check_style_compliance(
                project_id=project_id,
                chapter_content=chapter_content
            )
            results["style_compliance"] = style_result
        except Exception as e:
            logger.warning(f"风格合规检查失败: {e}")
        
        return results

    async def update_foreshadowing_status_from_content(
        self,
        project_id: str,
        chapter_number: int,
        chapter_content: str
    ) -> List[Dict[str, Any]]:
        """
        根据章节内容自动更新伏笔状态
        """
        updates = []
        
        # 获取活跃伏笔
        active_foreshadowings = await self.foreshadowing_service.get_active_foreshadowings(project_id)
        
        for fs in active_foreshadowings:
            # 检查伏笔内容是否在章节中被提及或揭示
            # 这里使用简单的关键词匹配，实际可以使用 LLM 进行更智能的检测
            if fs.name and fs.name in chapter_content:
                # 伏笔被提及，更新状态为 developing
                if fs.status == "planted":
                    await self.foreshadowing_service.update_foreshadowing_status(
                        foreshadowing_id=fs.id,
                        new_status="developing",
                        chapter_number=chapter_number,
                        reason="伏笔在章节中被提及",
                        action_taken="自动检测"
                    )
                    updates.append({
                        "id": fs.id,
                        "name": fs.name,
                        "old_status": "planted",
                        "new_status": "developing"
                    })
        
        return updates

    async def get_writing_health_report(self, project_id: str) -> Dict[str, Any]:
        """
        获取写作健康报告
        """
        report = {
            "constitution": None,
            "writer_persona": None,
            "foreshadowing_health": None,
            "faction_count": 0,
            "overall_health": "healthy",
            "recommendations": []
        }
        
        # 检查宪法
        constitution = await self.constitution_service.get_constitution(project_id)
        if constitution:
            report["constitution"] = "已配置"
        else:
            report["constitution"] = "未配置"
            report["recommendations"].append("建议配置小说宪法以确保创作一致性")
        
        # 检查 Writer 人格
        persona = await self.writer_persona_service.get_active_persona(project_id)
        if persona:
            report["writer_persona"] = persona.name
        else:
            report["writer_persona"] = "未配置"
            report["recommendations"].append("建议配置 Writer 人格以提升文本人味")
        
        # 检查伏笔健康度
        foreshadowing_health = await self.foreshadowing_service.analyze_foreshadowing_health(project_id)
        report["foreshadowing_health"] = foreshadowing_health
        if foreshadowing_health.get("status") != "healthy":
            report["overall_health"] = "warning"
            report["recommendations"].extend(foreshadowing_health.get("recommendations", []))
        
        # 检查势力数量
        factions = await self.faction_service.get_factions_by_project(project_id)
        report["faction_count"] = len(factions)
        
        return report
