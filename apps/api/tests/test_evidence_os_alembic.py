import ast
from pathlib import Path

VERSIONS_DIR = Path(__file__).parents[1] / "alembic" / "versions"


def test_011_evidence_os_follows_010_v02() -> None:
    tree = ast.parse((VERSIONS_DIR / "011_evidence_os.py").read_text(encoding="utf-8"))
    assignments = {
        target.id: assignment.value.value
        for assignment in ast.walk(tree)
        if isinstance(assignment, ast.Assign)
        and isinstance(assignment.value, ast.Constant)
        and isinstance(assignment.value.value, str)
        for target in assignment.targets
        if isinstance(target, ast.Name)
    }
    assert assignments["revision"] == "011_evidence_os"
    assert assignments["down_revision"] == "010_v02_integrated_job_mission"
    assert len(assignments["revision"]) <= 32
