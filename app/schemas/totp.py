"""
Schemas for 2FA enrollment/management (app/routers/users.py's
/me/2fa/* endpoints). Separate from app/schemas/auth.py, which covers
the LOGIN-time handshake (the MFA challenge) — this file is about
setting 2FA up in the first place, a different concern.
"""
from pydantic import BaseModel


class TotpEnrollResponse(BaseModel):
    secret: str
    # otpauth:// URI — the frontend renders this as a QR code (or shows
    # `secret` for manual entry); this API never generates an image.
    provisioning_uri: str


class TotpConfirmRequest(BaseModel):
    code: str


class TotpConfirmResponse(BaseModel):
    # Display-formatted ("XXXX-XXXX"), shown exactly once — same
    # "raw value exists only transiently in this one response" rule as
    # a refresh token or an email-verification link.
    backup_codes: list[str]


class TotpDisableRequest(BaseModel):
    # Re-proving the password, not just relying on the caller's
    # already-valid access token, before disabling 2FA — same "step up
    # for a sensitive action" reasoning as requiring the OLD password
    # nowhere else in this app (password reset doesn't need it, since
    # that flow already proves account control a different way via the
    # emailed token) but very much needed here, where the only proof on
    # the table otherwise is "I have a currently-valid access token",
    # which is exactly what you can't fully trust if 2FA is the thing
    # being turned off.
    password: str


class TotpStatusResponse(BaseModel):
    enabled: bool
    backup_codes_remaining: int


class RegenerateBackupCodesRequest(BaseModel):
    password: str


class RegenerateBackupCodesResponse(BaseModel):
    backup_codes: list[str]
