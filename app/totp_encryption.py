"""
Encrypts/decrypts TOTP shared secrets at rest (app/totp.py,
User.totp_secret_encrypted). NOT hashing — unlike a password or any of
the tokens in app/secret_tokens.py, a TOTP secret has to be read back in
its original form to compute the next valid code, so it can't go
through a one-way hash the way those do. Encryption (reversible, with a
key) is the correct primitive here, same as any other "store this
secret, but the app itself needs to use the real value later" case.

If the DB leaks without this, every enrolled user's 2FA is worthless to
an attacker who also has the encryption key — but worth exactly nothing
extra if they DON'T, since the secret alone can't be used to generate
valid codes. That's the whole point: a DB leak alone (the far more
likely scenario — a SQL injection, a misconfigured backup, a stolen
snapshot) isn't enough on its own to defeat 2FA.

Fernet (symmetric, from the `cryptography` package) — authenticated
encryption with a single shared key, the standard choice for "encrypt
this blob, decrypt it later with the same key," which is exactly this
use case (unlike password hashing, there's no need for the one-way,
slow-by-design properties bcrypt provides).

No key-rotation support (unlike JWT_SECRET_KEY's multi-key verification,
app/security.py) — rotating TOTP_ENCRYPTION_KEY would require
re-encrypting every existing stored secret with the new key in one pass,
not just accepting multiple keys at read time, since Fernet doesn't
have JWT's "try each key until one verifies" option built in the same
way. Flagged as a real limitation, not built yet — see SECRETS_ROTATION.md.
"""
from cryptography.fernet import Fernet

from app.config import settings


def _fernet() -> Fernet:
    return Fernet(settings.totp_encryption_key.encode())


def encrypt_totp_secret(raw_secret: str) -> str:
    return _fernet().encrypt(raw_secret.encode()).decode()


def decrypt_totp_secret(encrypted_secret: str) -> str:
    return _fernet().decrypt(encrypted_secret.encode()).decode()
