from app.schemas.user import UserCreate, UserInDB


def test_user_in_db_accepts_legacy_internal_email():
    user = UserInDB.model_validate({
        "id": 1,
        "username": "admin",
        "email": "admin@qwenpaw-mingzhu.local",
        "hashed_password": "hash",
        "is_admin": True,
        "is_active": True,
    })
    assert user.email == "admin@qwenpaw-mingzhu.local"


def test_user_create_keeps_strict_email_validation():
    try:
        UserCreate(username="admin", email="admin@qwenpaw-mingzhu.local", password="ChangeMe123!")
    except Exception:
        return
    raise AssertionError("UserCreate must continue rejecting special-use internal email domains")
