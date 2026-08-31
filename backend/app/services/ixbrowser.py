from typing import Any

from ixbrowser_local_api import Consts, IXBrowserClient, Profile, Proxy


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

    def find_profile_by_name(self, name: str) -> dict[str, Any] | None:
        result = self.client.get_profile_list(name=name)
        if result is None:
            self._raise_last_error("profile lookup")
        expected = name.strip()
        for item in result:
            if str(item.get("name") or "").strip() == expected:
                return dict(item)
        return None

    def create_profile(
        self,
        *,
        name: str,
        site_url: str = "chrome://newtab",
        group_id: int | None = None,
        proxy_type: str | None = None,
        proxy_ip: str | None = None,
        proxy_port: str | int | None = None,
        proxy_user: str | None = None,
        proxy_password: str | None = None,
    ) -> dict[str, Any]:
        """Create one persistent iXBrowser profile using iX defaults.

        Fingerprint values are intentionally not synthesized here. Optional
        SOCKS5 values are sent directly to iXBrowser through its official Proxy
        entity and are not persisted by Social Publisher.
        """

        normalized_name = name.strip()
        if not normalized_name:
            raise IXBrowserError("iXBrowser profile name cannot be empty.")

        profile = Profile()
        profile.name = normalized_name
        profile.site_url = site_url.strip() or "chrome://newtab"
        if group_id is not None:
            profile.group_id = group_id

        proxy_configured = any(
            value not in (None, "")
            for value in (proxy_type, proxy_ip, proxy_port, proxy_user, proxy_password)
        )
        if proxy_configured:
            normalized_type = (proxy_type or "socks5").strip().lower()
            if normalized_type != "socks5":
                raise IXBrowserError("当前工作台仅开放 SOCKS5 自定义代理。")
            normalized_ip = str(proxy_ip or "").strip()
            normalized_port = str(proxy_port or "").strip()
            if not normalized_ip or not normalized_port:
                raise IXBrowserError("SOCKS5 需要同时填写 Host 和 Port。")

            proxy = Proxy()
            proxy.change_to_custom_mode(
                proxy_type=Consts.PROXY_TYPE_SOCKS5,
                proxy_ip=normalized_ip,
                proxy_port=normalized_port,
                proxy_user=(proxy_user or "").strip() or None,
                proxy_password=proxy_password or None,
            )
            profile.proxy_config = proxy

        result = self.client.create_profile(profile)
        if result is None:
            self._raise_last_error("create profile")

        profile_id = self._extract_profile_id(result)
        if profile_id is None:
            created = self.find_profile_by_name(normalized_name)
            if created is not None:
                profile_id = self._extract_profile_id(created)

        return {
            "profile_id": profile_id,
            "name": normalized_name,
            "site_url": profile.site_url,
            "proxy_configured": proxy_configured,
            "proxy_type": "socks5" if proxy_configured else None,
        }

    def update_profile_socks5_proxy(
        self,
        profile_id: int,
        *,
        proxy_ip: str,
        proxy_port: str | int,
        proxy_user: str | None = None,
        proxy_password: str | None = None,
    ) -> dict[str, Any]:
        normalized_ip = proxy_ip.strip()
        normalized_port = str(proxy_port).strip()
        if not normalized_ip or not normalized_port:
            raise IXBrowserError("SOCKS5 需要同时填写 Host 和 Port。")

        result = self.client.update_profile_to_custom_proxy_mode(
            profile_id,
            proxy_type=Consts.PROXY_TYPE_SOCKS5,
            proxy_ip=normalized_ip,
            proxy_port=normalized_port,
            proxy_user=(proxy_user or "").strip() or None,
            proxy_password=proxy_password or None,
        )
        if result is None:
            self._raise_last_error(f"update SOCKS5 proxy for profile #{profile_id}")
        return {
            "profile_id": profile_id,
            "proxy_type": "socks5",
            "proxy_ip": normalized_ip,
            "proxy_port": normalized_port,
        }

    def clear_profile_proxy(self, profile_id: int) -> dict[str, Any]:
        result = self.client.update_profile_to_custom_proxy_mode(
            profile_id,
            proxy_type=Consts.PROXY_TYPE_DIRECT,
        )
        if result is None:
            self._raise_last_error(f"clear proxy for profile #{profile_id}")
        return {"profile_id": profile_id, "proxy_type": "direct"}

    @staticmethod
    def _extract_profile_id(result: object) -> int | None:
        if isinstance(result, bool):
            return None
        if isinstance(result, int):
            return result
        if isinstance(result, str) and result.isdigit():
            return int(result)
        if isinstance(result, dict):
            for key in ("profile_id", "id"):
                value = result.get(key)
                if isinstance(value, bool):
                    continue
                if isinstance(value, int):
                    return value
                if isinstance(value, str) and value.isdigit():
                    return int(value)
        return None

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
