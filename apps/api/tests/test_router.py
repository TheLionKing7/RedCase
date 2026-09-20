"""Task 2.4 DoD — dual-vault router endpoint tests (owner brief 2026-09-19).

DoD items (owner brief):
  * 60-question labeled synthetic route set, >=90% routing accuracy via the
    live provisioned chain (TestRouteSetAccuracy — live-gated like the
    citation battery; synthetic questions, no document content involved);
  * namespace-mixing test — an [A:...] citation resolving to a JURIS doc id
    (or vice versa) is a fabrication-class event: refusal, zero citations;
  * Vault A miss + Vault B miss -> refusal ("No binding support found.");
  * Vault A hit + Vault B miss -> internal-only answer labeled as such;
  * zero fabricated citations throughout (the namespace guard is the gate);
  * plus: route-B delegation to the Phase 1 engine, matter-binding ruling
    (PARTNER/ADMIN cross-matter, others pre-filtered), ADVISORY mode label,
    entitlement DECISION event for core.dual_vault, and one query_audit row
    per dual call with route metadata in filters.

All endpoint tests run on the embedded pgvector cluster with a deterministic
FakeLLM and ConstantEmbedder — zero live model spend, fully reproducible.
"""

import base64
import contextlib
import hashlib
import hmac
import json
import os
import time
import uuid
from pathlib import Path

import asyncpg
import pytest
from conftest import SEED_TENANT_AETOES
from fastapi.testclient import TestClient

import app.router.service as router_service
from app.config import Settings, get_settings
from app.main import create_app
from app.retrieval.clients import make_llm
from app.vault_a.crypto import make_key_provider

JWT_SECRET = "router-test-secret-not-a-real-secret"  # noqa: S105
MASTER_KEY_HEX = "cd" * 32  # throwaway test master key (dev provider)

ROUTE_SET_PATH = Path(__file__).parent / "fixtures" / "router_route_set.json"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def make_jwt(
    *, sub: str = "router-user", clearance: str = "PARTNER",
    tenant: str = SEED_TENANT_AETOES,
) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": sub,
        "exp": int(time.time()) + 3600,
        "app_metadata": {"tenant_id": tenant, "clearance": clearance},
    }
    seg = f"{_b64url(json.dumps(header).encode())}.{_b64url(json.dumps(payload).encode())}"
    sig = hmac.new(JWT_SECRET.encode(), seg.encode(), hashlib.sha256).digest()
    return f"{seg}.{_b64url(sig)}"


class ConstantEmbedder:
    """Every chunk is equidistant from every query (vsim = 1.0 >= any gate),
    so retrieval hits are controlled purely by what the fixture seeded."""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.25] * 1024 for _ in texts]


class FakeLLM:
    """Deterministic double. Distinguishes the router classifier call from
    answer/synthesis calls by the system prompt, per the real contracts."""

    def __init__(
        self, *, route: str = "BOTH", confidence: float = 0.95,
        synthesis: str | None = None,
    ) -> None:
        self.route, self.confidence, self.synthesis = route, confidence, synthesis
        self.calls: list[str] = []

    async def answer(self, system: str, user: str) -> str:
        if "Classify the legal query" in system:
            self.calls.append("classify")
            return json.dumps(
                {
                    "route": self.route,
                    "confidence": self.confidence,
                    "rewritten_queries": {"a": "firm side query", "b": "public law query"},
                }
            )
        self.calls.append("synthesis")
        if self.synthesis is None:
            raise AssertionError("unexpected synthesis call in this test")
        return self.synthesis


INSERT_DOC = """
    INSERT INTO documents
        (id, tenant_id, vault_id, case_title, citation, court_level, year,
         source_pdf_path, pdf_sha256, client_id, matter_id,
         classification_level, doc_type)
    VALUES ($1, $2, $3, $4, $5, $6, 2024, 's3://router-test.pdf', $7,
            $8, $9, $10, 'OPINION')
"""

VEC_LITERAL = "[" + ",".join(["0.25"] * 1024) + "]"


