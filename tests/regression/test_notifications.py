"""
Notification dispatch (app/notifications.py) exercised through the real
endpoints that trigger it — new message, booking status change, new
review, verification decision, report decision. Both channels use the
"console" backend (app/email.py / app/sms.py), so a sent notification
shows up as a logged line — caplog.clear() right before the triggering
action isolates that line from everything else logged during setup
(signup already sends its own verification email — see the same
pattern already used in tests/regression/test_password_reset.py).
"""
import io
from datetime import UTC, datetime, timedelta

from PIL import Image
from sqlalchemy import text

from tests.conftest import login, register_user, test_engine

FUTURE = (datetime.now(UTC) + timedelta(days=1)).isoformat()


def _real_jpeg_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (50, 50), (0, 128, 255)).save(buffer, format="JPEG")
    return buffer.getvalue()


def _document_file():
    return {"file": ("id.jpg", io.BytesIO(_real_jpeg_bytes()), "image/jpeg")}


async def _create_provider_with_profile(client, email="jane@example.com"):
    await register_user(client, email, password="secret123", role="provider", full_name="Jane Stylist")
    token = await login(client, email, "secret123")
    headers = {"Authorization": f"Bearer {token}"}
    profile = (
        await client.post(
            "/v1/providers/",
            json={"business_name": "Jane's Studio", "categories": ["hair"]},
            headers=headers,
        )
    ).json()
    return profile, headers


async def _create_customer_headers(client, email="cust@example.com"):
    await register_user(client, email)
    token = await login(client, email)
    return {"Authorization": f"Bearer {token}"}


async def _create_booking(client, provider_profile_id, customer_headers):
    response = await client.post(
        "/v1/bookings/",
        json={
            "provider_profile_id": provider_profile_id,
            "category": "hair",
            "visit_type": "shop_visit",
            "scheduled_at": FUTURE,
        },
        headers=customer_headers,
    )
    return response.json()


async def _create_completed_booking(client, provider_headers, customer_headers, profile_id):
    booking = await _create_booking(client, profile_id, customer_headers)
    await client.patch(f"/v1/bookings/{booking['id']}/status", json={"status": "confirmed"}, headers=provider_headers)
    await client.patch(f"/v1/bookings/{booking['id']}/status", json={"status": "completed"}, headers=provider_headers)
    return booking


async def _promote_to_admin(email: str) -> None:
    async with test_engine.begin() as conn:
        await conn.execute(text("UPDATE users SET role = 'admin' WHERE email = :email"), {"email": email})


async def _create_admin_headers(client, email="admin@example.com"):
    await register_user(client, email, role="customer")
    await _promote_to_admin(email)
    token = await login(client, email)
    return {"Authorization": f"Bearer {token}"}


async def _set_phone_number(client, headers, phone_number):
    await client.patch("/v1/users/me/phone-number", json={"phone_number": phone_number}, headers=headers)


async def _register_device_token(client, headers, token, platform="android"):
    await client.post(
        "/v1/users/me/device-tokens", json={"token": token, "platform": platform}, headers=headers
    )


async def _disable_preference(client, headers, field):
    await client.patch("/v1/users/me/notification-preferences", json={field: False}, headers=headers)


# --- new message ---


async def test_customer_message_notifies_the_provider(client, caplog):
    profile, _ = await _create_provider_with_profile(client, "provider-msg@example.com")
    customer_headers = await _create_customer_headers(client, "customer-msg@example.com")
    booking = await _create_booking(client, profile["id"], customer_headers)

    caplog.clear()
    with caplog.at_level("INFO"):
        response = await client.post(
            f"/v1/bookings/{booking['id']}/messages", json={"body": "Hi there"}, headers=customer_headers
        )
    assert response.status_code == 201
    assert "provider-msg@example.com" in caplog.text
    assert "New message" in caplog.text


async def test_provider_message_notifies_the_customer(client, caplog):
    profile, provider_headers = await _create_provider_with_profile(client, "provider-msg2@example.com")
    customer_headers = await _create_customer_headers(client, "customer-msg2@example.com")
    booking = await _create_booking(client, profile["id"], customer_headers)

    caplog.clear()
    with caplog.at_level("INFO"):
        response = await client.post(
            f"/v1/bookings/{booking['id']}/messages", json={"body": "On my way"}, headers=provider_headers
        )
    assert response.status_code == 201
    assert "customer-msg2@example.com" in caplog.text


async def test_first_message_only_preference_skips_later_messages(client, caplog):
    profile, provider_headers = await _create_provider_with_profile(client, "freq-provider@example.com")
    customer_headers = await _create_customer_headers(client, "freq-customer@example.com")
    booking = await _create_booking(client, profile["id"], customer_headers)
    # The PROVIDER is the recipient of a customer-sent message, so it's
    # the provider's preference that governs whether they get notified.
    await client.patch(
        "/v1/users/me/notification-preferences",
        json={"message_frequency": "first_message_only"},
        headers=provider_headers,
    )

    caplog.clear()
    with caplog.at_level("INFO"):
        first = await client.post(
            f"/v1/bookings/{booking['id']}/messages", json={"body": "first"}, headers=customer_headers
        )
    assert first.status_code == 201
    assert "freq-provider@example.com" in caplog.text

    caplog.clear()
    with caplog.at_level("INFO"):
        second = await client.post(
            f"/v1/bookings/{booking['id']}/messages", json={"body": "second"}, headers=customer_headers
        )
    assert second.status_code == 201
    assert "freq-provider@example.com" not in caplog.text


