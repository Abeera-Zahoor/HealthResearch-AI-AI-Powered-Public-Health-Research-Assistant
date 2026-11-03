"""REST API tests. They need FastAPI installed (it is in requirements.txt) and are skipped otherwise."""
import pytest

pytest.importorskip("fastapi")

from tests.helpers import make_clients, make_settings  # noqa: E402
from tests.test_pipeline import QUESTION, build  # noqa: E402


@pytest.fixture
def client(tmp_path):
    from fastapi.testclient import TestClient

    from app.main import create_app

    pipeline, _ = build(tmp_path)
    with TestClient(create_app(pipeline.settings, pipeline)) as test_client:
        yield test_client


def test_api_health_and_validation(client):
    health = client.get("/api/health").json()
    assert health["status"] == "ok" and health["llm"]["enabled"] is False and "sample_question" in health
    assert "api_key" not in str(health).lower()
    bad = client.post("/api/research", json={"question": "short"})
    assert bad.status_code == 422
    assert client.post("/api/research", json={"question": QUESTION, "audience": "aliens"}).status_code == 422


def test_api_run_lifecycle(client):
    created = client.post("/api/research", json={"question": QUESTION, "audience": "students", "output_type": "video_script"})
    assert created.status_code == 202
    run_id = created.json()["id"]
    run = client.get(f"/api/research/{run_id}").json()
    assert run["status"] == "completed" and run["audience"] == "students" and run["output"]["content"]
    assert client.get("/api/research").json()[0]["id"] == run_id
    assert client.delete(f"/api/research/{run_id}").status_code == 204
    assert client.get(f"/api/research/{run_id}").status_code == 404
    assert client.delete(f"/api/research/{run_id}").status_code == 404
