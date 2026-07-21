import time
from threading import Lock


class FixedWindowRateLimiter:
    """In-memory fixed-window rate limiter.

    Suitable for the single-process MVP deployment (docs/12 §4); replace with a
    shared store (e.g. Redis) if the API is ever scaled to multiple processes.
    """

    _MAX_TRACKED_KEYS = 10_000

    def __init__(self, max_attempts: int, window_seconds: int) -> None:
        self._max_attempts = max_attempts
        self._window_seconds = window_seconds
        self._attempts: dict[str, tuple[int, float]] = {}
        self._lock = Lock()

    def is_allowed(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            if len(self._attempts) > self._MAX_TRACKED_KEYS:
                self._purge_expired(now)

            count, window_start = self._attempts.get(key, (0, now))
            if now - window_start >= self._window_seconds:
                count, window_start = 0, now

            count += 1
            self._attempts[key] = (count, window_start)
            return count <= self._max_attempts

    def _purge_expired(self, now: float) -> None:
        self._attempts = {
            key: value
            for key, value in self._attempts.items()
            if now - value[1] < self._window_seconds
        }


login_rate_limiter = FixedWindowRateLimiter(max_attempts=5, window_seconds=60)
booking_rate_limiter = FixedWindowRateLimiter(max_attempts=10, window_seconds=60)
# Patient phone OTP: cap requests so a phone can't be spammed with codes.
otp_request_rate_limiter = FixedWindowRateLimiter(max_attempts=5, window_seconds=300)
patient_login_rate_limiter = FixedWindowRateLimiter(max_attempts=5, window_seconds=60)
