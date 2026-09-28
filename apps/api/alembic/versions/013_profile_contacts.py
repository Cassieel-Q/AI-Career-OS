"""Add objective contact facts to UserProfile."""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision = "013_profile_contacts"
down_revision: Union[str, None] = "012_workflow_state"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    for name, length in (("full_name", 255), ("phone", 64), ("email", 255), ("city", 255)):
        op.add_column("user_profiles", sa.Column(name, sa.String(length=length), nullable=True))

def downgrade() -> None:
    for name in ("city", "email", "phone", "full_name"):
        op.drop_column("user_profiles", name)
