"""TikTok browser provider via Playwright."""

from __future__ import annotations

import logging
import time

from .browser_base import BrowserProvider
from .types import MediaType, PostType, PublishContent, PublishResult

logger = logging.getLogger(__name__)


class TikTokBrowserProvider(BrowserProvider):
    platform_name = "TikTok (Browser)"
    profile_name = "tiktok"
    max_caption_length = 2200
    supported_post_types = [PostType.VIDEO, PostType.SHORT]
    supported_media_types = [MediaType.MP4]
    required_scopes = []

    LOGIN_URL = "https://www.tiktok.com/login"
    UPLOAD_URL = "https://www.tiktok.com/upload"

    def setup_session(self, account_id: str, login_url: str = "") -> None:
        super().setup_session(account_id, self.LOGIN_URL)

    def publish_post(self, access_token: str, content: PublishContent) -> PublishResult:
        p, ctx = self._launch(access_token)
        try:
            page = ctx.new_page()
            page.goto(self.UPLOAD_URL, wait_until="networkidle", timeout=30000)
            time.sleep(2)
            page.locator("input[type='file']").set_input_files(content.media_files[0])
            time.sleep(5)
            page.wait_for_selector("div[class*='caption'],.DraftEditor-root", timeout=60000)
            if content.text:
                cap = page.locator("div[class*='caption'] [contenteditable],.DraftEditor-root")
                if cap.count():
                    cap.first.click()
                    cap.first.fill(content.text[:self.max_caption_length])
                    time.sleep(0.5)
            page.locator("button:has-text('Post')").first.click()
            page.wait_for_selector("div:has-text('Your video is being uploaded'),div:has-text('successfully')", timeout=120000)
            logger.info("TikTok post published for %s", access_token)
            return PublishResult(platform_post_id="", url="https://www.tiktok.com/")
        finally:
            ctx.close()
            p.stop()
