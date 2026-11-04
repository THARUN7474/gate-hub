"""SQLAlchemy 2 models - THE integration contract between the three agent
workstreams (extraction, database/analytics, UI). Change only by Alembic
migration. Targets PostgreSQL 17 + pgvector (docker compose); the ORM stays
dialect-portable so tests and a no-Docker dev fallback run on SQLite.

Three data states are kept separate at all times:
  raw extraction -> machine suggestion (provenance=inferred) -> human-verified
  (provenance=validated / status=verified). Re-ingestion must never erase
  human decisions."""
from __future__ import annotations
import datetime as dt
from sqlalchemy import (Boolean, DateTime, Float, ForeignKey, Index, Integer,
                        JSON, String, Text, UniqueConstraint)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)

class Base(DeclarativeBase):
    pass

class Document(Base):
    """A raw source file. Immutable once registered; dedup by sha256."""
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)   # doc-<sha16>
    filename: Mapped[str] = mapped_column(String(500))
    sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    file_path: Mapped[str] = mapped_column(String(1000))
    source_url: Mapped[str | None] = mapped_column(String(1000))
    doc_type: Mapped[str] = mapped_column(String(20))      # paper|key|syllabus|book|fixture
    rights_status: Mapped[str] = mapped_column(String(20), default="official")
    status: Mapped[str] = mapped_column(String(20), default="registered")
    ingested_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class Paper(Base):
    __tablename__ = "papers"
    __table_args__ = (UniqueConstraint("year", "session", "branch", name="uq_paper_identity"),)
    id: Mapped[str] = mapped_column(String(40), primary_key=True)   # GATE-CS-2024-S1
    year: Mapped[int] = mapped_column(Integer)
    branch: Mapped[str] = mapped_column(String(10), default="CS")
    session: Mapped[str] = mapped_column(String(20))                # S1, S2...
    paper_code: Mapped[str | None] = mapped_column(String(20))
    document_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id"))
    expected_questions: Mapped[int | None] = mapped_column(Integer)  # NULL = derive + reconcile
    expected_marks: Mapped[float | None] = mapped_column(Float)
    derived_questions: Mapped[int | None] = mapped_column(Integer)
    derived_marks: Mapped[float | None] = mapped_column(Float)
    reconciled: Mapped[bool] = mapped_column(Boolean, default=False)
    questions: Mapped[list["Question"]] = relationship(back_populates="paper")

class Question(Base):
    __tablename__ = "questions"
    __table_args__ = (
        UniqueConstraint("paper_id", "q_number", name="uq_question_number"),
        Index("ix_questions_status", "needs_review"),
        Index("ix_questions_type", "q_type"),
    )
    id: Mapped[str] = mapped_column(String(50), primary_key=True)   # GATE-CS-2024-S1-Q17
    paper_id: Mapped[str] = mapped_column(ForeignKey("papers.id"), index=True)
    q_number: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text, default="")
    marks: Mapped[float | None] = mapped_column(Float)              # NULL => review, never guessed
    q_type: Mapped[str | None] = mapped_column(String(8))           # MCQ|MSQ|NAT|NULL => review
    page_start: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)
    image_path: Mapped[str | None] = mapped_column(String(1000))    # legacy stored crop (superseded by regions_json)
    regions_json: Mapped[str | None] = mapped_column(Text)          # [{page,y_top,y_bottom}] into the source PDF
    group_id: Mapped[str | None] = mapped_column(String(50))        # legacy linked/common-data groups
    extraction_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    extraction_status: Mapped[str] = mapped_column(String(20), default="extracted")   # extracted | ocr
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    review_reason: Mapped[str | None] = mapped_column(Text)
    # Label exactly as the paper prints it ("GA 5", "CS 12", "Q 56"). Papers before 2022
    # restart numbering at CS Q.1 after the GA block; q_number is the unique 1..65 id.
    printed_label: Mapped[str | None] = mapped_column(String(24))
    paper: Mapped[Paper] = relationship(back_populates="questions")
    options: Mapped[list["Option"]] = relationship(cascade="all, delete-orphan")

class Option(Base):
    __tablename__ = "options"
    __table_args__ = (UniqueConstraint("question_id", "label", name="uq_option_label"),)
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    question_id: Mapped[str] = mapped_column(ForeignKey("questions.id"), index=True)
    label: Mapped[str] = mapped_column(String(4))
    content: Mapped[str] = mapped_column(Text)

class AnswerKey(Base):
    """Models key anomalies: NAT ranges, MSQ sets, dropped/bonus, corrected
    final-key versions. Missing keys are listed, never guessed."""
    __tablename__ = "answer_keys"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    question_id: Mapped[str] = mapped_column(ForeignKey("questions.id"), unique=True)
    answer_kind: Mapped[str] = mapped_column(String(12))   # mcq_single|msq_set|nat_range|nat_value|dropped
    answer_list: Mapped[list] = mapped_column(JSON, default=list)
    answer_min: Mapped[float | None] = mapped_column(Float)
    answer_max: Mapped[float | None] = mapped_column(Float)
    key_version: Mapped[str | None] = mapped_column(String(30))
    source_document_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id"))
    notes: Mapped[str | None] = mapped_column(Text)

