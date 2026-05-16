"""YouTube browser provider via Playwright (YouTube Studio)."""

from __future__ import annotations

import logging
import time

from .browser_base import BrowserProvider
from .types import MediaType, PostType, PublishContent, PublishResult

logger = logging.getLogger(__name__)


class YouTubeBrowserProvider(BrowserProvider):
    platform_name = "YouTube (Browser)"
    profile_name = "youtube"
    max_caption_length = 5000
    supported_post_types = [PostType.VIDEO, PostType.SHORT]
    supported_media_types = [MediaType.MP4]
    required_scopes = []

    LOGIN_URL = "https://accounts.google.com/"
    STUDIO_URL = "https://studio.youtube.com/"

    def setup_session(self, account_id: str, login_url: str = "") -> None:
        super().setup_session(account_id, self.LOGIN_URL)

    def publish_post(self, access_token: str, content: PublishContent) -> PublishResult:
        p, ctx = self._launch(access_token)
        try:
            page = ctx.new_page()
            page.goto(self.STUDIO_URL, wait_until="networkidle", timeout=30000)
            time.sleep(2)
            page.locator("[aria-label='Upload videos']").first.click()
            time.sleep(1)
            with page.expect_file_chooser() as fc:
                page.locator("#select-files-button").first.click()
            fc.value.set_files(content.media_files[0])
            page.wait_for_selector("#title-textarea", timeout=30000)
            time.sleep(2)
            title = page.locator("#title-textarea [contenteditable]").first
            title.triple_click()
            title.fill((content.title or content.text or "")[:100])
            if content.text:
                desc = page.locator("#description-textarea [contenteditable]").first
                if desc.count():
                    desc.click()
                    desc.fill(content.text[:self.max_caption_length])
            for _ in range(3):
                nb = page.locator("[aria-label='Next']")
                if nb.count() and nb.first.is_visible():
                    nb.first.click()
                    time.sleep(1.5)
            pr = page.locator("[name='PUBLIC']")
            if pr.count():
                pr.first.click()
                time.sleep(0.5)
            page.locator("[aria-label='Publish']").first.click()
            page.wait_for_selector(".ytcp-video-share-url", timeout=120000)
            logger.info("YouTube video published for %s", access_token)
            return PublishResult(platform_post_id="", url="https://www.youtube.com/")
        finally:
            ctx.close()
            p.stop()
