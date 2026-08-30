from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import RLock, current_thread
from typing import Any

from selenium.common.exceptions import WebDriverException
from selenium.webdriver import Chrome
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

from app.services.ixbrowser import IXBrowserError, IXBrowserService
from app.services.runtime_settings import get_warm_session_ttl_seconds


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class BrowserSessionError(RuntimeError):
    """Raised when Selenium cannot attach to or control an iX profile."""


@dataclass
class BrowserSession:
    profile_id: int
    driver: Chrome
    debugging_address: str
    opened_at: datetime
    last_used_at: datetime
    managed_by_worker: bool = False
    warm_until: datetime | None = None

    def snapshot(self) -> dict[str, Any]:
        now = utcnow()
        try:
            warm_remaining = None
            if self.warm_until is not None:
                warm_remaining = max(0, int((self.warm_until - now).total_seconds()))
            return {
                "profile_id": self.profile_id,
                "attached": True,
                "alive": True,
                "opened_at": self.opened_at.isoformat(),
                "last_used_at": self.last_used_at.isoformat(),
                "managed_by_worker": self.managed_by_worker,
                "warm_until": self.warm_until.isoformat() if self.warm_until else None,
                "warm_remaining_seconds": warm_remaining,
                "current_url": self.driver.current_url,
                "title": self.driver.title,
                "window_count": len(self.driver.window_handles),
            }
        except WebDriverException as exc:
            return {
                "profile_id": self.profile_id,
                "attached": True,
                "alive": False,
                "opened_at": self.opened_at.isoformat(),
                "last_used_at": self.last_used_at.isoformat(),
                "managed_by_worker": self.managed_by_worker,
                "warm_until": self.warm_until.isoformat() if self.warm_until else None,
                "warm_remaining_seconds": None,
                "current_url": None,
                "title": None,
                "window_count": 0,
                "error": str(exc),
            }


