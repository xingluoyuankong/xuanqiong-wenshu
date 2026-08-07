# Test token_budget_service utility functions
from app.services.token_budget_service import TokenBudgetService

class TestNormalizeUsageModule:
    def test_generation_normalizes(self):
        result = TokenBudgetService.normalize_usage_module('generation')
        assert len(result) > 0

    def test_none_handled(self):
        result = TokenBudgetService.normalize_usage_module(None)
        assert isinstance(result, str)

    def test_empty_handled(self):
        result = TokenBudgetService.normalize_usage_module('')
        assert isinstance(result, str)

class TestEstimateCost:
    def test_zero_tokens(self):
        cost = TokenBudgetService.estimate_cost_from_tokens(0)
        assert cost == 0.0

    def test_positive_tokens(self):
        cost = TokenBudgetService.estimate_cost_from_tokens(1000, cny_per_1k=0.01)
        assert cost == 0.01

class TestCoercePositiveInt:
    def test_positive_value(self):
        result = TokenBudgetService._coerce_positive_int(5)
        assert result == 5

    def test_none_defaults_to_zero(self):
        result = TokenBudgetService._coerce_positive_int(None)
        assert result >= 0

    def test_string_value(self):
        result = TokenBudgetService._coerce_positive_int('3')
        assert result == 3
