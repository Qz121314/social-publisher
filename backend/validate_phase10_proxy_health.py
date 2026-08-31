from app.schemas.resource_pool import ProxyHealthCheckRequest
from app.services.proxy_health import build_socks5_url, parse_exit_ip, parse_geo


def main() -> None:
    plain = build_socks5_url("127.0.0.1", 1080)
    assert plain == "socks5://127.0.0.1:1080"

    authenticated = build_socks5_url(
        "proxy.example.com",
        1080,
        "user@example.com",
        "p:a/ss word",
    )
    assert authenticated == "socks5://user%40example.com:p%3Aa%2Fss%20word@proxy.example.com:1080"

    assert parse_exit_ip({"ip": "1.1.1.1"}) == "1.1.1.1"
    assert parse_exit_ip({"ip": "2001:4860:4860::8888"}) == "2001:4860:4860::8888"
    try:
        parse_exit_ip({"ip": "not-an-ip"})
    except ValueError:
        pass
    else:
        raise AssertionError("invalid exit IP must fail closed")

    country, region = parse_geo({"country_name": "United States", "region": "California"})
    assert country == "United States"
    assert region == "California"
    assert parse_geo({}) == (None, None)

    payload = ProxyHealthCheckRequest(proxy_ids=[3, 3, 2, 1, 2])
    assert payload.proxy_ids == [3, 2, 1]

    print("phase10 proxy health foundation ok")


if __name__ == "__main__":
    main()
