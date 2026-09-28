from __future__ import annotations

import hashlib
import os
from collections.abc import Generator
import threading
import time

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from app import main, models
from app.database import get_db
from app.derived_state import derived_state_fingerprint
from app.gap_schemas import GapProposalPayload
from app.gap_service import create_gap_analysis
from app.profile_service import create_draft_profile, get_profile
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


@pytest.mark.integration
def test_postgres_career_preferences_survive_fresh_session(
    postgres_client: TestClient, postgres_engine: Engine
) -> None:
    with Session(postgres_engine) as session:
        profile = create_draft_profile(
            session,
            ResumeExtractionResult(skills=[{"name": "Python", "evidence_text": "Python"}]),
        )
        profile_id = profile.id

    response = postgres_client.post(f"/api/v1/profiles/{profile_id}/confirm")
    assert response.status_code == 200

    response = postgres_client.put(
        f"/api/v1/profiles/{profile_id}/preferences",
        json={
            "priority_order": ["FAST_EMPLOYMENT", "CURRENT_FIT"],
            "weekly_hours": 20,
        },
    )
    assert response.status_code == 200
    assert response.json()["priority_order"] == ["FAST_EMPLOYMENT", "CURRENT_FIT"]

    with Session(postgres_engine) as fresh_session:
        profile_read = get_profile(fresh_session, profile_id)
        assert profile_read.preferences is not None
        assert profile_read.preferences.weekly_hours == 20
        assert profile_read.preferences.priority_order == [
            "FAST_EMPLOYMENT",
            "CURRENT_FIT",
        ]
        assert (
            fresh_session.query(models.CareerPreference)
            .filter_by(profile_id=profile_id)
            .count()
            == 1
        )


@pytest.mark.integration
def test_gap_generation_does_not_hold_postgres_lock_during_provider(
    postgres_engine: Engine,
) -> None:
    """A concurrent generation must not turn a slow provider into e3q8."""

    with Session(postgres_engine) as session:
        profile = create_draft_profile(
            session,
            ResumeExtractionResult(skills=[{"name": "Python", "evidence_text": "Python"}]),
        )
        profile.status = "CONFIRMED"
        exploration = models.RoleExploration(
            profile_id=profile.id,
            role_profile_version="v1",
            result={"role_profile_version": "v1", "items": []},
        )
        target = models.TargetRole(
            profile_id=profile.id,
            role_code="AI_PRODUCT_MANAGER",
            role_profile_version="v1",
            role_exploration=exploration,
        )
        session.add(target)
        session.flush()
        jds = [
            models.JobDescription(
                target_role_id=target.id,
                raw_text=f"Python JD {index}",
                content_hash=hashlib.sha256(f"Python JD {index}".encode()).hexdigest(),
            )
            for index in range(3)
        ]
        session.add_all(jds)
        session.flush()
        market = models.MarketProfile(
            target_role_id=target.id,
            sample_fingerprint=derived_state_fingerprint(target.id, jds),
            sample_count=3,
            status="VALID",
        )
        requirement = models.MarketRequirement(
            market_profile=market,
            name="Python",
            category="SKILL",
            occurrence_count=3,
            frequency_ratio=1.0,
            sort_order=1,
        )
        session.add(market)
        session.flush()
        session.add_all([
            models.MarketRequirementEvidence(
                requirement_id=requirement.id,
                job_description_id=jd.id,
                evidence_text="Python",
            )
            for jd in jds
        ])
        session.commit()
        profile_id = profile.id

    class RollbackSession(Session):
        def commit(self):
            self.flush()

    started = threading.Event()
    outcomes: list[tuple[str, str, str | None]] = []

    class SlowProvider:
        def compare(self, *, requirements, profile_facts):
            started.set()
            time.sleep(1.5)
            return GapProposalPayload(items=[])

    class FastProvider:
        def compare(self, *, requirements, profile_facts):
            return GapProposalPayload(items=[])

    def run(label: str, provider, timeout: bool = False) -> None:
        with RollbackSession(postgres_engine) as session:
            try:
                if timeout:
                    session.execute(text("SET LOCAL statement_timeout = '1s'"))
                result = create_gap_analysis(session, profile_id, provider=provider)
                outcomes.append((label, "success", str(len(result.gaps))))
            except Exception as exc:  # pragma: no cover - failure detail is asserted below
                outcomes.append((label, type(exc).__name__, str(exc)))
            finally:
                session.rollback()

    holder = threading.Thread(target=run, args=("holder", SlowProvider()))
    holder.start()
    assert started.wait(timeout=10)
    waiter = threading.Thread(target=run, args=("waiter", FastProvider(), True))
    waiter.start()
    holder.join(timeout=15)
    waiter.join(timeout=15)

    assert sorted(outcomes) == [("holder", "success", "1"), ("waiter", "success", "1")]