class TaxonomyNode(Base):
    __tablename__ = "taxonomy_nodes"
    __table_args__ = (UniqueConstraint("node_id", "version", name="uq_taxonomy_node"),)
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    node_id: Mapped[str] = mapped_column(String(20))
    version: Mapped[str] = mapped_column(String(30), index=True)
    parent_id: Mapped[str | None] = mapped_column(String(20))
    level: Mapped[str] = mapped_column(String(10))          # section|topic|concept
    name: Mapped[str] = mapped_column(String(200))
    syllabus_text: Mapped[str | None] = mapped_column(Text)
    provenance: Mapped[str] = mapped_column(String(12))     # official|inferred|validated
    deprecated: Mapped[bool] = mapped_column(Boolean, default=False)

class ClassificationRun(Base):
    __tablename__ = "classification_runs"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # Widths: `auto`/ensemble runs record composite values such as
    # "auto:gemini+openrouter" and "modelA+modelB+modelC"; SQLite ignores
    # VARCHAR length but PostgreSQL enforces it (migration 0004).
    model: Mapped[str] = mapped_column(String(300))
    prompt_version: Mapped[str] = mapped_column(String(40))
    provider: Mapped[str] = mapped_column(String(120))
    started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    stats: Mapped[dict | None] = mapped_column(JSON)

class Classification(Base):
    """Machine suggestions live here with provenance=inferred until a human
    verifies. primary_topic_id is the single additive attribution: headline
    counts/marks use it only, so totals never double-count."""
    __tablename__ = "classifications"
    __table_args__ = (UniqueConstraint("question_id", "taxonomy_version", "prompt_version",
                                       name="uq_classification_version"),)
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    question_id: Mapped[str] = mapped_column(ForeignKey("questions.id"), index=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("classification_runs.id"))
    taxonomy_version: Mapped[str] = mapped_column(String(30))
    section_id: Mapped[str] = mapped_column(String(20), index=True)
    primary_topic_id: Mapped[str] = mapped_column(String(20))
    topic_weight: Mapped[dict | None] = mapped_column(JSON)  # fractional view, labelled
    concept_ids: Mapped[list | None] = mapped_column(JSON)
    what_it_tests: Mapped[str | None] = mapped_column(Text)
    prerequisite_ids: Mapped[list | None] = mapped_column(JSON)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    agreement: Mapped[float | None] = mapped_column(Float)        # ensemble: fraction of providers on winning topic
    combo_score: Mapped[float | None] = mapped_column(Float)      # agreement x mean confidence (heuristic, see classify.combo_score)
    provider_votes: Mapped[list | None] = mapped_column(JSON)     # per-provider {provider,model,topic,confidence} or {provider,error}
    provider_count: Mapped[int | None] = mapped_column(Integer)   # providers that answered (errors excluded)
    evidence_quote: Mapped[str | None] = mapped_column(Text)
    raw_response: Mapped[dict | None] = mapped_column(JSON)
    provenance: Mapped[str] = mapped_column(String(12), default="inferred")
    status: Mapped[str] = mapped_column(String(12), default="suggested", index=True)  # suggested|verified|flagged
    model: Mapped[str] = mapped_column(String(300))
    prompt_version: Mapped[str] = mapped_column(String(40))
    classified_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class ClassificationProposal(Base):
    """Independent provider proposals: one row per (question, provider, model,
    prompt_version). These NEVER touch the classifications table - the agent/manual
    labels and any human review there stay exactly as they are - so an API run adds
    a second opinion instead of overwriting the first pass. Analytics only reads
    `classifications`, so proposals can never double-count headline figures;
    agreement is computed explicitly (classify.proposal_agreement)."""
    __tablename__ = "classification_proposals"
    __table_args__ = (UniqueConstraint("question_id", "provider", "model", "prompt_version",
                                       name="uq_proposal_provider"),)
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    question_id: Mapped[str] = mapped_column(ForeignKey("questions.id"), index=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("classification_runs.id"))
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(300))
    prompt_version: Mapped[str] = mapped_column(String(40))
    taxonomy_version: Mapped[str] = mapped_column(String(30))
    section_id: Mapped[str] = mapped_column(String(20))
    primary_topic_id: Mapped[str] = mapped_column(String(20))
    topic_weight: Mapped[dict | None] = mapped_column(JSON)
    concept_ids: Mapped[list | None] = mapped_column(JSON)
    what_it_tests: Mapped[str | None] = mapped_column(Text)
    prerequisite_ids: Mapped[list | None] = mapped_column(JSON)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    evidence_quote: Mapped[str | None] = mapped_column(Text)
    raw_response: Mapped[dict | None] = mapped_column(JSON)
    # SHA-256 of the exact evidence the provider saw (question text + options in label
    # order; classify.question_content_hash). If the question is later re-extracted or
    # OCR-corrected, the stored hash stops matching the live question and
    # classify.proposal_staleness flags the proposal as stale instead of silently
    # comparing an old opinion against changed input. NULL on proposals written
    # before this column existed.
    source_content_hash: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(12), default="suggested", index=True)  # suggested|flagged
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class BenchmarkSample(Base):
    """Stratified benchmark sample selected for HUMAN gold review (v11).

    Rows are created by the `benchmark-sample` CLI with status
    'pending_user_review'. The tool NEVER assigns gold labels: only a human
    decision turns a row into 'gold_verified' (or 'gold_rejected'), recorded
    with reviewer + reviewed_at. validation.metrics.evaluate_benchmark reads
    ONLY gold_verified rows, so an unreviewed sample can never leak into
    accuracy numbers as fabricated gold."""
    __tablename__ = "benchmark_samples"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    question_id: Mapped[str] = mapped_column(ForeignKey("questions.id"), unique=True, index=True)
    batch: Mapped[str] = mapped_column(String(40), index=True)     # e.g. "bench-2026-11-04"
    stratum: Mapped[str] = mapped_column(String(60))               # e.g. "2021-S1/marks1"
    status: Mapped[str] = mapped_column(String(20), default="pending_user_review", index=True)
    sampled_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    reviewed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    reviewer: Mapped[str | None] = mapped_column(String(60))
    gold_section_id: Mapped[str | None] = mapped_column(String(20))
    gold_primary_topic_id: Mapped[str | None] = mapped_column(String(20))
    gold_concept_ids: Mapped[list | None] = mapped_column(JSON)
    note: Mapped[str | None] = mapped_column(Text)
    # FROZEN machine prediction at sample-creation time (v11 fix): evaluation compares
    # THIS against the human's gold, never the live classifications row - after a human
    # correction the live row IS the gold, so scoring it would be a tautology.
    # NULL baseline topic = the question had no prediction when sampled.
    baseline_section_id: Mapped[str | None] = mapped_column(String(20))
    baseline_primary_topic_id: Mapped[str | None] = mapped_column(String(20))
    baseline_concept_ids: Mapped[list | None] = mapped_column(JSON)
    baseline_confidence: Mapped[float | None] = mapped_column(Float)
    baseline_run_id: Mapped[int | None] = mapped_column(ForeignKey("classification_runs.id"))
    # SHA-256 of question text+options at sampling (classify.question_content_hash):
    # if the question is re-extracted/OCR-fixed later, the frozen prediction no longer
    # describes the current input and evaluation marks the row stale instead of scoring it.
    baseline_content_hash: Mapped[str | None] = mapped_column(String(64))

