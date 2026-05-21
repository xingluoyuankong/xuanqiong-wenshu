from datetime import datetime, timezone

from app.api.routers.foreshadowing import _serialize_foreshadowing
from app.models.foreshadowing import Foreshadowing


def test_serialize_foreshadowing_exposes_payoff_planning_fields():
    item = Foreshadowing(
        id=7,
        project_id="project-1",
        chapter_id=3,
        chapter_number=3,
        name="盐痕账册",
        content="主角在账册上看到盐痕编号。",
        type="mystery",
        status="planted",
        target_reveal_chapter=6,
        reveal_method="用同一编号打开暗柜。",
        reveal_impact="证明账册仍在被人维护。",
        related_characters=["沈文朝", "守灯人"],
        related_plots=["潮祠暗线"],
        importance="major",
        urgency=9,
        keywords=["盐痕", "账册"],
        resolved_chapter_number=None,
        is_manual=False,
        ai_confidence=0.82,
        author_note="auto",
        created_at=datetime(2026, 5, 21, tzinfo=timezone.utc),
    )

    payload = _serialize_foreshadowing(item)

    assert payload["name"] == "盐痕账册"
    assert payload["target_reveal_chapter"] == 6
    assert payload["reveal_method"] == "用同一编号打开暗柜。"
    assert payload["related_characters"] == ["沈文朝", "守灯人"]
    assert payload["importance"] == "major"
    assert payload["urgency"] == 9
    assert payload["keywords"] == ["盐痕", "账册"]
