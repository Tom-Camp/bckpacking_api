"""add permit_required to checklistitemkey enum

Revision ID: b6f9a62a8866
Revises: af65a881b505
Create Date: 2026-09-22 17:54:16.524818

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b6f9a62a8866"
down_revision: str | Sequence[str] | None = "af65a881b505"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TYPE checklistitemkey ADD VALUE IF NOT EXISTS 'permit_required'")


def downgrade() -> None:
    """Downgrade schema."""
    # Postgres has no DROP VALUE for enum types; removing 'permit_required' would
    # require rebuilding the type and every column/row that uses it, and any
    # tripchecklistitem rows already using it would need to be deleted or remapped
    # first. Not supported here.
    raise NotImplementedError("Cannot downgrade: Postgres does not support dropping enum values")
