"""create media and mediables tables

Revision ID: 7c2e4a9b1f30
Revises: d6ba61f7d6d4
Create Date: 2026-10-08 18:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7c2e4a9b1f30'
down_revision: Union[str, Sequence[str], None] = 'd6ba61f7d6d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('media',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('key', sa.String(length=500), nullable=False),
    sa.Column('file_name', sa.String(length=255), nullable=False),
    sa.Column('mime_type', sa.String(length=100), nullable=False),
    sa.Column('size', sa.BigInteger(), nullable=False),
    sa.Column('disk', sa.String(length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_media')),
    sa.UniqueConstraint('key', name=op.f('uq_media_key'))
    )
    op.create_table('mediables',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('media_id', sa.Integer(), nullable=False),
    sa.Column('mediable_type', sa.String(length=50), nullable=False),
    sa.Column('mediable_id', sa.Integer(), nullable=False),
    sa.Column('tag', sa.String(length=50), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['media_id'], ['media.id'], name=op.f('fk_mediables_media_id_media'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_mediables'))
    )
    op.create_index('ix_mediables_mediable', 'mediables', ['mediable_type', 'mediable_id', 'tag'], unique=False)
    op.create_index(op.f('ix_mediables_media_id'), 'mediables', ['media_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_mediables_media_id'), table_name='mediables')
    op.drop_index('ix_mediables_mediable', table_name='mediables')
    op.drop_table('mediables')
    op.drop_table('media')
