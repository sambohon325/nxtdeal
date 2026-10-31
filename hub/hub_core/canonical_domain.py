"""Translate verified retired API hosts without changing persisted tenant records."""
from urllib.parse import urlsplit, urlunsplit


def canonical_api_url(value):
    url = urlsplit(value)
    replacements = {
        "dealer1-api.dealeros.xyz": "api.nxtdeal.app",
        "hub-api.dealeros.xyz": "hub-api.nxtdeal.app",
    }
    if url.hostname in replacements:
        return urlunsplit(("https", replacements[url.hostname], url.path, url.query, url.fragment)).rstrip("/")
    if url.hostname == "dealeros.xyz" or (url.hostname or "").endswith(".dealeros.xyz"):
        raise ValueError("This dealership needs its NXTDeal API address configured.")
    return value.rstrip("/")
