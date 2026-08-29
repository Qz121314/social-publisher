from typing import Any

from ixbrowser_local_api import IXBrowserClient


class IXBrowserError(RuntimeError):
    """Raised when the iXBrowser Local API reports an operation failure."""


class IXBrowserService:
    """Boundary around the official iXBrowser Python SDK.

    The rest of the application should use this service instead of depending on
    IXBrowserClient directly. SDK-specific return conventions and errors stay in
    one place.
    """

    def __init__(self, target: str = "127.0.0.1", port: int = 53200) -> None:
        self.client = IXBrowserClient(target=target, port=port)

    def _raise_last_error(self, action: str) -> None:
        raise IXBrowserError(
            f"iXBrowser {action} failed ({self.client.code}): {self.client.message}"
        )

    def connection_status(self) -> dict[str, Any]:
        profiles = self.client.get_profile_list(page=1, limit=1)
        if profiles is None:
            return {
                "connected": False,
                "code": self.client.code,
                "message": self.client.message,
            }
        return {
            "connected": True,
            "total_profiles": self.client.total or 0,
        }

    def get_profiles(self, page_size: int = 100) -> list[dict[str, Any]]:
        first_page = self.client.get_profile_list(page=1, limit=page_size)
        if first_page is None:
            self._raise_last_error("profile list")

        items = list(first_page)
        total = int(self.client.total or len(items))
        page = 2

        while len(items) < total:
            chunk = self.client.get_profile_list(page=page, limit=page_size)
            if chunk is None:
                self._raise_last_error("profile list")
            if not chunk:
                break
            items.extend(chunk)
            page += 1

        return items

    def get_profile(self, profile_id: int) -> dict[str, Any] | None:
        result = self.client.get_profile_list(profile_id=profile_id)
        if result is None:
            self._raise_last_error("profile lookup")
        if not result:
            return None
        return result[0]

    def get_opened_profiles(self) -> list[dict[str, Any]]:
        result = self.client.get_opened_profile_list()
        if result is None:
            self._raise_last_error("opened profile list")
        return list(result)

    def get_native_opened_profiles(self) -> list[dict[str, Any]]:
        result = self.client.get_native_opened_profile_list()
        if result is None:
            self._raise_last_error("native opened profile list")
        return list(result)

    def open_profile(self, profile_id: int) -> dict[str, Any]:
        result = self.client.open_profile(
            profile_id,
            cookies_backup=False,
            load_profile_info_page=False,
        )
        if result is None:
            self._raise_last_error(f"open profile #{profile_id}")
        return dict(result)

    def close_profile(self, profile_id: int) -> None:
        result = self.client.close_profile(profile_id)
        if result is None:
            self._raise_last_error(f"close profile #{profile_id}")
