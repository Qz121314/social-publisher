from __future__ import annotations

import time
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from selenium.common.exceptions import StaleElementReferenceException, WebDriverException
from selenium.webdriver import Chrome
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from app.services.platforms.facebook import FacebookAdapter


class FacebookPageDiscoveryError(RuntimeError):
    pass


MY_PROFILE_URL = "https://www.facebook.com/me"
MANAGED_PAGES_URL = "https://www.facebook.com/pages/?category=your_pages&ref=bookmarks"

_RESERVED_ROOTS = {
    "",
    "ad_center",
    "ads",
    "bookmarks",
    "business",
    "checkpoint",
    "composer",
    "create",
    "events",
    "friends",
    "fundraisers",
    "gaming",
    "groups",
    "help",
    "home.php",
    "latest",
    "legal",
    "login",
    "login.php",
    "marketplace",
    "memories",
    "messages",
    "notifications",
    "pages",
    "people",
    "policies",
    "privacy",
    "public",
    "recover",
    "saved",
    "settings",
    "watch",
}

_GENERIC_LABELS = {
    "ad center",
    "ads",
    "boost post",
    "create a page",
    "create a post",
    "create new page",
    "create post",
    "manage",
    "messages",
    "notifications",
    "pages",
    "pages you manage",
    "professional dashboard",
    "promote",
    "see all",
    "your pages",
    "公共主页",
    "你的公共主页",
    "你管理的公共主页",
    "创建公共主页",
    "创建帖子",
    "发布帖子",
    "广告",
    "广告中心",
    "推广",
    "消息",
    "通知",
    "管理",
    "专业面板",
    "查看全部",
}


def discover_managed_facebook_pages(driver: Chrome) -> list[dict[str, str]]:
    """Discover only publish identities: the personal profile and managed Pages."""
    adapter = FacebookAdapter()
    login = adapter.check_login(driver)
    if login.get("checkpoint"):
        raise FacebookPageDiscoveryError("Facebook 当前要求安全验证，请先在该 iX 环境里人工完成验证。")
    if not login.get("logged_in"):
        raise FacebookPageDiscoveryError("该 iX 环境中的 Facebook 尚未登录，请先人工登录后再扫描发布主页。")

    targets: dict[str, dict[str, str]] = {}

    # `/me` resolves to the currently active Facebook identity. When an account
    # is acting as a Page, that can be the Page rather than the human account.
    # `c_user` identifies the underlying logged-in Facebook account, while
    # `i_user` may represent an impersonated/Page identity. Resolve the personal
    # profile from `c_user` first so the scan remains correct even when the UI is
    # currently switched into a Page.
    personal = _discover_personal_profile(driver)
    if personal is not None:
        targets[f"profile:{personal['target_id']}"] = personal

    try:
        driver.get(MANAGED_PAGES_URL)
        _wait_ready(driver)
    except WebDriverException as exc:
        raise FacebookPageDiscoveryError(f"无法打开 Facebook 公共主页管理页面：{exc}") from exc

    _raise_for_auth_flow(driver)
    _scroll_page(driver)

    anchors = driver.find_elements(By.CSS_SELECTOR, "div[role='main'] a[href]")
    if not anchors:
        anchors = driver.find_elements(By.CSS_SELECTOR, "a[href]")

    for anchor in anchors:
        try:
            if not anchor.is_displayed():
                continue
            href = (anchor.get_attribute("href") or "").strip()
            text = " ".join((anchor.text or "").split()).strip()
            aria = " ".join((anchor.get_attribute("aria-label") or "").split()).strip()
        except StaleElementReferenceException:
            continue

        name = text or aria
        if _is_non_target_label(name):
            continue

        normalized = _normalize_facebook_page_url(href)
        if normalized is None:
            continue
        target_url, target_id = normalized

        # Never let the personal account discovered via c_user be reclassified
        # as a Page just because the managed-pages DOM links to the same ID.
        if personal is not None and target_id == personal["target_id"]:
            continue

        key = f"page:{target_id}"
        existing = targets.get(key)
        if existing is None or len(name) < len(existing["target_name"]):
            targets[key] = {
                "target_type": "page",
                "target_id": target_id,
                "target_name": name[:255],
                "target_url": target_url,
                "source": "facebook_managed_pages",
            }

    result = sorted(
        targets.values(),
        key=lambda item: (0 if item["target_type"] == "profile" else 1, item["target_name"].casefold()),
    )
    if not result:
        title = (driver.title or "Facebook").strip()
        raise FacebookPageDiscoveryError(
            "没有读取到 Facebook 个人主页或可管理的公共主页。"
            f"当前页面：{title}。可能是登录状态异常，或 Facebook 界面结构发生了变化。"
        )
    return result


