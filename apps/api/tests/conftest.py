from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import main
from app.database import Base, get_db
from app.models import UserProfile


TEST_ENGINE = create_engine(
    "sqlite+pysqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@pytest.fixture(autouse=True)
def isolated_model_config(tmp_path, monkeypatch) -> Generator[None, None, None]:
    """把「AI 模型中心」的用户配置指向临时文件。

    否则测试会读到用户在设置页真实保存的模型（例如设了默认模型后，resume provider
    的默认值断言就会随用户配置漂移而假失败）。只隔离这一处，环境变量与数据目录
    保持原样，避免影响依赖 .env 回退和数据目录的既有用例。
    """
    from app import model_config_service

    monkeypatch.setattr(model_config_service, "config_path", lambda: tmp_path / "model_config.json")
    yield


@pytest.fixture(autouse=True)
def database() -> Generator[None, None, None]:
    Base.metadata.create_all(TEST_ENGINE)

    def override_get_db() -> Generator[Session, None, None]:
        with Session(TEST_ENGINE) as session:
            yield session

    main.app.dependency_overrides[get_db] = override_get_db
    yield
    main.app.dependency_overrides.clear()
    Base.metadata.drop_all(TEST_ENGINE)


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(main.app) as test_client:
        yield test_client


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    with Session(TEST_ENGINE) as session:
        yield session


@pytest.fixture
def persisted_profile(db_session: Session) -> UserProfile:
    from app.profile_service import create_draft_profile
    from app.resume_schemas import ResumeExtractionResult

    return create_draft_profile(
        db_session,
        ResumeExtractionResult(
            education=[{"institution": "Example University", "degree": "MSc", "evidence_text": "Example University MSc"}],
            skills=[{"name": "Python", "evidence_text": "Python"}],
            experiences=[{"title": "Research Assistant", "organization": "Lab", "evidence_text": "Research Assistant Lab"}],
            certifications=[],
        ),
    )
