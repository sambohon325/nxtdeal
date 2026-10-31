"""Bounded, process-local admission for the opt-in kiosk HTTP surface."""
from collections import Counter, deque
import threading
import time


class KioskRequestLimit:
    WINDOW_SECONDS = 60
    PER_PEER = 60
    TOTAL = 600

    def __init__(self):
        self._requests = deque()
        self._peers = Counter()
        self._lock = threading.Lock()

    def allow(self, peer):
        # Use ASGI transport peer, never request-supplied forwarding headers.
        # Missing transport identity deliberately shares one bucket.
        peer = peer or 'unknown'
        with self._lock:
            now = time.monotonic()
            while self._requests and self._requests[0][0] <= now - self.WINDOW_SECONDS:
                _, expired = self._requests.popleft()
                self._peers[expired] -= 1
                if not self._peers[expired]:
                    del self._peers[expired]
            if len(self._requests) >= self.TOTAL or self._peers[peer] >= self.PER_PEER:
                return False
            self._requests.append((now, peer))
            self._peers[peer] += 1
            return True
