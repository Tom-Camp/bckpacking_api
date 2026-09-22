"""Moving required Trip fields

Revision ID: 8528f4b28b1e
Revises: 6132644ef769
Create Date: 2026-09-22 17:05:54.484652

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "8528f4b28b1e"
down_revision: str | Sequence[str] | None = "6132644ef769"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