async def test_disabling_message_notifications_sends_nothing(client, caplog):
    profile, provider_headers = await _create_provider_with_profile(client, "disabled-provider@example.com")
    customer_headers = await _create_customer_headers(client, "disabled-customer@example.com")
    booking = await _create_booking(client, profile["id"], customer_headers)
    await _disable_preference(client, provider_headers, "notify_on_new_message")

    caplog.clear()
    with caplog.at_level("INFO"):
        response = await client.post(
            f"/v1/bookings/{booking['id']}/messages", json={"body": "hello"}, headers=customer_headers
        )
    assert response.status_code == 201
    assert "disabled-provider@example.com" not in caplog.text


async def test_message_notification_includes_sms_when_phone_number_set(client, caplog):
    profile, provider_headers = await _create_provider_with_profile(client, "sms-provider@example.com")
    customer_headers = await _create_customer_headers(client, "sms-customer@example.com")
    await _set_phone_number(client, provider_headers, "+14155552671")
    booking = await _create_booking(client, profile["id"], customer_headers)

    caplog.clear()
    with caplog.at_level("INFO"):
        response = await client.post(
            f"/v1/bookings/{booking['id']}/messages", json={"body": "hi"}, headers=customer_headers
        )
    assert response.status_code == 201
    assert "+14155552671" in caplog.text
    assert "SMS to" in caplog.text


async def test_message_notification_has_no_sms_without_a_phone_number(client, caplog):
    profile, _ = await _create_provider_with_profile(client, "nosms-provider@example.com")
    customer_headers = await _create_customer_headers(client, "nosms-customer@example.com")
    booking = await _create_booking(client, profile["id"], customer_headers)

    caplog.clear()
    with caplog.at_level("INFO"):
        response = await client.post(
            f"/v1/bookings/{booking['id']}/messages", json={"body": "hi"}, headers=customer_headers
        )
    assert response.status_code == 201
    assert "SMS to" not in caplog.text


async def test_message_notification_includes_push_when_a_device_is_registered(client, caplog):
    profile, provider_headers = await _create_provider_with_profile(client, "push-provider@example.com")
    customer_headers = await _create_customer_headers(client, "push-customer@example.com")
    await _register_device_token(client, provider_headers, "providers-device-token")
    booking = await _create_booking(client, profile["id"], customer_headers)

    caplog.clear()
    with caplog.at_level("INFO"):
        response = await client.post(
            f"/v1/bookings/{booking['id']}/messages", json={"body": "hi"}, headers=customer_headers
        )
    assert response.status_code == 201
    assert "providers-device-token" in caplog.text
    assert "Push to" in caplog.text


async def test_message_notification_pushes_to_every_registered_device(client, caplog):
    profile, provider_headers = await _create_provider_with_profile(client, "multidevice-provider@example.com")
    customer_headers = await _create_customer_headers(client, "multidevice-customer@example.com")
    await _register_device_token(client, provider_headers, "providers-phone", platform="ios")
    await _register_device_token(client, provider_headers, "providers-tablet", platform="ios")
    booking = await _create_booking(client, profile["id"], customer_headers)

    caplog.clear()
    with caplog.at_level("INFO"):
        response = await client.post(
            f"/v1/bookings/{booking['id']}/messages", json={"body": "hi"}, headers=customer_headers
        )
    assert response.status_code == 201
    assert "providers-phone" in caplog.text
    assert "providers-tablet" in caplog.text


async def test_message_notification_has_no_push_without_a_registered_device(client, caplog):
    profile, _ = await _create_provider_with_profile(client, "nopush-provider@example.com")
    customer_headers = await _create_customer_headers(client, "nopush-customer@example.com")
    booking = await _create_booking(client, profile["id"], customer_headers)

    caplog.clear()
    with caplog.at_level("INFO"):
        response = await client.post(
            f"/v1/bookings/{booking['id']}/messages", json={"body": "hi"}, headers=customer_headers
        )
    assert response.status_code == 201
    assert "Push to" not in caplog.text


# --- booking status change ---


async def test_provider_confirming_booking_notifies_customer(client, caplog):
    profile, provider_headers = await _create_provider_with_profile(client, "confirm-provider@example.com")
    customer_headers = await _create_customer_headers(client, "confirm-customer@example.com")
    booking = await _create_booking(client, profile["id"], customer_headers)

    caplog.clear()
    with caplog.at_level("INFO"):
        response = await client.patch(
            f"/v1/bookings/{booking['id']}/status", json={"status": "confirmed"}, headers=provider_headers
        )
    assert response.status_code == 200
    assert "confirm-customer@example.com" in caplog.text
    assert "Booking update" in caplog.text


