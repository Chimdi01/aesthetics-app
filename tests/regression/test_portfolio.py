import io

import pytest

from app.config import settings
from tests.conftest import login, register_user


@pytest.fixture(autouse=True)
def _use_tmp_media_root(tmp_path, monkeypatch):
    # Without this, every upload in this file would land in the real
    # ./media directory at the project root instead of a throwaway one.
    monkeypatch.setattr(settings, "media_root", str(tmp_path))
    yield


async def _create_provider_headers(client, email="jane@example.com"):
    await register_user(client, email, password="secret123", role="provider", full_name="Jane Stylist")
    token = await login(client, email, "secret123")
    return {"Authorization": f"Bearer {token}"}


async def _create_provider_profile(client, headers, categories=None):
    response = await client.post(
        "/providers/",
        json={"business_name": "Jane's Studio", "categories": categories or ["hair"]},
        headers=headers,
    )
    return response.json()


async def _create_customer_headers(client, email="cust@example.com"):
    await register_user(client, email, password="secret123", role="customer")
    token = await login(client, email, "secret123")
    return {"Authorization": f"Bearer {token}"}


def _jpeg_file(content=b"fake-jpeg-bytes"):
    return {"file": ("photo.jpg", io.BytesIO(content), "image/jpeg")}


async def test_upload_portfolio_media_success(client):
    provider_headers = await _create_provider_headers(client)
    await _create_provider_profile(client, provider_headers)

    response = await client.post(
        "/providers/me/portfolio",
        files=_jpeg_file(),
        data={"caption": "Balayage look"},
        headers=provider_headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["media_type"] == "photo"
    assert body["caption"] == "Balayage look"
    assert body["url"].startswith("/media/")


async def test_upload_portfolio_media_without_token_returns_401(client):
    response = await client.post("/providers/me/portfolio", files=_jpeg_file())
    assert response.status_code == 401


async def test_upload_portfolio_media_as_customer_returns_403(client):
    customer_headers = await _create_customer_headers(client)
    response = await client.post("/providers/me/portfolio", files=_jpeg_file(), headers=customer_headers)
    assert response.status_code == 403


async def test_upload_portfolio_media_without_provider_profile_returns_404(client):
    provider_headers = await _create_provider_headers(client)
    response = await client.post("/providers/me/portfolio", files=_jpeg_file(), headers=provider_headers)
    assert response.status_code == 404


async def test_upload_portfolio_media_rejects_disallowed_content_type(client):
    provider_headers = await _create_provider_headers(client)
    await _create_provider_profile(client, provider_headers)

    response = await client.post(
        "/providers/me/portfolio",
        files={"file": ("doc.pdf", io.BytesIO(b"not an image"), "application/pdf")},
        headers=provider_headers,
    )
    assert response.status_code == 400


async def test_upload_portfolio_media_rejects_oversized_file(client, monkeypatch):
    monkeypatch.setattr(settings, "max_upload_size_bytes", 10)
    provider_headers = await _create_provider_headers(client)
    await _create_provider_profile(client, provider_headers)

    response = await client.post(
        "/providers/me/portfolio",
        files={"file": ("photo.jpg", io.BytesIO(b"x" * 1000), "image/jpeg")},
        headers=provider_headers,
    )
    assert response.status_code == 413


async def test_list_provider_portfolio_is_public_and_provider_scoped(client):
    provider_a_headers = await _create_provider_headers(client, "jane@example.com")
    profile_a = await _create_provider_profile(client, provider_a_headers)
    await client.post("/providers/me/portfolio", files=_jpeg_file(), headers=provider_a_headers)

    provider_b_headers = await _create_provider_headers(client, "amy@example.com")
    await _create_provider_profile(client, provider_b_headers, categories=["nails"])
    await client.post("/providers/me/portfolio", files=_jpeg_file(), headers=provider_b_headers)

    response = await client.get(f"/providers/{profile_a['id']}/portfolio")
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    assert items[0]["provider_profile_id"] == profile_a["id"]


async def test_list_portfolio_for_unknown_provider_returns_404(client):
    response = await client.get("/providers/00000000-0000-0000-0000-000000000000/portfolio")
    assert response.status_code == 404


async def test_delete_own_portfolio_media_succeeds(client):
    provider_headers = await _create_provider_headers(client)
    profile = await _create_provider_profile(client, provider_headers)
    uploaded = (
        await client.post("/providers/me/portfolio", files=_jpeg_file(), headers=provider_headers)
    ).json()

    response = await client.delete(f"/providers/me/portfolio/{uploaded['id']}", headers=provider_headers)
    assert response.status_code == 204

    listing = await client.get(f"/providers/{profile['id']}/portfolio")
    assert listing.json() == []


async def test_delete_someone_elses_portfolio_media_returns_404(client):
    owner_headers = await _create_provider_headers(client, "jane@example.com")
    await _create_provider_profile(client, owner_headers)
    uploaded = (
        await client.post("/providers/me/portfolio", files=_jpeg_file(), headers=owner_headers)
    ).json()

    other_provider_headers = await _create_provider_headers(client, "amy@example.com")
    await _create_provider_profile(client, other_provider_headers, categories=["nails"])

    response = await client.delete(
        f"/providers/me/portfolio/{uploaded['id']}", headers=other_provider_headers
    )
    assert response.status_code == 404


async def test_delete_portfolio_media_without_token_returns_401(client):
    response = await client.delete("/providers/me/portfolio/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 401
