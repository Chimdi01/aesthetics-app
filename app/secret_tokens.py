"""
Shared helpers for any "opaque, single-use, DB-backed secret token"
feature — refresh tokens (app/refresh_tokens.py) now, and email
verification / password reset tokens (planned next) later. All three
need the same two properties for the same reason: a long random value
handed to the client once (in a token response, or a verification/reset
link), and never stored anywhere in a form that's useful if the DB
leaks.

Deliberately NOT a JWT: a JWT's whole point is being self-contained and
verifiable without a DB round-trip — exactly the opposite of what's
needed here. Every one of these tokens must be revocable or single-use,
which means checking a stored record on every use regardless, so a
JWT's "stateless" property buys nothing here and only costs a payload
that still needs secure random generation underneath anyway.

Hashed, not encrypted or stored raw: same reasoning as password hashing
(see app/security.py), but a FAST hash (sha256), not bcrypt's
deliberately slow one — these are already high-entropy random values
from `secrets`, not a low-entropy human-chosen secret an attacker could
feasibly brute-force, so there's no brute-force-resistance need to
justify bcrypt's cost here.
"""
import hashlib
import secrets

# 32 random bytes, url-safe-base64-encoded (~43 chars) — comfortably
# more entropy than is practically guessable, and short enough to sit in
# a URL query param (for the email-link-based features) without issue.
_TOKEN_BYTES = 32


def generate_raw_token() -> str:
    return secrets.token_urlsafe(_TOKEN_BYTES)


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()
