from __future__ import annotations

from app.core.config import Settings


def _settings(**overrides):
    values = {
        'environment': 'development',
        'debug': False,
        'admin_default_password': 'A-strong-test-password-2026!',
        'secret_key': 's' * 64,
    }
    values.update(overrides)
    return Settings(**values)


def test_staging_uses_production_auth_and_startup_security_gate():
    settings = _settings(environment='staging')
    assert settings.is_production is True


def test_development_does_not_claim_production_gate():
    settings = _settings(environment='development')
    assert settings.is_production is False


def test_default_admin_password_is_reported_without_exposing_value():
    settings = _settings(environment='production', admin_default_password='ChangeMe123!')
    assert settings.admin_password_uses_default is True
    assert 'ADMIN_DEFAULT_PASSWORD 仍是默认值' in settings.startup_security_issues
    assert 'ChangeMe123!' not in '\n'.join(settings.startup_security_issues)
