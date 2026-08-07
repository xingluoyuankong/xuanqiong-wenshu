# Test faction_service translation
from app.services.faction_service import FactionService

svc = FactionService(None, None)

class TestTranslateRelationshipType:
    def test_ally(self):
        assert svc._translate_relationship_type('ally') == '盟友'

    def test_enemy(self):
        assert svc._translate_relationship_type('enemy') == '敌人'

    def test_rival(self):
        assert svc._translate_relationship_type('rival') == '竞争者'

    def test_unknown_returns_original(self):
        assert svc._translate_relationship_type('unknown_type') == 'unknown_type'

    def test_neutral(self):
        assert svc._translate_relationship_type('neutral') == '中立'
