from pydantic import ValidationError
from ixbrowser_local_api import Consts, Proxy

from app.database import init_db
from app.main import app
from app.schemas.account import AccountOnboardCreate, AccountProxyCreate, BrowserProfileRead
from app.services.profile_sync import sanitize_profile_payload


def main() -> None:
    init_db()

    paths = set(app.openapi()["paths"])
    assert "/api/accounts/onboard" in paths
    assert "/api/browser-profiles/{profile_id}/proxy" in paths

    proxy = AccountProxyCreate(
        enabled=True,
        host="127.0.0.1",
        port=1080,
        username="user",
        password="secret",
    )
    payload = AccountOnboardCreate(
        name="Demo Account",
        platform="facebook",
        environment_mode="new",
        proxy=proxy,
    )
    assert payload.proxy.proxy_type == "socks5"
    assert payload.proxy.port == 1080

    try:
        AccountProxyCreate(enabled=True, port=1080)
    except ValidationError:
        pass
    else:
        raise AssertionError("enabled SOCKS5 must require Host")

    try:
        AccountOnboardCreate(
            name="Bad Existing",
            platform="facebook",
            environment_mode="existing",
            ix_profile_id=123,
            proxy=proxy,
        )
    except ValidationError:
        pass
    else:
        raise AssertionError("binding an existing profile must not overwrite SOCKS5")

    official_proxy = Proxy()
    official_proxy.change_to_custom_mode(
        proxy_type=Consts.PROXY_TYPE_SOCKS5,
        proxy_ip="127.0.0.1",
        proxy_port="1080",
        proxy_user="user",
        proxy_password="secret",
    )
    dumped = official_proxy.dump_to_dict()
    assert dumped["proxy_type"] == Consts.PROXY_TYPE_SOCKS5
    assert dumped["proxy_ip"] == "127.0.0.1"
    assert dumped["proxy_port"] == "1080"

    sanitized = sanitize_profile_payload(
        {
            "profile_id": 9,
            "name": "Demo",
            "proxy_type": "socks5",
            "proxy_ip": "10.0.0.1",
            "proxy_port": "1080",
            "proxy_user": "should-not-be-mirrored",
            "proxy_password": "should-not-be-mirrored",
            "real_ip": "203.0.113.20",
            "password": "social-password",
            "tfa_secret": "totp-secret",
            "cookie": "cookie-data",
        }
    )
    assert sanitized["proxy_type"] == "socks5"
    assert sanitized["proxy_ip"] == "10.0.0.1"
    assert sanitized["proxy_port"] == "1080"
    assert sanitized["real_ip"] == "203.0.113.20"
    for secret_key in ("proxy_user", "proxy_password", "password", "tfa_secret", "cookie"):
        assert secret_key not in sanitized

    schema_fields = BrowserProfileRead.model_fields
    for field in ("proxy_type", "proxy_ip", "proxy_port", "real_ip"):
        assert field in schema_fields

    print("phase10 account onboarding and SOCKS5 ok")


if __name__ == "__main__":
    main()
