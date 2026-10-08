"""
Pure Pydantic validation on VerificationReviewUpdate — no DB, no HTTP.
"""
import pytest
from pydantic import ValidationError

from app.schemas.identity_verification import VerificationReviewUpdate


def test_approve_without_reason_is_valid():
    update = VerificationReviewUpdate(status="approved")
    assert update.rejection_reason is None


def test_reject_with_reason_is_valid():
    update = VerificationReviewUpdate(status="rejected", rejection_reason="Photo is blurry")
    assert update.rejection_reason == "Photo is blurry"


def test_reject_without_reason_is_rejected():
    with pytest.raises(ValidationError):
        VerificationReviewUpdate(status="rejected")


def test_setting_status_back_to_pending_is_rejected():
    with pytest.raises(ValidationError):
        VerificationReviewUpdate(status="pending")
