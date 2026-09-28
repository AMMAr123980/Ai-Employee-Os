"""Initial Enterprise Schema Migration

Revision ID: 001_initial_enterprise_schema
Revises: 
Create Date: 2026-09-16 21:15:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '001_initial_enterprise_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Tables are created via Base.metadata.create_all() or Alembic upgrade head
    pass


def downgrade() -> None:
    pass
