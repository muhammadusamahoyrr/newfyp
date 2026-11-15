from datetime import datetime

from pydantic import BaseModel, EmailStr

from app.core.constants import UserRole


class RegisterRequest(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    role: UserRole = UserRole.CLIENT
    phone: str | None = None
    # The sign-up checkbox. Required to be true (auth_service.register); the
    # versions accepted are recorded on the account.
    accepted_terms: bool = False


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    user_id: str


class RefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class VerifyEmailRequest(BaseModel):
    token: str


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class AuthSessionItem(BaseModel):
    session_id: str
    current: bool
    user_agent: str = ""
    created_at: datetime | None = None
    last_used_at: datetime | None = None
    expires_at: datetime | None = None


class AuthSessionList(BaseModel):
    items: list[AuthSessionItem]


class SessionsRevoked(BaseModel):
    revoked: int
