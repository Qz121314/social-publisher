from __future__ import annotations

import time
from typing import Any

from selenium.common.exceptions import WebDriverException
from selenium.webdriver import Chrome
from selenium.webdriver.support.ui import WebDriverWait

from app.services.platforms.base import PlatformContent, PlatformPublishError
from app.services.platforms.facebook_identity import IdentityAwareFacebookAdapter


_KEYWORDS = (
    "在想些什么",
    "有什么新鲜事",
    "创建帖子",
    "发帖",
    "写点什么",
    "说点什么",
    "发布动态",
    "what's on your mind",
    "what’s on your mind",
    "create post",
    "create a post",
    "write something",
    "share an update",
)


def probe_facebook_composer_entry(
    driver: Chrome,
    *,
    target_type: str,
    target_id: str,
    target_name: str,
    target_url: str,
) -> dict[str, Any]:
    """Inspect the real Facebook target page for composer-entry DOM candidates.

    This function never clicks a composer or Post button. It only validates the
    configured actor ID, navigates to the configured target URL, scrolls the
    page, and returns a small set of likely composer-entry elements.
    """

    adapter = IdentityAwareFacebookAdapter()
    content = PlatformContent(
        text="probe-only",
        media=(),
        target_type=target_type,
        target_id=target_id,
        target_name=target_name,
        target_url=target_url,
    )

    adapter._ensure_target_identity(driver, content)
    adapter._assert_target_actor(driver, content, stage="发帖入口检测前")

    try:
        driver.get(target_url)
        WebDriverWait(driver, 30).until(
            lambda browser: browser.execute_script("return document.readyState")
            in ("interactive", "complete")
        )
    except WebDriverException as exc:
        raise PlatformPublishError(f"打开 Facebook 目标主页进行发帖入口检测时失败：{exc}") from exc

    adapter._assert_target_actor(driver, content, stage="进入目标主页后")

    collected: dict[str, dict[str, Any]] = {}
    positions = _scroll_positions(driver)
    for position in positions:
        try:
            driver.execute_script("window.scrollTo(0, arguments[0]);", position)
        except WebDriverException:
            pass
        time.sleep(0.7)
        for item in _collect_candidates(driver):
            key = "|".join(
                str(item.get(field) or "")
                for field in ("tag", "role", "aria_label", "placeholder", "text", "xpath_hint")
            )
            current = collected.get(key)
            if current is None or int(item.get("score") or 0) > int(current.get("score") or 0):
                collected[key] = item

    try:
        driver.execute_script("window.scrollTo(0, 0);")
    except WebDriverException:
        pass

    items = sorted(collected.values(), key=lambda item: int(item.get("score") or 0), reverse=True)
    items = items[:20]
    return {
        "target_type": target_type,
        "target_id": target_id,
        "target_name": target_name,
        "current_actor_id": adapter._current_actor_id(driver),
        "current_url": driver.current_url,
        "title": driver.title,
        "count": len(items),
        "best": items[0] if items else None,
        "items": items,
    }


def _scroll_positions(driver: Chrome) -> list[int]:
    try:
        height = int(driver.execute_script("return Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)") or 0)
        viewport = int(driver.execute_script("return window.innerHeight") or 800)
    except WebDriverException:
        return [0, 450, 900]

    candidates = [0, 300, 600, 900, 1200]
    if height > viewport:
        candidates.extend([max(0, int(height * 0.25)), max(0, int(height * 0.5))])
    return sorted({min(max(0, value), max(0, height - viewport)) for value in candidates})


