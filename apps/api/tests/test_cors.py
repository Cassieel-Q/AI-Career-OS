from fastapi.testclient import TestClient

from app.main import app


JOB_DESCRIPTION_URL = "/api/v1/job-descriptions/00000000-0000-0000-0000-000000000000"


def _preflight(method: str, origin: str = "http://localhost:3000"):
    return TestClient(app).options(
        JOB_DESCRIPTION_URL,
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": "content-type",
        },
    )


def test_local_frontend_patch_preflight_allows_job_description_edits() -> None:
    response = _preflight("PATCH")

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "PATCH" in response.headers["access-control-allow-methods"]
    assert "content-type" in response.headers["access-control-allow-headers"].lower()


def test_local_frontend_delete_preflight_allows_job_description_deletes() -> None:
    response = _preflight("DELETE")

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "DELETE" in response.headers["access-control-allow-methods"]


def test_unconfigured_origin_cannot_preflight_job_description_mutations() -> None:
    response = _preflight("PATCH", origin="https://untrusted.example")

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
