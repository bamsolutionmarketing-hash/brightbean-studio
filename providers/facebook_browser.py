"""Facebook browser provider via Playwright."""

from __future__ import annotations

import logging
import time

from .browser_base import BrowserProvider
from .types import MediaType, PostType, PublishContent, PublishResult

logger = logging.getLogger(__name__)


class FacebookBrowserProvider(BrowserProvider):
    platform_name = "Facebook (Browser)"
    profile_name = "facebook"
    max_caption_length = 63206
    supported_post_types = [PostType.IMAGE, PostType.VIDEO, PostType.TEXT]
    supported_media_types = [MediaType.JPEG, MediaType.PNG, MediaType.MP4]
    required_scopes = []

    LOGIN_URL = "https://www.facebook.com/login"
    HOME_URL = "https://www.facebook.com/"

    def setup_session(self, account_id: str, login_url: str = "") -> None:
        super().setup_session(account_id, self.LOGIN_URL)

    def publish_post(self, access_token: str, content: PublishContent) -> PublishResult:
        p, ctx = self._launch(access_token)
        try:
            page = ctx.new_page()
            page.goto(self.HOME_URL, wait_until="networkidle", timeout=30000)
            time.sleep(2)
            page.locator("[aria-label=\"What's on your mind?\"]").first.click()
            time.sleep(1)
            if content.media_files:
                with page.expect_file_chooser() as fc:
                    page.locator("[aria-label='Photo/video']").first.click()
                fc.value.set_files(content.media_files)
                time.sleep(3)
            if content.text:
                cap = page.locator("[aria-label=\"What's on your mind?\"]")
                cap.first.click()
                cap.first.fill(content.text[:self.max_caption_length])
                time.sleep(0.5)
            page.locator("[aria-label='Post']").first.click()
            time.sleep(5)
            logger.info("Facebook post published for %s", access_token)
            return PublishResult(platform_post_id="", url=self.HOME_URL)
        finally:
            ctx.close()
            p.stop()
