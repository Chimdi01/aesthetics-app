"""
Schemas for the token-issuing/refreshing/verification/reset endpoints in
app/routers/auth.py. Kept separate from app/schemas/user.py — these
describe auth MECHANICS (tokens), not the User resource itself.
"""
from pydantic import BaseModel, EmailStr, Field


class TokenPair(BaseModel):
    # Field names/token_type match the OAuth2 "password" flow's expected
    # shape (access_token + token_type) so /docs's "Authorize" button
    # keeps working unchanged — refresh_token is additional, not a
    # replacement for anything it already relied on.
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class VerifyEmailRequest(BaseModel):
    token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    # Same min_length policy as UserCreate.password (app/schemas/user.py)
    # — this IS the password going forward, so it goes through the same
    # bar as one set at signup.
    new_password: str = Field(min_length=8)