def _discover_personal_profile(driver: Chrome) -> dict[str, str] | None:
    c_user = _facebook_cookie_value(driver, "c_user")
    if c_user:
        personal_url = urlunparse(
            ("https", "www.facebook.com", "/profile.php", "", urlencode({"id": c_user}), "")
        )
        try:
            driver.get(personal_url)
            _wait_ready(driver)
        except WebDriverException:
            return _discover_personal_profile_via_me(driver)

        _raise_for_auth_flow(driver)
        return {
            "target_type": "profile",
            "target_id": c_user,
            "target_name": _extract_profile_name(driver),
            "target_url": personal_url,
            "source": "facebook_c_user",
        }

    return _discover_personal_profile_via_me(driver)


def _discover_personal_profile_via_me(driver: Chrome) -> dict[str, str] | None:
    try:
        driver.get(MY_PROFILE_URL)
        _wait_ready(driver)
    except WebDriverException:
        return None

    _raise_for_auth_flow(driver)
    normalized = _normalize_facebook_page_url(driver.current_url or "")
    if normalized is None:
        return None

    target_url, target_id = normalized
    return {
        "target_type": "profile",
        "target_id": target_id,
        "target_name": _extract_profile_name(driver),
        "target_url": target_url,
        "source": "facebook_me_fallback",
    }


def _facebook_cookie_value(driver: Chrome, name: str) -> str | None:
    try:
        cookie = driver.get_cookie(name)
    except WebDriverException:
        return None
    if not cookie:
        return None
    value = str(cookie.get("value") or "").strip()
    return value or None


def _extract_profile_name(driver: Chrome) -> str:
    selectors = (
        "meta[property='og:title']",
        "meta[name='title']",
    )
    for selector in selectors:
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
        except WebDriverException:
            elements = []
        for element in elements:
            value = " ".join((element.get_attribute("content") or "").split()).strip()
            if value and value.casefold() != "facebook":
                return value[:255]

    try:
        headings = driver.find_elements(By.CSS_SELECTOR, "h1")
    except WebDriverException:
        headings = []
    for heading in headings:
        try:
            value = " ".join((heading.text or "").split()).strip()
            if value:
                return value[:255]
        except StaleElementReferenceException:
            continue

    title = _clean_facebook_title(driver.title or "")
    return (title or "个人主页")[:255]


def _wait_ready(driver: Chrome) -> None:
    WebDriverWait(driver, 30).until(
        lambda browser: browser.execute_script("return document.readyState") in ("interactive", "complete")
    )


def _raise_for_auth_flow(driver: Chrome) -> None:
    current_url = (driver.current_url or "").lower()
    if any(marker in current_url for marker in ("/checkpoint", "/recover", "/two_step_verification")):
        raise FacebookPageDiscoveryError("Facebook 打开了安全验证流程，请人工处理后再扫描。")
    if "/login" in current_url or "login.php" in current_url:
        raise FacebookPageDiscoveryError("Facebook 登录状态已失效，请重新登录后再扫描。")


def _is_non_target_label(value: str) -> bool:
    normalized = " ".join(value.split()).strip().casefold()
    if not normalized:
        return True
    if normalized in _GENERIC_LABELS:
        return True
    prefixes = (
        "create post",
        "boost post",
        "promote",
        "message",
        "创建帖子",
        "推广",
        "消息",
    )
    return normalized.startswith(prefixes)


def _scroll_page(driver: Chrome) -> None:
    stable_rounds = 0
    previous_height = 0
    for _ in range(10):
        try:
            height = int(driver.execute_script("return document.body.scrollHeight") or 0)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
        except WebDriverException:
            return
        time.sleep(0.7)
        if height == previous_height:
            stable_rounds += 1
            if stable_rounds >= 2:
                break
        else:
            stable_rounds = 0
            previous_height = height


def _normalize_facebook_page_url(raw_url: str) -> tuple[str, str] | None:
    if not raw_url:
        return None
    parsed = urlparse(raw_url)
    host = parsed.netloc.lower().split(":", 1)[0]
    if host not in {"facebook.com", "www.facebook.com", "m.facebook.com"}:
        return None

    path = parsed.path.strip("/")
    first = path.split("/", 1)[0]
    first_lower = first.lower()
    query = parse_qs(parsed.query)

    if first_lower == "profile.php" and query.get("id"):
        target_id = query["id"][0].strip()
        if not target_id:
            return None
        normalized = urlunparse(
            ("https", "www.facebook.com", "/profile.php", "", urlencode({"id": target_id}), "")
        )
        return normalized, target_id

    if first_lower in _RESERVED_ROOTS or not first:
        return None

    target_id = first
    normalized = urlunparse(("https", "www.facebook.com", f"/{target_id}", "", "", ""))
    return normalized, target_id


def _clean_facebook_title(value: str) -> str:
    cleaned = value.strip()
    for suffix in (" | Facebook", " - Facebook", " — Facebook"):
        if cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)].strip()
    return "" if cleaned.casefold() == "facebook" else cleaned