class QuestionMetadata(Base):
    __tablename__ = "question_metadata"
    question_id: Mapped[str] = mapped_column(ForeignKey("questions.id"), primary_key=True)
    skills: Mapped[list | None] = mapped_column(JSON)
    cognitive_level: Mapped[str | None] = mapped_column(String(20))
    difficulty: Mapped[str | None] = mapped_column(String(12))  # tentative until human-set
    explanation: Mapped[str | None] = mapped_column(Text)

class ConceptPrerequisite(Base):
    __tablename__ = "concept_prerequisites"
    concept_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    required_concept_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    provenance: Mapped[str] = mapped_column(String(12), default="inferred")
    source_note: Mapped[str | None] = mapped_column(Text)

class QuestionEmbedding(Base):
    """Placeholder. Native pgvector column is added by a later migration once
    the embedding model (and dimension) is chosen. Optional Day-5+ work."""
    __tablename__ = "question_embeddings"
    question_id: Mapped[str] = mapped_column(ForeignKey("questions.id"), primary_key=True)
    model: Mapped[str] = mapped_column(String(60))
    model_version: Mapped[str] = mapped_column(String(30))
    embedding_json: Mapped[list | None] = mapped_column(JSON)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class ReviewEvent(Base):
    """Audit log. Every human decision; corrections survive pipeline reruns."""
    __tablename__ = "review_events"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    question_id: Mapped[str] = mapped_column(ForeignKey("questions.id"), index=True)
    field: Mapped[str] = mapped_column(String(30))
    before: Mapped[str | None] = mapped_column(Text)
    after: Mapped[str | None] = mapped_column(Text)
    reviewer: Mapped[str] = mapped_column(String(60))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    note: Mapped[str | None] = mapped_column(Text)

class ProcessingRun(Base):
    __tablename__ = "processing_runs"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))
    file_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id"))
    status: Mapped[str] = mapped_column(String(20), default="started")
    model: Mapped[str | None] = mapped_column(String(300))
    errors: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    detail: Mapped[dict | None] = mapped_column(JSON)
