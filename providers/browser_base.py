"""Playwright-based browser provider — persistent sessions, no OAuth needed."""

from __future__ import annotations

import logging
import sys
from abc import abstractmethod
from pathlib import Path

from .base import SocialProvider
from .types import AccountProfile, AuthType, PublishContent, PublishResult

logger = logging.getLogger(__name__)


def _profiles_dir() -> Path:
    """OS-appropriate directory for persistent browser profiles."""
    if sys.platform == "win32":
        import os
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path.home() / ".local" / "share"
    return base / "brightbean-studio" / "browser-profiles"


class BrowserProvider(SocialProvider):
    """Base for browser-automation providers.

    Store the platform username in SocialAccount.oauth_access_token —
    it's used as the browser profile key (not an actual OAuth token).

    One-time setup per account:
        provider.setup_session("my_username")
    After that, all posting is fully automatic.
    """

    HEADLESS: bool = False
    SLOW_MO: int = 150

    @property
    @abstractmethod
    def profile_name(self) -> str:
        """Subdirectory name for this platform's profiles (e.g. 'instagram')."""

    @property
    def auth_type(self) -> AuthType:
        return AuthType.CUSTOM

    def _profile_path(self, account_id: str) -> Path:
        path = _profiles_dir() / self.profile_name / account_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _launch(self, account_id: str):
        """Launch Playwright with a persistent context. Returns (playwright, context)."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Run: pip install playwright && playwright install chromium"
            ) from exc
        p = sync_playwright().start()
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(self._profile_path(account_id)),
            headless=self.HEADLESS,
            slow_mo=self.SLOW_MO,
            args=["--start-maximized"],
            viewport=None,
            locale="en-US",
            timezone_id="America/New_York",
        )
        return p, ctx

    def setup_session(self, account_id: str, login_url: str) -> None:
        """Open browser for one-time manual login. Press ENTER in terminal when done."""
        p, ctx = self._launch(account_id)
        page = ctx.new_page()
        page.goto(login_url)
        print(f"\n[brightbean] Log in to {self.platform_name} in the browser window.")
        print("[brightbean] Press ENTER to save session and close.")
        input()
        ctx.close()
        p.stop()
        logger.info("Session saved: %s / %s", self.platform_name, account_id)

    def get_profile(self, access_token: str) -> AccountProfile:
        raise NotImplementedError("Browser providers do not use OAuth tokens")

    @abstractmethod
    def publish_post(self, access_token: str, content: PublishContent) -> PublishResult:
        """access_token = account_id (browser profile key)."""