async def _scope(conn, tenant, user_ref, clearance="PARTNER") -> None:
    await conn.execute("SELECT set_config('app.tenant_id', $1, true)", tenant)
    await conn.execute("SELECT set_config('app.user_ref', $1, true)", user_ref)
    await conn.execute("SELECT set_config('app.user_clearance', $1, true)", clearance)


async def _insert_chunk(conn, tenant, doc_id, text="synthetic holding text") -> None:
    await conn.execute(
        "INSERT INTO document_chunks"
        " (id, tenant_id, document_id, chunk_index, chunk_text,"
        "  page_start, page_end, embedding)"
        " VALUES ($1, $2, $3, 0, $4, 1, 2, $5::vector)",
        uuid.uuid4(), tenant, doc_id, text, VEC_LITERAL,
    )


async def _insert_doc(
    conn, *, tenant, vault_id, title, citation, court, classification,
    matter_id=None, client_id=None, sha=None,
) -> uuid.UUID:
    doc_id = uuid.uuid4()
    await conn.execute(
        INSERT_DOC, doc_id, tenant, vault_id, title, citation, court,
        sha or (uuid.uuid4().hex), client_id, matter_id, classification,
    )
    return doc_id


async def _new_tenant(conn) -> str:
    tid = str(uuid.uuid4())
    await conn.execute(
        "INSERT INTO tenants (id, name, slug) VALUES ($1, $2, $3)",
        uuid.UUID(tid), f"Router {tid[:8]}", f"r-{tid[:8]}",
    )
    return tid


@pytest.fixture
async def dual_corpus(app_db_url: str) -> dict:
    """Dedicated tenant: one FIRM doc (FIRM_INTERNAL, matter-bound) + one
    JURIS doc, both embedded, both vaults created for this tenant.
    (Dedicated tenant — not the shared seed tenant — so hit/miss
    assumptions can't be broken by other fixtures' rows.)"""
    conn = await asyncpg.connect(app_db_url)
    tenant = await _new_tenant(conn)
    marker = uuid.uuid4().hex[:8]
    client_id, matter_id = uuid.uuid4(), uuid.uuid4()
    try:
        firm_vault, juris_vault = uuid.uuid4(), uuid.uuid4()
        await conn.execute(
            "INSERT INTO vaults (id, tenant_id, vault_type, name, is_shared)"
            " VALUES ($1, $2, 'firm', $3, FALSE)",
            firm_vault, tenant, f"Router Firm Vault {marker}",
        )
        await conn.execute(
            "INSERT INTO vaults (id, tenant_id, vault_type, name, is_shared)"
            " VALUES ($1, $2, 'juris', $3, FALSE)",
            juris_vault, tenant, f"Router Juris Vault {marker}",
        )
        async with conn.transaction():
            await _scope(conn, tenant, "router-setup")
            await conn.execute(
                "INSERT INTO clients (id, tenant_id, name) VALUES ($1, $2, $3)",
                client_id, tenant, f"Router Client {marker}",
            )
            await conn.execute(
                "INSERT INTO matters (id, tenant_id, client_id, matter_ref)"
                " VALUES ($1, $2, $3, $4)",
                matter_id, tenant, client_id, f"ROUTER-{marker} v. Syn",
            )
            firm_doc = await _insert_doc(
                conn, tenant=tenant, vault_id=firm_vault,
                title=f"Router Firm Doc {marker}",
                citation=f"INTERNAL-{marker}", court="STATUTE",
                classification="FIRM_INTERNAL",
                matter_id=matter_id, client_id=client_id,
            )
            await _insert_chunk(conn, tenant, firm_doc, "synthetic firm strategy text")
            juris_doc = await _insert_doc(
                conn, tenant=tenant, vault_id=juris_vault,
                title=f"Router Juris Doc {marker}",
                citation=f"(2024) 9 RW-{marker}", court="SUPREME_COURT",
                classification="PUBLIC",
            )
            await _insert_chunk(conn, tenant, juris_doc, "synthetic ratio text")
        return {
            "tenant": tenant, "matter_id": str(matter_id),
            "firm_doc": str(firm_doc), "juris_doc": str(juris_doc),
            "client_id": str(client_id),
        }
    finally:
        await conn.close()


