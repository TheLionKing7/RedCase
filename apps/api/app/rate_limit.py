"""Process-local sliding-window rate limiter for the public signup path.

HANDOFF §4 / Part 2 DoD: ``POST /v1/public/signup`` is the system's first
UNAUTHENTICATED write path, so bot-driven tenant creation must be throttled per IP
and per normalized email. This is a single-process, in-memory sliding window with no
Redis dependency (none is in pyproject).

Production caveat (recorded): a multi-replica deployment relies on Cloudflare's
edge rate-limiting on top of this per-instance window; this module guards the
single FastAPI process. The window is monotonic-clock based so a moved clock cannot
freeze or burst the window, and entries are pruned lazily to bound memory.

Every rejection is logged via the ZDR logger with ids/timestamps only (no email
content) so abuse signals surface without leaking PII.
"""

import time
from collections import defaultdict, deque
from threading import Lock

from app.middleware.zdr import get_logger

log = get_logger("redcase.rate_limit")


class SlidingWindowLimiter:
    """Fixed-window-count sliding limiter keyed by arbitrary strings.

    ``_events[key]`` is a deque of (monotonic_seconds) hits within the window;
    a hit at time T is allowed iff the count of entries with t > T - window is
    below ``limit``. Expired entries are pruned from the deque head.
    """

    def __init__(self, limit: int, window_s: int) -> None:
        self.limit = limit
        self.window_s = float(window_s)
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key: str) -> bool:
        """Record a hit for ``key``; return True if it fits under the limit."""
        now = time.monotonic()
        cutoff = now - self.window_s
        with self._lock:
            q = self._events[key]
            while q and q[0] <= cutoff:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            return True


class PublicSignupLimiter:
    """Composite limiter for the signup/verify endpoints (per IP + per email)."""

    def __init__(
        self,
        *,
        ip_limit: int,
        email_limit: int,
        window_s: int,
        verify_ip_limit: int,
    ) -> None:
        self.signup_ip = SlidingWindowLimiter(ip_limit, window_s)
        self.signup_email = SlidingWindowLimiter(email_limit, window_s)
        self.verify_ip = SlidingWindowLimiter(verify_ip_limit, window_s)

    def allow_signup(self, ip: str, email: str) -> bool:
        ok_ip = self.signup_ip.allow(ip)
        if not ok_ip:
            log.warning("signup_rate_limited", key="ip")
        ok_email = self.signup_email.allow(email)
        if not ok_email:
            log.warning("signup_rate_limited", key="email")
        return ok_ip and ok_email

    def allow_verify(self, ip: str) -> bool:
        if not self.verify_ip.allow(ip):
            log.warning("verify_rate_limited", key="ip")
            return False
        return True


def client_ip(request) -> str:
    """Best-effort client address from the request (Cloudflare sets X-Forwarded-For).

    Returns a stable string for rate-limit bucketing. Never the raw header alone in
    trust-inferred code — production keeps this behind Cloudflare's trusted proxy.
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client else "unknown"


class InviteAcceptLimiter:
    """Composite limiter for the UNAUTHENTICATED invitee bootstrap path.

    ``POST /v1/invites/accept`` is an unauthenticated write, so it is throttled
    per IP (no auth to identify the caller) AND per invite token (a brute-forced
    link is shut down after a handful of guesses). Shares the same process-local
    sliding-window + Cloudflare-edge caveat as the signup limiter.
    """

    def __init__(
        self,
        *,
        ip_limit: int,
        token_limit: int,
        window_s: int,
    ) -> None:
        self.accept_ip = SlidingWindowLimiter(ip_limit, window_s)
        self.accept_token = SlidingWindowLimiter(token_limit, window_s)

    def allow_accept(self, ip: str, token_hash: str) -> bool:
        ok_ip = self.accept_ip.allow(ip)
        if not ok_ip:
            log.warning("invite_accept_rate_limited", key="ip")
        ok_token = self.accept_token.allow(token_hash)
        if not ok_token:
            log.warning("invite_accept_rate_limited", key="token")
        return ok_ip and ok_token
