from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from threading import RLock
from typing import Any


DEFAULT_FACEBOOK_FLOW: dict[str, list[str]] = {
    "entry_keywords": [
        "分享新鲜事",
        "分享你的新鲜事吧",
        "分享你的新鲜事",
        "在想些什么",
        "有什么新鲜事",
        "What's on your mind",
        "What’s on your mind",
        "Create post",
        "Create a post",
        "创建帖子",
        "Write something",
        "写点什么",
        "说点什么",
    ],
    "surface_titles": [
        "创建帖子",
        "发帖",
        "Create post",
        "Create Post",
        "Post",
    ],
    "media_keywords": [
        "照片/视频",
        "照片／视频",
        "图片/视频",
        "Photo/video",
        "Photo/Video",
    ],
    "next_keywords": [
        "下一页",
        "下一步",
        "继续",
        "Next",
        "Continue",
    ],
    "post_keywords": [
        "发帖",
        "发布帖子",
        "发布",
        "Post",
    ],
    "publish_original_keywords": [
        "发布原帖",
        "发布原始帖子",
        "Publish original post",
        "Publish Original Post",
    ],
    "upload_busy_keywords": [
        "正在上传",
        "正在处理",
        "Uploading",
        "Processing",
    ],
    "success_keywords": [
        "帖子已发布",
        "你的帖子已发布",
        "帖子正在处理中",
        "Your post was shared",
        "Post published",
        "Your post is being processed",
    ],
}

_ALLOWED_KEYS = tuple(DEFAULT_FACEBOOK_FLOW)
_REPO_ROOT = Path(__file__).resolve().parents[4]
_RUNTIME_PATH = _REPO_ROOT / "data" / "facebook_flow.json"
_CACHE_LOCK = RLock()
_CACHE_SIGNATURE: tuple[int, int] | None | object = object()
_CACHE_VALUE: dict[str, list[str]] | None = None


def runtime_path() -> Path:
    return _RUNTIME_PATH


def default_config() -> dict[str, list[str]]:
    return deepcopy(DEFAULT_FACEBOOK_FLOW)


def _runtime_signature() -> tuple[int, int] | None:
    try:
        stat = _RUNTIME_PATH.stat()
    except OSError:
        return None
    return stat.st_mtime_ns, stat.st_size


def _set_cache(signature: tuple[int, int] | None, value: dict[str, list[str]]) -> None:
    global _CACHE_SIGNATURE, _CACHE_VALUE
    _CACHE_SIGNATURE = signature
    _CACHE_VALUE = deepcopy(value)


def load_facebook_flow() -> dict[str, list[str]]:
    signature = _runtime_signature()
    with _CACHE_LOCK:
        if _CACHE_VALUE is not None and _CACHE_SIGNATURE == signature:
            return deepcopy(_CACHE_VALUE)

        if signature is None:
            value = default_config()
            _set_cache(None, value)
            return value

        try:
            payload = json.loads(_RUNTIME_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            value = default_config()
            _set_cache(signature, value)
            return value

        try:
            value = validate_facebook_flow(payload)
        except ValueError:
            value = default_config()

        _set_cache(signature, value)
        return deepcopy(value)


def save_facebook_flow(payload: dict[str, Any]) -> dict[str, list[str]]:
    normalized = validate_facebook_flow(payload)
    _RUNTIME_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = _RUNTIME_PATH.with_suffix(".json.tmp")
    temp_path.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(_RUNTIME_PATH)
    with _CACHE_LOCK:
        _set_cache(_runtime_signature(), normalized)
    return normalized


def reset_facebook_flow() -> dict[str, list[str]]:
    try:
        _RUNTIME_PATH.unlink(missing_ok=True)
    except OSError:
        pass
    value = default_config()
    with _CACHE_LOCK:
        _set_cache(None, value)
    return value


def validate_facebook_flow(payload: Any) -> dict[str, list[str]]:
    if not isinstance(payload, dict):
        raise ValueError("Facebook 流程配置必须是对象。")

    unknown = set(payload) - set(_ALLOWED_KEYS)
    if unknown:
        raise ValueError(f"不支持的 Facebook 流程配置项：{', '.join(sorted(unknown))}")

    normalized: dict[str, list[str]] = {}
    for key in _ALLOWED_KEYS:
        raw = payload.get(key, DEFAULT_FACEBOOK_FLOW[key])
        if not isinstance(raw, list):
            raise ValueError(f"{key} 必须是关键词数组。")
        if len(raw) > 50:
            raise ValueError(f"{key} 最多允许 50 个关键词。")

        values: list[str] = []
        for item in raw:
            if not isinstance(item, str):
                raise ValueError(f"{key} 只能包含文本关键词。")
            value = " ".join(item.split()).strip()
            if not value:
                continue
            if len(value) > 100:
                raise ValueError(f"{key} 单个关键词不能超过 100 个字符。")
            if value not in values:
                values.append(value)

        if not values:
            raise ValueError(f"{key} 至少需要 1 个关键词。")
        normalized[key] = values

    return normalized
