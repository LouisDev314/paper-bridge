import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
from app.core.config import settings
from app.db.database import Base

class Document(Base):
    __tablename__ = 'documents'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename = Column(String, nullable=False)
    storage_key = Column(String, nullable=False)
    checksum_sha256 = Column(String(64), nullable=False)
    version = Column(Integer, nullable=False, default=1)
    total_pages = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    pages = relationship("DocumentPage", back_populates="document", cascade="all, delete-orphan", order_by="DocumentPage.page_number")
    jobs = relationship("Job", back_populates="document", cascade="all, delete-orphan")
    extractions = relationship("Extraction", back_populates="document", cascade="all, delete-orphan")

class Job(Base):
    __tablename__ = 'jobs'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey('documents.id'), nullable=False)
    task_type = Column(String, nullable=False) # e.g., 'extract', 'embed'
    status = Column(String, default="queued") # queued | processing | needs_review | done | failed
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    document = relationship("Document", back_populates="jobs")

class DocumentPage(Base):
    __tablename__ = 'document_pages'
    __table_args__ = (UniqueConstraint("document_id", "page_number", name="uq_document_pages_document_page"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey('documents.id'), nullable=False)
    page_number = Column(Integer, nullable=False)
    text = Column(Text, nullable=True)
    text_quality_score = Column(Float, nullable=True)
    page_image_key = Column(String, nullable=True)

    document = relationship("Document", back_populates="pages")

class Extraction(Base):
    __tablename__ = 'extractions'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey('documents.id'), nullable=False)
    data = Column(JSONB, nullable=False)
    status = Column(String, default="PASSED") # PASSED | FLAGGED | FAILED
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    document = relationship("Document", back_populates="extractions")
    review_edits = relationship("ReviewEdit", back_populates="extraction", cascade="all, delete-orphan")

class ReviewEdit(Base):
    __tablename__ = 'review_edits'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    extraction_id = Column(UUID(as_uuid=True), ForeignKey('extractions.id'), nullable=False)
    original_data = Column(JSONB, nullable=False)
    updated_data = Column(JSONB, nullable=False)
    edited_by = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    extraction = relationship("Extraction", back_populates="review_edits")

class Embedding(Base):
    __tablename__ = 'embeddings'
    __table_args__ = (UniqueConstraint("document_id", "chunk_id", name="uq_embeddings_document_chunk"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey('documents.id'), nullable=False)
    chunk_id = Column(String, nullable=False)
    page_start = Column(Integer, nullable=False)
    page_end = Column(Integer, nullable=False)
    pdf_page_start = Column(Integer, nullable=False)
    pdf_page_end = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    embedding = Column(Vector(settings.openai_embed_dims), nullable=False)

    document = relationship("Document")
