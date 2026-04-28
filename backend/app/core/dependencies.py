# AIMETA P=依赖注入_FastAPI依赖项定义|R=数据库会话_当前用户获取|NR=不含业务逻辑|E=get_db_get_current_user|X=internal|A=依赖函数|D=fastapi,sqlalchemy|S=db|RD=./README.ai
import logging

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..core.security import hash_password
from ..db.session import get_session
from ..models import User
from ..schemas.user import UserInDB

logger = logging.getLogger(__name__)


async def _create_default_admin(session: AsyncSession) -> User:
    user = User(
        username=settings.admin_default_username,
        email=settings.admin_default_email,
        hashed_password=hash_password(settings.admin_default_password),
        is_admin=True,
        is_active=True,
    )
    session.add(user)

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        stmt = select(User).where(User.username == settings.admin_default_username)
        result = await session.execute(stmt)
        existing_user = result.scalars().first()
        if existing_user:
            return existing_user
        raise

    await session.refresh(user)
    return user


async def _ensure_system_user(session: AsyncSession) -> User:
    stmt = select(User).where(User.username == settings.admin_default_username)
    result = await session.execute(stmt)
    user = result.scalars().first()
    if user:
        return user

    admin_stmt = select(User).where(User.is_admin.is_(True)).order_by(User.id.asc())
    admin_result = await session.execute(admin_stmt)
    existing_admin = admin_result.scalars().first()
    if existing_admin:
        logger.error(
            "未找到默认管理员用户名 %s，且当前库内已有其他管理员 id=%s username=%s；拒绝回退绑定，避免误用错误用户上下文",
            settings.admin_default_username,
            existing_admin.id,
            existing_admin.username,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "DEFAULT_ADMIN_NOT_FOUND",
                "message": f"未找到默认管理员用户名 {settings.admin_default_username}，但数据库中存在其他管理员，系统不会自动回退绑定。",
                "hint": "请修复 ADMIN_DEFAULT_USERNAME，确保作品与默认管理员上下文绑定明确。",
            },
        )

    return await _create_default_admin(session)


def _to_user_schema(user: User) -> UserInDB:
    try:
        schema = UserInDB.model_validate(user)
    except Exception as exc:
        logger.warning("用户数据校验失败，已按兼容模式回退: username=%s error=%s", user.username, exc)
        schema = UserInDB(
            id=user.id,
            username=user.username,
            email=None,
            is_admin=bool(user.is_admin),
            is_active=bool(user.is_active),
            must_change_password=False,
            hashed_password=user.hashed_password,
        )
    schema.must_change_password = False
    return schema


async def get_current_user(session: AsyncSession = Depends(get_session)) -> UserInDB:
    user = await _ensure_system_user(session)
    return _to_user_schema(user)


async def get_current_admin(current_user: UserInDB = Depends(get_current_user)) -> UserInDB:
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "ADMIN_REQUIRED",
                "message": "当前用户缺少管理员权限",
                "hint": "请使用管理员账号，或修复默认管理员配置。",
            },
        )
    return current_user
