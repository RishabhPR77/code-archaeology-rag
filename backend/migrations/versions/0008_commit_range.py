"""commit range

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-10 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0008'
down_revision: Union[str, Sequence[str], None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# A plain ALTER TABLE, not batch mode: on SQLite batch mode rebuilds the table, and dropping
# `repos` would cascade to its data, chats and questions.
def upgrade() -> None:
    # How many of the newest commits to skip, so a repository can be ingested from a window
    # further back in its history (0 = the latest commits)
    op.add_column('repos', sa.Column('skip_commits', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('repos', 'skip_commits')