@pytest.fixture
async def firm_only(app_db_url: str) -> dict:
    """Seed tenant, firm side only (no juris docs -> route-B leg always misses)."""
    fx = await _seed_single_vault(app_db_url, juris=False)
    return fx


@pytest.fixture
async def juris_only(app_db_url: str) -> dict:
    """Seed tenant, juris side only (route-A leg always misses)."""
    fx = await _seed_single_vault(app_db_url, juris=True)
    return fx


async def _seed_single_vault(app_db_url: str, *, juris: bool) -> dict:
    """Dedicated tenant with exactly one seeded document — the other vault
    leg is guaranteed to miss."""
    conn = await asyncpg.connect(app_db_url)
    tenant = await _new_tenant(conn)
    marker = uuid.uuid4().hex[:8]
    try:
        if juris:
            juris_vault = uuid.uuid4()
            await conn.execute(
                "INSERT INTO vaults (id, tenant_id, vault_type, name, is_shared)"
                " VALUES ($1, $2, 'juris', $3, FALSE)",
                juris_vault, tenant, f"Router Solo Juris Vault {marker}",
            )
            # RLS on documents evaluates current_setting('app.tenant_id') —
            # the GUC must exist in the session before any documents DML.
            async with conn.transaction():
                await _scope(conn, tenant, "router-setup")
                doc_id = await _insert_doc(
                    conn, tenant=tenant, vault_id=juris_vault,
                    title=f"Router Solo Juris {marker}",
                    citation=f"(2024) 9 RW-{marker}", court="SUPREME_COURT",
                    classification="PUBLIC",
                )
                await _insert_chunk(conn, tenant, doc_id, "synthetic ratio text")
            return {"tenant": tenant, "doc_id": str(doc_id)}
        firm_vault = uuid.uuid4()
        client_id, matter_id = uuid.uuid4(), uuid.uuid4()
        await conn.execute(
            "INSERT INTO vaults (id, tenant_id, vault_type, name, is_shared)"
            " VALUES ($1, $2, 'firm', $3, FALSE)",
            firm_vault, tenant, f"Router Solo Firm {marker}",
        )
        async with conn.transaction():
            await _scope(conn, tenant, "router-setup")
            await conn.execute(
                "INSERT INTO clients (id, tenant_id, name) VALUES ($1, $2, $3)",
                client_id, tenant, f"Router Solo Client {marker}",
            )
            await conn.execute(
                "INSERT INTO matters (id, tenant_id, client_id, matter_ref)"
                " VALUES ($1, $2, $3, $4)",
                matter_id, tenant, client_id, f"RSOLO-{marker} v. Syn",
            )
            doc_id = await _insert_doc(
                conn, tenant=tenant, vault_id=firm_vault,
                title=f"Router Solo Firm {marker}",
                citation=f"INTERNAL-{marker}", court="STATUTE",
                classification="FIRM_INTERNAL",
                matter_id=matter_id, client_id=client_id,
            )
            await _insert_chunk(conn, tenant, doc_id, "synthetic firm strategy text")
        return {"tenant": tenant, "doc_id": str(doc_id), "matter_id": str(matter_id)}
    finally:
        await conn.close()


@pytest.fixture
async def empty_tenant(app_db_url: str) -> str:
    """A fresh tenant with no vaults, documents, or corpus — every leg misses."""
    conn = await asyncpg.connect(app_db_url)
    tid = str(uuid.uuid4())
    try:
        await conn.execute(
            "INSERT INTO tenants (id, name, slug) VALUES ($1, $2, $3)",
            uuid.UUID(tid), f"Router Empty {tid[:8]}", f"r-{tid[:8]}",
        )
        return tid
    finally:
        await conn.close()


