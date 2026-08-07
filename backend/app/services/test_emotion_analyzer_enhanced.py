# Test emotion_analyzer_enhanced enums
from app.services.emotion_analyzer_enhanced import EmotionType, NarrativePhase

class TestEmotionType:
    def test_all_values(self):
        values = [e.value for e in EmotionType]
        assert 'joy' in values
        assert 'fear' in values
        assert len(values) >= 8

    def test_from_value(self):
        assert EmotionType('joy') == EmotionType.JOY
        assert EmotionType('fear') == EmotionType.FEAR

class TestNarrativePhase:
    def test_all_values(self):
        values = [e.value for e in NarrativePhase]
        assert 'exposition' in values
        assert 'climax' in values
        assert 'resolution' in values

    def test_from_value(self):
        assert NarrativePhase('exposition') == NarrativePhase.EXPOSITION
        assert NarrativePhase('climax') == NarrativePhase.CLIMAX
