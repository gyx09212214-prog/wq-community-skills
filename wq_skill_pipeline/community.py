from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from .io_utils import write_json, write_jsonl

DEFAULT_BASE_URL = "https://platform.worldquantbrain.com"
DEFAULT_POSTS_PATH = "/forum/posts"
DEFAULT_COMMENTS_PATH_TEMPLATE = "/forum/posts/{post_id}/comments"


def save_login_state(state_path: Path, *, login_url: str = DEFAULT_BASE_URL, timeout_ms: int = 120_000) -> Path:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise RuntimeError("Playwright is not installed. Run: python -m pip install -e \".[live]\"") from exc

    state_path.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:  # pragma: no cover - interactive browser flow
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(login_url)
        page.wait_for_timeout(timeout_ms)
        page.context.storage_state(path=str(state_path))
        browser.close()
    return state_path


def auth_from_storage_state(state_path: Path, domain_suffix: str = "worldquantbrain.com") -> dict[str, Any]:
    if not state_path.is_file():
        return {"cookie_header": "", "cookie_count": 0, "authorization": ""}
    state = json.loads(state_path.read_text(encoding="utf-8"))
    cookies = []
    for cookie in state.get("cookies", []):
        domain = str(cookie.get("domain") or "")
        if domain_suffix in domain:
            name = str(cookie.get("name") or "")
            value = str(cookie.get("value") or "")
            if name and value:
                cookies.append(f"{name}={value}")
    authorization = ""
    for origin in state.get("origins", []):
        for item in origin.get("localStorage", []):
            key = str(item.get("name") or "").lower()
            if key in {"authorization", "token", "access_token"}:
                authorization = str(item.get("value") or "")
                break
    return {"cookie_header": "; ".join(cookies), "cookie_count": len(cookies), "authorization": authorization}


def export_community_readonly(
    *,
    state_path: Path,
    output_dir: Path,
    base_url: str = DEFAULT_BASE_URL,
    posts_path: str = DEFAULT_POSTS_PATH,
    comments_path_template: str = DEFAULT_COMMENTS_PATH_TEMPLATE,
    max_posts: int = 100,
    max_pages: int = 5,
    limit: int = 50,
    sleep_seconds: float = 0.5,
) -> dict[str, Any]:
    auth = auth_from_storage_state(state_path)
    if not auth.get("cookie_header") and not auth.get("authorization"):
        raise RuntimeError(f"No usable cookies or authorization found in Playwright storage state: {state_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    posts: list[dict[str, Any]] = []
    comments: list[dict[str, Any]] = []
    headers = _headers(auth)
    for page in range(1, max_pages + 1):
        url = _url(base_url, posts_path, {"page": page, "limit": limit})
        payload = _get_json(url, headers=headers)
        page_posts = _records_from_payload(payload)
        posts.extend(page_posts)
        if len(posts) >= max_posts or not page_posts:
            break
        time.sleep(max(0.0, sleep_seconds))
    posts = posts[:max_posts]
    for post in posts:
        post_id = post.get("id") or post.get("post_id") or post.get("uuid")
        if not post_id:
            continue
        path = comments_path_template.format(post_id=urllib.parse.quote(str(post_id)))
        try:
            payload = _get_json(_url(base_url, path, {"limit": limit}), headers=headers)
        except RuntimeError:
            continue
        comments.extend(_records_from_payload(payload))
        time.sleep(max(0.0, sleep_seconds))

    posts_path_out = output_dir / "posts.jsonl"
    comments_path_out = output_dir / "comments.jsonl"
    manifest_path = output_dir / "community_export_manifest.json"
    write_jsonl(posts_path_out, [_public_raw_row(row) for row in posts])
    write_jsonl(comments_path_out, [_public_raw_row(row) for row in comments])
    manifest = {
        "schema_version": 1,
        "mode": "readonly_live",
        "posts": len(posts),
        "comments": len(comments),
        "auth": {
            "playwright_state": str(state_path),
            "cookie_count": auth.get("cookie_count", 0),
            "authorization_present": bool(auth.get("authorization")),
        },
        "files": {"posts": str(posts_path_out), "comments": str(comments_path_out)},
        "privacy_note": "Credentials, cookies, and authorization headers are not written to raw artifacts.",
    }
    write_json(manifest_path, manifest)
    return manifest


def synthetic_community_records() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    posts = [
        {
            "id": "synthetic-post-001",
            "title": "Near-pass value quality template discussion",
            "body": "A high fitness value-quality idea is close to pass, but correlation is high. Use rank, ts_rank, and a broad overlay; do not submit the original template.",
        },
        {
            "id": "synthetic-post-002",
            "title": "Turnover and trade density repair",
            "body": "When turnover is unstable, tune decay and trade_when density together. Check coverage before changing the field family.",
        },
        {
            "id": "synthetic-post-003",
            "title": "Platform unit probe",
            "body": "Unsupported operator and unit issues should be tested with tiny probes before full simulation.",
        },
    ]
    comments = [
        {
            "id": "synthetic-comment-001",
            "post_id": "synthetic-post-001",
            "body": "If a template looks complete, treat it as grammar only and transform field family plus operator family.",
        },
        {
            "id": "synthetic-comment-002",
            "post_id": "synthetic-post-002",
            "body": "Sparse coverage and concentration need a broad high-coverage leg before rerun.",
        },
    ]
    return posts, comments


def _headers(auth: dict[str, Any]) -> dict[str, str]:
    headers = {
        "User-Agent": "wq-community-skills readonly exporter",
        "Accept": "application/json",
        "Accept-Encoding": "identity",
    }
    if auth.get("cookie_header"):
        headers["Cookie"] = str(auth["cookie_header"])
    if auth.get("authorization"):
        headers["Authorization"] = str(auth["authorization"])
    return headers


def _url(base_url: str, path: str, params: dict[str, Any]) -> str:
    if path.startswith("http://") or path.startswith("https://"):
        base = path
    else:
        base = base_url.rstrip("/") + "/" + path.lstrip("/")
    return base + "?" + urllib.parse.urlencode(params)


def _get_json(url: str, headers: dict[str, str]) -> Any:
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = response.read().decode("utf-8")
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"readonly fetch failed for {url}: {exc}") from exc
    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"readonly fetch returned non-JSON payload for {url}") from exc


def _records_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("results", "data", "items", "posts", "comments"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
        return [payload]
    return []


def _public_raw_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id") or row.get("post_id") or row.get("uuid"),
        "post_id": row.get("post_id"),
        "title": row.get("title") or row.get("name"),
        "body": row.get("body") or row.get("text") or row.get("content") or row.get("comment"),
        "created_at": row.get("created_at") or row.get("created") or row.get("date"),
    }
