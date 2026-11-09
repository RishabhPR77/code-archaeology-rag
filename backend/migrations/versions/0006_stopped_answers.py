"""stopped answers

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-09 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0006'
down_revision: Union[str, Sequence[str], None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # An answer the user stopped part-way: kept in the chat with the text written so far
    with op.batch_alter_table('queries', schema=None) as batch_op:
        batch_op.add_column(sa.Column('stopped', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table('queries', schema=None) as batch_op:
        batch_op.drop_column('stopped')
