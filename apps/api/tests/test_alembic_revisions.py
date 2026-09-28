import ast
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

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
    }
    assert script.get_heads() == ["013_profile_contacts"]
    revisions = {revision.revision: revision.down_revision for revision in script.walk_revisions()}
    assert revisions == expected_down_revisions
