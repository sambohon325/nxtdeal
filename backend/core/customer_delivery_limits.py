"""Bounded, process-local verification-send budget across customer accounts.

This reduces same-process recipient flooding and provider spend. It is not a
distributed limit: restart clears it and each worker has its own budget. Provider
and ingress limits must still be configured before customer access is launched.
"""
from collections import deque
import hashlib
import hmac
import secrets
import threading
import time


class DeliveryBudget:
    def __init__(self):
        self._events = deque()
        self._key = secrets.token_bytes(32)
        self._lock = threading.Lock()

    def reserve(self, channel, recipient):
        """Allow at most 3/15min per contact and 60/min across all contacts.

        Reserve before persistence/provider I/O; failed or uncertain sends retain
        their reservation. No raw recipient, account ID or code is retained.
        """
        digest = hmac.new(self._key, (channel + ':' + recipient).encode('utf-8'),
                          hashlib.sha256).digest()
        with self._lock:
            now = time.monotonic()
            while self._events and self._events[0][0] <= now - 900:
                self._events.popleft()
            if sum(at > now - 60 for at, _ in self._events) >= 60:
                return False
            if sum(key == digest for _, key in self._events) >= 3:
                return False
            self._events.append((now, digest))
            return True


delivery_budget = DeliveryBudget()
