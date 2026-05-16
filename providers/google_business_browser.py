"""Google Business Profile browser provider via Playwright."""

from __future__ import annotations

import logging
import time

from .browser_base import BrowserProvider
from .types import MediaType, PostType, PublishContent, PublishResult

logger = logging.getLogger(__name__)


class GoogleBusinessBrowserProvider(BrowserProvider):
    platform_name = "Google Business (Browser)"
    profile_name = "google_business"
    max_caption_length = 1500
    supported_post_types = [PostType.IMAGE, PostType.TEXT]
    supported_media_types = [MediaType.JPEG, MediaType.PNG]
    required_scopes = []

    LOGIN_URL = "https://accounts.google.com/"
    POSTS_URL = "https://business.google.com/posts"

    def setup_session(self, account_id: str, login_url: str = "") -> None:
        super().setup_session(account_id, self.LOGIN_URL)

    def publish_post(self, access_token: str, content: PublishContent) -> PublishResult:
        p, ctx = self._launch(access_token)
        try:
            page = ctx.new_page()
            page.goto(self.POSTS_URL, wait_until="networkidle", timeout=30000)
            time.sleep(2)
            page.locator("button:has-text('Add update'),button:has-text('Create post')").first.click()
            time.sleep(1)
            if content.text:
                ed = page.locator("[contenteditable='true'],textarea").first
                ed.click()
                ed.fill(content.text[:self.max_caption_length])
                time.sleep(0.5)
            if content.media_files:
                with page.expect_file_chooser() as fc:
                    page.locator("button:has-text('Add photos')").first.click()
                fc.value.set_files(content.media_files[0])
                time.sleep(4)
            page.locator("button:has-text('Publish')").first.click()
            time.sleep(4)
            logger.info("Google Business post published for %s", access_token)
            return PublishResult(platform_post_id="", url="https://business.google.com/")
        finally:
            ctx.close()
            p.stop()
