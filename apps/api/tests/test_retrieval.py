"""Retrieval + grounding pipeline tests — Tasks 1.4/1.5 synthetic DoD.

All model clients are fakes (deterministic, no network, no secrets):
  * ``ConstantEmbedder([0.5]*3072)`` — cosine similarity 1.0 against any
    positive-constant stored vector, so the 0.78 gate always passes when
    embeddings exist.
  * ``FarEmbedder([-1.0]*3072)`` — cosine -1.0, so the gate always fails
    (threshold-refusal path).
  * ``GoodLLM`` — cites the first doc_id it sees in the <passages> block
    (grounded behaviour), counting calls and recording system prompts so the
    one-regeneration contract (REGENERATION_SUFFIX on retry, cap at 2 calls)
    is asserted exactly.
  * ``FabricatingLLM`` — always cites a foreign doc_id, forcing the §3.4
    integrity-refusal path.

Corpus-dependent DoD items (VECTOR_GATE calibration, 50-question battery)
stay deferred-pending-credentials per owner instruction; they live in
test_citation_battery.py and pytest.skip when unprovisioned.
"""

import asyncio
import hashlib
import json
import re
import uuid

import asyncpg
import pytest
from conftest import SEED_TENANT_AETOES

import app.retrieval.service as service_module
from app.config import Settings
from app.ingestion.db import EMBEDDING_DIMS, ingest_pdf
from app.retrieval.service import (
    CitationIntegrityError,
    RetrievalService,
    answer_question,
    verify_citations,
)
from tests.pdf_factory import make_pdf, synthetic_judgment_pages

VAULT_JURIS_NG = uuid.UUID("b0000001-0000-4000-8000-000000000001")
FOREIGN_DOC_ID = "00000000-0000-0000-0000-000000000000"


class ConstantEmbedder:
    """Deterministic 3072-dim embeddings — cosine 1.0 vs any positive constant."""

    def __init__(self, value: float = 0.5) -> None:
        self.value = value

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[self.value] * EMBEDDING_DIMS for _ in texts]


class FarEmbedder(ConstantEmbedder):
    def __init__(self) -> None:
        super().__init__(-1.0)


class GoodLLM:
    """Grounded: cites the first doc_id from the passages block it is given."""

    def __init__(self) -> None:
        self.calls = 0
        self.systems: list[str] = []

    async def answer(self, system: str, user: str) -> str:
        self.calls += 1
        self.systems.append(system)
        m = re.search(r'<passage doc_id="([^"]+)"', user)
        assert m, "GoodLLM requires a passages block with doc_id pins"
        return (
            "Per the retrieved passage, the holding is settled. "
            f'<citations>doc_id="{m.group(1)}"</citations>'
        )


class FabricatingLLM:
    """Always cites a doc_id that was never retrieved."""

    def __init__(self) -> None:
        self.calls = 0
        self.systems: list[str] = []

    async def answer(self, system: str, user: str) -> str:
        self.calls += 1
        self.systems.append(system)
        return (
            "The court unquestionably held so. "
            f'<citations>doc_id="{FOREIGN_DOC_ID}"</citations>'
        )


async def connect_scoped(app_db_url: str) -> asyncpg.Connection:
    """App-role connection with the tenant GUC set session-wide.

    The real flow sets app.tenant_id inside a transaction in the auth
    dependency; tests that call answer_question/retrieve directly set it at
    session level so RLS policies (documents, chunks, and query_audit after
    migration 0002) resolve instead of failing closed."""
    conn = await asyncpg.connect(app_db_url)
    await conn.execute(
        "SELECT set_config('app.tenant_id', $1, false)", SEED_TENANT_AETOES
    )
    return conn


