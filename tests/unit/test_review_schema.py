"""
Pure Pydantic validation on ReviewCreate — no DB, no HTTP. The 1-5 range
is also enforced as a DB CheckConstraint (defense in depth), but that
requires a real DB to exercise and is covered by the 422 regression test
in tests/regression/test_reviews.py instead.
"""
import pytest
from pydantic import ValidationError

from app.schemas.review import ReviewCreate


def test_review_create_accepts_valid_rating():
    review = ReviewCreate(rating=5, comment="Great cut")
    assert review.rating == 5
    assert review.comment == "Great cut"


def test_review_create_allows_missing_comment():
    review = ReviewCreate(rating=3)
    assert review.comment is None


def test_review_create_rejects_rating_below_1():
    with pytest.raises(ValidationError):
        ReviewCreate(rating=0)


def test_review_create_rejects_rating_above_5():
    with pytest.raises(ValidationError):
        ReviewCreate(rating=6)


def test_review_create_rejects_comment_with_embedded_null_byte():
    # Postgres would reject this at the driver level with a raw DB error;
    # this validator turns it into a clean 422 instead.
    with pytest.raises(ValidationError):
        ReviewCreate(rating=4, comment="great\x00cut")
