"""Explicit browser origins for the dealer API during the NXTDeal domain move."""

DEALER_WEB_ORIGINS = [
    'http://localhost:3000',
    'http://127.0.0.1:3000',
    'http://localhost:5173',
    'http://127.0.0.1:5173',
    'https://nxtdeal.app',
    'https://www.nxtdeal.app',
    'https://app.nxtdeal.app',
    'https://apps.nxtdeal.app',
]
LEGACY_DEALER_ORIGIN_REGEX = None  # Legacy web origins are retired; use the explicit NXTDeal allowlist.
