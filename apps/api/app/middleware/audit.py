"""Audit writer stub — full implementation lands with Task 1.5 (Phase 1 3.4).

Contract (HANDOFF.md 2.3): every query, upload, and Slack event is written
to `query_audit`; the DB role has UPDATE/DELETE revoked; an audit write
failure must HALT LLM responses. Nothing here may bypass that invariant.
"""
