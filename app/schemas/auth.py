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
    # Always False here — a real token pair, not a 2FA challenge. Fixed
    # on both this and MfaChallengeResponse below so a client can check
    # one consistent field (`mfa_required`) regardless of which shape
    # login() actually returned, rather than needing to introspect for
    # which fields are present.
    mfa_required: bool = False


class MfaChallengeResponse(BaseModel):
    """What POST /v1/auth/login returns instead of a TokenPair when the
    account has 2FA enabled — see app/routers/auth.py's login(). No
    access to anything yet; `mfa_token` is only good for one thing:
    POST /v1/auth/login/verify-2fa."""

    mfa_required: bool = True
    mfa_token: str


class Verify2FARequest(BaseModel):
    mfa_token: str
    code: str


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


class RevokeAllSessionsRequest(BaseModel):
    # Required and must be literally true — see
    # app/routers/admin.py's revoke_all_sessions. This logs out every
    # user on the platform at once; a bare POST with no body (e.g. a
    # typo'd request, a misconfigured script) must not be enough to
    # trigger it.
    confirm: bool = False


class RevokeAllSessionsResponse(BaseModel):
    revoked_count: int
