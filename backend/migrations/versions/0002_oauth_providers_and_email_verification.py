"""oauth providers and email verification

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-26 15:23:57.236795

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('email_verifications',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('code_hash', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('last_sent_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('sends_in_window', sa.Integer(), nullable=False),
    sa.Column('window_started', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id')
    )
    # sa.true()/sa.false() render correctly on both PostgreSQL and SQLite
    with op.batch_alter_table('repos', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_private', sa.Boolean(), server_default=sa.false(), nullable=False))

    with op.batch_alter_table('users', schema=None) as batch_op:
        # Existing accounts predate verification, so they start out verified
        batch_op.add_column(sa.Column('email_verified', sa.Boolean(), server_default=sa.true(), nullable=False))
        batch_op.add_column(sa.Column('google_sub', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('github_token_expires_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('github_refresh_enc', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('github_refresh_expires_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.create_unique_constraint('uq_users_google_sub', ['google_sub'])


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_constraint('uq_users_google_sub', type_='unique')
        batch_op.drop_column('github_refresh_expires_at')
        batch_op.drop_column('github_refresh_enc')
        batch_op.drop_column('github_token_expires_at')
        batch_op.drop_column('google_sub')
        batch_op.drop_column('email_verified')

    with op.batch_alter_table('repos', schema=None) as batch_op:
        batch_op.drop_column('is_private')

    op.drop_table('email_verifications')
