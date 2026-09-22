"""Shared onboarding domain logic — Part 2 (HANDOFF §4 growth surface).

Homed here so the signup router, invite router, and their tests cannot drift:

* ``ROLE_TO_CLEARANCE`` — the firm-facing invite role -> RLS clearance ladder
  mapping. The ladder clearances that exist in the schema are STAFF | SENIOR |
  PARTNER | ADMIN (migration 0009). There is no ASSOCIATE clearance, so a firm
  inviting an Associate is provisioned at STAFF — the floor, never the ceiling.
  One mapping error here hands a non-partner employee partner-grade RLS vision
  (CONFIDENTIAL documents), which is the Part 2 DoD lynchpin.
* ``normalize_email`` — case/whitespace normalization, the key the unique index and
  the rate limiter both use, so ``A@B.com`` and ``A@b.com`` are the same
  signup.
* ``hash_verify_token`` — only the SHA-256 digest of the email-verification token
  is ever stored; a DB leak yields no usable token.

ZDR: emails are PII — never logged. The provisioned signup_audit rows carry ids,
slugs, and step names only.
"""

import hashlib
import hmac
import re
import secrets

from app.middleware.zdr import get_logger

log = get_logger("redcase.onboarding")

# Firm-facing invite role -> RLS clearance ladder value (invitee's Supabase claim).
ROLE_TO_CLEARANCE: dict[str, str] = {
    "PARTNER": "PARTNER",
    "SENIOR": "SENIOR",
    "ASSOCIATE": "STAFF",  # no ASSOCIATE clearance exists -> floor, not ceiling
    "STAFF": "STAFF",
}

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(email: str) -> str:
    """Lowercase + strip whitespace. Single canonical form for dedupe + rate limit."""
    return email.strip().lower()


def valid_email(email: str) -> bool:
    return EMAIL_RE.match(email) is not None


def clearance_for_role(role: str) -> str:
    """RLS clearance an invited user with this firm role receives (fail-closed)."""
    clearance = ROLE_TO_CLEARANCE.get(role)
    if clearance is None:
        raise ValueError(f"unknown invite role: {role!r}")
    return clearance


def new_verify_token() -> str:
    """Cryptographically random, URL-safe verification token (32 raw bytes => 43 chars)."""
    return secrets.token_urlsafe(32)


def hash_verify_token(token: str) -> str:
    """Subkeyed SHA-256 digest of the token for storage/comparison.

    ``hmac`` with a fixed tag avoids length-extension on a bare hash and keeps the
    comparison a hash of a token (never reversible to the token). Constant-time
    comparison is the caller's job (hmac.compare_digest)."""
    return hmac.new(b"redcase-verify", token.encode(), hashlib.sha256).hexdigest()
