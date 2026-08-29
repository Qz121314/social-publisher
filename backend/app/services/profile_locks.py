from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.execution import ProfileLock


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ProfileBusyError(RuntimeError):
    """Raised when another worker already owns a profile lock."""


class ProfileLockManager:
    def acquire(
        self,
        db: Session,
        profile_id: int,
        owner_id: str,
        task_id: str | None = None,
        ttl_seconds: int = 300,
    ) -> ProfileLock:
        now = utcnow()
        db.execute(
            delete(ProfileLock).where(
                ProfileLock.profile_id == profile_id,
                ProfileLock.expires_at <= now,
            )
        )
        db.flush()

        lock = ProfileLock(
            profile_id=profile_id,
            owner_id=owner_id,
            task_id=task_id,
            acquired_at=now,
            heartbeat_at=now,
            expires_at=now + timedelta(seconds=ttl_seconds),
        )
        db.add(lock)

        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            current = db.get(ProfileLock, profile_id)
            detail = f" owned by {current.owner_id}" if current else ""
            raise ProfileBusyError(
                f"iX profile #{profile_id} is currently locked{detail}."
            ) from exc

        db.refresh(lock)
        return lock

    def heartbeat(
        self,
        db: Session,
        profile_id: int,
        owner_id: str,
        ttl_seconds: int = 300,
    ) -> ProfileLock:
        lock = db.get(ProfileLock, profile_id)
        if lock is None or lock.owner_id != owner_id:
            raise ProfileBusyError(
                f"iX profile #{profile_id} is not owned by this worker."
            )

        now = utcnow()
        lock.heartbeat_at = now
        lock.expires_at = now + timedelta(seconds=ttl_seconds)
        db.commit()
        db.refresh(lock)
        return lock

    def release(self, db: Session, profile_id: int, owner_id: str) -> bool:
        lock = db.get(ProfileLock, profile_id)
        if lock is None:
            return False
        if lock.owner_id != owner_id:
            raise ProfileBusyError(
                f"iX profile #{profile_id} is owned by another worker."
            )

        db.delete(lock)
        db.commit()
        return True

    def assert_unlocked(self, db: Session, profile_id: int) -> None:
        self.cleanup_expired(db, profile_id=profile_id)
        lock = db.get(ProfileLock, profile_id)
        if lock is not None:
            raise ProfileBusyError(
                f"iX profile #{profile_id} is busy with task {lock.task_id or 'unknown'}."
            )

    def cleanup_expired(self, db: Session, profile_id: int | None = None) -> int:
        statement = delete(ProfileLock).where(ProfileLock.expires_at <= utcnow())
        if profile_id is not None:
            statement = statement.where(ProfileLock.profile_id == profile_id)
        result = db.execute(statement)
        db.commit()
        return int(result.rowcount or 0)

    def list_active(self, db: Session) -> list[ProfileLock]:
        self.cleanup_expired(db)
        statement = select(ProfileLock).order_by(ProfileLock.acquired_at.asc())
        return list(db.scalars(statement).all())


profile_locks = ProfileLockManager()
