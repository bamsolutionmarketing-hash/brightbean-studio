"""Instagram browser provider via Playwright."""

from __future__ import annotations

import logging
import time

from .browser_base import BrowserProvider
from .types import MediaType, PostType, PublishContent, PublishResult

logger = logging.getLogger(__name__)


class InstagramBrowserProvider(BrowserProvider):
    platform_name = "Instagram (Browser)"
    profile_name = "instagram"
    max_caption_length = 2200
    supported_post_types = [PostType.IMAGE, PostType.VIDEO, PostType.CAROUSEL, PostType.REEL]
    supported_media_types = [MediaType.JPEG, MediaType.PNG, MediaType.MP4]
    required_scopes = []

    LOGIN_URL = "https://www.instagram.com/accounts/login/"
    HOME_URL = "https://www.instagram.com/"

    def setup_session(self, account_id: str, login_url: str = "") -> None:
        super().setup_session(account_id, self.LOGIN_URL)

    def publish_post(self, access_token: str, content: PublishContent) -> PublishResult:
        p, ctx = self._launch(access_token)
        try:
            page = ctx.new_page()
            page.goto(self.HOME_URL, wait_until="networkidle", timeout=30000)
            page.click("[aria-label='New post'],[aria-label='Create']", timeout=15000)
            time.sleep(1)
            with page.expect_file_chooser() as fc:
                page.click("button:has-text('Select from computer'),input[type='file']", timeout=10000)
            fc.value.set_files(content.media_files[0] if content.media_files else [])
            time.sleep(2)
            for _ in range(2):
                btn = page.locator("button:has-text('Next')")
                if btn.count():
                    btn.first.click()
                    time.sleep(1.5)
            if content.text:
                cap = page.locator("div[aria-label='Write a caption...'],[contenteditable='true']")
                if cap.count():
                    cap.first.click()
                    cap.first.fill(content.text[:self.max_caption_length])
                    time.sleep(0.5)
            page.locator("button:has-text('Share')").first.click()
            page.wait_for_selector("[aria-label='Post shared'],span:has-text('Your post has been shared')", timeout=60000)
            logger.info("Instagram post published for %s", access_token)
            return PublishResult(platform_post_id="", url=self.HOME_URL)
        finally:
            ctx.close()
            p.stop()
