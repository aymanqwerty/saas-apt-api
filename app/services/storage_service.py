import uuid
from pathlib import Path

from fastapi import UploadFile

from app.core.config import settings
from app.core.exceptions import ApiException

ALLOWED_CONTENT_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
MAX_UPLOAD_BYTES = 5 * 1024 * 1024


class LocalMediaStorage:
    """Local-disk media storage served under /media (docs/12 §1).

    All storage access goes through this class so a future S3 implementation
    can replace it without changing callers.
    """

    def __init__(self, root: str | Path | None = None) -> None:
        self._root = Path(root or settings.media_root)

    def save_image(self, owner_id: str, upload: UploadFile) -> str:
        extension = ALLOWED_CONTENT_TYPES.get(upload.content_type or "")
        if extension is None:
            raise ApiException(
                422, "Only JPEG, PNG and WebP images are allowed", "VALIDATION_ERROR"
            )

        content = upload.file.read(MAX_UPLOAD_BYTES + 1)
        if len(content) > MAX_UPLOAD_BYTES:
            raise ApiException(422, "File exceeds the 5 MB limit", "VALIDATION_ERROR")

        directory = self._root / owner_id
        directory.mkdir(parents=True, exist_ok=True)
        filename = f"{uuid.uuid4().hex}{extension}"
        (directory / filename).write_bytes(content)

        return f"/media/{owner_id}/{filename}"
