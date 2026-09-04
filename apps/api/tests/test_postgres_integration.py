from __future__ import annotations

import os
from collections.abc import Generator

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from app import main
from app.database import get_db
from app.profile_service import create_draft_profile
from app.resume_schemas import ResumeExtractionResult


def _postgres_url() -> str:
    url = os.getenv("TEST_DATABASE_URL", "").strip()
    if not url:
        pytest.skip("PostgreSQL integration requires TEST_DATABASE_URL")
    if not url.startswith(("postgresql://", "postgresql+psycopg://", "postgresql+psycopg2://")):
        pytest.fail("TEST_DATABASE_URL must use PostgreSQL; SQLite is not accepted here")
    _assert_test_database_isolation(url)
    return url


def _database_target(database_url: str) -> tuple[str, str, int, str]:
    parsed = make_url(database_url)
    backend = parsed.get_backend_name()
    host = (parsed.host or "").lower()
    if backend == "postgresql":
        host = {"localhost": "local", "127.0.0.1": "local", "::1": "local"}.get(host, host)
        port = parsed.port or 5432
    else:
        port = parsed.port or 0
    return backend, host, port, parsed.database or ""


def _assert_test_database_isolation(test_database_url: str) -> None:
    application_database_url = os.getenv("DATABASE_URL", "").strip()
    if application_database_url and _database_target(application_database_url) == _database_target(test_database_url):
        raise RuntimeError("TEST_DATABASE_URL must not point to the application database.")


def test_identical_postgres_database_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://app:secret@localhost:5432/ai_career_os")
    test_url = "postgresql+psycopg://test:secret@localhost/ai_career_os"

    with pytest.raises(RuntimeError, match="TEST_DATABASE_URL must not point to the application database."):
        _assert_test_database_isolation(test_url)


def test_different_postgres_database_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://app:secret@localhost:5432/ai_career_os")

    _assert_test_database_isolation("postgresql+psycopg://test:secret@localhost:5432/ai_career_os_test")


def test_missing_test_database_url_keeps_skip_behavior(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)

    with pytest.raises(pytest.skip.Exception, match="PostgreSQL integration requires TEST_DATABASE_URL"):
        _postgres_url()


@pytest.fixture(scope="module")
def postgres_engine() -> Generator[Engine, None, None]:
    url = _postgres_url()
    engine = create_engine(url, pool_pre_ping=True)
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    command.upgrade(config, "head")
    try:
        yield engine
    finally:
        command.downgrade(config, "base")
        engine.dispose()


@pytest.fixture
def postgres_client(postgres_engine: Engine) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        with Session(postgres_engine) as session:
            yield session

    main.app.dependency_overrides[get_db] = override_get_db
    with TestClient(main.app) as client:
        yield client
    main.app.dependency_overrides.clear()


@pytest.mark.integration
def test_postgres_profile_api_round_trip(postgres_client: TestClient, postgres_engine: Engine) -> None:
    with Session(postgres_engine) as session:
        profile = create_draft_profile(
            session,
            ResumeExtractionResult(skills=[{"name": "Python", "evidence_text": "Python"}]),
        )
        profile_id = str(profile.id)

    response = postgres_client.get(f"/api/v1/profiles/{profile_id}")
    assert response.status_code == 200
    assert response.json()["status"] == "DRAFT"

    response = postgres_client.put(
        f"/api/v1/profiles/{profile_id}",
        json={
            "skills": [
                {
                    "id": response.json()["skills"][0]["id"],
                    "name": "Python",
                    "evidence_text": "Python",
                    "source_type": "AI_EXTRACTED",
                    "proficiency": "PROJECT_READY",
                }
            ]
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "DRAFT"
    assert response.json()["skills"][0]["proficiency"] == "PROJECT_READY"

    response = postgres_client.post(f"/api/v1/profiles/{profile_id}/confirm")
    assert response.status_code == 200
    assert response.json()["status"] == "CONFIRMED"

    response = postgres_client.get(f"/api/v1/profiles/{profile_id}")
    assert response.status_code == 200
    assert response.json()["status"] == "CONFIRMED"
