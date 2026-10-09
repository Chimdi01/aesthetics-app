"""
Pure logic, no DB/HTTP — mirrors tests/unit/test_email.py and
tests/unit/test_sms.py exactly, since app/push.py is the same
"console" placeholder pattern.
"""
import pytest

from app.push import send_push


async def test_console_backend_logs_the_push(caplog):
    with caplog.at_level("INFO"):
        await send_push("fake-device-token", "New message", "Jane: hi there")
    assert "fake-device-token" in caplog.text
    assert "New message" in caplog.text
    assert "Jane: hi there" in caplog.text


async def test_unknown_backend_raises(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "push_backend", "fcm")
    with pytest.raises(NotImplementedError):
        await send_push("fake-device-token", "title", "body")
