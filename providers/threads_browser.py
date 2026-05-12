"""Threads browser provider via Playwright."""

from __future__ import annotations

import logging
import time

from .browser_base import BrowserProvider
from .types import MediaType, PostType, PublishContent, PublishResult

logger = logging.getLogger(__name__)


class ThreadsBrowserProvider(BrowserProvider):
    platform_name = "Threads (Browser)"
    profile_name = "threads"
    max_caption_length = 500
    supported_post_types = [PostType.IMAGE, PostType.VIDEO, PostType.TEXT]
    supported_media_types = [MediaType.IMAGE, MediaType.VIDEO]
    required_scopes = []

    LOGIN_URL = "https://www.threads.net/login"
    HOME_URL = "https://www.threads.net/"

    def setup_session(self, account_id: str, login_url: str = "") -> None:
        super().setup_session(account_id, self.LOGIN_URL)

    def publish_post(self, access_token: str, content: PublishContent) -> PublishResult:
        p, ctx = self._launch(access_token)
        try:
            page = ctx.new_page()
            page.goto(self.HOME_URL, wait_until="networkidle", timeout=30000)
            time.sleep(2)
            page.locator("[aria-label='New thread']").first.click()
            time.sleep(1)
            if content.text:
                ed = page.locator("[contenteditable='true']").first
                ed.click()
                ed.fill(content.text[:self.max_caption_length])
                time.sleep(0.5)
            if content.media_files:
                with page.expect_file_chooser() as fc:
                    page.locator("[aria-label='Attach media']").first.click()
                fc.value.set_files(content.media_files[0])
                time.sleep(3)
            page.locator("button:has-text('Post')").first.click()
            time.sleep(4)
            logger.info("Threads post published for %s", access_token)
            return PublishResult(platform_post_id="", url=self.HOME_URL)
        finally:
            ctx.close()
            p.stop()