async def _ingest_doc(app_db_url: str, tmp_path, *, embed: bool = True) -> tuple[uuid.UUID, str]:
    """Ingest one synthetic judgment; returns (document_id, unique citation)."""
    n = int(uuid.uuid4().hex[:6], 16)
    citation = f"(2003) {1 + n % 9} NWLR (Pt. {150 + n % 700}) {1 + n % 400}"
    pages = synthetic_judgment_pages()
    pages[0] = [citation if "NWLR CITATION" in line else line for line in pages[0]]
    pdf = make_pdf(tmp_path / f"retrieval-{n}.pdf", pages)
    conn = await asyncpg.connect(app_db_url)
    try:
        result = await ingest_pdf(
            conn,
            tenant_id=uuid.UUID(SEED_TENANT_AETOES),
            vault_id=VAULT_JURIS_NG,
            pdf_path=pdf,
            embedder=ConstantEmbedder() if embed else None,
        )
    finally:
        await conn.close()
    return result.document_id, citation


async def _audit_rows(conn: asyncpg.Connection, question_hash: str) -> list:
    async with conn.transaction():
        await conn.execute(
            "SELECT set_config('app.tenant_id', $1, true)", SEED_TENANT_AETOES
        )
        return await conn.fetch(
            "SELECT * FROM query_audit WHERE question_hash = $1 ORDER BY created_at",
            question_hash,
        )


def _qhash(question: str) -> str:
    return hashlib.sha256(question.encode()).hexdigest()


QUESTION = "What is the ratio on statutory interpretation of constitutional questions?"


@pytest.fixture
def question() -> str:
    """Unique question per test — the session DB is shared, and query_audit
    rows are keyed by question_hash, so audit-count assertions need isolation."""
    return f"{QUESTION} (case {uuid.uuid4().hex[:8]})"


class TestRetrieve:
    async def test_court_filter_scopes_results(
        self, app_db_url: str, tmp_path
    ) -> None:
        doc_a, _ = await _ingest_doc(app_db_url, tmp_path)
        doc_b, _ = await _ingest_doc(app_db_url, tmp_path)
        conn = await connect_scoped(app_db_url)
        try:
            async with conn.transaction():
                await conn.execute(
                    "SELECT set_config('app.tenant_id', $1, true)", SEED_TENANT_AETOES
                )
                await conn.execute(
                    "UPDATE documents SET court_level = 'COURT_OF_APPEAL' WHERE id = $1",
                    doc_b,
                )
            svc = RetrievalService(conn, SEED_TENANT_AETOES)
            qvec = (await ConstantEmbedder().embed([QUESTION]))[0]
            rows = await svc.retrieve(QUESTION, qvec, {"court_level": "COURT_OF_APPEAL"})
            assert rows is not None
            assert {r["document_id"] for r in rows} == {doc_b}
            assert all(r["court_level"] == "COURT_OF_APPEAL" for r in rows)
        finally:
            await conn.close()

    async def test_no_filter_returns_sc_rows(self, app_db_url: str, tmp_path) -> None:
        await _ingest_doc(app_db_url, tmp_path)
        conn = await connect_scoped(app_db_url)
        try:
            svc = RetrievalService(conn, SEED_TENANT_AETOES)
            qvec = (await ConstantEmbedder().embed([QUESTION]))[0]
            rows = await svc.retrieve(QUESTION, qvec, {})
            assert rows is not None and len(rows) >= 1
            # Every embedded doc in this session shares the constant-vector
            # direction, so all retrieved rows sit at the cosine gate's max.
            assert all(float(r["vsim"]) == pytest.approx(1.0) for r in rows)
        finally:
            await conn.close()


