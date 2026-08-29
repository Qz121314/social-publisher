from typing import Any

from ixbrowser_local_api import IXBrowserClient


class IXBrowserService:
    """Small boundary around the official iXBrowser Python SDK.

    The rest of the application should use this service instead of depending on
    IXBrowserClient directly. That keeps SDK-specific return conventions and
    error handling in one place.
    """

    def __init__(self, target: str = "127.0.0.1", port: int = 53200) -> None:
        self.client = IXBrowserClient(target=target, port=port)

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
            raise RuntimeError(
                f"iXBrowser API error {self.client.code}: {self.client.message}"
            )

        items = list(first_page)
        total = int(self.client.total or len(items))
        page = 2

        while len(items) < total:
            chunk = self.client.get_profile_list(page=page, limit=page_size)
            if chunk is None:
                raise RuntimeError(
                    f"iXBrowser API error {self.client.code}: {self.client.message}"
                )
            if not chunk:
                break
            items.extend(chunk)
            page += 1

        return items
