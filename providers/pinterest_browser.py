"""Pinterest browser provider via Playwright."""

from __future__ import annotations

import logging
import time

from .browser_base import BrowserProvider
from .types import MediaType, PostType, PublishContent, PublishResult

logger = logging.getLogger(__name__)


class PinterestBrowserProvider(BrowserProvider):
    platform_name = "Pinterest (Browser)"
    profile_name = "pinterest"
    max_caption_length = 500
    supported_post_types = [PostType.PIN, PostType.IMAGE, PostType.VIDEO]
    supported_media_types = [MediaType.JPEG, MediaType.PNG, MediaType.MP4]
    required_scopes = []

    LOGIN_URL = "https://www.pinterest.com/login/"
    CREATE_URL = "https://www.pinterest.com/pin-creation-tool/"

    def setup_session(self, account_id: str, login_url: str = "") -> None:
        super().setup_session(account_id, self.LOGIN_URL)

    def publish_post(self, access_token: str, content: PublishContent) -> PublishResult:
        p, ctx = self._launch(access_token)
        try:
            page = ctx.new_page()
            page.goto(self.CREATE_URL, wait_until="networkidle", timeout=30000)
            time.sleep(2)
            if content.media_files:
                with page.expect_file_chooser() as fc:
                    page.locator("input[type='file'],[aria-label='Upload a file']").first.click()
                fc.value.set_files(content.media_files[0])
                time.sleep(4)
            ti = page.locator("[data-test-id='pin-title-input']")
            if ti.count() and (content.title or content.text):
                ti.first.fill((content.title or content.text or "")[:100])
            if content.text:
                d = page.locator("[data-test-id='pin-draft-description'],[contenteditable='true']")
                if d.count():
                    d.first.click()
                    d.first.fill(content.text[:self.max_caption_length])
            page.locator("button:has-text('Publish'),button:has-text('Save')").first.click()
            time.sleep(4)
            logger.info("Pinterest pin published for %s", access_token)
            return PublishResult(platform_post_id="", url="https://www.pinterest.com/")
        finally:
            ctx.close()
            p.stop()
