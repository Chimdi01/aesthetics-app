"""
Every server-generated, human-facing notification's copy lives here,
keyed by (event, language) — never built as an inline f-string at the
call site. See CLAUDE.md's Locale convention.

"en" always exists for every event; render() falls back to it when the
recipient's preferred language has no template yet (true for every
non-"en" language right now — French copy needs a native-speaker
review before it ships, see CLAUDE.md, so only the "en" entries are
real so far). Adding a language is adding entries to this dict, not
writing new code.

Plain str.format() templates, not callables/lambdas — keeps this file
looking like the data it is, so a future translator (or an automated
check that every language has every event) can read it as a table, not
Python logic.
"""
from app.locale import DEFAULT_LANGUAGE

# event -> language -> (subject_template, body_template)
_TEMPLATES: dict[str, dict[str, tuple[str, str]]] = {
    "verify_email": {
        "en": ("Verify your email", "Click to verify your email: {link}"),
    },
    "reset_password": {
        "en": ("Reset your password", "Click to reset your password: {link}"),
    },
    "new_message": {
        "en": ("New message", "{sender_name}: {message_body}"),
    },
    "booking_status_changed": {
        "en": ("Booking update", "Your booking is now {new_status}."),
    },
    "new_review": {
        "en": ("New review", "You received a new {rating}-star review."),
    },
    "verification_approved": {
        "en": ("Verification update", "Your identity verification was approved."),
    },
    "verification_rejected": {
        "en": ("Verification update", "Your identity verification was rejected: {reason}"),
    },
    "report_decision": {
        "en": ("Report update", "A report you filed has been {status}."),
    },
}


def render(event: str, language: str, **kwargs: object) -> tuple[str, str]:
    """Returns (subject, body) for `event`, in `language` if a
    template exists for it, else DEFAULT_LANGUAGE. kwargs are that
    event's own template variables — see _TEMPLATES above."""
    by_language = _TEMPLATES[event]
    subject_template, body_template = by_language.get(language) or by_language[DEFAULT_LANGUAGE]
    return subject_template.format(**kwargs), body_template.format(**kwargs)
