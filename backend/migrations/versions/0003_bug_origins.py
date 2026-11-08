"""bug origins

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-08 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, Sequence[str], None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Empty for repositories ingested before this existed; a re-sync fills it in
    with op.batch_alter_table('repo_data', schema=None) as batch_op:
        batch_op.add_column(sa.Column('origins_json', sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('repo_data', schema=None) as batch_op:
        batch_op.drop_column('origins_json')
