"""
═══════════════════════════════════════════════════════════════════
  Project Phoenix — In-Memory Store
  
  Drop-in replacement for Redis + SQS when running locally.
  In production, swap these for real Redis / SQS clients.
  
  This module provides three stores:
    1. OTP Store       — Stores generated OTP codes (TTL: 5 min)
    2. Draft Store     — Stores form drafts per email (TTL: 24h)
    3. Idempotency Store — Caches submit responses (TTL: 1h)
    4. Submission Queue  — Simulates SQS (in-memory list)
    5. Rate Limit Store  — Tracks request counts per IP
═══════════════════════════════════════════════════════════════════
"""

import time
import threading
from typing import Any, Optional
from collections import defaultdict

from app.config import settings


class TTLStore:
    """
    Thread-safe key-value store with per-key TTL expiry.
    Acts as a lightweight Redis replacement for development.
    """

    def __init__(self):
        self._data: dict[str, tuple[Any, float]] = {}  # key -> (value, expires_at)
        self._lock = threading.Lock()

    def set(self, key: str, value: Any, ttl: int) -> None:
        """Store a value with TTL in seconds."""
        with self._lock:
            self._data[key] = (value, time.time() + ttl)

    def get(self, key: str) -> Optional[Any]:
        """Get value if key exists and hasn't expired."""
        with self._lock:
            if key not in self._data:
                return None
            value, expires_at = self._data[key]
            if time.time() > expires_at:
                del self._data[key]
                return None
            return value

    def delete(self, key: str) -> None:
        """Remove a key."""
        with self._lock:
            self._data.pop(key, None)

    def exists(self, key: str) -> bool:
        """Check if key exists and hasn't expired."""
        return self.get(key) is not None


class RateLimiter:
    """
    Sliding-window rate limiter per client IP.
    Tracks request timestamps and enforces limits.
    """

    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def is_allowed(self, client_id: str) -> bool:
        """Check if the client is within rate limits. Returns True if allowed."""
        now = time.time()
        cutoff = now - self.window_seconds

        with self._lock:
            # Remove expired timestamps
            self._requests[client_id] = [
                ts for ts in self._requests[client_id] if ts > cutoff
            ]

            if len(self._requests[client_id]) >= self.max_requests:
                return False

            self._requests[client_id].append(now)
            return True

    def remaining(self, client_id: str) -> int:
        """How many requests the client has left in the current window."""
        now = time.time()
        cutoff = now - self.window_seconds

        with self._lock:
            self._requests[client_id] = [
                ts for ts in self._requests[client_id] if ts > cutoff
            ]
            return max(0, self.max_requests - len(self._requests[client_id]))


class SubmissionQueue:
    """
    In-memory submission queue simulating AWS SQS.
    In production, this gets replaced with boto3 SQS calls.
    """

    def __init__(self):
        self._queue: list[dict] = []
        self._lock = threading.Lock()

    def enqueue(self, submission: dict) -> None:
        """Add a submission to the queue."""
        with self._lock:
            self._queue.append(submission)

    def dequeue(self) -> Optional[dict]:
        """Pop the oldest submission (FIFO)."""
        with self._lock:
            return self._queue.pop(0) if self._queue else None

    @property
    def depth(self) -> int:
        """Current queue depth (for monitoring)."""
        with self._lock:
            return len(self._queue)


# ── Singleton Instances ──
# These are used across all route handlers

otp_store = TTLStore()                   # key: "otp:{email}" -> otp_code
draft_store = TTLStore()                 # key: "draft:{email}" -> draft_data
idempotency_store = TTLStore()           # key: "idem:{key}" -> response_dict
submission_queue = SubmissionQueue()      # Simulated SQS

rate_limiter = RateLimiter(
    max_requests=settings.RATE_LIMIT_REQUESTS,
    window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
)
