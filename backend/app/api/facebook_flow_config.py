from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.platforms.facebook_flow_config import (
    load_facebook_flow,
    reset_facebook_flow,
    runtime_path,
    save_facebook_flow,
)

router = APIRouter(tags=["facebook-flow-config"])


class FacebookFlowConfigPayload(BaseModel):
    entry_keywords: list[str] = Field(min_length=1, max_length=50)
    surface_titles: list[str] = Field(min_length=1, max_length=50)
    media_keywords: list[str] = Field(min_length=1, max_length=50)
    next_keywords: list[str] = Field(min_length=1, max_length=50)
    post_keywords: list[str] = Field(min_length=1, max_length=50)
    upload_busy_keywords: list[str] = Field(min_length=1, max_length=50)
    success_keywords: list[str] = Field(min_length=1, max_length=50)


@router.get("/facebook-flow-config")
def get_facebook_flow_config() -> dict[str, Any]:
    path = runtime_path()
    return {
        "config": load_facebook_flow(),
        "source": "runtime" if path.is_file() else "default",
        "runtime_path": str(path),
    }


@router.put("/facebook-flow-config")
def update_facebook_flow_config(payload: FacebookFlowConfigPayload) -> dict[str, Any]:
    try:
        config = save_facebook_flow(payload.model_dump())
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "status": "ok",
        "source": "runtime",
        "config": config,
    }


@router.post("/facebook-flow-config/reset")
def reset_facebook_flow_config() -> dict[str, Any]:
    return {
        "status": "ok",
        "source": "default",
        "config": reset_facebook_flow(),
    }
