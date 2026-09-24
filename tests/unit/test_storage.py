"""
app/storage.py touches the real filesystem but no DB/HTTP, so it's
exercised here with pytest's tmp_path fixture rather than in
tests/regression/ — these are the security-relevant behaviors (content-type
allowlist, size cap enforced while streaming, no client-controlled
filenames) that don't need a live app or Postgres to verify.
"""
import io
import uuid
from pathlib import Path

import pytest
from fastapi import HTTPException
from starlette.datastructures import Headers, UploadFile

from app.config import settings
from app.models.portfolio_media import MediaType
from app.storage import delete_file, save_upload


def _upload_file(content: bytes, content_type: str, filename: str = "upload") -> UploadFile:
    return UploadFile(file=io.BytesIO(content), filename=filename, headers=Headers({"content-type": content_type}))


@pytest.fixture(autouse=True)
def _use_tmp_media_root(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "media_root", str(tmp_path))
    yield


async def test_save_upload_accepts_allowed_image_type():
    profile_id = uuid.uuid4()
    relative_path, media_type = await save_upload(_upload_file(b"fake-jpeg-bytes", "image/jpeg"), profile_id)

    assert media_type == MediaType.photo
    assert relative_path.startswith(f"{profile_id}/")
    assert relative_path.endswith(".jpg")
    assert (Path(settings.media_root) / relative_path).read_bytes() == b"fake-jpeg-bytes"


async def test_save_upload_rejects_disallowed_content_type():
    with pytest.raises(HTTPException) as exc_info:
        await save_upload(_upload_file(b"whatever", "application/pdf"), uuid.uuid4())
    assert exc_info.value.status_code == 400


async def test_save_upload_ignores_client_supplied_filename_for_path_traversal():
    profile_id = uuid.uuid4()
    relative_path, _ = await save_upload(
        _upload_file(b"data", "image/png", filename="../../etc/passwd"), profile_id
    )
    # The on-disk name is always server-generated, never the client filename.
    assert "../" not in relative_path
    assert relative_path.startswith(f"{profile_id}/")


async def test_save_upload_rejects_file_over_max_size(monkeypatch):
    monkeypatch.setattr(settings, "max_upload_size_bytes", 10)
    with pytest.raises(HTTPException) as exc_info:
        await save_upload(_upload_file(b"x" * 100, "image/jpeg"), uuid.uuid4())
    assert exc_info.value.status_code == 413


async def test_save_upload_rejects_empty_file():
    with pytest.raises(HTTPException) as exc_info:
        await save_upload(_upload_file(b"", "image/jpeg"), uuid.uuid4())
    assert exc_info.value.status_code == 400


async def test_delete_file_removes_saved_file():
    profile_id = uuid.uuid4()
    relative_path, _ = await save_upload(_upload_file(b"bytes", "image/jpeg"), profile_id)

    saved_path = Path(settings.media_root) / relative_path
    assert saved_path.exists()

    delete_file(relative_path)
    assert not saved_path.exists()


async def test_delete_file_refuses_to_escape_media_root():
    # Defense in depth: even if a caller ever passed a traversal string,
    # delete_file must not unlink anything outside settings.media_root.
    outside_file = Path(settings.media_root).parent / "should_not_be_touched.txt"
    outside_file.write_text("keep me")

    delete_file("../should_not_be_touched.txt")

    assert outside_file.exists()
    outside_file.unlink()
