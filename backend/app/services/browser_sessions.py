from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock
from typing import Any

from selenium.common.exceptions import WebDriverException
from selenium.webdriver import Chrome
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

from app.services.ixbrowser import IXBrowserError, IXBrowserService


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class BrowserSessionError(RuntimeError):
    """Raised when Selenium cannot attach to or control an iX profile."""


@dataclass
class BrowserSession:
    profile_id: int
    driver: Chrome
    debugging_address: str
    opened_at: str

    def snapshot(self) -> dict[str, Any]:
        try:
            return {
                "profile_id": self.profile_id,
                "attached": True,
                "alive": True,
                "opened_at": self.opened_at,
                "current_url": self.driver.current_url,
                "title": self.driver.title,
                "window_count": len(self.driver.window_handles),
            }
        except WebDriverException as exc:
            return {
                "profile_id": self.profile_id,
                "attached": True,
                "alive": False,
                "opened_at": self.opened_at,
                "current_url": None,
                "title": None,
                "window_count": 0,
                "error": str(exc),
            }


class BrowserSessionManager:
    """Owns Selenium sessions attached to iXBrowser profiles.

    Sessions are intentionally kept in memory. A later worker/lock layer will
    own persistence and crash recovery; this manager only handles the live
    browser process lifecycle for the current backend process.
    """

    def __init__(self) -> None:
        self._sessions: dict[int, BrowserSession] = {}
        self._lock = RLock()

    def open(self, profile_id: int) -> dict[str, Any]:
        with self._lock:
            existing = self._sessions.get(profile_id)
            if existing is not None:
                snapshot = existing.snapshot()
                if snapshot["alive"]:
                    return {**snapshot, "already_open": True}
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

            session = BrowserSession(
                profile_id=profile_id,
                driver=driver,
                debugging_address=debugging_address,
                opened_at=utcnow_iso(),
            )
            self._sessions[profile_id] = session
            return {**session.snapshot(), "already_open": False}

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

    def close(self, profile_id: int) -> dict[str, Any]:
        with self._lock:
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
                "was_attached": session is not None,
            }

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

    @staticmethod
    def _stop_driver_service(driver: Chrome) -> None:
        try:
            driver.service.stop()
        except Exception:
            pass


browser_sessions = BrowserSessionManager()
