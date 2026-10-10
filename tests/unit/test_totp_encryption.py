"""
Pure logic, no DB/HTTP — app/totp_encryption.py's encrypt/decrypt round
trip.
"""
import pytest
from cryptography.fernet import Fernet, InvalidToken

from app.totp_encryption import decrypt_totp_secret, encrypt_totp_secret


def test_encrypt_then_decrypt_round_trips():
    secret = "JBSWY3DPEHPK3PXP"
    encrypted = encrypt_totp_secret(secret)
    assert decrypt_totp_secret(encrypted) == secret


def test_encrypted_value_is_not_the_raw_secret():
    secret = "JBSWY3DPEHPK3PXP"
    encrypted = encrypt_totp_secret(secret)
    assert encrypted != secret
    assert secret not in encrypted


def test_encrypting_the_same_secret_twice_produces_different_ciphertext():
    # Fernet includes a random IV/timestamp — two encryptions of the
    # same plaintext should never be byte-identical, so a DB leak can't
    # even confirm "these two users have the same TOTP secret" by
    # comparing stored values.
    secret = "JBSWY3DPEHPK3PXP"
    assert encrypt_totp_secret(secret) != encrypt_totp_secret(secret)


def test_decrypting_with_the_wrong_key_fails(monkeypatch):
    from app.config import settings

    secret = "JBSWY3DPEHPK3PXP"
    encrypted = encrypt_totp_secret(secret)

    monkeypatch.setattr(settings, "totp_encryption_key", Fernet.generate_key().decode())
    with pytest.raises(InvalidToken):
        decrypt_totp_secret(encrypted)
