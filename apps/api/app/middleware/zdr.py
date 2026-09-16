"""ZDR enforcement + log redaction (Phase 1 1.3, HANDOFF.md 2.1).

Zero Data Retention discipline: no raw document text, prompt bodies, or LLM
request/response payloads may appear in ANY log line. Structlog is wired with
the ZDRFilter processor, which redacts sensitive keys anywhere in the event
dict — top level or nested — before rendering.

What MAY be logged: metadata (ids, counts, scores, latency), generated
outputs by reference, and citation objects. What is NEVER logged: source
document text, full prompt bodies, raw LLM request payloads.
"""

from collections.abc import MutableMapping
from typing import Any

import structlog

REDACTED = "[REDACTED:ZDR]"

# Keys whose values must never reach a log sink (case-insensitive, matched on
# the exact field name). Extending this set is safe; shrinking it is a
# security review event.
DEFAULT_REDACT_KEYS: frozenset[str] = frozenset(
    {
        "prompt",
        "prompts",
        "system_prompt",
        "messages",
        "document_text",
        "chunk_text",
        "raw_text",
        "prompt_body",
        "llm_payload",
        "llm_request",
        "llm_response",
        "completion",
        "embeddings_input",
    }
)


class ZDRFilter:
    """Structlog processor that redacts ZDR-protected fields.

    Applied recursively to the event dict so nested payloads (e.g. an
    embedded request object) cannot leak prompt bodies or document text.
    """

    def __init__(self, redact_keys: frozenset[str] = DEFAULT_REDACT_KEYS) -> None:
        self._keys = {k.lower() for k in redact_keys}

    def __call__(
        self, logger: Any, method_name: str, event_dict: MutableMapping[str, Any]
    ) -> MutableMapping[str, Any]:
        return self._redact(event_dict)  # type: ignore[return-value]

    def _redact(self, node: Any) -> Any:
        if isinstance(node, MutableMapping):
            for key in list(node.keys()):
                if isinstance(key, str) and key.lower() in self._keys:
                    node[key] = REDACTED
                else:
                    node[key] = self._redact(node[key])
            return node
        if isinstance(node, (list, tuple)):
            redacted = [self._redact(item) for item in node]
            return type(node)(redacted)
        return node


def configure_logging(log_level: str = "INFO") -> None:
    """Configure structlog with the mandatory ZDR redaction filter.

    Every structlog logger in the process inherits this chain; there is no
    supported way to obtain an unfiltered logger from app code.
    """
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            ZDRFilter(),  # non-negotiable: HANDOFF.md 2.1
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            structlog.processors.NAME_TO_LEVEL[log_level.lower()]
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> Any:
    """Return a ZDR-filtered structlog logger."""
    return structlog.get_logger(name)
