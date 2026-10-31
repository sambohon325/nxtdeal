"""Defer optional provider construction until an already-gated AI call uses it.

Missing credentials must not prevent non-AI application routes from importing.
Existing feature gates and exception/fallback handling remain at each call site.
This does not enable AI, choose credentials, or change billing/provider settings.
"""
import threading

from openai import OpenAI


class LazyOpenAI:
    def __init__(self, **options):
        self._options = options
        self._client = None
        self._lock = threading.Lock()

    def __getattr__(self, name):
        with self._lock:
            if self._client is None:
                # Constructor errors reach the caller's existing fallback. Do not
                # cache failed construction or manufacture a dummy credential.
                self._client = OpenAI(**self._options)
            client = self._client
        return getattr(client, name)
