import io

import pytest
from PIL import Image

from app.config import settings
from app.main import app
from tests.conftest import login, register_user


@pytest.fixture(autouse=True)
def _use_tmp_media_root(tmp_path, monkeypatch):
    # Without this, every upload in this file would land in the real
    # ./media directory at the project root instead of a throwaway one.
    monkeypatch.setattr(settings, "media_root", str(tmp_path))
    # settings.media_root is read once, at app-startup time, to construct
    # the /media StaticFiles mount (app/main.py) — patching the setting
    # alone doesn't retroactively change that already-constructed
    # instance's directory, so a GET against an uploaded file's URL would
    # still (fail to) look in the real ./media directory unless this is
    # patched too.
    media_route = next(r for r in app.routes if getattr(r, "name", None) == "media")
    monkeypatch.setattr(media_route.app, "directory", str(tmp_path))
    # StaticFiles actually serves from self.all_directories (computed
    # once from `directory` at construction time), not self.directory
    # directly — patching directory alone isn't enough.
    monkeypatch.setattr(media_route.app, "all_directories", [str(tmp_path)])
    yield


async def _create_provider_headers(client, email="jane@example.com"):
    await register_user(client, email, password="secret123", role="provider", full_name="Jane Stylist")
    token = await login(client, email, "secret123")
    return {"Authorization": f"Bearer {token}"}


async def _create_provider_profile(client, headers, categories=None):
    response = await client.post(
        "/v1/providers/",
        json={"business_name": "Jane's Studio", "categories": categories or ["hair"]},
        headers=headers,
    )
    return response.json()


async def _create_customer_headers(client, email="cust@example.com"):
    await register_user(client, email, password="secret123", role="customer")
    token = await login(client, email, "secret123")
    return {"Authorization": f"Bearer {token}"}


def _real_jpeg_bytes() -> bytes:
    # A real, decodable JPEG — needed now that uploads are actually run
    # through Pillow (see app/storage.py), not just trusted by Content-Type.
    buffer = io.BytesIO()
    Image.new("RGB", (50, 50), (255, 0, 0)).save(buffer, format="JPEG")
    return buffer.getvalue()


def _jpeg_file(content: bytes | None = None):
    return {"file": ("photo.jpg", io.BytesIO(content or _real_jpeg_bytes()), "image/jpeg")}


async def test_upload_portfolio_media_success(client):
    provider_headers = await _create_provider_headers(client)
    await _create_provider_profile(client, provider_headers)

    response = await client.post(
        "/v1/providers/me/portfolio",
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
    response = await client.post("/v1/providers/me/portfolio", files=_jpeg_file())
    assert response.status_code == 401


async def test_upload_portfolio_media_as_customer_returns_403(client):
    customer_headers = await _create_customer_headers(client)
    response = await client.post("/v1/providers/me/portfolio", files=_jpeg_file(), headers=customer_headers)
    assert response.status_code == 403


async def test_upload_portfolio_media_without_provider_profile_returns_404(client):
    provider_headers = await _create_provider_headers(client)
    response = await client.post("/v1/providers/me/portfolio", files=_jpeg_file(), headers=provider_headers)
    assert response.status_code == 404


async def test_upload_portfolio_media_rejects_content_claiming_to_be_an_image_but_isnt(client):
    provider_headers = await _create_provider_headers(client)
    await _create_provider_profile(client, provider_headers)

    response = await client.post(
        "/v1/providers/me/portfolio",
        files=_jpeg_file(content=b"this is not actually a jpeg"),
        headers=provider_headers,
    )
    assert response.status_code == 400


async def test_uploaded_photo_is_served_with_long_lived_cache_control(client):
    provider_headers = await _create_provider_headers(client)
    await _create_provider_profile(client, provider_headers)
    uploaded = (
        await client.post("/v1/providers/me/portfolio", files=_jpeg_file(), headers=provider_headers)
    ).json()

    response = await client.get(uploaded["url"])
    assert response.status_code == 200
    # Safe to cache forever: filenames are server-generated UUIDs that
    # never get reused for different content (see app/storage.py).
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"


async def test_upload_portfolio_media_rejects_disallowed_content_type(client):
    provider_headers = await _create_provider_headers(client)
    await _create_provider_profile(client, provider_headers)

    response = await client.post(
        "/v1/providers/me/portfolio",
        files={"file": ("doc.pdf", io.BytesIO(b"not an image"), "application/pdf")},
        headers=provider_headers,
    )
    assert response.status_code == 400


async def test_upload_portfolio_media_rejects_oversized_file(client, monkeypatch):
    monkeypatch.setattr(settings, "max_upload_size_bytes", 10)
    provider_headers = await _create_provider_headers(client)
    await _create_provider_profile(client, provider_headers)

    response = await client.post(
        "/v1/providers/me/portfolio",
        files={"file": ("photo.jpg", io.BytesIO(b"x" * 1000), "image/jpeg")},
        headers=provider_headers,
    )
    assert response.status_code == 413


async def test_list_provider_portfolio_is_public_and_provider_scoped(client):
    provider_a_headers = await _create_provider_headers(client, "jane@example.com")
    profile_a = await _create_provider_profile(client, provider_a_headers)
    await client.post("/v1/providers/me/portfolio", files=_jpeg_file(), headers=provider_a_headers)

    provider_b_headers = await _create_provider_headers(client, "amy@example.com")
    await _create_provider_profile(client, provider_b_headers, categories=["nails"])
    await client.post("/v1/providers/me/portfolio", files=_jpeg_file(), headers=provider_b_headers)

    response = await client.get(f"/v1/providers/{profile_a['id']}/portfolio")
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    assert items[0]["provider_profile_id"] == profile_a["id"]


async def test_list_portfolio_for_unknown_provider_returns_404(client):
    response = await client.get("/v1/providers/00000000-0000-0000-0000-000000000000/portfolio")
    assert response.status_code == 404


async def test_delete_own_portfolio_media_succeeds(client):
    provider_headers = await _create_provider_headers(client)
    profile = await _create_provider_profile(client, provider_headers)
    uploaded = (
        await client.post("/v1/providers/me/portfolio", files=_jpeg_file(), headers=provider_headers)
    ).json()

    response = await client.delete(f"/v1/providers/me/portfolio/{uploaded['id']}", headers=provider_headers)
    assert response.status_code == 204

    listing = await client.get(f"/v1/providers/{profile['id']}/portfolio")
    assert listing.json() == []


async def test_delete_someone_elses_portfolio_media_returns_404(client):
    owner_headers = await _create_provider_headers(client, "jane@example.com")
    await _create_provider_profile(client, owner_headers)
    uploaded = (
        await client.post("/v1/providers/me/portfolio", files=_jpeg_file(), headers=owner_headers)
    ).json()

    other_provider_headers = await _create_provider_headers(client, "amy@example.com")
    await _create_provider_profile(client, other_provider_headers, categories=["nails"])

    response = await client.delete(
        f"/v1/providers/me/portfolio/{uploaded['id']}", headers=other_provider_headers
    )
    assert response.status_code == 404


async def test_delete_portfolio_media_without_token_returns_401(client):
    response = await client.delete("/v1/providers/me/portfolio/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 401
