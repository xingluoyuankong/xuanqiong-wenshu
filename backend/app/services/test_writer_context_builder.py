from app.services.writer_context_builder import WriterContextBuilder


class TestWriterContextBuilder:
    def test_analyze_character_scope_separates_introduced_and_planned_roles(self):
        builder = WriterContextBuilder()
        blueprint = {
            "characters": [
                {"name": "林七"},
                {"name": "沈舟"},
                {"name": "顾棠"},
            ]
        }

        scope = builder.analyze_character_scope(
            blueprint=blueprint,
            completed_summaries=["林七与沈舟在地牢交锋。"],
            previous_tail="林七听见门外脚步声。",
            outline_title="逼问之夜",
            outline_summary="林七继续试探沈舟，并准备见到顾棠。",
            writing_notes="强化顾棠的首次登场压迫感",
            allowed_new_characters=["顾棠"],
        )

        assert set(scope["introduced_characters"]) == {"林七", "沈舟"}
        assert set(scope["planned_characters"]) == {"林七", "沈舟", "顾棠"}
        assert set(scope["allowed_characters"]) == {"林七", "沈舟", "顾棠"}

    def test_build_visibility_context_adds_safe_macro_continuity_digest(self):
        builder = WriterContextBuilder()
        blueprint = {
            "title": "异海开拓史",
            "full_synopsis": "这段内容不应直接暴露给 writer。",
            "chapter_outline": [{"chapter_number": 1, "title": "旧大纲", "summary": "旧摘要"}],
            "characters": [
                {"name": "林七", "role": "主角"},
                {"name": "沈舟", "role": "对手"},
                {"name": "顾棠", "role": "新角色"},
            ],
            "relationships": [
                {"from": "林七", "to": "沈舟", "description": "互相试探，压迫感很强"},
                {"from": "林七", "to": "顾棠", "description": "尚未正式见面"},
            ],
            "story_arcs": [
                {"title": "黑潮疑云", "conflict": "林七必须查清黑潮异动真相"},
            ],
            "novel_outline": [
                {"title": "地牢脱身阶段", "main_conflict": "逃出追捕并锁定幕后线索"},
            ],
        }

        context = builder.build_visibility_context(
            blueprint=blueprint,
            completed_summaries=["林七与沈舟交锋，留下未解的压迫感。"],
            previous_tail="门外传来脚步声，林七意识到危险没结束。",
            outline_title="逼问之夜",
            outline_summary="林七继续试探沈舟，并允许顾棠登场。",
            writing_notes="强调对话压迫感与章末钩子",
            allowed_new_characters=["顾棠"],
        )

        digest = context["macro_continuity_context"]
        assert "## 已登场角色" in digest
        assert "林七" in digest
        assert "沈舟" in digest
        assert "## 本章角色范围" in digest
        assert "顾棠" in digest
        assert "## 当前关键关系" in digest
        assert "互相试探" in digest
        assert "## 长线剧情压力" in digest
        assert "黑潮疑云" in digest
        assert "## 当前阶段任务" in digest
        assert "地牢脱身阶段" in digest
        assert "full_synopsis" not in context["writer_blueprint"]
        assert all(item.get("name") != "顾棠" for item in context["writer_blueprint"]["characters"]) is False
