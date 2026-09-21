"""Feature-Addendum Step A DoD tests — analysis endpoints.

DoD under test (owner 2026-09-17): an ingested fixture document produces a
schema-valid battle card retrievable via GET /v1/analyses/{id}, with exactly
one query_audit row (analysis_id link) per analysis.

All model clients are fakes (no network, no secrets):
  * ``ConstantEmbedder`` — cosine 1.0 vs every stored synthetic vector, so the
    0.78 gate always passes and per-claim retrieval returns the fixture doc.
  * ``StageLLM`` — dispatches on the §2.1 agent name in the system prompt:
    Extractor -> ClaimGraph, Strategist -> battle card citing a retrieved
    ``B:{uuid}`` authority, Matcher -> all-valid, Critic -> pass.
  * ``BrokenLLM`` — raises on the first call, driving the FAILED path.

The engine resolves ``make_llm``/``make_embedder`` as module-level names
(``app.redteam.engine``), so that is where the monkeypatch lands. Settings are
built with ``_env_file=None`` in every test so the developer's real .env
(Supabase DSN, live API keys) can never leak into a test run.
"""

import asyncio
import json
import re
import uuid

import asyncpg
import pytest
from conftest import SEED_TENANT_AETOES
from fastapi.testclient import TestClient

import app.redteam.engine as engine_module
from app.config import Settings
from app.ingestion.db import EMBEDDING_DIMS, ingest_pdf
from app.main import create_app
from app.redteam.schemas import BattleCard
from tests.pdf_factory import make_pdf, synthetic_judgment_pages
from tests.test_query_api import make_jwt

VAULT_JURIS_NG = uuid.UUID("b0000001-0000-4000-8000-000000000001")
JWT_SECRET = "test-jwt-secret-not-a-real-secret"  # noqa: S105 (throwaway test secret)
UUID_RE = re.compile(r"B:([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})")
DOC_TYPE_BRIEF = "BRIEF"


class ConstantEmbedder:
    def __init__(self, value: float = 0.5) -> None:
        self.value = value

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[self.value] * EMBEDDING_DIMS for _ in texts]


class StageLLM:
    """§2.1 chain fake: answers per agent stage, citing only retrieved uuids."""

    def __init__(self) -> None:
        self.systems: list[str] = []

    async def answer(self, system: str, user: str) -> str:
        self.systems.append(system)
        if "Extractor" in system:
            return json.dumps(
                {
                    "parties": {"claimant": "Adeyemi", "defendant": "FRN"},
                    "prayers": ["Dismiss the charge"],
                    "procedural_history": ["Arraigned 2024-03-12"],
                    "claims": [
                        {
                            "id": "c1",
                            "type": "LEGAL",
                            "text": "The trial court lacked jurisdiction"
                            " over the constitutional question",
                            "cited_authorities": [],
                            "relief_sought": "Quash the charge",
                        }
                    ],
                    "notable_dates": ["2024-03-12: hearing"],
                    "document_type": DOC_TYPE_BRIEF,
                }
            )
        if "Strategist" in system:
            m = UUID_RE.search(user)
            assert m, "Strategist payload must carry B: uuids to cite"
            auth = f"B:{m.group(1)}"
            return json.dumps(
                {
                    "sections": {
                        "procedural_flaws": [
                            {
                                "flaw": "Jurisdiction not vesting at first instance",
                                "basis": "Constitution s.251 ouster analysis",
                                "authority": [auth],
                                "severity": "MED",
                                "confidence": 0.8,
                            }
                        ],
                        "opposing_arguments": [
                            {
                                "argument": "The constitutional issue is"
                                " precluded by prior holding",
                                "strength": 7,
                                "our_counter": "Distinguishable: the prior"
                                " holding turned on a repealed provision",
                                "authority": [auth],
                                "confidence": 0.7,
                                "manual_review": False,
                            }
                        ],
                        "jurisdictional_notes": ["Note one"],
                    }
                }
            )
        if "Matcher" in system:
            valid = [
                {"uuid": u, "supports": "on point"}
                for u in set(UUID_RE.findall(user))
            ]
            return json.dumps({"valid": valid, "invalid": []})
        if "Critic" in system:
            return json.dumps(
                {
                    "pass": True,
                    "section_feedback": {
                        "procedural_flaws": "sound",
                        "opposing_arguments": "sound",
                    },
                    "downgrade": [],
                }
            )
        raise AssertionError(f"unexpected system prompt: {system[:60]}")


