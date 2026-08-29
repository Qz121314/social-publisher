from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.database import DATA_DIR

UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


class MediaValidationError(ValueError):
    """Raised when an uploaded file is not a supported media asset."""


def media_type_from_mime(mime_type: str | None) -> str:
    value = (mime_type or "").lower().strip()
    if value.startswith("image/"):
        return "image"
    if value.startswith("video/"):
        return "video"
    raise MediaValidationError("Only image and video uploads are supported.")


async def save_upload(upload: UploadFile) -> dict[str, object]:
    media_type = media_type_from_mime(upload.content_type)
    original_name = Path(upload.filename or "media").name
    suffix = Path(original_name).suffix.lower()
    stored_name = f"{uuid4().hex}{suffix}"
    destination = UPLOAD_DIR / stored_name

    file_size = 0
    try:
        with destination.open("wb") as output:
            while chunk := await upload.read(1024 * 1024):
                output.write(chunk)
                file_size += len(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()

    if file_size == 0:
        destination.unlink(missing_ok=True)
        raise MediaValidationError(f"{original_name} is empty.")

    return {
        "media_type": media_type,
        "original_name": original_name,
        "stored_name": stored_name,
        "mime_type": upload.content_type or "application/octet-stream",
        "file_size": file_size,
    }


def get_media_path(stored_name: str) -> Path:
    safe_name = Path(stored_name).name
    path = UPLOAD_DIR / safe_name
    if not path.is_file():
        raise FileNotFoundError(safe_name)
    return path


def delete_media(stored_name: str) -> None:
    (UPLOAD_DIR / Path(stored_name).name).unlink(missing_ok=True)
