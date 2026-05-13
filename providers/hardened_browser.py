"""Hardened Chromium session for shared team tools (Canva, ChatGPT, etc.).

The browser is locked down so the user CANNOT:
  - Install Chrome extensions (no Web Store, no extension API)
  - Open DevTools (F12, Ctrl+Shift+I/J/C, Ctrl+U disabled)
  - Right-click → Inspect (contextmenu blocked)
  - Navigate to chrome://, chrome-extension:// or chromewebstore.google.com
  - Download arbitrary files
  - Use the address bar / browser menu (runs in --app mode)

Cookies are injected into a fresh temp profile, used for the session, then
the entire profile directory is shredded on `cleanup_session`.
"""

from __future__ import annotations

import json
import logging
import shutil
import tempfile
from pathlib import Path

from .cookie_import import _normalize_cookie, _parse_payload

logger = logging.getLogger(__name__)


_HARDEN_INIT_SCRIPT = r"""
(() => {
  // Block DevTools keyboard shortcuts and view-source.
  const block = (e) => {
    const k = (e.key || '').toLowerCase();
    if (k === 'f12') return e.preventDefault();
    if (e.ctrlKey && e.shiftKey && (k === 'i' || k === 'j' || k === 'c')) return e.preventDefault();
    if ((e.ctrlKey || e.metaKey) && k === 'u') return e.preventDefault();
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && k === 's') return e.preventDefault();  // Save as
  };
  window.addEventListener('keydown', block, true);
  document.addEventListener('keydown', block, true);
  // Block right-click context menu
  window.addEventListener('contextmenu', (e) => e.preventDefault(), true);
  document.addEventListener('contextmenu', (e) => e.preventDefault(), true);
})();
"""


_HARDENED_ARGS = [
    "--disable-extensions",
    "--disable-extensions-file-access-check",
    "--disable-extensions-http-throttling",
    "--disable-component-extensions-with-background-pages",
    "--disable-features=ExtensionsToolbarMenu,DevTools,ChromeWhatsNewUI",
    "--no-default-browser-check",
    "--no-first-run",
    "--disable-background-networking",
    "--disable-sync",
    "--disable-translate",
    "--disable-default-apps",
    "--disable-popup-blocking",
    "--disable-prompt-on-repost",
    "--disable-component-update",
    "--disable-domain-reliability",
]

# Hosts that allow installing/exporting cookies — block at network layer.
_BLOCKED_URL_PATTERNS = [
    "chrome://*",
    "chrome-extension://*",
    "*://chromewebstore.google.com/*",
    "*://chrome.google.com/webstore/*",
    "*://addons.mozilla.org/*",
    "*://microsoftedge.microsoft.com/addons/*",
]


def _make_temp_profile() -> Path:
    """Fresh disposable profile directory."""
    return Path(tempfile.mkdtemp(prefix="brightbean-tool-"))


def _cookies_for_playwright(payload: str) -> list[dict]:
    raw = _parse_payload(payload)
    cookies = [c for c in (_normalize_cookie(rc) for rc in raw) if c]
    if not cookies:
        raise ValueError("No valid cookies in payload")
    return cookies


def launch_tool_session(tool_url: str, cookies_payload: str) -> str:
    """Open a hardened Chromium window for the given tool URL.

    Blocks until the user closes the window, then deletes the temp profile.
    Returns the path to the temp profile that was used (already deleted).
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Run: pip install playwright && playwright install chromium"
        ) from exc

    cookies = _cookies_for_playwright(cookies_payload)
    profile_dir = _make_temp_profile()

    p = sync_playwright().start()
    try:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=False,
            accept_downloads=False,
            args=[*_HARDENED_ARGS, f"--app={tool_url}"],
            ignore_default_args=["--enable-automation"],
            viewport=None,
        )

        ctx.add_init_script(_HARDEN_INIT_SCRIPT)
        ctx.add_cookies(cookies)

        # Block extension stores / chrome-internal pages at network layer.
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            cdp = ctx.new_cdp_session(page)
            cdp.send("Network.enable")
            cdp.send("Network.setBlockedURLs", {"urls": _BLOCKED_URL_PATTERNS})
        except Exception:
            logger.warning("Could not install CDP URL blocklist", exc_info=True)

        if not page.url or page.url == "about:blank":
            page.goto(tool_url)

        # Wait until the user closes every page (the --app window).
        try:
            page.wait_for_event("close", timeout=0)
        except Exception:
            pass

        try:
            ctx.close()
        except Exception:
            pass
    finally:
        p.stop()
        cleanup_session(str(profile_dir))

    return str(profile_dir)


def cleanup_session(profile_dir: str) -> None:
    """Permanently delete the temp browser profile (best-effort)."""
    path = Path(profile_dir)
    if not path.exists():
        return
    try:
        shutil.rmtree(path, ignore_errors=True)
        logger.info("Tool session profile shredded: %s", profile_dir)
    except Exception:
        logger.exception("Failed to remove temp profile %s", profile_dir)