class BrowserSessionManager:
    """Owns Selenium sessions attached to iXBrowser profiles.

    Sessions opened by the bounded Worker Pool are kept warm for a short,
    persisted TTL after a task finishes. Manual sessions keep their original
    explicit open/close semantics and are never auto-closed by the warm pool.
    """

    def __init__(self) -> None:
        self._sessions: dict[int, BrowserSession] = {}
        self._lock = RLock()
        self._expired_total = 0

    @staticmethod
    def _is_worker_thread() -> bool:
        return current_thread().name.startswith("social-publisher-worker")

    def open(self, profile_id: int) -> dict[str, Any]:
        requested_by_worker = self._is_worker_thread()
        with self._lock:
            existing = self._sessions.get(profile_id)
            if existing is not None:
                snapshot = existing.snapshot()
                if snapshot["alive"]:
                    now = utcnow()
                    existing.last_used_at = now
                    if requested_by_worker and existing.managed_by_worker:
                        # Re-activating a warm worker-owned session. Return
                        # already_open=False intentionally so WorkerManager's
                        # existing cleanup path calls close(), which refreshes
                        # the warm TTL after the task completes.
                        existing.warm_until = None
                        return {**existing.snapshot(), "already_open": False, "reused_warm": True}
                    if not requested_by_worker and existing.managed_by_worker:
                        # An explicit manual Open claims the session from the
                        # warm pool. It will remain open until manually closed.
                        existing.managed_by_worker = False
                        existing.warm_until = None
                    return {**existing.snapshot(), "already_open": True, "reused_warm": False}
                self._sessions.pop(profile_id, None)
                self._stop_driver_service(existing.driver)

            ix = IXBrowserService()
            open_result = ix.open_profile(profile_id)
            webdriver_path = open_result.get("webdriver")
            debugging_address = open_result.get("debugging_address")

            if not webdriver_path or not debugging_address:
                try:
                    ix.close_profile(profile_id)
                except IXBrowserError:
                    pass
                raise BrowserSessionError(
                    "iXBrowser opened the profile but did not return webdriver "
                    "and debugging_address values."
                )

            options = Options()
            options.add_experimental_option("debuggerAddress", debugging_address)

            try:
                driver = Chrome(
                    service=Service(webdriver_path),
                    options=options,
                )
            except Exception as exc:
                try:
                    ix.close_profile(profile_id)
                except IXBrowserError:
                    pass
                raise BrowserSessionError(
                    f"Selenium could not attach to iX profile #{profile_id}: {exc}"
                ) from exc

            now = utcnow()
            session = BrowserSession(
                profile_id=profile_id,
                driver=driver,
                debugging_address=debugging_address,
                opened_at=now,
                last_used_at=now,
                managed_by_worker=requested_by_worker,
            )
            self._sessions[profile_id] = session
            return {**session.snapshot(), "already_open": False, "reused_warm": False}

    def get_driver(self, profile_id: int) -> Chrome:
        """Return the live Selenium driver for a profile owned by this process."""
        with self._lock:
            session = self._sessions.get(profile_id)
            if session is None:
                raise BrowserSessionError(
                    f"Profile #{profile_id} is not attached to this backend process."
                )

            snapshot = session.snapshot()
            if not snapshot["alive"]:
                self._sessions.pop(profile_id, None)
                self._stop_driver_service(session.driver)
                raise BrowserSessionError(
                    f"Selenium session for profile #{profile_id} is no longer alive."
                )
            session.last_used_at = utcnow()
            return session.driver

    def probe(self, profile_id: int) -> dict[str, Any]:
        with self._lock:
            session = self._sessions.get(profile_id)
            if session is None:
                raise BrowserSessionError(
                    f"Profile #{profile_id} is not attached to this backend process."
                )

            snapshot = session.snapshot()
            if not snapshot["alive"]:
                self._sessions.pop(profile_id, None)
                self._stop_driver_service(session.driver)
            return snapshot

    def close(self, profile_id: int, *, force: bool = False) -> dict[str, Any]:
        with self._lock:
            session = self._sessions.get(profile_id)
            if (
                session is not None
                and not force
                and session.managed_by_worker
                and self._is_worker_thread()
            ):
                ttl_seconds = get_warm_session_ttl_seconds()
                if ttl_seconds > 0:
                    now = utcnow()
                    session.last_used_at = now
                    session.warm_until = now + timedelta(seconds=ttl_seconds)
                    return {
                        "profile_id": profile_id,
                        "closed": False,
                        "warm": True,
                        "warm_until": session.warm_until.isoformat(),
                        "warm_ttl_seconds": ttl_seconds,
                        "was_attached": True,
                    }

            session = self._sessions.pop(profile_id, None)
            ix = IXBrowserService()

            try:
                ix.close_profile(profile_id)
            except IXBrowserError:
                if session is not None:
                    self._sessions[profile_id] = session
                raise

            if session is not None:
                self._stop_driver_service(session.driver)

            return {
                "profile_id": profile_id,
                "closed": True,
                "warm": False,
                "was_attached": session is not None,
            }

    def expire_warm_sessions(self) -> int:
        now = utcnow()
        with self._lock:
            expired_ids = [
                profile_id
                for profile_id, session in self._sessions.items()
                if session.managed_by_worker
                and session.warm_until is not None
                and session.warm_until <= now
            ]

        expired = 0
        for profile_id in expired_ids:
            try:
                result = self.close(profile_id, force=True)
                if result.get("closed"):
                    expired += 1
            except Exception:
                # A temporary iX close failure should not break Scheduler ticks.
                continue

        with self._lock:
            self._expired_total += expired
        return expired

    def list_sessions(self) -> list[dict[str, Any]]:
        with self._lock:
            stale: list[int] = []
            snapshots: list[dict[str, Any]] = []

            for profile_id, session in self._sessions.items():
                snapshot = session.snapshot()
                snapshots.append(snapshot)
                if not snapshot["alive"]:
                    stale.append(profile_id)

            for profile_id in stale:
                session = self._sessions.pop(profile_id, None)
                if session is not None:
                    self._stop_driver_service(session.driver)

            return snapshots

    def stats(self) -> dict[str, int]:
        with self._lock:
            warm = sum(
                1
                for session in self._sessions.values()
                if session.managed_by_worker and session.warm_until is not None
            )
            return {
                "total_sessions": len(self._sessions),
                "warm_sessions": warm,
                "expired_warm_sessions_total": self._expired_total,
            }

    @staticmethod
    def _stop_driver_service(driver: Chrome) -> None:
        try:
            driver.service.stop()
        except Exception:
            pass


browser_sessions = BrowserSessionManager()
