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


MANAGED_PAGES_URL = "https://www.facebook.com/pages/?category=your_pages&ref=bookmarks"

_RESERVED_ROOTS = {
    "",
    "ads",
    "bookmarks",
    "business",
    "checkpoint",
    "events",
    "friends",
    "fundraisers",
    "gaming",
    "groups",
    "help",
    "home.php",
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
    "pages",
    "your pages",
    "pages you manage",
    "see all",
    "create new page",
    "create a page",
    "公共主页",
    "你的公共主页",
    "你管理的公共主页",
    "查看全部",
    "创建公共主页",
}


def discover_managed_facebook_pages(driver: Chrome) -> list[dict[str, str]]:
    adapter = FacebookAdapter()
    login = adapter.check_login(driver)
    if login.get("checkpoint"):
        raise FacebookPageDiscoveryError("Facebook 当前要求安全验证，请先在该 iX 环境里人工完成验证。")
    if not login.get("logged_in"):
        raise FacebookPageDiscoveryError("该 iX 环境中的 Facebook 尚未登录，请先人工登录后再扫描公共主页。")

    try:
        driver.get(MANAGED_PAGES_URL)
        WebDriverWait(driver, 30).until(
            lambda browser: browser.execute_script("return document.readyState") in ("interactive", "complete")
        )
    except WebDriverException as exc:
        raise FacebookPageDiscoveryError(f"无法打开 Facebook 公共主页管理页面：{exc}") from exc

    current_url = (driver.current_url or "").lower()
    if any(marker in current_url for marker in ("/checkpoint", "/recover", "/two_step_verification")):
        raise FacebookPageDiscoveryError("Facebook 打开了安全验证流程，请人工处理后再扫描。")
    if "/login" in current_url or "login.php" in current_url:
        raise FacebookPageDiscoveryError("Facebook 登录状态已失效，请重新登录后再扫描。")

    _scroll_page(driver)

    anchors = driver.find_elements(By.CSS_SELECTOR, "div[role='main'] a[href]")
    if not anchors:
        anchors = driver.find_elements(By.CSS_SELECTOR, "a[href]")

    pages: dict[str, dict[str, str]] = {}
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
        if not name or name.lower() in _GENERIC_LABELS:
            continue

        normalized = _normalize_facebook_page_url(href)
        if normalized is None:
            continue
        target_url, target_id = normalized

        existing = pages.get(target_id)
        if existing is None or len(name) < len(existing["target_name"]):
            pages[target_id] = {
                "target_type": "page",
                "target_id": target_id,
                "target_name": name[:255],
                "target_url": target_url,
                "source": "facebook_managed_pages",
            }

    result = sorted(pages.values(), key=lambda item: item["target_name"].casefold())
    if not result:
        title = (driver.title or "Facebook").strip()
        raise FacebookPageDiscoveryError(
            "没有从 Facebook 的“你管理的公共主页”界面读取到可发布主页。"
            f"当前页面：{title}。可能是该账号没有公共主页，或 Facebook 界面结构发生了变化。"
        )
    return result


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
