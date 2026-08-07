# Test constitution_service basic logic
from app.services.constitution_service import ConstitutionService

svc = ConstitutionService(None, None, None)

class TestGetConstitutionContext:
    def test_none_constitution_returns_default(self):
        result = svc.get_constitution_context(None)
        assert result is not None
        assert len(result) > 0

    def test_none_indicates_no_constitution(self):
        result = svc.get_constitution_context(None)
        assert '未设置' in result or 'none' in result.lower() or 'no' in result.lower()
