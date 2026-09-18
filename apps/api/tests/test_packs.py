"""Feature-Addendum Step C DoD tests — §3.3 prompt packs.

DoD under test (owner 2026-09-18): SUMMONS_RESPONSE and CONTRACT_REVIEW packs
registered in the pack registry, accepted by POST /v1/documents/{id}/analyze,
producing schema-valid tabbed outputs (Overview / Arguments / Law) from
synthetic fixture documents (a one-page mock summons, a short mock
contract), with the Matcher dropping a planted fabricated citation UUID and
marking the affected item for manual review.

All model clients are fakes (no network, no secrets) — same harness
conventions as tests/test_analyses.py. The engine resolves
``make_llm``/``make_embedder`` as module-level names (``app.redteam.engine``),
so that is where the monkeypatch lands.
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
from app.redteam.schemas import (
    ContractReviewOutput,
    SummonsResponseOutput,
)
from tests.pdf_factory import make_pdf
from tests.test_query_api import make_jwt

VAULT_JURIS_NG = uuid.UUID("b0000001-0000-4000-8000-000000000001")
JWT_SECRET = "test-jwt-secret-not-a-real-secret"  # noqa: S105 (throwaway test secret)
UUID_RE = re.compile(r"B:([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})")
# Planted fabrication: a well-formed B: UUID the specialist cites even though
# it was never in <context_uuids>. The Matcher must drop it.
FABRICATED = "B:00000000-0000-0000-0000-000000000000"


def mock_summons_pages() -> list[list[str]]:
    """One-page mock summons: court, service date, return date, two claims."""
    return [
        [
            "IN THE HIGH COURT OF LAGOS STATE",
            "SUIT NO: LD/1234/2026",
            "BETWEEN: CHIJIOKE OKAFOR (Claimant) AND ADEOLA TRADERS LTD"
            " (Defendant)",
            "SUMMONS FOR APPEARANCE AND DEFENCE",
            "Served on the defendant on 2026-08-14.",
            "TAKE NOTICE that you must enter appearance within 42 days,"
            " that is by 2026-09-25.",
            "1. The claimant claims the sum of N5,000,000 being the balance"
            " of the purchase price of goods supplied.",
            "2. The claimant claims interest at 21 percent per annum from"
            " the date of delivery until judgment.",
        ]
    ]


def mock_contract_pages() -> list[list[str]]:
    """Short mock contract: parties, date, three operative clauses."""
    return [
        [
            "SERVICES AGREEMENT",
            "BETWEEN: LAGOS LOGISTICS LTD (the Company) AND KEHINDE ADEYEMI"
            " (the Contractor)",
            "DATED: 2026-01-15",
            "1. Clause 1 - Engagement: The Company engages the Contractor to"
            " provide haulage services for twelve months from the date hereof.",
            "2. Clause 2 - Payment: The Company shall pay the Contractor"
            " N200,000 monthly, payable 90 days after invoice.",
            "3. Clause 3 - Liability: The Contractor bears unlimited liability"
            " for all losses however arising, and the Company may terminate"
            " without notice or cause.",
        ]
    ]


class ConstantEmbedder:
    def __init__(self, value: float = 0.5) -> None:
        self.value = value

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[self.value] * EMBEDDING_DIMS for _ in texts]


class PackStageLLM:
    """Four-agent fake for the §3.3 packs. The specialist plants FABRICATED
    next to one real retrieved authority; the matcher (honestly) marks every
    cited UUID absent from <context_uuids> invalid — the engine under test
    must then drop it."""

    def __init__(self) -> None:
        self.systems: list[str] = []

    async def answer(self, system: str, user: str) -> str:
        self.systems.append(system)
        if "served summons" in system:
            return json.dumps(
                {
                    "parties": {"claimant": "Chijioke Okafor",
                                "defendant": "Adeola Traders Ltd"},
                    "court": "High Court of Lagos State",
                    "case_number": "LD/1234/2026",
                    "served_on": "2026-08-14",
                    "return_date": "2026-09-25",
                    "claims": [
                        {"id": "c1", "type": "LEGAL",
                         "text": "Claim for N5,000,000 balance of purchase"
                                 " price of goods supplied",
                         "cited_authorities": [], "relief_sought": "N5,000,000"},
                        {"id": "c2", "type": "LEGAL",
                         "text": "Claim for interest at 21 percent per annum",
                         "cited_authorities": [], "relief_sought": "Interest"},
                    ],
                    "document_type": "SUMMONS",
                }
            )
        if "this contract" in system:
            return json.dumps(
                {
                    "parties": {"party_a": "Lagos Logistics Ltd",
                                "party_b": "Kehinde Adeyemi"},
                    "agreement_date": "2026-01-15",
                    "clauses": [
                        {"id": "c1", "type": "LEGAL",
                         "text": "Clause 1 - Engagement: twelve-month haulage"
                                 " engagement",
                         "cited_authorities": [], "relief_sought": ""},
                        {"id": "c2", "type": "LEGAL",
                         "text": "Clause 2 - Payment: N200,000 monthly payable"
                                 " 90 days after invoice",
                         "cited_authorities": [], "relief_sought": ""},
                        {"id": "c3", "type": "LEGAL",
                         "text": "Clause 3 - Liability: unlimited liability,"
                                 " termination without notice",
                         "cited_authorities": [], "relief_sought": ""},
                    ],
                    "document_type": "CONTRACT",
                }
            )
        if "Summons Response Specialist" in system:
            m = UUID_RE.search(user)
            assert m, "Specialist payload must carry B: uuids to cite"
            auth = [f"B:{m.group(1)}", FABRICATED]
            return json.dumps(
                {
                    "sections": {
                        "overview": {
                            "court": "High Court of Lagos State",
                            "case_number": "LD/1234/2026",
                            "served_on": "2026-08-14",
                            "return_date": "2026-09-25",
                            "claimant": "Chijioke Okafor",
                            "defendant": "Adeola Traders Ltd",
                            "claims_served": 2,
                            "headline_risks": ["21 percent interest claim"],
                        },
                        "arguments": [
                            {"claim": "N5,000,000 purchase-price balance",
                             "response_deadline": "2026-09-25",
                             "strategy": "Deny indebtedness; plead part"
                                         " performance and set-off",
                             "authority": auth, "confidence": 0.8,
                             "manual_review": False},
                            {"claim": "21 percent interest",
                             "response_deadline": "2026-09-25",
                             "strategy": "Challenge rate as penal; the"
                                         " provision is unsupported",
                             "authority": [FABRICATED],
                             "confidence": 0.6, "manual_review": False},
                        ],
                        "law": [
                            {"point": "Appearance must be entered before the"
                                      " return date",
                             "authority": auth, "confidence": 0.9},
                        ],
                    }
                }
            )
        if "Contract Review Specialist" in system:
            m = UUID_RE.search(user)
            assert m, "Specialist payload must carry B: uuids to cite"
            auth = [f"B:{m.group(1)}", FABRICATED]
            return json.dumps(
                {
                    "sections": {
                        "overview": {
                            "parties": {"party_a": "Lagos Logistics Ltd",
                                        "party_b": "Kehinde Adeyemi"},
                            "agreement_date": "2026-01-15",
                            "clause_count": 3,
                            "overall_risk": "HIGH",
                            "headline_flags": ["Unlimited liability clause"],
                        },
                        "arguments": [
                            {"clause": "Clause 1 - Engagement",
                             "risk": "LOW",
                             "rationale": "Standard fixed-term engagement",
                             "deviation": "",
                             "authority": auth, "confidence": 0.9,
                             "manual_review": False},
                            {"clause": "Clause 3 - Liability",
                             "risk": "HIGH",
                             "rationale": "Unlimited liability plus"
                                          " termination without cause is"
                                          " one-sided",
                             "deviation": "Standard form caps liability and"
                                          " requires notice",
                             "authority": [FABRICATED],
                             "confidence": 0.7, "manual_review": False},
                        ],
                        "law": [
                            {"point": "Exclusion clauses are construed"
                                      " contra proferentem",
                             "authority": auth, "confidence": 0.85},
                        ],
                    }
                }
            )
        if "Matcher" in system:
            context_uuids = set(UUID_RE.findall(user.split("context_uuids")[1]))
            cited = set(UUID_RE.findall(user))
            invalid = [{"uuid": u, "reason": "not in retrieved context"}
                       for u in cited - context_uuids]
            valid = [{"uuid": u, "supports": "on point"}
                     for u in cited & context_uuids]
            return json.dumps({"valid": valid, "invalid": invalid})
        if "Critic" in system:
            return json.dumps(
                {"pass": True, "section_feedback": {}, "downgrade": []}
            )
        raise AssertionError(f"unexpected system prompt: {system[:60]}")


async def _ingest(app_db_url: str, tmp_path, name: str, pages: list[list[str]]) -> uuid.UUID:
    n = int(uuid.uuid4().hex[:6], 16)
    pdf = make_pdf(tmp_path / f"{name}-{n}.pdf", pages)
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
    import time

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        body = client.get(f"/v1/analyses/{analysis_id}", headers=_auth()).json()
        if body["status"] != "RUNNING":
            return body
        time.sleep(0.1)
    raise AssertionError("analysis never settled (still RUNNING)")


def _authorities(output: dict, *section_names: str) -> list[str]:
    return [
        a
        for name in section_names
        for item in output["sections"][name]
        for a in item["authority"]
    ]


class TestSummonsResponsePack:
    def test_mock_summons_produces_schema_valid_output(
        self, app_db_url: str, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        doc_id = asyncio.run(
            _ingest(app_db_url, tmp_path, "summons", mock_summons_pages())
        )
        monkeypatch.setattr(engine_module, "make_embedder", lambda s: ConstantEmbedder())
        monkeypatch.setattr(engine_module, "make_llm", lambda s: PackStageLLM())

        with TestClient(create_app(_settings(app_db_url))) as client:
            resp = client.post(
                f"/v1/documents/{doc_id}/analyze",
                json={"prompt_pack": "SUMMONS_RESPONSE"},
                headers=_auth(),
            )
            assert resp.status_code == 202, resp.text
            body = _poll(client, resp.json()["analysis_id"])

        assert body["status"] == "COMPLETE", body.get("error")
        assert body["prompt_pack"] == "SUMMONS_RESPONSE"

        # Schema validity: round-trips through the pack output schema.
        out = SummonsResponseOutput.model_validate(body["output"])
        assert out.source_document_id == str(doc_id)
        assert out.critic_verdict.pass_ is True
        assert body["output"]["critic_verdict"]["pass"] is True
        # Overview tab carries the extracted service facts.
        assert out.sections.overview.court == "High Court of Lagos State"
        assert out.sections.overview.claims_served == 2
        assert out.sections.overview.return_date == "2026-09-25"
        # Arguments tab: per-claim deadline + strategy present.
        assert len(out.sections.arguments) == 2
        assert all(c.response_deadline == "2026-09-25"
                   for c in out.sections.arguments)

        # Matcher enforcement: the planted fabrication is dropped everywhere.
        auths = _authorities(body["output"], "arguments", "law")
        assert auths, "output carries no authorities"
        assert FABRICATED not in auths
        assert all(a.startswith("B:") for a in auths)
        # The claim that cited ONLY the fabrication is flagged for review.
        only_fake = next(
            c for c in body["output"]["sections"]["arguments"]
            if "interest" in c["claim"]
        )
        assert only_fake["manual_review"] is True
        assert only_fake["authority"] == []
        # The claim that cited real + fake keeps the real one.
        mixed = next(
            c for c in body["output"]["sections"]["arguments"]
            if "purchase-price" in c["claim"]
        )
        assert len(mixed["authority"]) == 1
        assert mixed["authority"][0] != FABRICATED

        # Audit integration: one row, pack recorded.
        rows = asyncio.run(_fetch_analysis_audit(app_db_url, body["analysis_id"]))
        assert len(rows) == 1
        assert json.loads(rows[0]["filters"])["prompt_pack"] == "SUMMONS_RESPONSE"


class TestContractReviewPack:
    def test_mock_contract_produces_schema_valid_output(
        self, app_db_url: str, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        doc_id = asyncio.run(
            _ingest(app_db_url, tmp_path, "contract", mock_contract_pages())
        )
        monkeypatch.setattr(engine_module, "make_embedder", lambda s: ConstantEmbedder())
        monkeypatch.setattr(engine_module, "make_llm", lambda s: PackStageLLM())

        with TestClient(create_app(_settings(app_db_url))) as client:
            resp = client.post(
                f"/v1/documents/{doc_id}/analyze",
                json={"prompt_pack": "CONTRACT_REVIEW"},
                headers=_auth(),
            )
            assert resp.status_code == 202, resp.text
            body = _poll(client, resp.json()["analysis_id"])

        assert body["status"] == "COMPLETE", body.get("error")
        assert body["prompt_pack"] == "CONTRACT_REVIEW"

        out = ContractReviewOutput.model_validate(body["output"])
        assert out.critic_verdict.pass_ is True
        assert out.sections.overview.clause_count == 3
        assert out.sections.overview.overall_risk == "HIGH"
        # Arguments tab: per-clause risk flags.
        risks = {f.clause: f.risk for f in out.sections.arguments}
        assert risks["Clause 3 - Liability"] == "HIGH"
        assert risks["Clause 1 - Engagement"] == "LOW"

        # Matcher enforcement: planted fabrication dropped; fake-only item
        # to manual review; real authority retained on the mixed item.
        auths = _authorities(body["output"], "arguments", "law")
        assert FABRICATED not in auths
        high = next(
            f for f in body["output"]["sections"]["arguments"]
            if f["risk"] == "HIGH"
        )
        assert high["manual_review"] is True
        assert high["authority"] == []
        low = next(
            f for f in body["output"]["sections"]["arguments"]
            if f["risk"] == "LOW"
        )
        assert len(low["authority"]) == 1

        rows = asyncio.run(_fetch_analysis_audit(app_db_url, body["analysis_id"]))
        assert len(rows) == 1
        assert json.loads(rows[0]["filters"])["prompt_pack"] == "CONTRACT_REVIEW"


class TestPackRegistryValidation:
    @pytest.mark.parametrize("pack", ["SUMMONS_RESPONSE", "CONTRACT_REVIEW"])
    def test_registered_packs_accepted_and_entitlement_inherited(
        self, app_db_url: str, tmp_path, pack: str
    ) -> None:
        # Entitlement contract: require_feature('workbench.analyze') guards
        # the endpoint once for ALL packs (Step A wiring) — a request with a
        # valid JWT and entitled tenant must pass the dependency and reach
        # pack validation / document lookup, not 402/403.
        pages = (mock_summons_pages() if pack == "SUMMONS_RESPONSE"
                 else mock_contract_pages())
        doc_id = asyncio.run(_ingest(app_db_url, tmp_path, f"{pack.lower()}-ent", pages))
        with TestClient(create_app(_settings(app_db_url))) as client:
            resp = client.post(
                f"/v1/documents/{doc_id}/analyze",
                json={"prompt_pack": pack},
                headers=_auth(),
            )
        # 202 proves the entitlement check passed for the new pack; the
        # background worker's LLM call would fail without fakes, which this
        # test deliberately does not wait for.
        assert resp.status_code == 202, resp.text

    def test_unregistered_pack_still_rejected(
        self, app_db_url: str, tmp_path
    ) -> None:
        doc_id = asyncio.run(
            _ingest(app_db_url, tmp_path, "any", mock_summons_pages())
        )
        with TestClient(create_app(_settings(app_db_url))) as client:
            resp = client.post(
                f"/v1/documents/{doc_id}/analyze",
                json={"prompt_pack": "CASE_SUMMARY"},  # §3.3 pack, Step E
                headers=_auth(),
            )
        assert resp.status_code == 422


async def _fetch_analysis_audit(app_db_url: str, analysis_id: str) -> list:
    conn = await asyncpg.connect(app_db_url)
    try:
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.tenant_id', $1, true)", SEED_TENANT_AETOES
            )
            return await conn.fetch(
                "SELECT threshold_passed, filters FROM query_audit"
                " WHERE analysis_id = $1 ORDER BY created_at",
                uuid.UUID(analysis_id),
            )
    finally:
        await conn.close()
