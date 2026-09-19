"""Vault A envelope crypto — per-document DEK, KMS-style wrapping interface.

Phase 2 Task 2.2 per docs/RedCase-Phase2-Design.md 1.2 (encryption model,
corrected-in-implementation note): each Vault A document gets a unique
256-bit DEK; the DEK is wrapped by a tenant master key; chunk text for
classification_level >= 'CONFIDENTIAL' is AES-256-GCM encrypted at the
application layer before storage, and decrypted on retrieve by workers
holding the unwrapped DEK.

KeyProvider is the wrapping interface. Two implementations:
  * KMSKeyProvider  — AWS KMS-shaped production interface (wired at the
                      production deploy task; constructing one today
                      raises, so a misconfigured prod cannot silently
                      fall back to the local key).
  * LocalKeyProvider — dev fallback: master key from VAULT_A_MASTER_KEY
                      (64-char hex). Wrapping is AES-256-GCM under the
                      master key with the document id as associated data.

Storage format (chunk_text column): ``enc:v1:<base64(nonce ‖ ciphertext)>``
— self-describing, so decrypt-on-retrieve needs no extra column. Tamper
evidence: encrypted_content_hash is HMAC-SHA256 over the document's
ciphertext set, keyed by an HKDF-derived key (info=b"redcase-content-hmac")
that never touches the wrapping path.

KNOWN LIMITATION (recorded, not silently accepted): the Phase 1 fts
generated column indexes chunk_text as stored — ciphertext for CONF+
chunks produces garbage tokens, so Vault A full-text search over encrypted
chunks is meaningless until the Phase 2 router task moves indexing to a
decrypt-then-index worker. Embeddings likewise use plaintext in the
worker (design: "only retrieval workers holding the unwrapped DEK can
embed or serve it"). ZDR: plaintext never logged; ciphertext is not
sensitive (key separation) but is still not logged either way.

ZDR + HANDOFF.md 3: the master key arrives via env (SecretStr) and is
never rendered in logs or reprs.
"""

import base64
import hashlib
import hmac
import secrets
from typing import Protocol

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf import hkdf

from app.config import Settings

DEK_BYTES = 32
PREFIX = "enc:v1:"
CLASSIFICATIONS_ENCRYPTED = ("CONFIDENTIAL", "PARTNER_RESTRICTED")


def generate_dek() -> bytes:
    """A fresh 256-bit data-encryption key for one document."""
    return secrets.token_bytes(DEK_BYTES)


def _b64e(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _b64d(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"))


class KeyProvider(Protocol):
    """KMS-style wrapping interface: wrap/unwrap a document DEK.

    ``aad`` is the document id (bytes) — binding the wrapped DEK to its
    document so a wrapped key lifted from one row cannot be replayed
    against another.
    """

    def wrap(self, dek: bytes, aad: bytes) -> bytes: ...
    def unwrap(self, wrapped: bytes, aad: bytes) -> bytes: ...
    def content_hash(self, ciphertext: bytes) -> str: ...


class LocalKeyProvider:
    """Dev key provider: AES-256-GCM wrapping under a local master key.

    NOT for production — the production provider is KMS-backed
    (KMSKeyProvider). The derived HMAC subkey is separate from the
    wrapping key material via HKDF domain separation.
    """

    def __init__(self, master_key: bytes) -> None:
        if len(master_key) != DEK_BYTES:
            raise ValueError(
                f"Vault A master key must be {DEK_BYTES} bytes, got {len(master_key)}"
            )
        self._aead = AESGCM(master_key)
        self._hmac_key = hkdf.HKDF(
            hashes.SHA256(), DEK_BYTES, None, b"redcase-content-hmac"
        ).derive(master_key)

    def wrap(self, dek: bytes, aad: bytes) -> bytes:
        nonce = secrets.token_bytes(12)
        return nonce + self._aead.encrypt(nonce, dek, aad)

    def unwrap(self, wrapped: bytes, aad: bytes) -> bytes:
        nonce, ciphertext = wrapped[:12], wrapped[12:]
        return self._aead.decrypt(nonce, ciphertext, aad)

    def content_hash(self, ciphertext: bytes) -> str:
        return hmac.new(self._hmac_key, ciphertext, hashlib.sha256).hexdigest()


class KMSKeyProvider:
    """Production interface shape (AWS KMS). Wired at the deploy task.

    Deliberately fails closed: constructing one before the KMS wiring
    exists is a configuration error, not a fallback opportunity.
    """

    def __init__(self, *_args, **_kwargs) -> None:
        raise NotImplementedError(
            "KMSKeyProvider is the production wrapping backend and is wired "
            "at the deploy task (GCP KMS / AWS KMS + Secret Manager). Use "
            "vault_a_key_provider=local with VAULT_A_MASTER_KEY for dev."
        )


def make_key_provider(settings: Settings) -> KeyProvider:
    """Resolve the wrapping key provider from configuration.

    local (default for dev): requires VAULT_A_MASTER_KEY (64-char hex).
    kms: production; raises until the KMS wiring lands.
    """
    kind = settings.vault_a_key_provider.lower()
    if kind == "kms":
        return KMSKeyProvider()
    if kind == "local":
        raw = settings.vault_a_master_key
        if raw is None:
            raise RuntimeError(
                "vault_a_key_provider=local requires VAULT_A_MASTER_KEY "
                "(64-char hex, dev fallback) — never commit it (HANDOFF.md 3)."
            )
        return LocalKeyProvider(bytes.fromhex(raw.get_secret_value()))
    raise ValueError(f"unknown vault_a_key_provider: {settings.vault_a_key_provider!r}")


def encrypt_chunk_text(dek: bytes, plaintext: str, aad: bytes) -> str:
    """AES-256-GCM encrypt chunk text -> enc:v1 storage form."""
    nonce = secrets.token_bytes(12)
    ct = AESGCM(dek).encrypt(nonce, plaintext.encode("utf-8"), aad)
    return PREFIX + _b64e(nonce + ct)


def decrypt_chunk_text(dek: bytes, stored: str, aad: bytes) -> str:
    """Decrypt an enc:v1 value; raises InvalidTag on tamper/wrong key.

    Values without the prefix are returned as-is (FIRM_INTERNAL and
    Vault B chunks are stored in plaintext, by design).
    """
    if not stored.startswith(PREFIX):
        return stored
    nonce_ct = _b64d(stored[len(PREFIX):])
    nonce, ct = nonce_ct[:12], nonce_ct[12:]
    return AESGCM(dek).decrypt(nonce, ct, aad).decode("utf-8")


def needs_encryption(classification_level: str) -> bool:
    """classification_level >= 'CONFIDENTIAL' per the design's model."""
    return classification_level in CLASSIFICATIONS_ENCRYPTED


__all__ = [
    "CLASSIFICATIONS_ENCRYPTED",
    "DEK_BYTES",
    "KMSKeyProvider",
    "KeyProvider",
    "LocalKeyProvider",
    "decrypt_chunk_text",
    "encrypt_chunk_text",
    "generate_dek",
    "make_key_provider",
    "needs_encryption",
]

# Re-exported for callers that want to catch tamper failures without
# importing cryptography directly.
TamperError = InvalidTag
