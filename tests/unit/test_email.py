"""
Pure logic, no DB/HTTP — app/email.py's "console" backend and its
unknown-backend failure mode.
"""
import pytest

from app.email import send_email


async def test_console_backend_logs_the_email(caplog):
    with caplog.at_level("INFO"):
        await send_email("someone@example.com", "subject line", "body text with a link")
    assert "someone@example.com" in caplog.text
    assert "subject line" in caplog.text
    assert "body text with a link" in caplog.text


async def test_unknown_backend_raises(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "email_backend", "ses")
    with pytest.raises(NotImplementedError):
        await send_email("someone@example.com", "subject", "body")
