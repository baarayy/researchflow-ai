"""initial schema

Revision ID: 0001
Revises: 
Create Date: 2026-10-09 18:07:21.457216
"""
# Some lines below were adjusted by hand (pgvector extension and configurable dimension).
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from app.core.config import get_settings

revision: str = '0001'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    # The vector dimension is read from EMBEDDING_DIM when the migration runs.
    op.create_table('documents',
    sa.Column('owner_id', sa.String(length=64), nullable=False),
    sa.Column('filename', sa.String(length=255), nullable=False),
    sa.Column('content_type', sa.String(length=100), nullable=False),
    sa.Column('size_bytes', sa.Integer(), nullable=False),
    sa.Column('sha256', sa.String(length=64), nullable=False),
    sa.Column('storage_key', sa.String(length=255), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('page_count', sa.Integer(), nullable=True),
    sa.Column('chunk_count', sa.Integer(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_documents')),
    sa.UniqueConstraint('owner_id', 'sha256', name='uq_documents_owner_sha256')
    )
    op.create_index(op.f('ix_documents_owner_id'), 'documents', ['owner_id'], unique=False)
    op.create_table('research_sessions',
    sa.Column('owner_id', sa.String(length=64), nullable=False),
    sa.Column('question', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('stage', sa.String(length=64), nullable=True),
    sa.Column('iteration', sa.Integer(), nullable=False),
    sa.Column('max_iterations', sa.Integer(), nullable=False),
    sa.Column('options', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('pending_approval', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('critic_feedback', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('idempotency_key', sa.String(length=128), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_research_sessions')),
    sa.UniqueConstraint('owner_id', 'idempotency_key', name='uq_research_sessions_idem')
    )
    op.create_index('ix_research_sessions_owner_created', 'research_sessions', ['owner_id', 'created_at'], unique=False)
    op.create_index(op.f('ix_research_sessions_status'), 'research_sessions', ['status'], unique=False)
    op.create_table('document_chunks',
    sa.Column('document_id', sa.Uuid(), nullable=False),
    sa.Column('chunk_index', sa.Integer(), nullable=False),
    sa.Column('page_number', sa.Integer(), nullable=True),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('embedding', Vector(get_settings().embedding_dim), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], name=op.f('fk_document_chunks_document_id_documents'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_document_chunks')),
    sa.UniqueConstraint('document_id', 'chunk_index', name='uq_document_chunks_doc_index')
    )
    op.create_index(op.f('ix_document_chunks_document_id'), 'document_chunks', ['document_id'], unique=False)
    op.create_index('ix_document_chunks_embedding_hnsw', 'document_chunks', ['embedding'], unique=False, postgresql_using='hnsw', postgresql_ops={'embedding': 'vector_cosine_ops'})
    op.create_table('evidence_items',
    sa.Column('session_id', sa.Uuid(), nullable=False),
    sa.Column('evidence_key', sa.String(length=32), nullable=False),
    sa.Column('source_key', sa.String(length=32), nullable=False),
    sa.Column('task_key', sa.String(length=16), nullable=True),
    sa.Column('claim', sa.Text(), nullable=False),
    sa.Column('quote', sa.Text(), nullable=True),
    sa.Column('quote_verified', sa.Boolean(), nullable=False),
    sa.Column('confidence', sa.Float(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['session_id'], ['research_sessions.id'], name=op.f('fk_evidence_items_session_id_research_sessions'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_evidence_items')),
    sa.UniqueConstraint('session_id', 'evidence_key', name='uq_evidence_key')
    )
    op.create_index(op.f('ix_evidence_items_session_id'), 'evidence_items', ['session_id'], unique=False)
    op.create_table('reports',
    sa.Column('session_id', sa.Uuid(), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('markdown', sa.Text(), nullable=False),
    sa.Column('content', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['session_id'], ['research_sessions.id'], name=op.f('fk_reports_session_id_research_sessions'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_reports')),
    sa.UniqueConstraint('session_id', name=op.f('uq_reports_session_id'))
    )
    op.create_table('research_tasks',
    sa.Column('session_id', sa.Uuid(), nullable=False),
    sa.Column('task_key', sa.String(length=16), nullable=False),
    sa.Column('question', sa.Text(), nullable=False),
    sa.Column('rationale', sa.Text(), nullable=False),
    sa.Column('evidence_type', sa.String(length=64), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('origin', sa.String(length=16), nullable=False),
    sa.Column('iteration_added', sa.Integer(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['session_id'], ['research_sessions.id'], name=op.f('fk_research_tasks_session_id_research_sessions'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_research_tasks')),
    sa.UniqueConstraint('session_id', 'task_key', name='uq_research_tasks_key')
    )
    op.create_index(op.f('ix_research_tasks_session_id'), 'research_tasks', ['session_id'], unique=False)
    op.create_table('sources',
    sa.Column('session_id', sa.Uuid(), nullable=False),
    sa.Column('source_key', sa.String(length=32), nullable=False),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('title', sa.Text(), nullable=False),
    sa.Column('url', sa.Text(), nullable=True),
    sa.Column('document_id', sa.Uuid(), nullable=True),
    sa.Column('page_number', sa.Integer(), nullable=True),
    sa.Column('excerpt', sa.Text(), nullable=False),
    sa.Column('content_kind', sa.String(length=16), nullable=False),
    sa.Column('published_date', sa.String(length=32), nullable=True),
    sa.Column('retrieved_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('possibly_outdated', sa.Boolean(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], name=op.f('fk_sources_document_id_documents'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['session_id'], ['research_sessions.id'], name=op.f('fk_sources_session_id_research_sessions'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sources')),
    sa.UniqueConstraint('session_id', 'source_key', name='uq_sources_key')
    )
    op.create_index(op.f('ix_sources_session_id'), 'sources', ['session_id'], unique=False)
    op.create_table('workflow_events',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('session_id', sa.Uuid(), nullable=False),
    sa.Column('type', sa.String(length=32), nullable=False),
    sa.Column('node', sa.String(length=64), nullable=True),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['session_id'], ['research_sessions.id'], name=op.f('fk_workflow_events_session_id_research_sessions'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_workflow_events'))
    )
    op.create_index('ix_workflow_events_session_id_id', 'workflow_events', ['session_id', 'id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_workflow_events_session_id_id', table_name='workflow_events')
    op.drop_table('workflow_events')
    op.drop_index(op.f('ix_sources_session_id'), table_name='sources')
    op.drop_table('sources')
    op.drop_index(op.f('ix_research_tasks_session_id'), table_name='research_tasks')
    op.drop_table('research_tasks')
    op.drop_table('reports')
    op.drop_index(op.f('ix_evidence_items_session_id'), table_name='evidence_items')
    op.drop_table('evidence_items')
    op.drop_index('ix_document_chunks_embedding_hnsw', table_name='document_chunks', postgresql_using='hnsw', postgresql_ops={'embedding': 'vector_cosine_ops'})
    op.drop_index(op.f('ix_document_chunks_document_id'), table_name='document_chunks')
    op.drop_table('document_chunks')
    op.drop_index(op.f('ix_research_sessions_status'), table_name='research_sessions')
    op.drop_index('ix_research_sessions_owner_created', table_name='research_sessions')
    op.drop_table('research_sessions')
    op.drop_index(op.f('ix_documents_owner_id'), table_name='documents')
    op.drop_table('documents')