@pytest.fixture
def make_client(app_db_url: str, monkeypatch: pytest.MonkeyPatch):
    """Factory: patched TestClient for a given FakeLLM. Module-level factory
    names in app.router.service are monkeypatched so the endpoint's internal
    resolution picks the doubles up."""

    @contextlib.contextmanager
    def _make(fake: FakeLLM, *, tenant: str = SEED_TENANT_AETOES):
        settings = Settings(
            database_url=app_db_url,
            supabase_jwt_secret=JWT_SECRET,
            vault_a_key_provider="local",
            vault_a_master_key=MASTER_KEY_HEX,
        )
        monkeypatch.setattr(router_service, "make_embedder", lambda s: ConstantEmbedder())
        monkeypatch.setattr(router_service, "make_llm", lambda s: fake)
        monkeypatch.setattr(
            router_service, "make_key_provider", lambda s: make_key_provider(settings)
        )
        with TestClient(create_app(settings)) as client:
            yield client

    return _make


def _post_dual(client, question, token, *, matter_id=None, mode=None):
    body: dict = {"question": question}
    if matter_id:
        body["matter_id"] = matter_id
    if mode:
        body["mode"] = mode
    return client.post(
        "/v1/dual/query",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
    )


async def _audit_rows(app_db_url: str, tenant: str) -> list[dict]:
    conn = await asyncpg.connect(app_db_url)
    try:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", tenant)
            rows = await conn.fetch(
                "SELECT question_hash, filters, answer_text IS NOT NULL AS answered"
                " FROM query_audit ORDER BY created_at DESC LIMIT 10"
            )
        return [dict(r) for r in rows]
    finally:
        await conn.close()


class TestClassifyParsing:
    """classify() degradation contract: bad output never widens the surface."""

    async def test_malformed_json_degrades_to_b(self):
        class Garbage:
            async def answer(self, system, user):
                return "not json at all"

        plan = await router_service.classify("anything", Garbage())
        assert plan["route"] == "B"
        assert plan["confidence"] == 0.0

    async def test_low_confidence_degrades_to_b(self):
        fake = FakeLLM(route="A", confidence=0.4)
        plan = await router_service.classify("anything", fake)
        assert plan["route"] == "B"

    async def test_unknown_route_degrades_to_b(self):
        class Weird:
            async def answer(self, system, user):
                return json.dumps({"route": "Z", "confidence": 0.99})

        plan = await router_service.classify("anything", Weird())
        assert plan["route"] == "B"

    async def test_valid_both_preserved(self):
        fake = FakeLLM(route="BOTH", confidence=0.91)
        plan = await router_service.classify("anything", fake)
        assert plan["route"] == "BOTH"
        assert plan["rewritten_queries"]["a"] == "firm side query"


