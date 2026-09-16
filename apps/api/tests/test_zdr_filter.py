"""ZDR redaction filter unit tests — Task 1.1 DoD (HANDOFF.md 4, Phase1 1.3).

Zero Data Retention discipline: no raw document text, prompt bodies, or LLM
request/response payloads may appear in ANY log line. These tests pin that
contract at the processor and the fully-configured logging pipeline level.
"""

import json
import logging

import pytest
import structlog

from app.middleware.zdr import DEFAULT_REDACT_KEYS, REDACTED, ZDRFilter, configure_logging


def _filter() -> ZDRFilter:
    return ZDRFilter()


class TestZDRFilterProcessor:
    def test_top_level_sensitive_keys_redacted(self) -> None:
        ev = _filter()(None, "info", {"prompt": "SECRET", "event": "x"})
        assert ev["prompt"] == REDACTED

    def test_nested_dicts_redacted_recursively(self) -> None:
        ev = _filter()(
            None,
            "info",
            {"outer": {"inner": {"messages": [{"role": "user", "content": "S"}]}}},
        )
        assert ev["outer"]["inner"]["messages"] == REDACTED

    def test_sensitive_keys_inside_lists_of_dicts_redacted(self) -> None:
        ev = _filter()(None, "info", {"items": [{"document_text": "S"}, {"ok": 1}]})
        assert ev["items"][0]["document_text"] == REDACTED
        assert ev["items"][1]["ok"] == 1

    def test_key_matching_is_case_insensitive(self) -> None:
        ev = _filter()(None, "info", {"PROMPT": "S", "Messages": "S", "Llm_Response": "S"})
        assert ev["PROMPT"] == REDACTED
        assert ev["Messages"] == REDACTED
        assert ev["Llm_Response"] == REDACTED

    def test_unrelated_keys_and_values_preserved(self) -> None:
        ev = _filter()(None, "info", {"event": "retrieve", "score": 0.91, "doc_id": "d1"})
        assert ev == {"event": "retrieve", "score": 0.91, "doc_id": "d1"}

    def test_safe_value_that_mentions_prompt_key_name_is_untouched(self) -> None:
        # Values are never scanned — only field names trigger redaction.
        ev = _filter()(None, "info", {"note": "the prompt was fine"})
        assert ev["note"] == "the prompt was fine"

    def test_default_key_set_covers_prompt_messages_document_text(self) -> None:
        for key in ("prompt", "messages", "document_text", "llm_request"):
            assert key in DEFAULT_REDACT_KEYS


class TestConfiguredPipeline:
    def test_secret_values_never_reach_rendered_log_line(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        configure_logging("INFO")
        log = structlog.get_logger("test.pipeline")
        secret = "RAW-DOCUMENT-TEXT-THAT-MUST-NEVER-LEAK"  # noqa: S105 (test fixture)
        log.info(
            "retrieval",
            prompt=secret,
            document_text=secret,
            llm_payload={"messages": [{"role": "user", "content": secret}]},
            tenant_id="aetoes",
            score=0.88,
        )
        rendered = capsys.readouterr().out
        assert secret not in rendered
        assert REDACTED in rendered
        record = json.loads(rendered.strip().splitlines()[-1])
        assert record["tenant_id"] == "aetoes"
        assert record["score"] == 0.88

    def test_structlog_uses_stdlib_levels(self) -> None:
        # Regression: structlog.processors.NAME_TO_LEVEL must resolve levels.
        configure_logging("DEBUG")
        assert structlog.get_logger("test.levels").is_enabled_for(logging.DEBUG)
