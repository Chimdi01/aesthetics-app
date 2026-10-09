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
- Photos are actually decoded (not just trusted-by-Content-Length) before
  being written — see _compress_image. A request whose Content-Type
  claims image/jpeg but whose body isn't a real decodable image is
  rejected with a 400, not written to disk as a "photo" that nothing can
  actually open.

Cost note: photos are resized/recompressed (_compress_image) before
being written — see that function's docstring. This is a genuine cost
lever, not just a quality tweak: storage and every future bandwidth-byte
serving that image back (every search result, every profile view) scale
with however many bytes get stored, and a typical modern phone photo is
far higher resolution than any screen will display it at.
"""
import io
import logging
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError

from app.config import settings
from app.models.portfolio_media import MediaType

logger = logging.getLogger(__name__)

ALLOWED_CONTENT_TYPES: dict[str, tuple[MediaType, str]] = {
    "image/jpeg": (MediaType.photo, ".jpg"),
    "image/png": (MediaType.photo, ".png"),
    "image/webp": (MediaType.photo, ".webp"),
    "video/mp4": (MediaType.video, ".mp4"),
    "video/quicktime": (MediaType.video, ".mov"),
}

# Read in fixed-size chunks so a large upload is never buffered beyond
# the configured size limit just to check its size.
_CHUNK_SIZE = 1024 * 1024

# Longest edge, in pixels, after resizing — comfortably more than any
# phone or web screen displays a portfolio photo at. Re-encoded as JPEG
# regardless of the original format (the most size-efficient format for
# photographic content), which is why the on-disk extension for every
# photo is always ".jpg" post-compression, overriding whatever
# ALLOWED_CONTENT_TYPES said for the original upload format.
_MAX_IMAGE_DIMENSION = 1600
_JPEG_QUALITY = 85


def _compress_image(raw: bytes) -> bytes:
    """Resizes to _MAX_IMAGE_DIMENSION on the longest edge and re-encodes
    as JPEG. Video isn't transcoded here — that needs ffmpeg and likely
    async/background processing (transcoding is slow enough to block a
    request), a separate piece of work if it's ever needed."""
    try:
        with Image.open(io.BytesIO(raw)) as opened:
            # convert("RGB"): drops alpha/palette modes (e.g. a PNG with
            # transparency) that JPEG can't encode — losing transparency
            # is an acceptable tradeoff for a photo portfolio, not a
            # format meant for graphics/icons. A separate name (not
            # reassigning `opened`) because convert() returns the base
            # Image type, not the narrower ImageFile type `opened` is —
            # mypy flags the narrowing loss on a same-name reassignment.
            rgb_image = opened.convert("RGB")
            # Image.Resampling.LANCZOS, not the bare Image.LANCZOS alias:
            # the alias is deprecated (removed outright in some future
            # Pillow release per their own deprecation notice) and isn't
            # in current type stubs either.
            rgb_image.thumbnail((_MAX_IMAGE_DIMENSION, _MAX_IMAGE_DIMENSION), Image.Resampling.LANCZOS)
            buffer = io.BytesIO()
            rgb_image.save(buffer, format="JPEG", quality=_JPEG_QUALITY, optimize=True)
            return buffer.getvalue()
    except UnidentifiedImageError:
        # from None: a corrupt/spoofed upload's decode error isn't
        # actionable beyond "it's not a valid image", which the message
        # already says.
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid image") from None


async def save_upload(file: UploadFile, provider_profile_id: uuid.UUID) -> tuple[str, MediaType]:
    """Validates, reads, and (for photos) compresses `file`, then writes
    it to local disk. Returns (relative_path, media_type)."""
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        # WARNING, not INFO: a legitimate client never sends a disallowed
        # type (the frontend only offers valid pickers) — a volume of
        # these is a signal worth noticing, not routine traffic.
        logger.warning(
            "Rejected upload for provider %s: disallowed content-type '%s'", provider_profile_id, file.content_type
        )
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{file.content_type}'. Allowed: {sorted(ALLOWED_CONTENT_TYPES)}",
        )
    media_type, extension = ALLOWED_CONTENT_TYPES[file.content_type]

    # Read fully into memory first (bounded by max_upload_size_bytes,
    # checked while streaming so an oversized upload is rejected before
    # ever being held in full) — photos need the complete bytes to decode
    # and recompress anyway, so there's no streaming-to-disk benefit left
    # to keep for that case, and keeping one code path for both media
    # types is simpler than two.
    chunks: list[bytes] = []
    bytes_read = 0
    while chunk := await file.read(_CHUNK_SIZE):
        bytes_read += len(chunk)
        if bytes_read > settings.max_upload_size_bytes:
            logger.warning(
                "Rejected upload for provider %s: exceeded %d byte limit",
                provider_profile_id,
                settings.max_upload_size_bytes,
            )
            raise HTTPException(status_code=413, detail="File exceeds maximum upload size")
        chunks.append(chunk)

    if bytes_read == 0:
        logger.warning("Rejected upload for provider %s: empty file", provider_profile_id)
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    raw = b"".join(chunks)
    if media_type == MediaType.photo:
        data = _compress_image(raw)
        extension = ".jpg"
    else:
        data = raw

    destination_dir = Path(settings.media_root) / str(provider_profile_id)
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination_path = destination_dir / f"{uuid.uuid4().hex}{extension}"
    destination_path.write_bytes(data)

    relative_path = f"{provider_profile_id}/{destination_path.name}"
    logger.debug("Saved upload %s (%d bytes, from %d uploaded)", relative_path, len(data), bytes_read)
    return relative_path, media_type


def delete_file(relative_path: str) -> None:
    # relative_path always comes from a value we generated ourselves in
    # save_upload (never directly from client input) — this containment
    # check is defense in depth, not a fix for a known path here.
    media_root = Path(settings.media_root).resolve()
    target = (media_root / relative_path).resolve()
    if media_root not in target.parents:
        logger.error("Refused to delete path outside media_root: %s", relative_path)
        return
    target.unlink(missing_ok=True)
    logger.debug("Deleted file %s", relative_path)
