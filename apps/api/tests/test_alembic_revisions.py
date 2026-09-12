import ast
from pathlib import Path


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
