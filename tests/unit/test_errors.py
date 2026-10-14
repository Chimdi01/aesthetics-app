"""
Pure logic in app/errors.py — no DB, no HTTP.
"""
import pytest
from pydantic import BaseModel, ValidationError

from app.errors import AppError, ErrorCode, build_field_errors, fallback_error_code, field_error_code


def test_fallback_error_code_known_statuses():
    assert fallback_error_code(404) == ErrorCode.not_found
    assert fallback_error_code(403) == ErrorCode.forbidden
    assert fallback_error_code(409) == ErrorCode.duplicate_resource
    assert fallback_error_code(429) == ErrorCode.rate_limited


def test_fallback_error_code_unknown_status_defaults_to_invalid_state():
    # 405 isn't in the explicit map — confirms the deliberate generic
    # default rather than a KeyError.
    assert fallback_error_code(405) == ErrorCode.invalid_state


def test_app_error_carries_code_detail_and_params():
    err = AppError(status_code=404, error_code=ErrorCode.not_found, detail="Booking not found")
    assert err.status_code == 404
    assert err.error_code == ErrorCode.not_found
    assert err.detail == "Booking not found"
    assert err.params is None

    err_with_params = AppError(
        status_code=429,
        error_code=ErrorCode.rate_limited,
        detail="Too many requests",
        params={"retry_after_seconds": 60},
    )
    assert err_with_params.params == {"retry_after_seconds": 60}


# --- field_error_code: frozen mapping, pinned deliberately so a Pydantic
# upgrade renaming one of these internally is caught, not silently leaked
# as a new, unreviewed string. ---


@pytest.mark.parametrize(
    "pydantic_type,expected_code",
    [
        ("missing", "missing"),
        ("string_too_short", "too_short"),
        ("string_too_long", "too_long"),
        ("value_error", "invalid"),
        ("greater_than_equal", "out_of_range"),
        ("less_than_equal", "out_of_range"),
        ("int_parsing", "invalid_type"),
        ("uuid_parsing", "invalid_type"),
        ("timezone_aware", "invalid_type"),
        ("enum", "invalid_choice"),
        ("extra_forbidden", "unexpected_field"),
    ],
)
def test_field_error_code_frozen_mapping(pydantic_type, expected_code):
    assert field_error_code(pydantic_type) == expected_code


def test_field_error_code_falls_back_to_generic_for_unmapped_type():
    assert field_error_code("some_future_pydantic_type_type_we_have_never_seen") == "invalid"


# --- build_field_errors: the actual Pydantic error dicts this app
# produces, end to end through real model validation (not hand-built
# fixtures) — confirms both the mapping AND that `input` never leaks. ---


class _Model(BaseModel):
    email: str
    age: int


def _errors_from(**kwargs):
    try:
        _Model(**kwargs)
    except ValidationError as exc:
        return exc.errors()
    raise AssertionError("expected a ValidationError")


def test_build_field_errors_strips_input_and_maps_codes():
    errors = _errors_from(age="not-a-number")
    fields = build_field_errors(errors)
    assert len(fields) == 2  # email missing, age invalid
    for f in fields:
        assert set(f.keys()) == {"field", "code", "message"}
        assert "input" not in f


def test_build_field_errors_uses_the_single_segment_directly():
    # loc for a direct model_validate (not through a real request) is a
    # single-element tuple, e.g. ("age",) — no "body"/"query" prefix to
    # drop. The multi-segment case (FastAPI's real loc is
    # ("body", "email", ...), and the leading "body" gets dropped,
    # leaving just "email") is covered end to end through a real
    # request in tests/regression/test_error_envelope.py.
    errors = _errors_from(email="x", age="not-a-number")
    fields = build_field_errors(errors)
    assert fields == [
        {
            "field": "age",
            "code": "invalid_type",
            "message": "Input should be a valid integer, unable to parse string as an integer",
        }
    ]