class TestAnswerQuestion:
    async def test_happy_path_answers_with_verified_citations(
        self, app_db_url: str, tmp_path, question: str
    ) -> None:
        await _ingest_doc(app_db_url, tmp_path)
        conn = await connect_scoped(app_db_url)
        llm = GoodLLM()
        try:
            result = await answer_question(
                question, {}, conn, SEED_TENANT_AETOES, "user-1",
                settings=Settings(_env_file=None),
                embedder=ConstantEmbedder(), llm=llm,
            )
            assert result["refusal"] is False
            assert "holding" in result["answer"]
            assert len(result["citations"]) == 1
            cite = result["citations"][0]
            # The session DB is shared: any embedded doc may win the (all-tie)
            # top-5, so assert the citation is consistent with the documents
            # row it cites — not that it is the doc this test ingested.
            doc = await conn.fetchrow(
                "SELECT citation, court_level, year FROM documents WHERE id = $1",
                uuid.UUID(cite["document_id"]),
            )
            assert doc["citation"] == cite["citation"]
            assert doc["court_level"] == cite["court_level"]
            assert doc["year"] == cite["year"]
            assert cite["verified"] is True
            assert 1 <= cite["page_start"] <= cite["page_end"] <= 3
            assert cite["source_pdf_url"]  # storage_public_url unset -> raw path
            assert llm.calls == 1  # no regeneration on a clean pass

            rows = await _audit_rows(conn, _qhash(question))
            assert len(rows) == 1  # exactly one audit row per query
            row = rows[0]
            assert row["user_ref"] == "user-1"
            assert row["threshold_passed"] is True
            assert row["answer_text"] == result["answer"]
            assert len(row["retrieved_chunk_ids"]) > 0
            assert all(float(s) == pytest.approx(1.0) for s in row["similarity_scores"])
            assert isinstance(row["latency_ms"], int) and row["latency_ms"] >= 0
        finally:
            await conn.close()

    async def test_out_of_scope_year_refuses_and_audits(
        self, app_db_url: str, tmp_path, question: str
    ) -> None:
        await _ingest_doc(app_db_url, tmp_path)
        conn = await connect_scoped(app_db_url)
        try:
            result = await answer_question(
                question, {"year_from": 1900, "year_to": 1900},
                conn, SEED_TENANT_AETOES, "user-1",
                settings=Settings(_env_file=None),
                embedder=ConstantEmbedder(), llm=GoodLLM(),
            )
            assert result["refusal"] is True
            assert result["citations"] == []
            rows = await _audit_rows(conn, _qhash(question))
            assert len(rows) == 1
            assert rows[0]["threshold_passed"] is False
            assert rows[0]["answer_text"] is None
        finally:
            await conn.close()

    async def test_null_embeddings_refuse_not_crash(
        self, app_db_url: str, tmp_path, question: str
    ) -> None:
        """Deferred-embed chunks (Task 1.3) have embedding NULL: 1-(NULL<=>q)
        is NULL and must be treated as a threshold failure, not a TypeError.

        The NULL doc is fenced under a unique court_level so the shared
        session corpus (other tests' embedded docs) cannot win retrieval —
        the query then sees ONLY NULL-embedding chunks."""
        doc_id, _ = await _ingest_doc(app_db_url, tmp_path, embed=False)
        conn = await connect_scoped(app_db_url)
        try:
            await conn.execute(
                "UPDATE documents SET court_level = 'NICN' WHERE id = $1", doc_id
            )
            result = await answer_question(
                question, {"court_level": "NICN"}, conn,
                SEED_TENANT_AETOES, "user-1",
                settings=Settings(_env_file=None),
                embedder=ConstantEmbedder(), llm=GoodLLM(),
            )
            assert result["refusal"] is True
            rows = await _audit_rows(conn, _qhash(question))
            assert len(rows) == 1
            assert rows[0]["threshold_passed"] is False
        finally:
            await conn.close()

    async def test_far_embedding_fails_threshold(
        self, app_db_url: str, tmp_path, question: str
    ) -> None:
        await _ingest_doc(app_db_url, tmp_path)
        conn = await connect_scoped(app_db_url)
        try:
            result = await answer_question(
                question, {}, conn, SEED_TENANT_AETOES, "user-1",
                settings=Settings(_env_file=None),
                embedder=FarEmbedder(), llm=GoodLLM(),
            )
            assert result["refusal"] is True
            rows = await _audit_rows(conn, _qhash(question))
            assert rows[0]["threshold_passed"] is False
        finally:
            await conn.close()

    async def test_fabricated_citation_regenerates_once_then_refuses(
        self, app_db_url: str, tmp_path, question: str
    ) -> None:
        await _ingest_doc(app_db_url, tmp_path)
        conn = await connect_scoped(app_db_url)
        llm = FabricatingLLM()
        try:
            result = await answer_question(
                question, {}, conn, SEED_TENANT_AETOES, "user-1",
                settings=Settings(_env_file=None),
                embedder=ConstantEmbedder(), llm=llm,
            )
            assert result["refusal"] is True
            assert result["citations"] == []
            assert llm.calls == 2  # §3.4: exactly one regeneration, then refuse
            from app.retrieval.prompts import REGENERATION_SUFFIX

            assert REGENERATION_SUFFIX not in llm.systems[0]
            assert REGENERATION_SUFFIX in llm.systems[1]

            rows = await _audit_rows(conn, _qhash(question))
            assert len(rows) == 1  # still exactly one audit row
            assert rows[0]["threshold_passed"] is True  # retrieval passed; LLM failed
            assert rows[0]["answer_text"] is None  # fabricated answer never persisted
            # jsonb comes back from asyncpg as text — decode before comparing.
            assert json.loads(rows[0]["citations"]) == []
        finally:
            await conn.close()

    async def test_audit_write_failure_halts(
        self, app_db_url: str, tmp_path, question: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """HANDOFF.md 2.3: an audit-write failure must HALT the response —
        the exception propagates out of answer_question (never swallowed)."""
        await _ingest_doc(app_db_url, tmp_path)

        async def boom(db, audit):  # noqa: ANN001
            raise RuntimeError("audit sink unavailable")

        monkeypatch.setattr(service_module, "write_audit", boom)
        conn = await connect_scoped(app_db_url)
        try:
            with pytest.raises(RuntimeError, match="audit sink"):
                await answer_question(
                    question, {}, conn, SEED_TENANT_AETOES, "user-1",
                    settings=Settings(_env_file=None),
                    embedder=ConstantEmbedder(), llm=GoodLLM(),
                )
        finally:
            await conn.close()

    async def test_answer_timeout_ceiling_refuses_and_audits_both_attempts(
        self, app_db_url: str, tmp_path, question: str
    ) -> None:
        """answer_timeout_s ceiling: an answer call that overruns is logged
        as a refusal for that attempt, the one-retry policy fires once, and
        BOTH attempts land in query_audit (append-only, insertion-ordered)."""

        class SlowLLM:
            def __init__(self) -> None:
                self.calls = 0

            async def answer(self, system: str, user: str) -> str:
                self.calls += 1
                await asyncio.sleep(30)
                return "never reached"

        await _ingest_doc(app_db_url, tmp_path)
        conn = await connect_scoped(app_db_url)
        llm = SlowLLM()
        try:
            result = await answer_question(
                question, {}, conn, SEED_TENANT_AETOES, "user-1",
                settings=Settings(_env_file=None, answer_timeout_s=0.1),
                embedder=ConstantEmbedder(), llm=llm,
            )
            assert result["refusal"] is True
            assert result["citations"] == []
            assert llm.calls == 2  # ceiling per attempt; retry policy applies
            rows = await _audit_rows(conn, _qhash(question))
            assert len(rows) == 2  # one append-only row per attempt
            assert all(r["threshold_passed"] is True for r in rows)
            assert all(r["answer_text"] is None for r in rows)
        finally:
            await conn.close()


class TestVerifyCitations:
    def _row(self, doc_id: str = "11111111-1111-4111-8111-111111111111") -> dict:
        return {
            "id": uuid.uuid4(),
            "document_id": uuid.UUID(doc_id),
            "chunk_text": "ratio text",
            "page_start": 2,
            "page_end": 2,
            "paragraph_refs": ["4"],
            "is_ratio": True,
            "vsim": 1.0,
            "case_title": "Adesina v. FRN",
            "citation": "(2008) 5 NWLR (Pt. 1080) 227",
            "court_level": "SUPREME_COURT",
            "year": 2008,
            "source_pdf_path": "pdfs/adesina.pdf",
        }

    def test_valid_citation_carries_page_pins(self) -> None:
        rows = [self._row()]
        doc = "11111111-1111-4111-8111-111111111111"
        answer = f'The court held so. <citations>doc_id="{doc}"</citations>'
        cites = verify_citations(answer, rows, storage_public_url="https://cdn.example")
        assert len(cites) == 1
        c = cites[0]
        assert c["page_start"] == 2 and c["page_end"] == 2
        assert c["paragraph_refs"] == ["4"]
        assert c["source_pdf_url"] == "https://cdn.example/pdfs/adesina.pdf"
        assert c["verified"] is True

    def test_foreign_doc_id_raises(self) -> None:
        rows = [self._row()]
        answer = f'<citations>doc_id="{FOREIGN_DOC_ID}"</citations>'
        with pytest.raises(CitationIntegrityError):
            verify_citations(answer, rows)

    def test_answer_without_citations_yields_empty(self) -> None:
        assert verify_citations("No binding precedent found in Vault B.", [self._row()]) == []


class TestPassages:
    def test_build_passages_pins_docs_pages_paras(self, app_db_url: str) -> None:
        rows = [
            {
                "document_id": uuid.UUID("11111111-1111-4111-8111-111111111111"),
                "chunk_text": "text one",
                "page_start": 1,
                "page_end": 2,
                "paragraph_refs": ["1", "2"],
                "is_ratio": False,
            },
            {
                "document_id": uuid.UUID("22222222-2222-4222-8222-222222222222"),
                "chunk_text": "ratio text",
                "page_start": 3,
                "page_end": 3,
                "paragraph_refs": ["4"],
                "is_ratio": True,
            },
        ]
        block = RetrievalService.build_passages(rows)
        assert 'doc_id="11111111-1111-4111-8111-111111111111"' in block
        assert 'pages="1-2"' in block and 'paras="1,2"' in block
        assert 'pages="3-3"' in block and 'ratio="True"' in block


class TestBudget:
    """Presentation-budget unit tests (gating-matrix groundwork, 2026-09-18).

    ``candidates`` is stubbed so no database is needed: the budget logic in
    ``retrieve`` is the unit under test.
    """

    def _rows(self) -> list[dict]:
        doc_a = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
        doc_b = uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
        # B11 shape: document A's caption chunks rank above A's own holding
        # chunk; the ratio lands last in hybrid order.
        return [
            {"id": 1, "document_id": doc_a, "is_ratio": False, "vsim": 0.90},
            {"id": 2, "document_id": doc_a, "is_ratio": False, "vsim": 0.85},
            {"id": 3, "document_id": doc_a, "is_ratio": False, "vsim": 0.80},
            {"id": 4, "document_id": doc_b, "is_ratio": False, "vsim": 0.75},
            {"id": 5, "document_id": doc_a, "is_ratio": True, "vsim": 0.70},
        ]

    async def _svc(self, monkeypatch: pytest.MonkeyPatch) -> RetrievalService:
        svc = RetrievalService(None, SEED_TENANT_AETOES)  # type: ignore[arg-type]

        async def fake_candidates(*args: object, **kwargs: object) -> list[dict]:
            return self._rows()

        monkeypatch.setattr(svc, "candidates", fake_candidates)
        return svc

    async def test_ratio_chunk_crowded_out_at_cap(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        svc = await self._svc(monkeypatch)
        rows = await svc.retrieve("q", [0.1], {}, per_doc_cap=2, top_k=8)
        assert rows is not None
        assert 5 not in {r["id"] for r in rows}  # A's ratio excluded at cap

    async def test_ratio_exemption_keeps_holding_chunk(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        svc = await self._svc(monkeypatch)
        rows = await svc.retrieve(
            "q", [0.1], {}, per_doc_cap=2, top_k=8, ratio_exempt=True
        )
        assert rows is not None
        ids = {r["id"] for r in rows}
        assert 5 in ids  # ratio exempt from the per-doc cap
        assert 3 not in ids  # third caption still capped
        assert len(rows) <= 8  # top-k budget still enforced

    async def test_top_k_budget_enforced(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        svc = await self._svc(monkeypatch)
        rows = await svc.retrieve("q", [0.1], {}, per_doc_cap=5, top_k=3)
        assert rows is not None
        assert len(rows) == 3
