"""follow-up search query

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-08 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0005'
down_revision: Union[str, Sequence[str], None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # What a follow-up question was rewritten to before searching; empty when it was used as asked
    with op.batch_alter_table('queries', schema=None) as batch_op:
        batch_op.add_column(sa.Column('search_query', sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('queries', schema=None) as batch_op:
        batch_op.drop_column('search_query')
