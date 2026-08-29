from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models.account import BrowserProfile
from app.models.content import ContentItem, MediaAsset, PublishJob
from app.schemas.content import ContentRead
from app.services.content_store import (
    MediaValidationError,
    delete_media,
    get_media_path,
    media_type_from_mime,
    save_upload,
)
from app.services.platforms.base import PlatformContent, PlatformMedia, PlatformValidationError
from app.services.platforms.registry import get_platform_adapter, list_platforms

router = APIRouter(tags=["content"])


@router.get("/platforms")
def platforms() -> dict[str, object]:
    items = list_platforms()
    return {"items": items, "count": len(items)}


@router.get("/contents", response_model=list[ContentRead])
def list_contents(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[ContentItem]:
    statement = (
        select(ContentItem)
        .options(selectinload(ContentItem.media), selectinload(ContentItem.jobs))
        .order_by(ContentItem.created_at.desc())
        .limit(limit)
    )
    return list(db.scalars(statement).unique().all())


@router.get("/contents/{content_id}", response_model=ContentRead)
def get_content(content_id: str, db: Session = Depends(get_db)) -> ContentItem:
    return _get_content_or_404(db, content_id)


@router.post("/contents", response_model=ContentRead, status_code=status.HTTP_201_CREATED)
async def create_content(
    platform: str = Form(...),
    text: str = Form(default=""),
    profile_ids: str = Form(...),
    files: list[UploadFile] | None = File(default=None),
    db: Session = Depends(get_db),
) -> ContentItem:
    normalized_platform = platform.strip().lower()
    try:
        adapter = get_platform_adapter(normalized_platform)
        target_ids = _parse_profile_ids(profile_ids)
    except PlatformValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    profiles = list(
        db.scalars(
            select(BrowserProfile).where(BrowserProfile.profile_id.in_(target_ids))
        ).all()
    )
    found_ids = {profile.profile_id for profile in profiles}
    missing = [profile_id for profile_id in target_ids if profile_id not in found_ids]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown iX profile id(s): {', '.join(map(str, missing))}. Sync profiles first.",
        )

    unavailable = [profile.profile_id for profile in profiles if not profile.is_available]
    if unavailable:
        raise HTTPException(
            status_code=400,
            detail=f"Unavailable iX profile id(s): {', '.join(map(str, unavailable))}.",
        )

    uploads = files or []
    try:
        preview_media = tuple(
            PlatformMedia(
                media_type=media_type_from_mime(upload.content_type),
                path=Path(upload.filename or "media"),
                mime_type=upload.content_type or "application/octet-stream",
                original_name=Path(upload.filename or "media").name,
            )
            for upload in uploads
        )
        adapter.validate_content(PlatformContent(text=text, media=preview_media))
    except (MediaValidationError, PlatformValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    saved_names: list[str] = []
    content = ContentItem(platform=normalized_platform, text=text, status="draft")
    db.add(content)
    db.flush()

    try:
        for sort_order, upload in enumerate(uploads):
            metadata = await save_upload(upload)
            stored_name = str(metadata["stored_name"])
            saved_names.append(stored_name)
            db.add(
                MediaAsset(
                    content_id=content.id,
                    media_type=str(metadata["media_type"]),
                    original_name=str(metadata["original_name"]),
                    stored_name=stored_name,
                    mime_type=str(metadata["mime_type"]),
                    file_size=int(metadata["file_size"]),
                    sort_order=sort_order,
                )
            )

        for profile_id in target_ids:
            db.add(
                PublishJob(
                    content_id=content.id,
                    profile_id=profile_id,
                    platform=normalized_platform,
                    status="draft",
                )
            )

        db.commit()
    except MediaValidationError as exc:
        db.rollback()
        for stored_name in saved_names:
            delete_media(stored_name)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        for stored_name in saved_names:
            delete_media(stored_name)
        raise

    return _get_content_or_404(db, content.id)


@router.delete("/contents/{content_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_content(content_id: str, db: Session = Depends(get_db)) -> Response:
    content = _get_content_or_404(db, content_id)
    stored_names = [asset.stored_name for asset in content.media]
    db.delete(content)
    db.commit()
    for stored_name in stored_names:
        delete_media(stored_name)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/media/{media_id}/file")
def media_file(media_id: str, db: Session = Depends(get_db)) -> FileResponse:
    asset = db.get(MediaAsset, media_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Media asset not found.")

    try:
        path = get_media_path(asset.stored_name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Media file is missing from local storage.") from exc

    safe_name = Path(asset.original_name).name.replace('"', "")
    disposition = f"inline; filename*=UTF-8''{quote(safe_name)}"
    return FileResponse(
        path,
        media_type=asset.mime_type,
        headers={"Content-Disposition": disposition},
    )


def _parse_profile_ids(raw: str) -> list[int]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("profile_ids must be a JSON array of iX profile ids.") from exc

    if not isinstance(value, list):
        raise ValueError("profile_ids must be a JSON array.")

    result: list[int] = []
    for item in value:
        if isinstance(item, bool):
            raise ValueError("profile_ids may only contain integer ids.")
        try:
            profile_id = int(item)
        except (TypeError, ValueError) as exc:
            raise ValueError("profile_ids may only contain integer ids.") from exc
        if profile_id <= 0:
            raise ValueError("profile_ids must contain positive integer ids.")
        if profile_id not in result:
            result.append(profile_id)

    if not result:
        raise ValueError("Select at least one iX profile.")
    if len(result) > 200:
        raise ValueError("A single draft may target at most 200 iX profiles.")
    return result


def _get_content_or_404(db: Session, content_id: str) -> ContentItem:
    statement = (
        select(ContentItem)
        .options(selectinload(ContentItem.media), selectinload(ContentItem.jobs))
        .where(ContentItem.id == content_id)
    )
    content = db.scalar(statement)
    if content is None:
        raise HTTPException(status_code=404, detail="Content not found.")
    return content
