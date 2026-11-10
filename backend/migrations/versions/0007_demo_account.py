"""demo account

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-09 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0007'
down_revision: Union[str, Sequence[str], None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# A plain ALTER TABLE, not batch mode: on SQLite batch mode rebuilds the table, and dropping
# `users` would cascade to every repository, chat and key that belongs to it.
def upgrade() -> None:
    # The shared, read-only account behind "Try the demo"
    op.add_column('users', sa.Column('is_demo', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column('users', 'is_demo')