class BrokenLLM:
    async def answer(self, system: str, user: str) -> str:
        raise RuntimeError("llm sink unavailable")


async def _ingest_doc(app_db_url: str, tmp_path) -> uuid.UUID:
    n = int(uuid.uuid4().hex[:6], 16)
    citation = f"(2001) {1 + n % 9} NWLR (Pt. {150 + n % 700}) {1 + n % 400}"
    pages = synthetic_judgment_pages()
    pages[0] = [citation if "NWLR CITATION" in line else line for line in pages[0]]
    pdf = make_pdf(tmp_path / f"analyses-{n}.pdf", pages)
    conn = await asyncpg.connect(app_db_url)
    try:
        result = await ingest_pdf(
            conn,
            tenant_id=uuid.UUID(SEED_TENANT_AETOES),
            vault_id=VAULT_JURIS_NG,
            pdf_path=pdf,
            embedder=ConstantEmbedder(),
        )
    finally:
        await conn.close()
    return result.document_id


def _settings(app_db_url: str) -> Settings:
    return Settings(
        _env_file=None,
        database_url=app_db_url,
        supabase_jwt_secret=JWT_SECRET,
    )


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {make_jwt()}"}


def _poll(client: TestClient, analysis_id: str, *, timeout_s: float = 30.0) -> dict:
    """Background tasks run after the 202 response; poll until settled."""
    import time

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        body = client.get(f"/v1/analyses/{analysis_id}", headers=_auth()).json()
        if body["status"] != "RUNNING":
            return body
        time.sleep(0.1)
    raise AssertionError("analysis never settled (still RUNNING)")


