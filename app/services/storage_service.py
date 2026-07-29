"""Media storage behind a swappable interface.

Local disk is fine for development, but on Cloud Run the container filesystem
is ephemeral AND per-instance: uploads vanish on the next revision or scale-to-
zero, and with two instances an image written to A is a 404 from B — while the
database still holds the URL, so the UI shows permanently broken images. The
GCS backend exists for that reason and is the only production-safe option.

Adding a provider means writing a class satisfying `MediaStorage` and returning
it from `get_media_storage()`. Callers only ever see the interface.
"""

import logging
import uuid
from pathlib import Path
from typing import Protocol, runtime_checkable

from fastapi import UploadFile

from app.core.config import settings
from app.core.exceptions import ApiException

logger = logging.getLogger(__name__)

ALLOWED_CONTENT_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
MAX_UPLOAD_BYTES = 5 * 1024 * 1024

# Magic-byte signatures, checked against the client-declared content type. The
# browser controls Content-Type, so on its own it decides nothing about what is
# actually in the file.
_MAGIC_SIGNATURES: dict[str, tuple[bytes, ...]] = {
    ".jpg": (b"\xff\xd8\xff",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".webp": (b"RIFF",),
}


class StorageError(Exception):
    """Raised when the backing store cannot accept the upload."""


@runtime_checkable
class MediaStorage(Protocol):
    name: str

    def save_image(self, owner_id: str, upload: UploadFile) -> str:
        """Persist `upload` and return the URL it will be served from."""
        ...


def _validated_bytes(upload: UploadFile) -> tuple[bytes, str]:
    """Shared validation: declared type, size cap, and magic-byte agreement."""
    extension = ALLOWED_CONTENT_TYPES.get(upload.content_type or "")
    if extension is None:
        raise ApiException(422, "Only JPEG, PNG and WebP images are allowed", "VALIDATION_ERROR")

    content = upload.file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise ApiException(422, "File exceeds the 5 MB limit", "VALIDATION_ERROR")
    if not content:
        raise ApiException(422, "The uploaded file is empty", "VALIDATION_ERROR")

    signatures = _MAGIC_SIGNATURES.get(extension, ())
    if signatures and not any(content.startswith(sig) for sig in signatures):
        raise ApiException(
            422, "The file content does not match its image type", "VALIDATION_ERROR"
        )

    return content, extension


class LocalMediaStorage:
    """Local-disk media storage served under /media (docs/12 §1).

    Development only — see the module docstring for why this loses data on
    Cloud Run.
    """

    name = "local"

    def __init__(self, root: str | Path | None = None) -> None:
        self._root = Path(root or settings.media_root)

    def save_image(self, owner_id: str, upload: UploadFile) -> str:
        content, extension = _validated_bytes(upload)

        directory = self._root / owner_id
        directory.mkdir(parents=True, exist_ok=True)
        filename = f"{uuid.uuid4().hex}{extension}"
        (directory / filename).write_bytes(content)

        return f"/media/{owner_id}/{filename}"


class GcsMediaStorage:
    """Google Cloud Storage media storage.

    Objects are written under `media/{owner_id}/{uuid}.{ext}` and served
    straight from the bucket, so the API process is never in the image path.
    The bucket is expected to be publicly readable (these are profile photos
    and gallery images on a public website); no signed URLs are issued.
    """

    name = "gcs"

    def __init__(self, bucket: str, public_base_url: str = "") -> None:
        self._bucket_name = bucket
        self._public_base_url = public_base_url.rstrip("/")
        self._client = None

    def _bucket(self):
        # Imported lazily so local/dev installs need not carry the GCS SDK.
        if self._client is None:
            from google.cloud import storage

            self._client = storage.Client()
        return self._client.bucket(self._bucket_name)

    def save_image(self, owner_id: str, upload: UploadFile) -> str:
        content, extension = _validated_bytes(upload)

        blob_path = f"media/{owner_id}/{uuid.uuid4().hex}{extension}"
        try:
            blob = self._bucket().blob(blob_path)
            blob.cache_control = "public, max-age=31536000, immutable"
            blob.upload_from_string(content, content_type=upload.content_type)
        except Exception as exc:  # SDK raises a wide range of transport errors
            logger.exception("GCS upload failed for %s", blob_path)
            raise StorageError(f"Could not store the image: {exc}") from exc

        if self._public_base_url:
            return f"{self._public_base_url}/{blob_path}"
        return f"https://storage.googleapis.com/{self._bucket_name}/{blob_path}"


def get_media_storage() -> MediaStorage:
    """The single switch point for media storage."""
    provider = settings.media_storage_provider.lower()
    if provider == "local":
        return LocalMediaStorage()
    if provider == "gcs":
        if not settings.gcs_bucket:
            raise StorageError("MEDIA_STORAGE_PROVIDER=gcs but GCS_BUCKET is not set")
        return GcsMediaStorage(settings.gcs_bucket, settings.gcs_public_base_url)
    raise StorageError(f"Unknown media storage provider: {settings.media_storage_provider}")
