"""
Pure Pydantic validation on MessageCreate — no DB, no HTTP.
"""
import pytest
from pydantic import ValidationError

from app.schemas.message import MessageCreate


def test_message_create_accepts_valid_body():
    message = MessageCreate(body="Running 10 minutes late, sorry!")
    assert message.body == "Running 10 minutes late, sorry!"


def test_message_create_rejects_empty_body():
    with pytest.raises(ValidationError):
        MessageCreate(body="")


def test_message_create_rejects_whitespace_only_body():
    with pytest.raises(ValidationError):
        MessageCreate(body="   ")


def test_message_create_rejects_body_with_embedded_null_byte():
    with pytest.raises(ValidationError):
        MessageCreate(body="hello\x00world")


def test_message_create_rejects_body_over_max_length():
    with pytest.raises(ValidationError):
        MessageCreate(body="x" * 2001)


def test_message_create_accepts_body_at_max_length():
    message = MessageCreate(body="x" * 2000)
    assert len(message.body) == 2000
