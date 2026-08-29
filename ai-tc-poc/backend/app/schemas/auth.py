from typing import Literal

from pydantic import BaseModel, Field


class DemoLoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class AuthenticatedUser(BaseModel):
    id: str
    displayName: str
    role: Literal["OWNER", "QA", "VIEWER"]
    approvalStatus: Literal["PENDING", "APPROVED", "REJECTED"]


class LoginResponse(BaseModel):
    user: AuthenticatedUser
    expiresIn: int
