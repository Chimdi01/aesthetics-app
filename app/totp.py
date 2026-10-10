"""
TOTP 2FA business logic: secret generation, code verification, and
backup-code generation/verification/invalidation. Deliberately separate
from:
  - app/totp_encryption.py — how the secret is stored at rest (this
    module only ever deals in the RAW secret).
  - app/mfa_challenge.py — the login-handshake token that carries "this
    account passed the password check, now prove you have the 2FA
    device too" across two requests.
  - app/routers/users.py / app/routers/auth.py — where this gets called
    from; this module has no FastAPI/HTTP awareness at all.

Backup codes follow the same convention as every other DB-backed secret
here (app/secret_tokens.py's hash_token) — only the hash is ever stored,
functions that generate a fresh batch return the raw values once, same
pattern as issue_refresh_token/issue_email_token.
"""
import secrets
import uuid
from datetime import UTC, datetime

import pyotp
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.totp_backup_code import TotpBackupCode
from app.secret_tokens import hash_token

# Shown in the authenticator app next to the account entry.
ISSUER_NAME = "Aesthetics App"

# Excludes 0/O and 1/I/L — characters easy to misread when a user is
# typing a backup code off a printed/saved list, not off a screen with
# a font chosen for legibility.
_BACKUP_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_BACKUP_CODE_COUNT = 10


def generate_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, email: str) -> str:
    """The otpauth:// URI an authenticator app's QR scanner expects —
    rendering it as an actual QR code is a frontend concern; this just
    returns the string."""
    return pyotp.totp.TOTP(secret).provisioning_uri(name=email, issuer_name=ISSUER_NAME)


def verify_totp_code(secret: str, code: str) -> bool:
    # valid_window=1: accepts the previous/current/next 30s step, a
    # standard, small clock-drift allowance — not a brute-force-friendly
    # widening, since it's still only ever 3 valid codes at any instant.
    return pyotp.totp.TOTP(secret).verify(code, valid_window=1)


def _normalize_backup_code(code: str) -> str:
    return code.strip().upper().replace("-", "").replace(" ", "")


def _generate_backup_code() -> str:
    return "".join(secrets.choice(_BACKUP_CODE_ALPHABET) for _ in range(8))


def format_backup_code_for_display(raw_code: str) -> str:
    return f"{raw_code[:4]}-{raw_code[4:]}"


def generate_backup_codes(db: AsyncSession, user_id: uuid.UUID) -> list[str]:
    """Stages _BACKUP_CODE_COUNT new TotpBackupCode rows (uncommitted —
    caller commits, same convention as app/refresh_tokens.py) and
    returns the RAW codes, display-formatted — the only place they ever
    exist outside the one response that shows them to the user."""
    raw_codes = []
    for _ in range(_BACKUP_CODE_COUNT):
        raw = _generate_backup_code()
        raw_codes.append(raw)
        db.add(TotpBackupCode(user_id=user_id, code_hash=hash_token(raw)))
    return [format_backup_code_for_display(code) for code in raw_codes]


async def invalidate_backup_codes(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Marks every still-unused backup code for this user as used —
    called before issuing a fresh batch (regenerate) and when 2FA is
    disabled entirely, so an old code can't suddenly work again if 2FA
    is re-enabled later with a freshly generated secret."""
    await db.execute(
        update(TotpBackupCode)
        .where(TotpBackupCode.user_id == user_id, TotpBackupCode.used_at.is_(None))
        .values(used_at=datetime.now(UTC))
    )


async def verify_and_consume_backup_code(db: AsyncSession, user_id: uuid.UUID, code: str) -> bool:
    """Checks `code` against this user's still-unused backup codes. On
    a match, marks that ONE code used (single-use — a stolen printed
    list is worth less with each code spent) and returns True."""
    normalized = _normalize_backup_code(code)
    result = await db.execute(
        select(TotpBackupCode).where(
            TotpBackupCode.user_id == user_id,
            TotpBackupCode.used_at.is_(None),
            TotpBackupCode.code_hash == hash_token(normalized),
        )
    )
    backup_code = result.scalar_one_or_none()
    if backup_code is None:
        return False
    backup_code.used_at = datetime.now(UTC)
    return True
