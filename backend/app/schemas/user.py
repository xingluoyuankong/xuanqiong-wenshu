# AIMETA P=用户模式_用户和认证请求响应|R=用户结构_令牌结构|NR=不含业务逻辑|E=UserSchema_TokenSchema|X=internal|A=Pydantic模式|D=pydantic|S=none|RD=./README.ai
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserBase(BaseModel):
    """用户基础数据结构，供多处复用。"""

    username: str = Field(..., description="用户名")
    email: Optional[EmailStr] = Field(default=None, description="邮箱，可选")


class UserCreate(UserBase):
    """注册时使用的模型。"""

    password: str = Field(..., min_length=6, description="明文密码")


class UserUpdate(BaseModel):
    """用户信息修改模型。"""

    email: Optional[EmailStr] = Field(default=None, description="邮箱")
    password: Optional[str] = Field(default=None, min_length=6, description="新密码")


class User(UserBase):
    """对外暴露的用户信息。"""

    id: int = Field(..., description="用户主键")
    is_admin: bool = Field(default=False, description="是否为管理员")
    is_active: bool = Field(default=True, description="是否激活")
    must_change_password: bool = Field(default=False, description="是否需要强制修改密码")

    model_config = ConfigDict(from_attributes=True)


class UserInDB(User):
    """数据库内部使用的模型，包含哈希后的密码。"""

    hashed_password: str


