"""Import cookies (e.g. from the J2TEAM Cookies Chrome extension) into a
Playwright persistent browser profile, so the user can connect a social
account by pasting JSON instead of logging in.

Supports two common shapes:

1. J2TEAM Cookies export:
     {"url": "https://www.facebook.com", "cookies": [ {...}, {...} ]}

2. EditThisCookie / generic array:
     [ {"name": "...", "value": "...", "domain": "...", ...}, ... ]
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .browser_base import _profiles_dir

logger = logging.getLogger(__name__)


# Reasonable defaults for cookie attributes Playwright requires
_SAMESITE_MAP = {
    "lax": "Lax", "strict": "Strict", "no_restriction": "None",
    "none": "None", "unspecified": "Lax", "": "Lax",
}


def _normalize_cookie(raw: dict) -> dict | None:
    """Turn a J2TEAM / EditThisCookie cookie into Playwright's expected shape."""
    name = raw.get("name")
    value = raw.get("value")
    domain = raw.get("domain") or ""
    if not name or value is None or not domain:
        return None

    cookie: dict[str, Any] = {
        "name": name,
        "value": str(value),
        "domain": domain if domain.startswith(".") else domain,
        "path": raw.get("path") or "/",
        "secure": bool(raw.get("secure", False)),
        "httpOnly": bool(raw.get("httpOnly", False)),
    }

    same_site = str(raw.get("sameSite", "Lax")).lower()
    cookie["sameSite"] = _SAMESITE_MAP.get(same_site, "Lax")

    exp = raw.get("expirationDate") or raw.get("expires")
    if exp and not raw.get("session"):
        try:
            cookie["expires"] = int(float(exp))
        except (TypeError, ValueError):
            pass

    return cookie


def _parse_payload(payload: str) -> list[dict]:
    """Extract a list of cookie dicts from any of the supported JSON shapes."""
    data = json.loads(payload)
    if isinstance(data, dict) and "cookies" in data:
        cookies = data["cookies"]
    elif isinstance(data, list):
        cookies = data
    else:
        raise ValueError("Unrecognised cookie JSON format")
    if not isinstance(cookies, list):
        raise ValueError("'cookies' must be an array")
    return cookies


def import_cookies(profile_name: str, account_id: str, payload: str) -> int:
    """Inject cookies into the persistent browser profile.

    Args:
        profile_name: BrowserProvider.profile_name (e.g. "facebook").
        account_id: Unique id for this account (becomes profile sub-dir).
        payload: Raw JSON string copied from J2TEAM Cookies / EditThisCookie.

    Returns the number of cookies successfully imported.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Run: pip install playwright && playwright install chromium"
        ) from exc

    raw_cookies = _parse_payload(payload)
    cookies = [c for c in (_normalize_cookie(rc) for rc in raw_cookies) if c]
    if not cookies:
        raise ValueError("No valid cookies found in the JSON payload")

    profile_path = _profiles_dir() / profile_name / account_id
    profile_path.mkdir(parents=True, exist_ok=True)

    p = sync_playwright().start()
    try:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(profile_path),
            headless=True,
        )
        ctx.add_cookies(cookies)
        ctx.close()
    finally:
        p.stop()

    logger.info(
        "Imported %d cookies into %s / %s", len(cookies), profile_name, account_id
    )
    return len(cookies)