class TestAnalyzeEndpoints:
    def test_fixture_doc_produces_schema_valid_battle_card(
        self, app_db_url: str, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        doc_id = asyncio.run(_ingest_doc(app_db_url, tmp_path))
        monkeypatch.setattr(engine_module, "make_embedder", lambda s: ConstantEmbedder())
        monkeypatch.setattr(engine_module, "make_llm", lambda s: StageLLM())

        with TestClient(create_app(_settings(app_db_url))) as client:
            resp = client.post(
                f"/v1/documents/{doc_id}/analyze",
                json={"prompt_pack": "ADVERSAL_BRIEF"},
                headers=_auth(),
            )
            assert resp.status_code == 202
            analysis_id = resp.json()["analysis_id"]
            assert uuid.UUID(analysis_id)

            body = _poll(client, analysis_id)

        assert body["status"] == "COMPLETE", body.get("error")
        assert body["error"] is None
        assert body["prompt_pack"] == "ADVERSAL_BRIEF"
        assert body["document_id"] == str(doc_id)

        # Schema validity: the stored output round-trips through §1.2 BattleCard.
        card = BattleCard.model_validate(body["output"])
        assert card.source_document_id == str(doc_id)
        assert card.critic_verdict.pass_ is True
        # Matcher-verified authority survived: cited uuid is a retrieved Vault B doc.
        auths = [
            a
            for item in [
                *card.sections.procedural_flaws,
                *card.sections.opposing_arguments,
            ]
            for a in item.authority
        ]
        assert auths, "battle card carries no authorities"
        assert all(a.startswith("B:") for a in auths)
        # Wire shape: the client-visible verdict key is "pass" (§1.2).
        assert body["output"]["critic_verdict"]["pass"] is True

        # Audit integration: exactly one query_audit row, analysis_id linked.
        rows = asyncio.run(_fetch_analysis_audit(app_db_url, analysis_id))
        assert len(rows) == 1
        row = rows[0]
        assert row["user_ref"] == "user-1"
        assert row["threshold_passed"] is True
        filters = json.loads(row["filters"])
        assert filters == {
            "document_id": str(doc_id),
            "prompt_pack": "ADVERSAL_BRIEF",
            "status": "COMPLETE",
        }

    def test_llm_failure_marks_failed_and_audits(
        self, app_db_url: str, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        doc_id = asyncio.run(_ingest_doc(app_db_url, tmp_path))
        monkeypatch.setattr(engine_module, "make_embedder", lambda s: ConstantEmbedder())
        monkeypatch.setattr(engine_module, "make_llm", lambda s: BrokenLLM())

        with TestClient(create_app(_settings(app_db_url))) as client:
            resp = client.post(
                f"/v1/documents/{doc_id}/analyze",
                json={"prompt_pack": "ADVERSAL_BRIEF"},
                headers=_auth(),
            )
            assert resp.status_code == 202
            body = _poll(client, resp.json()["analysis_id"])

        assert body["status"] == "FAILED"
        assert "llm sink unavailable" in body["error"]

        rows = asyncio.run(_fetch_analysis_audit(app_db_url, body["analysis_id"]))
        assert len(rows) == 1
        assert rows[0]["threshold_passed"] is False
        assert json.loads(rows[0]["filters"])["status"] == "FAILED"

    def test_unknown_pack_rejected_before_work(
        self, app_db_url: str, tmp_path
    ) -> None:
        doc_id = asyncio.run(_ingest_doc(app_db_url, tmp_path))
        with TestClient(create_app(_settings(app_db_url))) as client:
            resp = client.post(
                f"/v1/documents/{doc_id}/analyze",
                json={"prompt_pack": "CROSS_EXAM_PLAN"},
                headers=_auth(),
            )
        assert resp.status_code == 422

    def test_unknown_document_returns_404(self, app_db_url: str) -> None:
        with TestClient(create_app(_settings(app_db_url))) as client:
            resp = client.post(
                f"/v1/documents/{uuid.uuid4()}/analyze",
                json={"prompt_pack": "ADVERSAL_BRIEF"},
                headers=_auth(),
            )
        assert resp.status_code == 404

    def test_foreign_analysis_not_visible(self, app_db_url: str) -> None:
        with TestClient(create_app(_settings(app_db_url))) as client:
            resp = client.get(
                f"/v1/analyses/{uuid.uuid4()}", headers=_auth()
            )
        assert resp.status_code == 404

    def test_list_analyses_returns_own_analyses(self, app_db_url: str, tmp_path) -> None:
        """Addendum §6.2 per-user 'My Operations': the list endpoint returns the
        caller's own analyses (created_by scoped) with the tabbed wire shape."""
        doc_id = asyncio.run(_ingest_doc(app_db_url, tmp_path))
        with TestClient(create_app(_settings(app_db_url))) as client:
            resp = client.post(
                f"/v1/documents/{doc_id}/analyze",
                json={"prompt_pack": "ADVERSAL_BRIEF"},
                headers=_auth(),
            )
            assert resp.status_code == 202
            analysis_id = resp.json()["analysis_id"]

            listing = client.get("/v1/analyses", headers=_auth())
            assert listing.status_code == 200
            rows = listing.json()
            assert isinstance(rows, list)
            assert any(r["analysis_id"] == analysis_id for r in rows)
            row = next(r for r in rows if r["analysis_id"] == analysis_id)
            assert row["status"] in {"RUNNING", "COMPLETE", "FAILED"}
            assert row["document_id"] == str(doc_id)

            one = client.get(f"/v1/analyses/{analysis_id}", headers=_auth())
            assert one.status_code == 200
            assert one.json()["created_by"] == "user-1"


async def _fetch_analysis_audit(app_db_url: str, analysis_id: str) -> list:
    """Connect, read the analysis' audit rows, close — all on ONE event loop
    (an asyncpg connection is bound to the loop it was created on)."""
    conn = await asyncpg.connect(app_db_url)
    try:
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.tenant_id', $1, true)", SEED_TENANT_AETOES
            )
            return await conn.fetch(
                "SELECT user_ref, threshold_passed, filters FROM query_audit"
                " WHERE analysis_id = $1 ORDER BY created_at",
                uuid.UUID(analysis_id),
            )
    finally:
        await conn.close()
