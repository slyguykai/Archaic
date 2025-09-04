"""
Global rate limiter with token-bucket semantics and jitter.

Used to keep average request rate respectful even with limited concurrency.
"""

from __future__ import annotations

import threading
import time
import random


class TokenBucket:
    def __init__(self, rate_per_sec: float = 0.66, burst: int = 1, jitter_ms: int = 300):
        """
        Args:
            rate_per_sec: average tokens per second (e.g., 0.66 ≈ 1 token/1.5s)
            burst: bucket capacity
            jitter_ms: random jitter added after acquire to avoid lockstep
        """
        self.rate = rate_per_sec
        self.capacity = burst
        self.tokens = burst
        self.last = time.monotonic()
        self.lock = threading.Lock()
        self.jitter_ms = jitter_ms

    def acquire(self):
        while True:
            with self.lock:
                now = time.monotonic()
                elapsed = now - self.last
                # Refill
                self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
                if self.tokens >= 1:
                    self.tokens -= 1
                    self.last = now
                    break
                # Compute wait for next token
                needed = 1 - self.tokens
                wait = max(needed / self.rate, 0.01)
            time.sleep(wait)

        # Apply small jitter outside lock
        if self.jitter_ms > 0:
            time.sleep(random.uniform(0, self.jitter_ms) / 1000.0)

