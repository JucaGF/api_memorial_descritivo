from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

UserRole = Literal["owner", "user"]
UserStatus = Literal["active", "inactive"]


class UserProfileResponse(BaseModel):
    user_id: str
    email: str
    display_name: str
    role: UserRole
    status: UserStatus
    created_at: datetime | str | None = None
    updated_at: datetime | str | None = None


class CurrentUserResponse(UserProfileResponse):
    pass


class UpdateMyProfilePayload(BaseModel):
    display_name: str = Field(min_length=2, max_length=80)


class AdminUserListResponse(BaseModel):
    users: list[UserProfileResponse]


class CreateAdminUserPayload(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=2, max_length=80)
    role: UserRole = "user"


class UpdateAdminUserPayload(BaseModel):
    display_name: str | None = Field(default=None, min_length=2, max_length=80)
    role: UserRole | None = None
    status: UserStatus | None = None
