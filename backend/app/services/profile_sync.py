import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.account import BrowserProfile
from app.services.ixbrowser import IXBrowserService


def sync_ix_profiles(db: Session) -> dict[str, int]:
    profiles = IXBrowserService().get_profiles()
    now = datetime.now(timezone.utc)

    existing = {
        item.profile_id: item
        for item in db.scalars(select(BrowserProfile)).all()
    }

    for item in existing.values():
        item.is_available = False

    created = 0
    updated = 0

    for payload in profiles:
        profile_id = int(payload["profile_id"])
        profile = existing.get(profile_id)

        if profile is None:
            profile = BrowserProfile(profile_id=profile_id)
            db.add(profile)
            created += 1
        else:
            updated += 1

        profile.name = str(payload.get("name") or f"Profile {profile_id}")
        profile.group_id = _optional_int(payload.get("group_id"))
        profile.group_name = _optional_str(payload.get("group_name"))
        profile.raw_json = json.dumps(payload, ensure_ascii=False, default=str)
        profile.is_available = True
        profile.last_seen_at = now

    db.commit()
    return {
        "fetched": len(profiles),
        "created": created,
        "updated": updated,
    }


def _optional_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_str(value: object) -> str | None:
    if value in (None, ""):
        return None
    return str(value)
