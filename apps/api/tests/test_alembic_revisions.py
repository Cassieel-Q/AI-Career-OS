import ast
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect

from app.database import Base
from app import models  # noqa: F401
from app.evidence_os import models as evidence_os_models  # noqa: F401

VERSIONS_DIR = Path(__file__).parents[1] / "alembic" / "versions"


def test_alembic_revision_ids_fit_alembic_version_column() -> None:
    for migration_path in sorted(VERSIONS_DIR.glob("*.py")):
        tree = ast.parse(migration_path.read_text(encoding="utf-8"))
        revision_values = [
            assignment.value.value
            for assignment in ast.walk(tree)
            if isinstance(assignment, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "revision" for target in assignment.targets)
            and isinstance(assignment.value, ast.Constant)
            and isinstance(assignment.value.value, str)
        ]
        assert revision_values, f"Missing revision ID in {migration_path.name}"
        for revision in revision_values:
            assert len(revision) <= 32, f"Alembic revision ID is too long: {migration_path.name}: {revision}"


def test_career_preferences_revision_follows_credential_details() -> None:
    tree = ast.parse((VERSIONS_DIR / "004_career_preferences.py").read_text(encoding="utf-8"))
    assignments = {
        target.id: assignment.value.value
        for assignment in ast.walk(tree)
        if isinstance(assignment, ast.Assign)
        and isinstance(assignment.value, ast.Constant)
        and isinstance(assignment.value.value, str)
        for target in assignment.targets
        if isinstance(target, ast.Name)
    }
    assert assignments["revision"] == "004_career_preferences"
    assert assignments["down_revision"] == "003_credential_details"
    assert len(assignments["revision"]) <= 32


def test_role_explorations_revision_follows_career_preferences() -> None:
    tree = ast.parse((VERSIONS_DIR / "005_role_explorations.py").read_text(encoding="utf-8"))
    assignments = {
        target.id: assignment.value.value
        for assignment in ast.walk(tree)
        if isinstance(assignment, ast.Assign)
        and isinstance(assignment.value, ast.Constant)
        and isinstance(assignment.value.value, str)
        for target in assignment.targets
        if isinstance(target, ast.Name)
    }
    assert assignments["revision"] == "005_role_explorations"
    assert assignments["down_revision"] == "004_career_preferences"
    revisions = []
    for migration_path in VERSIONS_DIR.glob("*.py"):
        migration_tree = ast.parse(migration_path.read_text(encoding="utf-8"))
        for assignment in ast.walk(migration_tree):
            if (
                isinstance(assignment, ast.Assign)
                and isinstance(assignment.value, ast.Constant)
                and isinstance(assignment.value.value, str)
                and any(isinstance(target, ast.Name) and target.id == "revision" for target in assignment.targets)
            ):
                revisions.append(assignment.value.value)
    assert "005_role_explorations" in revisions


def test_target_roles_revision_is_latest_and_follows_role_explorations() -> None:
    tree = ast.parse((VERSIONS_DIR / "006_target_roles.py").read_text(encoding="utf-8"))
    assignments = {
        target.id: assignment.value.value
        for assignment in ast.walk(tree)
        if isinstance(assignment, ast.Assign)
        and isinstance(assignment.value, ast.Constant)
        and isinstance(assignment.value.value, str)
        for target in assignment.targets
        if isinstance(target, ast.Name)
    }
    assert assignments["revision"] == "006_target_roles"
    assert assignments["down_revision"] == "005_role_explorations"
    assert len(assignments["revision"]) <= 32


def test_job_descriptions_revision_is_latest_and_follows_target_roles() -> None:
    tree = ast.parse((VERSIONS_DIR / "007_job_descriptions.py").read_text(encoding="utf-8"))
    assignments = {
        target.id: assignment.value.value
        for assignment in ast.walk(tree)
        if isinstance(assignment, ast.Assign)
        and isinstance(assignment.value, ast.Constant)
        and isinstance(assignment.value.value, str)
        for target in assignment.targets
        if isinstance(target, ast.Name)
    }
    assert assignments["revision"] == "007_job_descriptions"
    assert assignments["down_revision"] == "006_target_roles"
    assert len(assignments["revision"]) <= 32


def test_p0_completion_revision_follows_job_descriptions() -> None:
    tree = ast.parse((VERSIONS_DIR / "008_p0_completion_sprint.py").read_text(encoding="utf-8"))
    assignments = {
        target.id: assignment.value.value
        for assignment in ast.walk(tree)
        if isinstance(assignment, ast.Assign)
        and isinstance(assignment.value, ast.Constant)
        and isinstance(assignment.value.value, str)
        for target in assignment.targets
        if isinstance(target, ast.Name)
    }
    assert assignments["revision"] == "008_p0_completion_sprint"
    assert assignments["down_revision"] == "007_job_descriptions"
    assert len(assignments["revision"]) <= 32


def test_v02_resume_to_proof_revision_follows_p0_completion() -> None:
    tree = ast.parse((VERSIONS_DIR / "009_v0_2_resume_to_proof.py").read_text(encoding="utf-8"))
    assignments = {
        target.id: assignment.value.value
        for assignment in ast.walk(tree)
        if isinstance(assignment, ast.Assign)
        and isinstance(assignment.value, ast.Constant)
        and isinstance(assignment.value.value, str)
        for target in assignment.targets
        if isinstance(target, ast.Name)
    }
    assert assignments["revision"] == "009_v0_2_resume_to_proof"
    assert assignments["down_revision"] == "008_p0_completion_sprint"
    assert len(assignments["revision"]) <= 32


