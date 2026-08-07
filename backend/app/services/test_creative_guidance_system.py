# Test creative_guidance_system enums and dataclasses
from app.services.creative_guidance_system import GuidanceType, Priority, GuidanceItem, CreativeGuidance

class TestGuidanceType:
    def test_all_values(self):
        assert GuidanceType('plot_development') == GuidanceType.PLOT_DEVELOPMENT
        assert GuidanceType('character_arc') == GuidanceType.CHARACTER_ARC
        assert GuidanceType('theme_depth') == GuidanceType.THEME_DEPTH

class TestPriority:
    def test_levels(self):
        assert Priority('critical') == Priority.CRITICAL
        assert Priority('low') == Priority.LOW

class TestGuidanceItem:
    def test_create_item(self):
        item = GuidanceItem(
            type=GuidanceType.PLOT_DEVELOPMENT, priority=Priority.HIGH,
            title='Midpoint', description='Add twist',
            specific_suggestions=['Hint'], affected_chapters=[3,4,5],
        )
        assert item.type == GuidanceType.PLOT_DEVELOPMENT
        assert item.affected_chapters == [3,4,5]

class TestCreativeGuidance:
    def test_create(self):
        item = GuidanceItem(
            type=GuidanceType.THEME_DEPTH, priority=Priority.MEDIUM,
            title='Explore', description='Explore',
            specific_suggestions=['Add'], affected_chapters=[5],
        )
        g = CreativeGuidance(
            overall_assessment='Good', strengths=['Pacing'],
            weaknesses=['Flat'], guidance_items=[item],
            next_chapter_suggestions=['More'], long_term_planning=['Ending setup'],
        )
        assert g.overall_assessment == 'Good'
        assert len(g.guidance_items) == 1
        assert g.long_term_planning == ['Ending setup']
