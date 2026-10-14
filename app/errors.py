"""
Stable, machine-readable error codes — added alongside the existing
human-readable `detail`, never replacing it. See docs/backend-slices.md
Slice 1 Step 1.

`detail` stays a plain string for humans. `fields` (validation only)
carries per-field detail as structured data instead of free text, so a
client can highlight the right form field without parsing English.
`error_code` is what a client should actually branch logic on: wording
can change (or get localized) later without that being a breaking
change, but `error_code`/field `code` values are a contract.

AppError replaces raise HTTPException(...) everywhere in this app;
plain HTTPException is still handled (see app/main.py) as a fallback
so nothing is ever silently missing an error_code, but new code should
always raise AppError directly. A guard test
(tests/unit/test_no_raw_http_exception.py) enforces this once the
migration is complete.
"""
import enum
from collections.abc import Sequence

from fastapi import HTTPException


class ErrorCode(str, enum.Enum):
    # The brief's explicit minimum set.
    provider_profile_required = "provider_profile_required"
    slot_unavailable = "slot_unavailable"
    validation_failed = "validation_failed"
    not_found = "not_found"
    forbidden = "forbidden"
    duplicate_resource = "duplicate_resource"
    outside_service_area = "outside_service_area"
    idempotency_conflict = "idempotency_conflict"
    # Additions beyond that minimum, approved during the mapping review.
    unauthenticated = "unauthenticated"  # 401s: bad/missing/expired credentials or token, not a permissions question
    account_deactivated = "account_deactivated"  # a specific, actionable reason to be unauthenticated
    invalid_credentials = "invalid_credentials"  # wrong password — shared by login and account step-up re-auth
    invalid_code = "invalid_code"  # wrong 2FA code — login verify and enrollment confirm
    token_invalid_or_expired = "token_invalid_or_expired"  # email verification / password reset links
    cannot_target_self = "cannot_target_self"  # every "you can't do this to your own account/content" 400
    invalid_state = "invalid_state"  # other 400s rejecting based on a resource's current state, not malformed input
    payload_too_large = "payload_too_large"  # 413s (upload size limits)
    not_implemented = "not_implemented"  # the payment-webhook skeleton's deliberate 501
    rate_limited = "rate_limited"  # 429s
    # Deliberately NOT added: "account_locked". A locked-out login
    # attempt must stay byte-for-byte identical to a wrong-password
    # one — see app/login_lockout.py's docstring and CLAUDE.md's rule
    # that an account/credential-state security control must never
    # change the response in a way that reveals that state. Adding a
    # distinct error_code here would be exactly that leak, just moved
    # from the HTTP status/body into a different field of the same
    # body — flagged and rejected during review, not an oversight.


class AppError(HTTPException):
    def __init__(
        self,
        status_code: int,
        error_code: ErrorCode,
        detail: str,
        params: dict[str, object] | None = None,
        headers: dict | None = None,
    ):
        self.error_code = error_code
        self.params = params
        super().__init__(status_code=status_code, detail=detail, headers=headers)


# Fallback mapping for any plain HTTPException not yet migrated to
# AppError (see app/main.py's exception handler) — generic by status
# code only, so "every error response has error_code" holds even for
# code this pass misses.
_FALLBACK_CODE_BY_STATUS: dict[int, ErrorCode] = {
    400: ErrorCode.invalid_state,
    401: ErrorCode.unauthenticated,
    403: ErrorCode.forbidden,
    404: ErrorCode.not_found,
    409: ErrorCode.duplicate_resource,
    413: ErrorCode.payload_too_large,
    422: ErrorCode.validation_failed,
    429: ErrorCode.rate_limited,
    501: ErrorCode.not_implemented,
}


def fallback_error_code(status_code: int) -> ErrorCode:
    return _FALLBACK_CODE_BY_STATUS.get(status_code, ErrorCode.invalid_state)


# Maps Pydantic v2's own internal error `type` strings to the field
# codes we actually expose to clients — frozen deliberately, pinned by
# tests/unit/test_errors.py, specifically so a future Pydantic upgrade
# that renames one of these internally degrades to the generic
# fallback below rather than silently leaking a new, unreviewed
# string. Covers every validator pattern currently used in this
# codebase (see that test for the full list).
_FIELD_CODE_BY_PYDANTIC_TYPE: dict[str, str] = {
    "missing": "missing",
    "string_too_short": "too_short",
    "string_too_long": "too_long",
    "value_error": "invalid",
    "greater_than_equal": "out_of_range",
    "less_than_equal": "out_of_range",
    "greater_than": "out_of_range",
    "less_than": "out_of_range",
    "int_parsing": "invalid_type",
    "float_parsing": "invalid_type",
    "bool_parsing": "invalid_type",
    "uuid_parsing": "invalid_type",
    "datetime_parsing": "invalid_type",
    "datetime_from_date_parsing": "invalid_type",
    "timezone_aware": "invalid_type",
    "enum": "invalid_choice",
    "literal_error": "invalid_choice",
    "json_invalid": "invalid_type",
    "extra_forbidden": "unexpected_field",
    "list_type": "invalid_type",
    "too_short": "too_short",
    "too_long": "too_long",
}
_GENERIC_FIELD_CODE = "invalid"


def field_error_code(pydantic_type: str) -> str:
    return _FIELD_CODE_BY_PYDANTIC_TYPE.get(pydantic_type, _GENERIC_FIELD_CODE)


def build_field_errors(errors: Sequence[dict]) -> list[dict[str, str]]:
    """Builds the `fields` array from Pydantic's exc.errors() —
    deliberately reading ONLY loc/type/msg from each error dict, NEVER
    `input` (or `ctx`, which can itself echo part of the input in some
    error types) — `input` is the raw submitted value for ANY field,
    including a password or token, attached by Pydantic uniformly
    regardless of which constraint failed. Never include it."""
    fields = []
    for err in errors:
        loc = err["loc"]
        # Drop the leading location-type segment (body/query/path) —
        # not useful to a client matching this against a form field.
        field_path = ".".join(str(p) for p in loc[1:]) if len(loc) > 1 else str(loc[0])
        fields.append({"field": field_path, "code": field_error_code(err["type"]), "message": err["msg"]})
    return fields
