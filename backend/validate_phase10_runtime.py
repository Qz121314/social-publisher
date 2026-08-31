from app.services.ixbrowser import IXBrowserService
from app.services.profile_sync import sanitize_profile_payload


class FakeIXClient:
    code = 0
    message = "success"

    def __init__(self) -> None:
        self.created_profile = None

    def create_profile(self, profile):
        self.created_profile = profile
        return {"profile_id": 901}


def validate_profile_creation_boundary() -> None:
    service = object.__new__(IXBrowserService)
    service.client = FakeIXClient()

    result = service.create_profile(
        name="  Store-A-017  ",
        site_url="https://www.facebook.com/",
    )

    assert result["profile_id"] == 901
    assert result["name"] == "Store-A-017"
    assert result["site_url"] == "https://www.facebook.com/"
    assert service.client.created_profile is not None
    assert service.client.created_profile.name == "Store-A-017"
    assert service.client.created_profile.site_url == "https://www.facebook.com/"


def validate_profile_id_normalization() -> None:
    assert IXBrowserService._extract_profile_id(9) == 9
    assert IXBrowserService._extract_profile_id("10") == 10
    assert IXBrowserService._extract_profile_id({"profile_id": 11}) == 11
    assert IXBrowserService._extract_profile_id({"id": "12"}) == 12
    assert IXBrowserService._extract_profile_id(True) is None
    assert IXBrowserService._extract_profile_id({"ok": True}) is None


def validate_profile_mirror_sanitization() -> None:
    payload = {
        "profile_id": 17,
        "name": "John-US",
        "group_id": 1,
        "group_name": "Default",
        "site_url": "https://www.facebook.com/",
        "proxy_mode": 2,
        "proxy_type": "socks5",
        "real_ip": "203.0.113.10",
        "username": "john@example.com",
        "password": "plain-password-must-not-be-stored",
        "tfa_secret": "TOTP-SECRET-MUST-NOT-BE-STORED",
        "cookie": "COOKIE-MUST-NOT-BE-STORED",
        "proxy_password": "PROXY-SECRET-MUST-NOT-BE-STORED",
    }

    safe = sanitize_profile_payload(payload)

    assert safe["profile_id"] == 17
    assert safe["name"] == "John-US"
    assert safe["real_ip"] == "203.0.113.10"
    assert "username" not in safe
    assert "password" not in safe
    assert "tfa_secret" not in safe
    assert "cookie" not in safe
    assert "proxy_password" not in safe


def main() -> None:
    validate_profile_creation_boundary()
    validate_profile_id_normalization()
    validate_profile_mirror_sanitization()
    print("phase10 iX runtime validation ok")


if __name__ == "__main__":
    main()
