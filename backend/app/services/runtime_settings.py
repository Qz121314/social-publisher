from __future__ import annotations

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.settings import AppSetting


WARM_SESSION_TTL_KEY = "browser.warm_session_ttl_seconds"
DEFAULT_WARM_SESSION_TTL_SECONDS = 60
MAX_WARM_SESSION_TTL_SECONDS = 3600


def _normalize_ttl(value: int) -> int:
    return max(0, min(int(value), MAX_WARM_SESSION_TTL_SECONDS))


def get_warm_session_ttl_seconds(db: Session | None = None) -> int:
    owns_session = db is None
    session = db or SessionLocal()
    try:
        item = session.get(AppSetting, WARM_SESSION_TTL_KEY)
        if item is None:
            return DEFAULT_WARM_SESSION_TTL_SECONDS
        try:
            return _normalize_ttl(int(item.value_text))
        except (TypeError, ValueError):
            return DEFAULT_WARM_SESSION_TTL_SECONDS
    finally:
        if owns_session:
            session.close()


def set_warm_session_ttl_seconds(value: int, db: Session | None = None) -> int:
    normalized = _normalize_ttl(value)
    owns_session = db is None
    session = db or SessionLocal()
    try:
        item = session.get(AppSetting, WARM_SESSION_TTL_KEY)
        if item is None:
            item = AppSetting(key=WARM_SESSION_TTL_KEY, value_text=str(normalized))
            session.add(item)
        else:
            item.value_text = str(normalized)
        session.commit()
        return normalized
    finally:
        if owns_session:
            session.close()
