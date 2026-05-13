"""Social platform provider registry.

Maps PlatformCredential.Platform enum values to provider classes.
Use get_provider() to instantiate a provider with app credentials.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .bluesky import BlueskyProvider
from .facebook import FacebookProvider
from .facebook_browser import FacebookBrowserProvider
from .google_business import GoogleBusinessProvider
from .google_business_browser import GoogleBusinessBrowserProvider
from .instagram import InstagramProvider
from .instagram_browser import InstagramBrowserProvider
from .instagram_login import InstagramLoginProvider
from .linkedin_browser import LinkedInBrowserProvider
from .linkedin_company import LinkedInCompanyProvider
from .linkedin_personal import LinkedInPersonalProvider
from .mastodon import MastodonProvider
from .pinterest import PinterestProvider
from .pinterest_browser import PinterestBrowserProvider
from .threads import ThreadsProvider
from .threads_browser import ThreadsBrowserProvider
from .tiktok import TikTokProvider
from .tiktok_browser import TikTokBrowserProvider
from .youtube import YouTubeProvider
from .youtube_browser import YouTubeBrowserProvider

if TYPE_CHECKING:
    from .base import SocialProvider

PROVIDER_REGISTRY: dict[str, type[SocialProvider]] = {
    "facebook": FacebookProvider,
    "instagram": InstagramProvider,
    "instagram_login": InstagramLoginProvider,
    "linkedin_personal": LinkedInPersonalProvider,
    "linkedin_company": LinkedInCompanyProvider,
    "tiktok": TikTokProvider,
    "youtube": YouTubeProvider,
    "pinterest": PinterestProvider,
    "threads": ThreadsProvider,
    "bluesky": BlueskyProvider,
    "google_business": GoogleBusinessProvider,
    "mastodon": MastodonProvider,
}

# Browser-automation providers (no OAuth required — log in once, sessions persist).
# Keys here intentionally match PROVIDER_REGISTRY so the UI can offer "Quick Connect"
# as a one-click alternative for any supported platform.
BROWSER_PROVIDER_REGISTRY: dict[str, type[SocialProvider]] = {
    "facebook": FacebookBrowserProvider,
    "instagram": InstagramBrowserProvider,
    "instagram_login": InstagramBrowserProvider,
    "linkedin_personal": LinkedInBrowserProvider,
    "linkedin_company": LinkedInBrowserProvider,
    "tiktok": TikTokBrowserProvider,
    "youtube": YouTubeBrowserProvider,
    "pinterest": PinterestBrowserProvider,
    "threads": ThreadsBrowserProvider,
    "google_business": GoogleBusinessBrowserProvider,
}


def get_browser_provider(platform: str):
    """Return a browser-automation provider for ``platform`` (no OAuth needed)."""
    cls = BROWSER_PROVIDER_REGISTRY.get(platform)
    if cls is None:
        raise ValueError(f"No browser provider for platform: {platform}")
    return cls(credentials={})


def get_provider(platform: str, credentials: dict | None = None) -> SocialProvider:
    """Instantiate and return a provider for the given platform.

    Args:
        platform: A PlatformCredential.Platform value (e.g. "facebook").
        credentials: Platform app credentials (client_id, client_secret, etc.)
                     from PlatformCredential or settings.PLATFORM_CREDENTIALS_FROM_ENV.
                     If None, falls back to env credentials from
                     ``settings.PLATFORM_CREDENTIALS_FROM_ENV``.

    Raises:
        ValueError: If no provider is registered for the given platform.
    """
    provider_cls = PROVIDER_REGISTRY.get(platform)
    if provider_cls is None:
        raise ValueError(f"No provider registered for platform: {platform}")
    if credentials is None:
        from django.conf import settings

        env_creds = getattr(settings, "PLATFORM_CREDENTIALS_FROM_ENV", {})
        credentials = env_creds.get(platform, {})
    return provider_cls(credentials=credentials)
