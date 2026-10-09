"""
Pure logic, no DB/HTTP — mirrors tests/unit/test_email.py exactly, since
app/sms.py is the same "console" placeholder pattern.
"""
import pytest

from app.sms import send_sms


async def test_console_backend_logs_the_sms(caplog):
    with caplog.at_level("INFO"):
        await send_sms("+14155552671", "your booking is confirmed")
    assert "+14155552671" in caplog.text
    assert "your booking is confirmed" in caplog.text


async def test_unknown_backend_raises(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "sms_backend", "twilio")
    with pytest.raises(NotImplementedError):
        await send_sms("+14155552671", "body")
