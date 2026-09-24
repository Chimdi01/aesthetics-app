"""
Local-disk storage for uploaded portfolio media. Every other layer
(router, model, schema) deals only with the relative path this returns —
nothing else knows settings.media_root exists. Swapping to S3 later means
rewriting this one file (save_upload -> put_object, delete_file ->
delete_object, and building a presigned/public URL instead of a local
path), not touching routers, models, or schemas.

Security notes:
- The on-disk filename is always server-generated (uuid4 + an extension
  from ALLOWED_CONTENT_TYPES), never derived from the client-supplied
  filename — avoids path traversal / injection via a crafted filename
  (e.g. "../../etc/passwd" or an embedded null byte).
- Only an explicit allowlist of content-types is accepted; the same
  mapping fixes the on-disk extension, so a mismatched/spoofed extension
  can't sneak in via the client-supplied filename.
- Upload size is enforced while streaming, chunk by chunk — not by
  trusting the Content-Length header, which a client can omit or lie
  about.
"""
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.config import settings
from app.models.portfolio_media import MediaType

ALLOWED_CONTENT_TYPES: dict[str, tuple[MediaType, str]] = {
    "image/jpeg": (MediaType.photo, ".jpg"),
    "image/png": (MediaType.photo, ".png"),
    "image/webp": (MediaType.photo, ".webp"),
    "video/mp4": (MediaType.video, ".mp4"),
    "video/quicktime": (MediaType.video, ".mov"),
}

# Read in fixed-size chunks so a large upload is never buffered into
# memory all at once just to check its size.
_CHUNK_SIZE = 1024 * 1024


async def save_upload(file: UploadFile, provider_profile_id: uuid.UUID) -> tuple[str, MediaType]:
    """Validates and streams `file` to local disk. Returns (relative_path, media_type)."""
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{file.content_type}'. Allowed: {sorted(ALLOWED_CONTENT_TYPES)}",
        )
    media_type, extension = ALLOWED_CONTENT_TYPES[file.content_type]

    destination_dir = Path(settings.media_root) / str(provider_profile_id)
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination_path = destination_dir / f"{uuid.uuid4().hex}{extension}"

    bytes_written = 0
    try:
        with destination_path.open("wb") as out_file:
            while chunk := await file.read(_CHUNK_SIZE):
                bytes_written += len(chunk)
                if bytes_written > settings.max_upload_size_bytes:
                    raise HTTPException(status_code=413, detail="File exceeds maximum upload size")
                out_file.write(chunk)
    except HTTPException:
        destination_path.unlink(missing_ok=True)
        raise

    if bytes_written == 0:
        destination_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    return f"{provider_profile_id}/{destination_path.name}", media_type


def delete_file(relative_path: str) -> None:
    # relative_path always comes from a value we generated ourselves in
    # save_upload (never directly from client input) — this containment
    # check is defense in depth, not a fix for a known path here.
    media_root = Path(settings.media_root).resolve()
    target = (media_root / relative_path).resolve()
    if media_root not in target.parents:
        return
    target.unlink(missing_ok=True)
