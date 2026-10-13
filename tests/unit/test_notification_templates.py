"""
Pure logic on app/notification_templates.py's render() — no DB, no HTTP.
"""
from app.notification_templates import render


def test_render_fills_in_the_requested_event_and_language():
    subject, body = render("new_review", "en", rating=5)
    assert subject == "New review"
    assert body == "You received a new 5-star review."


def test_render_falls_back_to_english_for_an_unsupported_language():
    # French templates don't exist yet (see CLAUDE.md's Locale
    # convention — "fr later", not now) — a French-preferring
    # recipient still gets a real, correct notification today, not a
    # KeyError or empty copy.
    en_subject, en_body = render("new_review", "en", rating=5)
    fr_subject, fr_body = render("new_review", "fr", rating=5)
    assert (fr_subject, fr_body) == (en_subject, en_body)


def test_render_verification_approved_takes_no_extra_kwargs():
    subject, body = render("verification_approved", "en")
    assert subject == "Verification update"
    assert body == "Your identity verification was approved."


def test_render_verification_rejected_includes_the_reason():
    _, body = render("verification_rejected", "en", reason="Document was blurry")
    assert body == "Your identity verification was rejected: Document was blurry"