def test_v02_integrated_job_mission_revision_follows_resume_to_proof() -> None:
    tree = ast.parse((VERSIONS_DIR / "010_v02_integrated_job_mission.py").read_text(encoding="utf-8"))
    assignments = {
        target.id: assignment.value.value
        for assignment in ast.walk(tree)
        if isinstance(assignment, ast.Assign)
        and isinstance(assignment.value, ast.Constant)
        and isinstance(assignment.value.value, str)
        for target in assignment.targets
        if isinstance(target, ast.Name)
    }
    assert assignments["revision"] == "010_v02_integrated_job_mission"
    assert assignments["down_revision"] == "009_v0_2_resume_to_proof"
    assert len(assignments["revision"]) <= 32


def test_alembic_graph_has_single_latest_head_and_preserves_prior_chain() -> None:
    config = Config()
    config.set_main_option("script_location", str(VERSIONS_DIR.parent))
    script = ScriptDirectory.from_config(config)

    expected_down_revisions = {
        "001_create_profile_tables": None,
        "002_profile_normalization": "001_create_profile_tables",
        "003_credential_details": "002_profile_normalization",
        "004_career_preferences": "003_credential_details",
        "005_role_explorations": "004_career_preferences",
        "006_target_roles": "005_role_explorations",
        "007_job_descriptions": "006_target_roles",
        "008_p0_completion_sprint": "007_job_descriptions",
        "009_v0_2_resume_to_proof": "008_p0_completion_sprint",
        "010_v02_integrated_job_mission": "009_v0_2_resume_to_proof",
        "011_evidence_os": "010_v02_integrated_job_mission",
        "012_workflow_state": "011_evidence_os",
        "013_profile_contacts": "012_workflow_state",
        "014_resume_studio": "013_profile_contacts",
        "015_interview_records": "014_resume_studio",
        "016_education_honors": "015_interview_records",
        "017_job_applications": "016_education_honors",
        "018_assistant": "017_job_applications",
        "019_candidate_jobs": "018_assistant",
        "020_profile_boundary": "019_candidate_jobs",
        "021_question_bank": "020_profile_boundary",
        "022_template_layout": "021_question_bank",
        "023_write_proposals": "022_template_layout",
        "024_interview_agent": "023_write_proposals",
        "025_job_insight": "024_interview_agent",
        "026_webform_and_ingest": "025_job_insight",
        "027_application_binding": "026_webform_and_ingest",
        "028_trusted_facts": "027_application_binding",
        "029_delivery_snapshots": "028_trusted_facts",
        "030_fact_signature": "029_delivery_snapshots",
    }
    assert script.get_heads() == ["030_fact_signature"]
    revisions = {revision.revision: revision.down_revision for revision in script.walk_revisions()}
    assert revisions == expected_down_revisions


# Tables introduced by migrations 019–024 (this change).
NEW_TABLES = {
    "candidate_jobs",
    "application_profiles",
    "question_banks",
    "question_items",
    "reference_answers",
    "resume_template_drafts",
    "write_proposals",
    "write_receipts",
    "mock_interview_sessions",
    "mock_interview_turns",
}


def test_new_revisions_upgrade_and_downgrade_from_018(tmp_path, monkeypatch) -> None:
    """Exercise the 019–024 migrations on an isolated SQLite DB.

    The full chain cannot run on SQLite (early revisions use create_check_constraint),
    so the pre-019 schema is built with create_all and stamped at 018_assistant.
    """
    database_path = tmp_path / "migration-check.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_engine(database_url)
    new_tables = NEW_TABLES
    Base.metadata.create_all(
        engine,
        tables=[table for table in Base.metadata.sorted_tables if table.name not in new_tables],
    )
    # create_all reflects the latest ORM, so peel off the columns later migrations add,
    # to make the base schema match the 018 state.
    with engine.begin() as connection:
        for table, column in (
            ("education", "cet4_score"),
            ("education", "cet6_score"),
            ("resume_studio_documents", "layout_config"),
            ("interview_sessions", "config"),
        ):
            try:
                connection.exec_driver_sql(f"ALTER TABLE {table} DROP COLUMN {column}")
            except Exception:  # pragma: no cover - older SQLite without DROP COLUMN
                pass
    engine.dispose()

    monkeypatch.setenv("DATABASE_URL", database_url)
    config = Config()
    config.set_main_option("script_location", str(VERSIONS_DIR.parent))
    command.stamp(config, "018_assistant")

    command.upgrade(config, "head")
    engine = create_engine(database_url)
    tables = set(inspect(engine).get_table_names())
    columns = {col["name"] for col in inspect(engine).get_columns("education")}
    engine.dispose()
    assert new_tables.issubset(tables)
    assert {"cet4_score", "cet6_score"}.issubset(columns)

    command.downgrade(config, "018_assistant")
    engine = create_engine(database_url)
    tables = set(inspect(engine).get_table_names())
    engine.dispose()
    assert new_tables.isdisjoint(tables)

    command.upgrade(config, "head")
    engine = create_engine(database_url)
    assert new_tables.issubset(set(inspect(engine).get_table_names()))
    engine.dispose()
