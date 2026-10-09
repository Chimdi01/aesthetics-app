"""
Local-disk storage for identity-verification documents — deliberately a
separate module from app/storage.py, not a shared code path, because the
requirements are opposite in two ways that matter:

- Privacy: portfolio media is meant to be public (customers browse it);
  verification documents are government ID photos and must NEVER be
  reachable by a public URL. Stored under settings.verification_root,
  which app/main.py never mounts as a StaticFiles route — retrieval only
  happens through the authenticated endpoints in
  app/routers/verification.py (the submitter) and app/routers/admin.py
  (an admin reviewing it), both of which stream the file directly rather
  than handing back a URL.
- Fidelity: portfolio photos are deliberately resized/recompressed (see
  app/storage.py) since they're viewed repeatedly and bandwidth cost
  matters; a verification document is viewed once by one admin, and
  legibility (can they actually read the document) matters far more than
  shaving bytes off a file nobody else will ever fetch. No resizing here.

Still decoded and validated as a real image for the same reason as
app/storage.py: a spoofed/corrupt upload gets a clean 400, not a file
written to disk that nothing can open when an admin goes to review it.
"""
import io
import logging
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError

from app.config import settings

ALLOWED_CONTENT_TYPES: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
}

_CHUNK_SIZE = 1024 * 1024


async def save_verification_document(file: UploadFile, user_id: uuid.UUID) -> str:
    """Validates, reads, and writes `file` to local disk unmodified
    (beyond format validation). Returns the relative path."""
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{file.content_type}'. Allowed: {sorted(ALLOWED_CONTENT_TYPES)}",
        )
    extension = ALLOWED_CONTENT_TYPES[file.content_type]

    chunks: list[bytes] = []
    bytes_read = 0
    while chunk := await file.read(_CHUNK_SIZE):
        bytes_read += len(chunk)
        if bytes_read > settings.max_upload_size_bytes:
            raise HTTPException(status_code=413, detail="File exceeds maximum upload size")
        chunks.append(chunk)

    if bytes_read == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    raw = b"".join(chunks)
    try:
        with Image.open(io.BytesIO(raw)) as image:
            image.verify()
    except UnidentifiedImageError:
        # from None: same reasoning as app/storage.py's identical check.
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid image") from None

    destination_dir = Path(settings.verification_root) / str(user_id)
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination_path = destination_dir / f"{uuid.uuid4().hex}{extension}"
    destination_path.write_bytes(raw)

    return f"{user_id}/{destination_path.name}"


def read_verification_document(relative_path: str) -> bytes:
    verification_root = Path(settings.verification_root).resolve()
    target = (verification_root / relative_path).resolve()
    if verification_root not in target.parents:
        logging.getLogger(__name__).error("Refused to read path outside verification_root: %s", relative_path)
        raise HTTPException(status_code=404, detail="Document not found")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Document not found")
    return target.read_bytes()


def content_type_for_path(relative_path: str) -> str:
    extension = "." + relative_path.rsplit(".", 1)[-1]
    for content_type, ext in ALLOWED_CONTENT_TYPES.items():
        if ext == extension:
            return content_type
    return "application/octet-stream"


def delete_verification_document(relative_path: str) -> None:
    verification_root = Path(settings.verification_root).resolve()
    target = (verification_root / relative_path).resolve()
    if verification_root not in target.parents:
        logging.getLogger(__name__).error("Refused to delete path outside verification_root: %s", relative_path)
        return
    target.unlink(missing_ok=True)