class TestNamespaceGuard:
    async def test_namespace_mixing_refuses_with_zero_citations(
        self, dual_corpus: dict, make_client, app_db_url: str
    ):
        """[A:<juris-doc-id>] is namespace mixing — a fabrication-class event:
        the guard must refuse and surface ZERO citations."""
        t = dual_corpus["tenant"]
        j = dual_corpus["juris_doc"]
        fake = FakeLLM(
            route="BOTH",
            synthesis=f"Our internal practice supports this [A:{j}, p.1] fully.",
        )
        with make_client(fake, tenant=t) as client:
            resp = _post_dual(
                client, "combined strategy question", make_jwt(tenant=t)
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["refusal"] is True
        assert body["citations"] == []
        assert fake.calls.count("synthesis") == 1

    async def test_clean_namespaces_pass_with_pins(self, dual_corpus: dict, make_client):
        t = dual_corpus["tenant"]
        f, j = dual_corpus["firm_doc"], dual_corpus["juris_doc"]
        fake = FakeLLM(
            route="BOTH",
            synthesis=(
                f"Internal strategy [A:{f}, p.1] informs the structure, while "
                f"public authority [B:{j}, (2024) 9 NWLR, p.2] grounds it.\n"
                f"<citations>[A:{f}] [B:{j}]</citations>"
            ),
        )
        with make_client(fake, tenant=t) as client:
            resp = _post_dual(
                client, "combined strategy question", make_jwt(tenant=t)
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["refusal"] is False
        namespaces = {c["namespace"] for c in body["citations"]}
        assert namespaces == {"A", "B"}
        refs = {c["ref"] for c in body["citations"]}
        assert refs == {f"A:{f}", f"B:{j}"}
        for c in body["citations"]:
            assert c["verified"] is True
            assert c["page_start"] == 1 and c["page_end"] == 2


class TestRefusalSemantics:
    async def test_dual_miss_refuses(self, empty_tenant: str, make_client):
        fake = FakeLLM(route="BOTH", synthesis="should never be called")
        token = make_jwt(tenant=empty_tenant)
        with make_client(fake, tenant=empty_tenant) as client:
            resp = _post_dual(client, "anything at all", token)
        assert resp.status_code == 200
        body = resp.json()
        assert body["refusal"] is True
        assert "No binding support found." in body["answer"]
        assert body["citations"] == []
        assert fake.calls == ["classify"]  # no synthesis on a dual miss

    async def test_a_hit_b_miss_is_internal_only_labeled(
        self, firm_only: dict, make_client
    ):
        t = firm_only["tenant"]
        f = firm_only["doc_id"]
        fake = FakeLLM(
            route="BOTH",
            synthesis=f"Per our playbook [A:{f}, p.1] we sequence it this way.",
        )
        with make_client(fake, tenant=t) as client:
            resp = _post_dual(
                client, "how do we handle this", make_jwt(tenant=t)
            )
        body = resp.json()
        assert body["refusal"] is False
        assert "internal strategy" in body["answer"].lower()
        assert "no public authority found" in body["answer"].lower()
        assert [c["namespace"] for c in body["citations"]] == ["A"]

    async def test_a_miss_b_hit_is_public_only_labeled(
        self, juris_only: dict, make_client
    ):
        t = juris_only["tenant"]
        j = juris_only["doc_id"]
        fake = FakeLLM(
            route="BOTH",
            synthesis=f"The Supreme Court held [B:{j}, (2024) 9 NWLR, p.2].",
        )
        with make_client(fake, tenant=t) as client:
            resp = _post_dual(
                client, "what is the leading case", make_jwt(tenant=t)
            )
        body = resp.json()
        assert body["refusal"] is False
        assert "public authority only" in body["answer"].lower()
        assert [c["namespace"] for c in body["citations"]] == ["B"]

    async def test_advisory_mode_labels_instead_of_refusing(
        self, empty_tenant: str, make_client
    ):
        fake = FakeLLM(route="BOTH")
        token = make_jwt(tenant=empty_tenant)
        with make_client(fake, tenant=empty_tenant) as client:
            resp = _post_dual(client, "weak signal question", token, mode="ADVISORY")
        body = resp.json()
        assert body["refusal"] is False
        assert body["advisory"] is True
        assert "manual review recommended" in body["answer"].lower()


class TestRouteBDelegation:
    async def test_route_b_uses_phase1_engine_and_audits_route(
        self, juris_only: dict, make_client, app_db_url: str
    ):
        t = juris_only["tenant"]
        j = juris_only["doc_id"]
        fake = FakeLLM(
            route="B",
            synthesis=f"The controlling authority supports the answer. <citations>{j}</citations>",
        )
        with make_client(fake, tenant=t) as client:
            resp = _post_dual(
                client, "leading case on garnishee", make_jwt(tenant=t)
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["route"] == "B"
        assert body["refusal"] is False
        assert body["citations"][0]["document_id"] == j
        # Route metadata lands in the audit filters (one row, Phase 1 shape).
        rows = await _audit_rows(app_db_url, juris_only["tenant"])
        assert rows and rows[0]["answered"] is True
        raw_filters = rows[0]["filters"]
        filters = json.loads(raw_filters) if isinstance(raw_filters, str) else raw_filters
        assert filters.get("route") == "B"
        assert "route_confidence" in filters


class TestMatterBinding:
    async def test_staff_matter_prefilter_misses_other_matter(
        self, firm_only: dict, make_client
    ):
        """STAFF + matter_id other than the doc's matter -> A-miss -> refusal
        (the 2.2 ruling: retrieval pre-filtered to the matter)."""
        other_matter = str(uuid.uuid4())
        t = firm_only["tenant"]
        f = firm_only["doc_id"]
        fake = FakeLLM(route="A", synthesis=f"playbook [A:{f}, p.1]")
        staff = make_jwt(clearance="STAFF", tenant=t)
        with make_client(fake, tenant=t) as client:
            resp = _post_dual(
                client, "our approach", staff, matter_id=other_matter
            )
        body = resp.json()
        assert body["refusal"] is True

    async def test_partner_cross_matter_sees_document(
        self, firm_only: dict, make_client
    ):
        """PARTNER + matter_id elsewhere -> no pre-filter -> hit, labeled."""
        other_matter = str(uuid.uuid4())
        t = firm_only["tenant"]
        f = firm_only["doc_id"]
        fake = FakeLLM(route="A", synthesis=f"playbook [A:{f}, p.1]")
        partner = make_jwt(clearance="PARTNER", tenant=t)
        with make_client(fake, tenant=t) as client:
            resp = _post_dual(
                client, "our approach", partner, matter_id=other_matter
            )
        body = resp.json()
        assert body["refusal"] is False
        assert "internal strategy" in body["answer"].lower()


class TestEntitlementAndAudit:
    async def test_core_feature_gate_decision_is_logged(
        self, empty_tenant: str, make_client, app_db_url: str
    ):
        fake = FakeLLM(route="BOTH")
        token = make_jwt(tenant=empty_tenant)
        with make_client(fake, tenant=empty_tenant) as client:
            resp = _post_dual(client, "anything", token)
        assert resp.status_code == 200
        conn = await asyncpg.connect(app_db_url)
        try:
            async with conn.transaction():
                await conn.execute(
                    "SELECT set_config('app.tenant_id', $1, true)", empty_tenant
                )
                row = await conn.fetchrow(
                    "SELECT decision FROM entitlement_events"
                    " WHERE tenant_id = $1 AND feature = 'core.dual_vault'"
                    " ORDER BY created_at DESC LIMIT 1",
                    uuid.UUID(empty_tenant),
                )
        finally:
            await conn.close()
        assert row is not None and row["decision"] == "ALLOW"


class TestRouteSetAccuracy:
    """Live-gated DoD: 60-question labeled synthetic route set through the
    provisioned chain (owner: DeepSeek acceptable for the classifier — it
    sees questions only, never document content). Accuracy bar >= 90%.

    Batchable: ROUTE_SET_SLICE="0:30" runs the first half (the shell caps
    a single command at 295s; 60 short calls fit, but slicing keeps the
    gate runnable under the cap).
    """

    async def test_route_set_accuracy(self):
        items = json.loads(ROUTE_SET_PATH.read_text(encoding="utf-8"))
        slice_spec = os.environ.get("ROUTE_SET_SLICE", "")
        if slice_spec:
            start, end = (int(x) for x in slice_spec.split(":"))
            items = items[start:end]
        try:
            llm = make_llm(get_settings())
        except RuntimeError:
            pytest.skip("no answer-LLM credential provisioned in this environment")
        wrong: list[str] = []
        per_route: dict[str, list[str]] = {}
        for item in items:
            plan = await router_service.classify(item["question"], llm)
            got, want = plan["route"], item["label"]
            per_route.setdefault(want, []).append("ok" if got == want else f"got {got}")
            if got != want:
                wrong.append(f"{item['id']}: want {want}, got {got}")
        total, n_wrong = len(items), len(wrong)
        accuracy = (total - n_wrong) / total if total else 1.0
        summary = {
            r: {"n": len(v), "misses": sum(1 for x in v if x != "ok")}
            for r, v in per_route.items()
        }
        print(f"\nroute-set accuracy: {total - n_wrong}/{total} ({accuracy:.1%})")
        print(f"per-route: {json.dumps(summary)}")
        for line in wrong:
            print(f"  MISS {line}")
        assert accuracy >= 0.90, f"routing accuracy {accuracy:.1%} < 90%: {wrong}"
