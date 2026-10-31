"""Browser origins for Hub console and shared-app tenant resolution."""
HUB_WEB_ORIGINS = [
    'http://localhost:3000', 'http://127.0.0.1:3000',
    'https://hub.nxtdeal.app', 'https://apps.nxtdeal.app',
    'https://app.nxtdeal.app',
]
LEGACY_HUB_ORIGIN_REGEX = None  # Legacy web origins are retired; use the explicit NXTDeal allowlist.
