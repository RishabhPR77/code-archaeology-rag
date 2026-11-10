"""account security: email codes for any purpose, two-step sign-in, rate limits and security events
in the database, and ingest attempts

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-10 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0010'
down_revision: Union[str, Sequence[str], None] = '0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Plain ALTER TABLE and CREATE TABLE only, never batch mode: on SQLite batch mode rebuilds a table,
# and dropping `users` or `repos` would cascade to everything that belongs to them.
def upgrade() -> None:
    op.add_column('users', sa.Column('totp_secret_enc', sa.Text(), nullable=True))
    op.add_column('users', sa.Column('totp_pending_enc', sa.Text(), nullable=True))
    op.add_column('users', sa.Column('totp_enabled_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('totp_last_step', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('users', sa.Column('recovery_codes_json', sa.Text(), nullable=True))
    op.add_column('repos', sa.Column('ingest_attempts', sa.Integer(), nullable=False, server_default='0'))

    # Sign-up codes move into a table that also holds password-reset codes
    op.create_table(
        'email_codes',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('purpose', sa.String(16), nullable=False),
        sa.Column('code_hash', sa.String(64), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('last_sent_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('sends_in_window', sa.Integer(), nullable=False),
        sa.Column('window_started', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('user_id', 'purpose'),
    )
    op.create_index('ix_email_codes_user_id', 'email_codes', ['user_id'])
    # Codes already emailed keep working through the deploy
    op.execute("INSERT INTO email_codes (user_id, purpose, code_hash, expires_at, attempts, last_sent_at, "
               "sends_in_window, window_started) SELECT user_id, 'verify', code_hash, expires_at, attempts, "
               "last_sent_at, sends_in_window, window_started FROM email_verifications")
    op.drop_table('email_verifications')

    op.create_table(
        'rate_limit_hits',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('key', sa.String(64), nullable=False),
        sa.Column('at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_rate_limit_hits_key_at', 'rate_limit_hits', ['key', 'at'])
    op.create_index('ix_rate_limit_hits_at', 'rate_limit_hits', ['at'])

    op.create_table(
        'security_events',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('kind', sa.String(40), nullable=False),
        sa.Column('detail', sa.String(200), nullable=False, server_default=''),
        sa.Column('ip', sa.String(64), nullable=False, server_default=''),
        sa.Column('device', sa.String(120), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_security_events_user_id', 'security_events', ['user_id'])
    op.create_index('ix_security_events_created_at', 'security_events', ['created_at'])


def downgrade() -> None:
    op.drop_table('security_events')
    op.drop_table('rate_limit_hits')
    op.create_table(
        'email_verifications',
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('code_hash', sa.String(64), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('last_sent_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('sends_in_window', sa.Integer(), nullable=False),
        sa.Column('window_started', sa.DateTime(timezone=True), nullable=False),
    )
    op.execute("INSERT INTO email_verifications SELECT user_id, code_hash, expires_at, attempts, last_sent_at, "
               "sends_in_window, window_started FROM email_codes WHERE purpose = 'verify'")
    op.drop_table('email_codes')
    for column in ('totp_secret_enc', 'totp_pending_enc', 'totp_enabled_at', 'totp_last_step',
                   'recovery_codes_json'):
        op.drop_column('users', column)
    op.drop_column('repos', 'ingest_attempts')
