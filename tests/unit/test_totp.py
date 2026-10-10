"""
Pure logic, no DB/HTTP — the parts of app/totp.py that don't need a
session (generate_backup_codes/verify_and_consume_backup_code/
invalidate_backup_codes all touch the DB and are covered through the
real endpoints instead, see tests/regression/test_two_factor_auth.py).
"""
import pyotp

from app.totp import format_backup_code_for_display, generate_secret, provisioning_uri, verify_totp_code


def test_generate_secret_produces_a_valid_base32_string():
    secret = generate_secret()
    # pyotp.TOTP() raises on a malformed secret — constructing one
    # successfully IS the validity check here.
    pyotp.TOTP(secret)
    assert len(secret) >= 16


def test_generate_secret_produces_different_values_each_time():
    assert generate_secret() != generate_secret()


def test_provisioning_uri_includes_the_email_and_issuer():
    secret = generate_secret()
    uri = provisioning_uri(secret, "jane@example.com")
    assert uri.startswith("otpauth://totp/")
    assert "jane%40example.com" in uri or "jane@example.com" in uri
    assert "Aesthetics" in uri


def test_verify_totp_code_accepts_the_current_valid_code():
    secret = generate_secret()
    current_code = pyotp.TOTP(secret).now()
    assert verify_totp_code(secret, current_code)


def test_verify_totp_code_rejects_a_wrong_code():
    secret = generate_secret()
    assert not verify_totp_code(secret, "000000")


def test_verify_totp_code_rejects_a_code_for_a_different_secret():
    secret_a = generate_secret()
    secret_b = generate_secret()
    code_for_b = pyotp.TOTP(secret_b).now()
    assert not verify_totp_code(secret_a, code_for_b)


def test_format_backup_code_for_display_inserts_a_dash_in_the_middle():
    assert format_backup_code_for_display("ABCD1234") == "ABCD-1234"
