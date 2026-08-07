# Test continuity_guard_utils
from app.services.continuity_guard_utils import _contains_term, _add_token

class TestContainsTerm:
    def test_exact_match(self):
        assert _contains_term('hello world', 'hello') is True

    def test_no_match(self):
        assert _contains_term('hello world', 'xyz') is False

class TestAddToken:
    def test_adds_new_token(self):
        tokens = []
        seen = set()
        _add_token(tokens, seen, 'alpha')
        assert len(tokens) == 1
        assert 'alpha' in tokens

    def test_skips_duplicate(self):
        tokens = []
        seen = set()
        _add_token(tokens, seen, 'beta')
        _add_token(tokens, seen, 'beta')
        assert len(tokens) == 1

    def test_cleans_whitespace(self):
        tokens = []
        seen = set()
        _add_token(tokens, seen, '  clean me  ')
        assert len(tokens) == 1
        assert tokens[0] == 'clean me'
