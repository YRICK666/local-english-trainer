from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ImportValidationStats(BaseModel):
    passage_count: int = 0
    paragraph_count: int = 0
    question_count: int = 0


class ImportValidationResult(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    stats: ImportValidationStats = Field(default_factory=ImportValidationStats)


class ReadingPackSummary(BaseModel):
    pack_id: str
    title: str
    description: str = ""
    language: str = "en"
    level: str = ""
    tags: list[str] = Field(default_factory=list)
    source: dict[str, Any] = Field(default_factory=dict)
    passage_count: int = 0
    question_count: int = 0


class ParagraphOut(BaseModel):
    paragraph_id: str
    text: str
    order: int


class PassageOut(BaseModel):
    passage_id: str
    material_id: str = ""
    title: str = ""
    content: str
    order: int
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    paragraphs: list[ParagraphOut] = Field(default_factory=list)


class QuestionOptionOut(BaseModel):
    option_id: str = ""
    label: str
    text: str


class QuestionOut(BaseModel):
    question_id: str
    passage_id: str
    question_no: str = ""
    question_type: str
    stem: str
    answer: str
    analysis: str = ""
    explanation: str = ""
    evidence_hint: str = ""
    tags: list[str] = Field(default_factory=list)
    score_points: float | None = None
    options: list[QuestionOptionOut] = Field(default_factory=list)


class ReadingPackDetail(ReadingPackSummary):
    metadata: dict[str, Any] = Field(default_factory=dict)
    passages: list[PassageOut] = Field(default_factory=list)
    questions: list[QuestionOut] = Field(default_factory=list)


class ReadingPackImportResponse(BaseModel):
    imported: bool
    pack: ReadingPackDetail
    validation: ImportValidationResult


class PracticeAttemptAnswerIn(BaseModel):
    question_id: str
    selected_answer: str


class PracticeAttemptCreate(BaseModel):
    pack_id: str
    answers: list[PracticeAttemptAnswerIn]


class PracticeAttemptAnswerOut(BaseModel):
    answer_id: str
    attempt_id: str
    question_id: str
    selected_answer: str
    correct_answer: str
    is_correct: bool


class PracticeAttemptSummary(BaseModel):
    attempt_id: str
    pack_id: str
    total_questions: int
    correct_count: int
    accuracy: float
    created_at: datetime | None = None


class PracticeAttemptDetail(PracticeAttemptSummary):
    answers: list[PracticeAttemptAnswerOut] = Field(default_factory=list)


class AnnotationCreate(BaseModel):
    pack_id: str
    passage_id: str
    paragraph_id: str
    question_id: str | None = None
    annotation_type: str
    selected_text: str
    start_offset: int | None = None
    end_offset: int | None = None
    note: str | None = None


class AnnotationOut(BaseModel):
    annotation_id: str
    pack_id: str
    passage_id: str
    paragraph_id: str
    question_id: str | None = None
    annotation_type: str
    selected_text: str
    start_offset: int | None = None
    end_offset: int | None = None
    note: str | None = None
    created_at: datetime | None = None


class AnnotationDeleteResponse(BaseModel):
    deleted: bool
    annotation_id: str


class VocabularyItemCreate(BaseModel):
    word: str
    meaning: str | None = None
    source_sentence: str | None = None
    source_pack_id: str | None = None
    source_passage_id: str | None = None
    source_paragraph_id: str | None = None
    source_annotation_id: str | None = None
    review_status: str | None = None


class VocabularyItemUpdate(BaseModel):
    word: str | None = None
    meaning: str | None = None
    source_sentence: str | None = None
    source_pack_id: str | None = None
    source_passage_id: str | None = None
    source_paragraph_id: str | None = None
    source_annotation_id: str | None = None
    review_status: str | None = None


class VocabularyItemOut(BaseModel):
    vocab_id: str
    word: str
    meaning: str | None = None
    source_sentence: str | None = None
    source_pack_id: str | None = None
    source_passage_id: str | None = None
    source_paragraph_id: str | None = None
    source_annotation_id: str | None = None
    review_status: str
    created_at: datetime | None = None


class VocabularyDeleteResponse(BaseModel):
    deleted: bool
    vocab_id: str


class SentenceItemCreate(BaseModel):
    sentence_text: str
    translation: str | None = None
    structure_note: str | None = None
    source_pack_id: str | None = None
    source_passage_id: str | None = None
    source_paragraph_id: str | None = None
    source_annotation_id: str | None = None
    review_status: str | None = None


class SentenceItemUpdate(BaseModel):
    sentence_text: str | None = None
    translation: str | None = None
    structure_note: str | None = None
    source_pack_id: str | None = None
    source_passage_id: str | None = None
    source_paragraph_id: str | None = None
    source_annotation_id: str | None = None
    review_status: str | None = None


class SentenceItemOut(BaseModel):
    sentence_id: str
    sentence_text: str
    translation: str | None = None
    structure_note: str | None = None
    source_pack_id: str | None = None
    source_passage_id: str | None = None
    source_paragraph_id: str | None = None
    source_annotation_id: str | None = None
    review_status: str
    created_at: datetime | None = None


class SentenceDeleteResponse(BaseModel):
    deleted: bool
    sentence_id: str

class AnnotationCreateResult(BaseModel):
    annotation: AnnotationOut
    created_vocabulary_item: VocabularyItemOut | None = None
    created_sentence_item: SentenceItemOut | None = None