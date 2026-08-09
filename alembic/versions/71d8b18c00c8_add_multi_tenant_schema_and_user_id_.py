"""add multi-tenant schema and user_id foreign keys

Revision ID: 71d8b18c00c8
Revises: 
Create Date: 2026-08-08 20:05:39.662901

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import fastapi_users_db_sqlalchemy.generics


# revision identifiers, used by Alembic.
revision: str = '71d8b18c00c8'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema — create all tables with the multi-tenant schema."""
    op.create_table('users',
        sa.Column('id', fastapi_users_db_sqlalchemy.generics.GUID(), nullable=False),
        sa.Column('email', sa.String(length=320), nullable=False),
        sa.Column('hashed_password', sa.String(length=1024), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('is_superuser', sa.Boolean(), nullable=False),
        sa.Column('is_verified', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)

    op.create_table('bundles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', fastapi_users_db_sqlalchemy.generics.GUID(), nullable=True),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('purchase_date', sa.String(), nullable=True),
        sa.Column('captured_at', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'title', name='uq_user_bundle_title'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )
    op.create_index(op.f('ix_bundles_id'), 'bundles', ['id'], unique=False)
    op.create_index(op.f('ix_bundles_user_id'), 'bundles', ['user_id'], unique=False)
    op.create_index(op.f('ix_bundles_title'), 'bundles', ['title'], unique=False)

    op.create_table('evaluated_bundles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', fastapi_users_db_sqlalchemy.generics.GUID(), nullable=True),
        sa.Column('bundle_name', sa.String(), nullable=False),
        sa.Column('url', sa.String(), nullable=False),
        sa.Column('machine_name', sa.String(), nullable=True),
        sa.Column('end_date', sa.String(), nullable=True),
        sa.Column('evaluated_at', sa.String(), nullable=True),
        sa.Column('expired_at', sa.String(), nullable=True),
        sa.Column('evaluation', sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'url', name='uq_user_evaluated_bundle_url'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )
    op.create_index(op.f('ix_evaluated_bundles_id'), 'evaluated_bundles', ['id'], unique=False)
    op.create_index(op.f('ix_evaluated_bundles_url'), 'evaluated_bundles', ['url'], unique=False)
    op.create_index(op.f('ix_evaluated_bundles_user_id'), 'evaluated_bundles', ['user_id'], unique=False)

    op.create_table('items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', fastapi_users_db_sqlalchemy.generics.GUID(), nullable=True),
        sa.Column('bundle_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('publisher', sa.String(), nullable=False),
        sa.Column('item_type', sa.String(), nullable=False),
        sa.Column('available_formats', sa.JSON(), nullable=False),
        sa.Column('downloads', sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'bundle_id', 'title', name='uq_user_item_bundle_title'),
        sa.ForeignKeyConstraint(['bundle_id'], ['bundles.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )
    op.create_index(op.f('ix_items_id'), 'items', ['id'], unique=False)
    op.create_index(op.f('ix_items_user_id'), 'items', ['user_id'], unique=False)
    op.create_index(op.f('ix_items_title'), 'items', ['title'], unique=False)
    op.create_index(op.f('ix_items_publisher'), 'items', ['publisher'], unique=False)


def downgrade() -> None:
    """Drop all tables."""
    op.drop_table('items')
    op.drop_table('evaluated_bundles')
    op.drop_table('bundles')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')