async def test_customer_cancelling_booking_notifies_provider(client, caplog):
    profile, _ = await _create_provider_with_profile(client, "cancel-provider@example.com")
    customer_headers = await _create_customer_headers(client, "cancel-customer@example.com")
    booking = await _create_booking(client, profile["id"], customer_headers)

    caplog.clear()
    with caplog.at_level("INFO"):
        response = await client.patch(
            f"/v1/bookings/{booking['id']}/status", json={"status": "cancelled"}, headers=customer_headers
        )
    assert response.status_code == 200
    assert "cancel-provider@example.com" in caplog.text


async def test_disabling_booking_status_notifications(client, caplog):
    profile, provider_headers = await _create_provider_with_profile(client, "nostatus-provider@example.com")
    customer_headers = await _create_customer_headers(client, "nostatus-customer@example.com")
    booking = await _create_booking(client, profile["id"], customer_headers)
    await _disable_preference(client, customer_headers, "notify_on_booking_status_change")

    caplog.clear()
    with caplog.at_level("INFO"):
        response = await client.patch(
            f"/v1/bookings/{booking['id']}/status", json={"status": "confirmed"}, headers=provider_headers
        )
    assert response.status_code == 200
    assert "nostatus-customer@example.com" not in caplog.text


# --- new review ---


async def test_new_review_notifies_the_provider(client, caplog):
    profile, provider_headers = await _create_provider_with_profile(client, "review-provider@example.com")
    customer_headers = await _create_customer_headers(client, "review-customer@example.com")
    booking = await _create_completed_booking(client, provider_headers, customer_headers, profile["id"])

    caplog.clear()
    with caplog.at_level("INFO"):
        response = await client.post(
            f"/v1/bookings/{booking['id']}/review", json={"rating": 5}, headers=customer_headers
        )
    assert response.status_code == 201
    assert "review-provider@example.com" in caplog.text
    assert "New review" in caplog.text


async def test_disabling_review_notifications(client, caplog):
    profile, provider_headers = await _create_provider_with_profile(client, "noreview-provider@example.com")
    customer_headers = await _create_customer_headers(client, "noreview-customer@example.com")
    booking = await _create_completed_booking(client, provider_headers, customer_headers, profile["id"])
    await _disable_preference(client, provider_headers, "notify_on_new_review")

    caplog.clear()
    with caplog.at_level("INFO"):
        response = await client.post(
            f"/v1/bookings/{booking['id']}/review", json={"rating": 3}, headers=customer_headers
        )
    assert response.status_code == 201
    assert "noreview-provider@example.com" not in caplog.text


# --- verification decision ---


async def test_verification_approval_notifies_the_submitter(client, caplog):
    await register_user(client, "verify-me@example.com")
    token = await login(client, "verify-me@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    submitted = (
        await client.post(
            "/v1/verification/me", files=_document_file(), data={"document_type": "passport"}, headers=headers
        )
    ).json()

    admin_headers = await _create_admin_headers(client, "verify-admin@example.com")
    caplog.clear()
    with caplog.at_level("INFO"):
        response = await client.patch(
            f"/v1/admin/verifications/{submitted['id']}", json={"status": "approved"}, headers=admin_headers
        )
    assert response.status_code == 200
    assert "verify-me@example.com" in caplog.text
    assert "Verification update" in caplog.text


async def test_verification_rejection_notifies_the_submitter_with_reason(client, caplog):
    await register_user(client, "reject-me@example.com")
    token = await login(client, "reject-me@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    submitted = (
        await client.post(
            "/v1/verification/me", files=_document_file(), data={"document_type": "passport"}, headers=headers
        )
    ).json()

    admin_headers = await _create_admin_headers(client, "reject-admin@example.com")
    caplog.clear()
    with caplog.at_level("INFO"):
        response = await client.patch(
            f"/v1/admin/verifications/{submitted['id']}",
            json={"status": "rejected", "rejection_reason": "Blurry photo"},
            headers=admin_headers,
        )
    assert response.status_code == 200
    assert "reject-me@example.com" in caplog.text
    assert "Blurry photo" in caplog.text


# --- report decision ---


async def test_report_resolution_notifies_the_reporter_not_the_reported_user(client, caplog):
    await register_user(client, "reporter@example.com")
    reporter_token = await login(client, "reporter@example.com")
    target = (await register_user(client, "reported-target@example.com")).json()

    report = (
        await client.post(
            f"/v1/users/{target['id']}/report",
            json={"reason": "spam"},
            headers={"Authorization": f"Bearer {reporter_token}"},
        )
    ).json()

    admin_headers = await _create_admin_headers(client, "report-admin@example.com")
    caplog.clear()
    with caplog.at_level("INFO"):
        response = await client.patch(
            f"/v1/admin/reports/{report['id']}", json={"status": "resolved"}, headers=admin_headers
        )
    assert response.status_code == 200
    assert "reporter@example.com" in caplog.text
    # The reported user is never told a report concerning them exists
    # or was resolved — see app/notifications.py's
    # notify_report_decision docstring.
    assert "reported-target@example.com" not in caplog.text
    assert "Report update" in caplog.text
