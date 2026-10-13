"""
Pure logic on app/payments/payment_provider.py — no DB, no HTTP.
"""
import pytest

from app.payments.payment_provider import PaymentProvider, provider_for_country


@pytest.mark.parametrize(
    "country,expected",
    [
        ("GB", PaymentProvider.stripe),
        ("FR", PaymentProvider.stripe),
        ("NG", PaymentProvider.flutterwave),
        ("CI", PaymentProvider.flutterwave),
        ("SN", PaymentProvider.flutterwave),
    ],
)
def test_provider_for_country_matches_the_right_processor(country, expected):
    assert provider_for_country(country) == expected


def test_provider_for_country_raises_for_an_unconfigured_market():
    # US/South America are real future intent (see CLAUDE.md) but not
    # a decided market yet — this is the correct failure mode until
    # they are, not a silent guess.
    with pytest.raises(KeyError):
        provider_for_country("US")
