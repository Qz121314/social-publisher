from __future__ import annotations

import csv
import io
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.asset_pool import Asset
from app.schemas.asset_pool import AssetBatchDelete, AssetRead, TextAssetCreate, TextAssetImport
from app.services.content_store import MediaValidationError, delete_media, get_media_path, save_upload

router = APIRouter(prefix="/asset-pool", tags=["asset-pool"])


@router.get("", response_model=list[AssetRead])
def list_assets(db: Session = Depends(get_db)) -> list[Asset]:
    return list(db.scalars(select(Asset).order_by(Asset.created_at.desc())).all())


@router.post("/text", response_model=AssetRead, status_code=status.HTTP_201_CREATED)
def create_text_asset(
    payload: TextAssetCreate,
    db: Session = Depends(get_db),
) -> Asset:
    asset = Asset(
        name=payload.name,
        asset_type="text",
        platform=payload.platform,
        text_content=payload.text,
        status="ready",
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


@router.post("/media", response_model=AssetRead, status_code=status.HTTP_201_CREATED)
async def create_media_asset(
    name: str = Form(...),
    platform: str = Form(default="generic"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> Asset:
    normalized_name = name.strip()
    if not normalized_name:
        raise HTTPException(status_code=400, detail="素材名称不能为空。")
    normalized_platform = _normalize_platform(platform)
    stored_name: str | None = None
    try:
        metadata = await save_upload(file)
        stored_name = str(metadata["stored_name"])
        asset = Asset(
            name=normalized_name,
            asset_type=str(metadata["media_type"]),
            platform=normalized_platform,
            original_name=str(metadata["original_name"]),
            stored_name=stored_name,
            mime_type=str(metadata["mime_type"]),
            file_size=int(metadata["file_size"]),
            status="ready",
        )
        db.add(asset)
        db.commit()
        db.refresh(asset)
        return asset
    except MediaValidationError as exc:
        if stored_name:
            delete_media(stored_name)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        if stored_name:
            delete_media(stored_name)
        raise


@router.post("/text/import")
def import_text_assets(
    payload: TextAssetImport,
    db: Session = Depends(get_db),
) -> dict[str, int]:
    rows = _parse_text_asset_csv(payload.text)
    for name, platform, text in rows:
        db.add(
            Asset(
                name=name,
                asset_type="text",
                platform=platform,
                text_content=text,
                status="ready",
            )
        )
    db.commit()
    return {"received": len(rows), "created": len(rows), "skipped": 0}


@router.post("/media/import")
async def import_media_assets(
    platform: str = Form(default="generic"),
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    if not files:
        raise HTTPException(status_code=400, detail="请选择至少一个图片或视频文件。")
    if len(files) > 500:
        raise HTTPException(status_code=400, detail="一次最多批量上传 500 个媒体文件。")

    normalized_platform = _normalize_platform(platform)
    saved_names: list[str] = []
    created = 0
    try:
        for upload in files:
            metadata = await save_upload(upload)
            stored_name = str(metadata["stored_name"])
            saved_names.append(stored_name)
            original_name = str(metadata["original_name"])
            db.add(
                Asset(
                    name=Path(original_name).stem or original_name,
                    asset_type=str(metadata["media_type"]),
                    platform=normalized_platform,
                    original_name=original_name,
                    stored_name=stored_name,
                    mime_type=str(metadata["mime_type"]),
                    file_size=int(metadata["file_size"]),
                    status="ready",
                )
            )
            created += 1
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
    return {"received": len(files), "created": created, "skipped": 0}


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_asset(asset_id: str, db: Session = Depends(get_db)) -> Response:
    asset = db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="未找到该素材。")
    stored_name = asset.stored_name
    db.delete(asset)
    db.commit()
    if stored_name:
        delete_media(stored_name)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/batch/delete")
def delete_assets_batch(
    payload: AssetBatchDelete,
    db: Session = Depends(get_db),
) -> dict[str, int]:
    ids = list(dict.fromkeys(payload.asset_ids))
    assets = list(db.scalars(select(Asset).where(Asset.id.in_(ids))).all())
    found = {asset.id for asset in assets}
    missing = [asset_id for asset_id in ids if asset_id not in found]
    if missing:
        raise HTTPException(status_code=404, detail=f"有 {len(missing)} 条素材不存在，请刷新后重试。")
    stored_names = [asset.stored_name for asset in assets if asset.stored_name]
    for asset in assets:
        db.delete(asset)
    db.commit()
    for stored_name in stored_names:
        delete_media(stored_name)
    return {"deleted": len(assets)}


@router.get("/{asset_id}/file")
def asset_file(asset_id: str, db: Session = Depends(get_db)) -> FileResponse:
    asset = db.get(Asset, asset_id)
    if asset is None or not asset.stored_name:
        raise HTTPException(status_code=404, detail="该素材没有可读取的媒体文件。")
    try:
        path = get_media_path(asset.stored_name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="素材文件已丢失。") from exc
    safe_name = Path(asset.original_name or asset.name).name.replace('"', "")
    return FileResponse(
        path,
        media_type=asset.mime_type or "application/octet-stream",
        headers={"Content-Disposition": f"inline; filename*=UTF-8''{quote(safe_name)}"},
    )


def _normalize_platform(value: str) -> str:
    normalized = value.strip().lower() or "generic"
    if normalized not in {"generic", "facebook", "instagram"}:
        raise HTTPException(status_code=400, detail="素材平台只能是通用、Facebook 或 Instagram。")
    return normalized


def _parse_text_asset_csv(raw: str) -> list[tuple[str, str, str]]:
    stream = io.StringIO(raw.lstrip("\ufeff"))
    reader = csv.DictReader(stream)
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="文案 CSV 必须包含表头。")

    headers = {str(name).strip().lower(): str(name) for name in reader.fieldnames if name}

    def column(*aliases: str) -> str | None:
        for alias in aliases:
            if alias.lower() in headers:
                return headers[alias.lower()]
        return None

    name_column = column("name", "名称", "素材名称")
    text_column = column("text", "文案", "正文", "内容")
    platform_column = column("platform", "平台")
    if text_column is None:
        raise HTTPException(status_code=400, detail="文案 CSV 缺少“文案/text”列。")

    rows: list[tuple[str, str, str]] = []
    for row_number, item in enumerate(reader, start=2):
        text = str(item.get(text_column) or "").strip()
        if not text:
            raise HTTPException(status_code=400, detail=f"第 {row_number} 行文案不能为空。")
        name = str(item.get(name_column) or "").strip() if name_column else ""
        if not name:
            name = f"文案 {row_number - 1}"
        platform = str(item.get(platform_column) or "generic").strip().lower() if platform_column else "generic"
        if platform not in {"generic", "facebook", "instagram"}:
            raise HTTPException(status_code=400, detail=f"第 {row_number} 行平台不支持：{platform}")
        rows.append((name, platform, text))

    if not rows:
        raise HTTPException(status_code=400, detail="文案 CSV 中没有可导入记录。")
    if len(rows) > 2000:
        raise HTTPException(status_code=400, detail="一次最多导入 2000 条文案。")
    return rows
