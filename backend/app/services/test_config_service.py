# Test config_service hidden key detection
from app.services.config_service import is_hidden_system_config_key, is_visible_system_config_key

class TestHiddenConfigKeys:
    def test_auth_prefix_hidden(self):
        assert is_hidden_system_config_key('auth.some_key') is True

    def test_linuxdo_prefix_hidden(self):
        assert is_hidden_system_config_key('linuxdo.some_key') is True

    def test_normal_key_visible(self):
        assert is_hidden_system_config_key('app.some_key') is False

    def test_visible_check(self):
        assert is_visible_system_config_key('app.some_key') is True

    def test_auth_is_not_visible(self):
        assert is_visible_system_config_key('auth.secret') is False

    def test_linuxdo_is_not_visible(self):
        assert is_visible_system_config_key('linuxdo.token') is False
