from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from backend.app.db import Base


class ReadingPack(Base):
    __tablename__ = "reading_packs"

    id = Column(Integer, primary_key=True, index=True)
    pack_id = Column(String(120), nullable=False, unique=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    language = Column(String(20), nullable=False, default="en")
    level = Column(String(80), nullable=True)
    tags_json = Column(Text, nullable=False, default="[]")
    source_json = Column(Text, nullable=False, default="{}")
    metadata_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    passages = relationship("Passage", back_populates="pack", cascade="all, delete-orphan")
    questions = relationship("Question", back_populates="pack", cascade="all, delete-orphan")
    attempts = relationship("PracticeAttempt", back_populates="pack", cascade="all, delete-orphan")
    annotations = relationship("ReadingAnnotation", back_populates="pack", cascade="all, delete-orphan")


class Passage(Base):
    __tablename__ = "passages"
    __table_args__ = (UniqueConstraint("pack_db_id", "passage_id", name="uq_passage_pack_id"),)

    id = Column(Integer, primary_key=True, index=True)
    pack_db_id = Column(Integer, ForeignKey("reading_packs.id"), nullable=False)
    passage_id = Column(String(120), nullable=False, index=True)
    material_id = Column(String(120), nullable=True)
    title = Column(String(255), nullable=True)
    content = Column(Text, nullable=False)
    order_index = Column(Integer, nullable=False, default=0)
    tags_json = Column(Text, nullable=False, default="[]")
    metadata_json = Column(Text, nullable=False, default="{}")

    pack = relationship("ReadingPack", back_populates="passages")
    paragraphs = relationship("Paragraph", back_populates="passage", cascade="all, delete-orphan")
    questions = relationship("Question", back_populates="passage")
    annotations = relationship("ReadingAnnotation", back_populates="passage")


class Paragraph(Base):
    __tablename__ = "paragraphs"
    __table_args__ = (UniqueConstraint("passage_db_id", "paragraph_id", name="uq_paragraph_passage_id"),)

    id = Column(Integer, primary_key=True, index=True)
    passage_db_id = Column(Integer, ForeignKey("passages.id"), nullable=False)
    paragraph_id = Column(String(120), nullable=False)
    text = Column(Text, nullable=False)
    order_index = Column(Integer, nullable=False, default=0)

    passage = relationship("Passage", back_populates="paragraphs")
    annotations = relationship("ReadingAnnotation", back_populates="paragraph")


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = (UniqueConstraint("pack_db_id", "question_id", name="uq_question_pack_id"),)

    id = Column(Integer, primary_key=True, index=True)
    pack_db_id = Column(Integer, ForeignKey("reading_packs.id"), nullable=False)
    passage_db_id = Column(Integer, ForeignKey("passages.id"), nullable=False)
    question_id = Column(String(120), nullable=False, index=True)
    passage_id = Column(String(120), nullable=False)
    question_no = Column(String(40), nullable=True)
    question_type = Column(String(40), nullable=False)
    stem = Column(Text, nullable=False)
    answer = Column(String(1), nullable=False)
    analysis = Column(Text, nullable=True)
    evidence_hint = Column(Text, nullable=True)
    tags_json = Column(Text, nullable=False, default="[]")
    score_points = Column(Float, nullable=True)

    pack = relationship("ReadingPack", back_populates="questions")
    passage = relationship("Passage", back_populates="questions")
    options = relationship("QuestionOption", back_populates="question", cascade="all, delete-orphan")
    annotations = relationship("ReadingAnnotation", back_populates="question")


class QuestionOption(Base):
    __tablename__ = "question_options"
    __table_args__ = (UniqueConstraint("question_db_id", "label", name="uq_question_option_label"),)

    id = Column(Integer, primary_key=True, index=True)
    question_db_id = Column(Integer, ForeignKey("questions.id"), nullable=False)
    option_id = Column(String(120), nullable=True)
    label = Column(String(1), nullable=False)
    text = Column(Text, nullable=False)
    order_index = Column(Integer, nullable=False, default=0)

    question = relationship("Question", back_populates="options")


class PracticeAttempt(Base):
    __tablename__ = "practice_attempts"

    id = Column(Integer, primary_key=True, index=True)
    attempt_id = Column(String(120), nullable=False, unique=True, index=True)
    pack_db_id = Column(Integer, ForeignKey("reading_packs.id"), nullable=False)
    pack_id = Column(String(120), nullable=False, index=True)
    total_questions = Column(Integer, nullable=False)
    correct_count = Column(Integer, nullable=False)
    accuracy = Column(Float, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    pack = relationship("ReadingPack", back_populates="attempts")
    answers = relationship("PracticeAttemptAnswer", back_populates="attempt", cascade="all, delete-orphan")


class PracticeAttemptAnswer(Base):
    __tablename__ = "practice_attempt_answers"

    id = Column(Integer, primary_key=True, index=True)
    answer_id = Column(String(120), nullable=False, unique=True, index=True)
    attempt_db_id = Column(Integer, ForeignKey("practice_attempts.id"), nullable=False)
    attempt_id = Column(String(120), nullable=False, index=True)
    question_id = Column(String(120), nullable=False)
    selected_answer = Column(String(1), nullable=False)
    correct_answer = Column(String(1), nullable=False)
    is_correct = Column(Boolean, nullable=False)

    attempt = relationship("PracticeAttempt", back_populates="answers")


class ReadingAnnotation(Base):
    __tablename__ = "reading_annotations"

    id = Column(Integer, primary_key=True, index=True)
    annotation_id = Column(String(120), nullable=False, unique=True, index=True)
    pack_db_id = Column(Integer, ForeignKey("reading_packs.id"), nullable=False)
    pack_id = Column(String(120), nullable=False, index=True)
    passage_db_id = Column(Integer, ForeignKey("passages.id"), nullable=False)
    passage_id = Column(String(120), nullable=False, index=True)
    paragraph_db_id = Column(Integer, ForeignKey("paragraphs.id"), nullable=False)
    paragraph_id = Column(String(120), nullable=False, index=True)
    question_db_id = Column(Integer, ForeignKey("questions.id"), nullable=True)
    question_id = Column(String(120), nullable=True, index=True)
    annotation_type = Column(String(64), nullable=False)
    selected_text = Column(Text, nullable=False)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    pack = relationship("ReadingPack", back_populates="annotations")
    passage = relationship("Passage", back_populates="annotations")
    paragraph = relationship("Paragraph", back_populates="annotations")
    question = relationship("Question", back_populates="annotations")
