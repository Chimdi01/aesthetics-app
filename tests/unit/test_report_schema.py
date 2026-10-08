"""
Pure Pydantic validation on ReportCreate/ReportReviewUpdate — no DB, no HTTP.
"""
import pytest
from pydantic import ValidationError

from app.schemas.report import ReportCreate, ReportReviewUpdate


def test_report_create_accepts_valid_reason_without_details():
    report = ReportCreate(reason="safety_concern")
    assert report.details is None


def test_report_create_accepts_details():
    report = ReportCreate(reason="spam", details="Kept messaging about unrelated services")
    assert report.details == "Kept messaging about unrelated services"


def test_report_create_rejects_details_with_null_byte():
    with pytest.raises(ValidationError):
        ReportCreate(reason="other", details="bad\x00byte")


def test_report_create_rejects_invalid_reason():
    with pytest.raises(ValidationError):
        ReportCreate(reason="not_a_real_reason")


def test_report_review_update_accepts_resolved():
    update = ReportReviewUpdate(status="resolved")
    assert update.status.value == "resolved"


def test_report_review_update_accepts_dismissed():
    update = ReportReviewUpdate(status="dismissed")
    assert update.status.value == "dismissed"


def test_report_review_update_rejects_pending():
    with pytest.raises(ValidationError):
        ReportReviewUpdate(status="pending")
