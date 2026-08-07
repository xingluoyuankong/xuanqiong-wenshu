# Test emotion_curve_service: ArcType enum
from app.services.emotion_curve_service import ArcType

class TestArcType:
    def test_standard(self):
        assert ArcType.STANDARD == 'standard'

    def test_all_values(self):
        values = [e.value for e in ArcType]
        assert 'standard' in values
        assert 'slow_burn' in values
        assert 'fast_paced' in values
        assert 'episodic' in values
        assert 'rising' in values
        assert 'wave' in values

    def test_from_string(self):
        assert ArcType('slow_burn') == ArcType.SLOW_BURN
        assert ArcType('fast_paced') == ArcType.FAST_PACED
