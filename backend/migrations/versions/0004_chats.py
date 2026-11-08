"""chats on the Ask tab

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-08 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0004'
down_revision: Union[str, Sequence[str], None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _title(question: str) -> str:
    text = " ".join(question.split())
    return text if len(text) <= 80 else text[:79].rstrip() + "…"


def _group_existing_questions():
    """Questions asked before chats existed become one chat per repository, in their original order."""
    conn = op.get_bind()
    queries = sa.table('queries', sa.column('repo_id'), sa.column('kind'), sa.column('question'),
                       sa.column('created_at'), sa.column('id'), sa.column('conversation_id'))
    # A full Table (not sa.table) so SQLAlchemy knows the primary key and can return each new id.
    # The dates stay untyped: they're copied from queries exactly as the database returned them.
    conversations = sa.Table('conversations', sa.MetaData(), sa.Column('id', sa.Integer, primary_key=True),
                             sa.Column('repo_id', sa.String(32)), sa.Column('title', sa.String(200)),
                             sa.Column('created_at'), sa.Column('updated_at'))
    rows = conn.execute(sa.select(queries.c.repo_id, queries.c.question, queries.c.created_at)
                        .where(queries.c.kind == 'ask')
                        .order_by(queries.c.repo_id, queries.c.created_at, queries.c.id)).all()
    first, last = {}, {}
    for repo_id, question, created in rows:
        first.setdefault(repo_id, (question, created))
        last[repo_id] = created
    for repo_id, (question, created) in first.items():
        result = conn.execute(conversations.insert().values(
            repo_id=repo_id, title=_title(question), created_at=created, updated_at=last[repo_id]))
        conn.execute(queries.update()
                     .where(queries.c.repo_id == repo_id, queries.c.kind == 'ask')
                     .values(conversation_id=result.inserted_primary_key[0]))


def upgrade() -> None:
    op.create_table('conversations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('repo_id', sa.String(length=32), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['repo_id'], ['repos.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('conversations', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_conversations_repo_id'), ['repo_id'], unique=False)

    with op.batch_alter_table('queries', schema=None) as batch_op:
        batch_op.add_column(sa.Column('conversation_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_queries_conversation_id'), ['conversation_id'], unique=False)
        batch_op.create_foreign_key('fk_queries_conversation_id', 'conversations', ['conversation_id'], ['id'],
                                    ondelete='CASCADE')

    _group_existing_questions()


def downgrade() -> None:
    with op.batch_alter_table('queries', schema=None) as batch_op:
        batch_op.drop_constraint('fk_queries_conversation_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_queries_conversation_id'))
        batch_op.drop_column('conversation_id')

    with op.batch_alter_table('conversations', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_conversations_repo_id'))

    op.drop_table('conversations')
