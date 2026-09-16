"""App factory smoke tests — Task 1.1 DoD (pytest green; HANDOFF.md §4)."""

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_health_endpoint() -> None:
    client = TestClient(create_app(Settings()))
    resp = client.get("/v1/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_app_boots_without_secrets() -> None:
    # HANDOFF §3: secrets come from AWS Secrets Manager at deploy time; the
    # app (and CI) must boot with none set.
    app = create_app(Settings())
    assert app.state.settings.supabase_service_role is None
    assert app.state.settings.vector_gate == 0.78
