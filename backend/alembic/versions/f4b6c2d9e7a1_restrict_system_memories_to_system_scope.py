"""restrict system_memories to system scope

Revision ID: f4b6c2d9e7a1
Revises: e1a4c8d3b9f2
Create Date: 2026-02-14 11:30:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f4b6c2d9e7a1"
down_revision: Union[str, Sequence[str], None] = "e1a4c8d3b9f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Migrate system memories to single-level scope and tighten constraints."""
    op.execute("UPDATE system_memories SET scope = 'system', scope_name = NULL")
    op.drop_constraint("ck_system_memories_scope_valid", "system_memories", type_="check")
    op.drop_constraint("ck_system_memories_scope_name_required", "system_memories", type_="check")
    op.create_check_constraint(
        "ck_system_memories_scope_system",
        "system_memories",
        "scope = 'system'",
    )
    op.create_check_constraint(
        "ck_system_memories_scope_name_null",
        "system_memories",
        "scope_name IS NULL",
    )


def downgrade() -> None:
    """Restore original multi-scope constraints for system memories."""
    op.drop_constraint("ck_system_memories_scope_name_null", "system_memories", type_="check")
    op.drop_constraint("ck_system_memories_scope_system", "system_memories", type_="check")
    op.create_check_constraint(
        "ck_system_memories_scope_valid",
        "system_memories",
        "scope IN ('global', 'site', 'device')",
    )
    op.create_check_constraint(
        "ck_system_memories_scope_name_required",
        "system_memories",
        "(scope = 'global' AND scope_name IS NULL) OR "
        "(scope IN ('site', 'device') AND scope_name IS NOT NULL)",
    )
    op.execute("UPDATE system_memories SET scope = 'global', scope_name = NULL")
