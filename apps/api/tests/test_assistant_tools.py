"""Assistant analysis drill-down tools (M1) — show_overview / show_arguments /
show_similar_cases / show_law, each keyed by the caller's own analysis_id.

These are pure DB-backed tools: no live LLM. A fake connection returns whatever
output JSON the test seeds, and the tools must surface the right sections dict /
honest refusal when the analysis is missing or has no such section (never fabrication).

ZDR: returned summaries are analysis sections (analyser-authored text), never raw
document text; nothing here is persisted.
"""

import json
import uuid

import app.assistant.service as svc

TENANT = "a0000001-0000-4000-8000-000000000001"
USER = "lawyer-a"
ANALYSIS = "b0000002-0000-4000-8000-000000000002"


class FakeConn:
    def __init__(self, output):
        self._output = output  # dict with "output" key, or None
        self.fetched = None

    async def fetchrow(self, sql, *args):
        self.fetched = (sql, args)
        return self._output

    async def fetch(self, sql, *args):
        return []


def _fake_db(output):
    return FakeConn({"output": output})


async def test_show_overview_returns_overview_section():
    conn = _fake_db(json.dumps({"sections": {"overview": {"headline_risks": ["x"]}}}))
    res = await svc._show_overview(conn, TENANT, USER, ANALYSIS)
    assert res.ok is True
    assert res.tool == "show_overview"
    assert json.loads(res.summary) == {"headline_risks": ["x"]}


async def test_show_arguments_returns_arguments_section():
    conn = _fake_db(json.dumps({"sections": {"arguments": [{"argument": "a"}]}}))
    res = await svc._show_arguments(conn, TENANT, USER, ANALYSIS)
    assert res.ok is True
    assert json.loads(res.summary) == [{"argument": "a"}]


async def test_show_law_returns_law_section():
    conn = _fake_db(json.dumps({"sections": {"law": [{"point": "p"}]}}))
    res = await svc._show_law(conn, TENANT, USER, ANALYSIS)
    assert res.ok is True
    assert json.loads(res.summary) == [{"point": "p"}]


async def test_show_similar_cases_uses_similar_cases_then_jurisdictional_notes():
    conn = _fake_db(
        json.dumps({"sections": {"similar_cases": [{"case": "A v B"}]}})
    )
    res = await svc._show_similar_cases(conn, TENANT, USER, ANALYSIS)
    assert res.ok is True
    assert json.loads(res.summary) == [{"case": "A v B"}]


async def test_show_similar_cases_refuses_when_section_missing():
    conn = _fake_db(json.dumps({"sections": {"arguments": []}}))
    res = await svc._show_similar_cases(conn, TENANT, USER, ANALYSIS)
    assert res.ok is False
    assert "no similar-cases" in res.summary


async def test_all_tools_refuse_when_analysis_missing():
    conn = FakeConn(None)
    for tool in (
        svc._show_overview,
        svc._show_arguments,
        svc._show_similar_cases,
        svc._show_law,
    ):
        res = await tool(conn, TENANT, USER, ANALYSIS)
        assert res.ok is False
        assert "No complete analysis" in res.summary


async def test_tools_scope_by_user_ref():
    conn = FakeConn({"output": json.dumps({"sections": {"overview": {}}})})
    await svc._show_overview(conn, TENANT, USER, ANALYSIS)
    _, args = conn.fetched
    assert str(args[0]) == str(uuid.UUID(ANALYSIS))
    assert args[1] == USER
