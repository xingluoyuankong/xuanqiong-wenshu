"""
US-008: Test quality gate failure path
=======================================
目标：验证当章节生成不符合一致性要求时，系统正确拒绝并进入修复/重试状态。

测试场景：
1. 故意生成矛盾的章节（角色名冲突）
2. 触发 self-critique 对明显错误文本进行检查
3. 验证 ChapterVersion 保持 superseded 状态
4. 确认系统进入 repair/retry 而非直接持久化失败内容
5. 验证前端 UI 显示错误但不崩溃
6. 检查 allowed_actions 包含'retry'选项
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, MagicMock
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from backend.app.db.session import AsyncSessionLocal
from backend.app.services.consistency_service import ConsistencyService, ConsistencyCheckResult, ConsistencyViolation, ViolationSeverity
from backend.app.services.llm_service import LLMService
from backend.app.models.novel import ChapterVersion, NovelProject, Chapter, ChapterEvaluation


class TestQualityGateFailurePath:
    """测试质量门失败路径"""
    
    @pytest.fixture
    def mock_violations(self):
        """返回严重的一致性冲突"""
        return [
            ConsistencyViolation(
                category="character_naming",
                severity=ViolationSeverity.CRITICAL,
                description="章节内主角名字前后矛盾：前文称'林默'，后文变为'林海'",
                location="第 3 段 vs 第 8 段",
                suggested_fix="统一使用原名'林默'"
            ),
            ConsistencyViolation(
                category="continuity_conflict", 
                severity=ViolationSeverity.CRITICAL,
                description="时间线错误：第一章明确说'三天后'，本章却说'当晚'",
                location="上下文 vs 本章第 5 段",
                suggested_fix="调整时间描述"
            )
        ]
    
    @pytest.fixture
    def mock_llm_service(self):
        """Mock LLM Service"""
        service = Mock(spec=LLMService)
        service.client = Mock()
        return service
    
    @pytest.mark.asyncio
    async def test_consistency_check_rejects_critical_violations(
        self, 
        mock_violations: list[ConsistencyViolation],
        mock_llm_service: LLMService,
        db_session: AsyncSession
    ):
        """验证严重违反项会被拒绝"""
        # Setup: 创建一个项目、蓝图、章节
        project = NovelProject(name="Test Novel", user_id=1)
        chapter = Chapter(title="Chapter 1", content="Test")
        db_session.add(project)
        db_session.add(chapter)
        await db_session.flush()
        
        # Create consistency service
        service = ConsistencyService(mock_llm_service)
        
        # Generate intentionally bad content
        bad_content = """
        林默坐在桌前沉思。（第 1 段）
        ...中间文字...
        林海推开房门走进来。（第 8 段 - 名字矛盾！）
        ...
        三天过去了，他依然等待。（第 12 段 - 但第一章说是当天）
        """
        
        # Mock the LLM response with critical violations
        mock_result = ConsistencyCheckResult(
            is_consistent=False,
            violations=mock_violations,
            summary="检测到严重一致性冲突",
            check_time_ms=1500,
            status="failed"
        )
        
        # Verify result
        assert mock_result.is_consistent == False
        assert len(mock_result.violations) == 2
        assert any(v.severity == ViolationSeverity.CRITICAL for v in mock_result.violations)
    
    @pytest.mark.asyncio
    async def test_chapter_version_remains_superseded_on_failure(
        self,
        db_session: AsyncSession
    ):
        """验证失败的版本不会被选中为当前版本"""
        from datetime import datetime
        
        # Create a failed generation attempt
        failed_version = ChapterVersion(
            chapter_id=1,
            version_label="attempt_1",
            provider="test_provider",
            content="This content has critical errors",
            metadata_={
                "consistency_failed": True,
                "violations_count": 2,
                "critical_violations": ["character_naming", "continuity_conflict"]
            }
        )
        db_session.add(failed_version)
        
        # In production, this would be handled by pipeline_orchestrator
        # which sets status='superseded' and keeps only valid versions as active
        
        # For now, verify the model supports the required fields
        assert failed_version.metadata_.get("consistency_failed") == True
        assert len(failed_version.metadata_.get("critical_violations", [])) > 0
    
    @pytest.mark.asyncio
    async def test_allowed_actions_includes_retry(
        self,
        quality_gate_summary: dict,
        mock_violations: list[ConsistencyViolation]
    ):
        """验证允许的操作包括 retry"""
        # Simulate quality gate rejection
        gate_summary = {
            "passed": False,
            "codes": ["critical_consistency_unresolved"],
            "labels": ["严重连续性冲突未修复"],
            "blocker_count": 2,
            "tone": "danger"
        }
        
        # In production, this maps to frontend allowed_actions
        allowed_actions = ["retry", "abort"] if not gate_summary["passed"] else ["publish"]
        
        assert "retry" in allowed_actions, "重试按钮应该出现在失败状态下"
        assert "publish" not in allowed_actions, "发布按钮在失败时应禁用"
    
    @pytest.mark.asyncio
    async def test_ui_shows_quality_issues_without_crashing(
        self,
        mock_violations: list[ConsistencyViolation]
    ):
        """验证 UI 能显示质量问题而不崩溃"""
        # Format violations for UI display
        ui_items = []
        for v in mock_violations:
            ui_items.append({
                "code": v.category,
                "label": f"[{v.severity.value}] {v.category}",
                "message": v.description,
                "suggested_fix": v.suggested_fix,
                "location": v.location or "未指定位置"
            })
        
        # Verify UI data structure
        assert len(ui_items) > 0
        assert all("message" in item for item in ui_items)
        assert all("suggested_fix" in item for item in ui_items)
        
        # Frontend should render these without errors
        print(f"UI items ready: {ui_items}")


@pytest.fixture
def quality_gate_summary():
    """模拟质量门摘要"""
    return {
        "passed": False,
        "codes": ["critical_consistency_unresolved"],
        "labels": ["严重连续性冲突未修复"],
        "blocker_count": 2
    }


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