def _collect_candidates(driver: Chrome) -> list[dict[str, Any]]:
    script = r"""
const keywords = arguments[0].map(v => v.toLowerCase());
const selector = [
  'button', '[role="button"]', '[role="textbox"]', '[contenteditable="true"]',
  '[aria-label]', '[aria-placeholder]', '[data-placeholder]', '[tabindex="0"]',
  'textarea', 'input', 'div', 'span'
].join(',');

function visible(el) {
  const r = el.getBoundingClientRect();
  const s = getComputedStyle(el);
  return r.width > 1 && r.height > 1 && s.display !== 'none' && s.visibility !== 'hidden' && Number(s.opacity || 1) > 0;
}

function textOf(el) {
  return [
    el.getAttribute('aria-label') || '',
    el.getAttribute('aria-placeholder') || '',
    el.getAttribute('data-placeholder') || '',
    el.getAttribute('placeholder') || '',
    el.innerText || '',
    el.textContent || ''
  ].join(' ').replace(/\s+/g, ' ').trim();
}

function clickableAncestor(el) {
  let cur = el;
  for (let i = 0; cur && i < 7; i++, cur = cur.parentElement) {
    const role = cur.getAttribute && (cur.getAttribute('role') || '');
    const tabindex = cur.getAttribute && (cur.getAttribute('tabindex') || '');
    const href = cur.getAttribute && (cur.getAttribute('href') || '');
    const cursor = getComputedStyle(cur).cursor;
    if (role === 'button' || role === 'textbox' || tabindex === '0' || href || cursor === 'pointer' || typeof cur.onclick === 'function') {
      return cur;
    }
  }
  return null;
}

function hint(el) {
  const parts = [];
  let cur = el;
  for (let i = 0; cur && i < 4; i++, cur = cur.parentElement) {
    let p = (cur.tagName || '').toLowerCase();
    const role = cur.getAttribute && cur.getAttribute('role');
    const aria = cur.getAttribute && cur.getAttribute('aria-label');
    if (role) p += `[role=${role}]`;
    if (aria) p += `[aria-label=${aria.slice(0,60)}]`;
    parts.unshift(p);
  }
  return parts.join(' > ');
}

const nodes = Array.from(document.querySelectorAll(selector));
const result = [];
for (const el of nodes) {
  if (!visible(el)) continue;
  const text = textOf(el);
  const lower = text.toLowerCase();
  const role = el.getAttribute('role') || '';
  const editable = (el.getAttribute('contenteditable') || '').toLowerCase() === 'true';
  const keyword = keywords.find(k => lower.includes(k));
  if (!keyword && role !== 'textbox' && !editable) continue;

  const click = clickableAncestor(el);
  const rect = el.getBoundingClientRect();
  let score = 0;
  if (keyword) score += 60;
  if (role === 'textbox') score += 40;
  if (editable) score += 35;
  if (role === 'button') score += 25;
  if (el.getAttribute('aria-label')) score += 15;
  if (el.getAttribute('aria-placeholder') || el.getAttribute('data-placeholder')) score += 15;
  if (click) score += 20;
  if (rect.top > 80) score += 5;

  result.push({
    score,
    matched_keyword: keyword || '',
    tag: (el.tagName || '').toLowerCase(),
    role,
    aria_label: (el.getAttribute('aria-label') || '').slice(0,160),
    placeholder: (el.getAttribute('aria-placeholder') || el.getAttribute('data-placeholder') || el.getAttribute('placeholder') || '').slice(0,160),
    text: text.slice(0,220),
    contenteditable: el.getAttribute('contenteditable') || '',
    tabindex: el.getAttribute('tabindex') || '',
    cursor: getComputedStyle(el).cursor || '',
    x: Math.round(rect.x), y: Math.round(rect.y + window.scrollY),
    width: Math.round(rect.width), height: Math.round(rect.height),
    clickable_tag: click ? (click.tagName || '').toLowerCase() : '',
    clickable_role: click ? (click.getAttribute('role') || '') : '',
    clickable_aria_label: click ? (click.getAttribute('aria-label') || '').slice(0,160) : '',
    xpath_hint: hint(el).slice(0,320),
  });
}
return result.sort((a,b) => b.score - a.score).slice(0,40);
"""
    try:
        result = driver.execute_script(script, list(_KEYWORDS))
    except WebDriverException:
        return []
    return result if isinstance(result, list) else []
