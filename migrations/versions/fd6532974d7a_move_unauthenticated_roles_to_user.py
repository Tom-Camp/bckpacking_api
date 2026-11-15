"""move unauthenticated roles to user

Revision ID: fd6532974d7a
Revises: b977bf434d0d
Create Date: 2026-11-15 11:31:56.943652

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fd6532974d7a"
down_revision: str | Sequence[str] | None = "b977bf434d0d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Lightweight table stub so SQLAlchemy quotes the reserved name "user".
user_table = sa.table("user", sa.column("role", sa.String))


def upgrade() -> None:
    """Move rows off the removed "unauthenticated" role.

    UserRole is a non-native enum (VARCHAR, no CHECK constraint), so dropping the member needs no
    schema change, but SQLAlchemy raises on loading a value the enum no longer has.
    """
    op.execute(user_table.update().where(user_table.c.role == "unauthenticated").values(role="user"))


def downgrade() -> None:
    """No-op: the role can't be restored, since it's unknown which users held it."""
