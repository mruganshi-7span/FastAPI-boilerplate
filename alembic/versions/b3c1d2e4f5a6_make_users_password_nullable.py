"""make users.password nullable

Revision ID: b3c1d2e4f5a6
Revises: 381a525ae6ea
Create Date: 2026-10-22 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3c1d2e4f5a6'
down_revision: Union[str, Sequence[str], None] = '381a525ae6ea'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column('users', 'password', existing_type=sa.String(length=255), nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    # Fails if any social-only users (password IS NULL) exist; set or remove them first.
    op.alter_column('users', 'password', existing_type=sa.String(length=255), nullable=False)
