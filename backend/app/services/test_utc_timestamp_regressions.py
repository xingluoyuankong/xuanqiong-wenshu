from datetime import datetime, timezone

from app.core.security import create_access_token, decode_access_token


def test_access_token_uses_current_utc_timestamp_without_deprecated_utcnow():
    token = create_access_token("user-1")
    payload = decode_access_token(token)

    assert isinstance(payload["iat"], int)
    assert isinstance(payload["exp"], int)
    assert payload["exp"] > payload["iat"]
    assert datetime.now(timezone.utc).timestamp() >= payload["iat"]