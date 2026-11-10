"""session version

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-10 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0009'
down_revision: Union[str, Sequence[str], None] = '0008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# A plain ALTER TABLE, not batch mode: on SQLite batch mode rebuilds the table, and dropping
# `users` would cascade to every repository, chat and key that belongs to it.
def upgrade() -> None:
    # Every session token carries this number; raising it signs the user out everywhere
    op.add_column('users', sa.Column('session_version', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('users', 'session_version')
