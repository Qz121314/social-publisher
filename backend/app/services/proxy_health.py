from __future__ import annotations

from dataclasses import dataclass
from ipaddress import ip_address
from time import perf_counter
from urllib.parse import quote

import httpx

IP_CHECK_URL = "https://api.ipify.org?format=json"
GEO_CHECK_URL = "https://ipapi.co/json/"
DEFAULT_TIMEOUT_SECONDS = 8.0


@dataclass(frozen=True)
class ProxyHealthResult:
    status: str
    exit_ip: str | None = None
    country: str | None = None
    region: str | None = None
    latency_ms: int | None = None
    error_code: str | None = None


def build_socks5_url(
    host: str,
    port: int,
    username: str | None = None,
    password: str | None = None,
) -> str:
    """Build a SOCKS5 URL without ever logging or persisting its credentials."""

    if username:
        user = quote(username, safe="")
        secret = quote(password or "", safe="")
        return f"socks5://{user}:{secret}@{host}:{port}"
    return f"socks5://{host}:{port}"


def parse_exit_ip(payload: object) -> str:
    if not isinstance(payload, dict):
        raise ValueError("invalid ip response")
    candidate = str(payload.get("ip") or "").strip()
    if not candidate:
        raise ValueError("missing exit ip")
    return str(ip_address(candidate))


def parse_geo(payload: object) -> tuple[str | None, str | None]:
    if not isinstance(payload, dict):
        return None, None
    country = str(payload.get("country_name") or "").strip() or None
    region = str(payload.get("region") or "").strip() or None
    return country, region


def check_socks5_proxy(
    *,
    host: str,
    port: int,
    username: str | None = None,
    password: str | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> ProxyHealthResult:
    """Verify that a SOCKS5 endpoint can reach the public Internet.

    Exit IP is authoritative for health. Geographic metadata is best-effort so a
    geo provider outage or rate limit never turns a working proxy into an error.
    Exception text is intentionally not returned because transport errors may
    contain credential-bearing proxy URLs.
    """

    proxy_url = build_socks5_url(host, port, username, password)
    timeout = httpx.Timeout(timeout_seconds)
    try:
        started = perf_counter()
        with httpx.Client(
            proxy=proxy_url,
            timeout=timeout,
            follow_redirects=True,
            trust_env=False,
            headers={"User-Agent": "SocialPublisher/1.0", "Accept": "application/json"},
        ) as client:
            response = client.get(IP_CHECK_URL)
            response.raise_for_status()
            exit_ip = parse_exit_ip(response.json())
            latency_ms = max(1, round((perf_counter() - started) * 1000))

            country = None
            region = None
            try:
                geo_response = client.get(GEO_CHECK_URL)
                geo_response.raise_for_status()
                country, region = parse_geo(geo_response.json())
            except (httpx.HTTPError, ValueError, TypeError):
                pass

        return ProxyHealthResult(
            status="healthy",
            exit_ip=exit_ip,
            country=country,
            region=region,
            latency_ms=latency_ms,
        )
    except httpx.TimeoutException:
        return ProxyHealthResult(status="error", error_code="timeout")
    except httpx.ProxyError:
        return ProxyHealthResult(status="error", error_code="proxy")
    except httpx.ConnectError:
        return ProxyHealthResult(status="error", error_code="connect")
    except httpx.HTTPStatusError:
        return ProxyHealthResult(status="error", error_code="http_status")
    except (httpx.HTTPError, ValueError, TypeError):
        return ProxyHealthResult(status="error", error_code="invalid_response")
