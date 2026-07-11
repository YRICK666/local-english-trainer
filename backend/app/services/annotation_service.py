from __future__ import annotations

from uuid import uuid4

from sqlalchemy.orm import Session

from backend.app import models, schemas

VALID_ANNOTATION_TYPES = {
    "answer_evidence",
    "synonym_replacement",
    "vocabulary",
    "difficult_sentence",
}


class AnnotationError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def create_annotation(db: Session, payload: schemas.AnnotationCreate) -> schemas.AnnotationOut:
    pack_id = payload.pack_id.strip()
    passage_id = payload.passage_id.strip()
    paragraph_id = payload.paragraph_id.strip()
    question_id = payload.question_id.strip() if payload.question_id else None
    annotation_type = payload.annotation_type.strip()
    selected_text = payload.selected_text
    start_offset = payload.start_offset
    end_offset = payload.end_offset
    note = payload.note.strip() if payload.note is not None else None

    if annotation_type not in VALID_ANNOTATION_TYPES:
        raise AnnotationError(400, f"annotation_type is invalid: {annotation_type}")
    if (start_offset is None) != (end_offset is None):
        raise AnnotationError(400, "start_offset and end_offset must both be provided or both be null")
    if start_offset is None and end_offset is None and not selected_text.strip():
        raise AnnotationError(400, "selected_text must not be empty")

    pack = db.query(models.ReadingPack).filter(models.ReadingPack.pack_id == pack_id).one_or_none()
    if pack is None:
        raise AnnotationError(404, f"Reading pack not found: {pack_id}")

    passage = db.query(models.Passage).filter(
        models.Passage.pack_db_id == pack.id,
        models.Passage.passage_id == passage_id,
    ).one_or_none()
    if passage is None:
        raise AnnotationError(400, f"passage_id does not belong to pack {pack_id}: {passage_id}")

    paragraph = db.query(models.Paragraph).filter(
        models.Paragraph.passage_db_id == passage.id,
        models.Paragraph.paragraph_id == paragraph_id,
    ).one_or_none()
    if paragraph is None:
        raise AnnotationError(400, f"paragraph_id does not belong to passage {passage_id}: {paragraph_id}")

    question = None
    if question_id is not None:
        question = db.query(models.Question).filter(
            models.Question.pack_db_id == pack.id,
            models.Question.question_id == question_id,
        ).one_or_none()
        if question is None:
            raise AnnotationError(400, f"question_id does not belong to pack {pack_id}: {question_id}")

    if start_offset is not None and end_offset is not None:
        _validate_offsets(paragraph.text, selected_text, start_offset, end_offset)
        conflict = db.query(models.ReadingAnnotation).filter(
            models.ReadingAnnotation.paragraph_db_id == paragraph.id,
            models.ReadingAnnotation.annotation_type == annotation_type,
            models.ReadingAnnotation.start_offset == start_offset,
            models.ReadingAnnotation.end_offset == end_offset,
        ).one_or_none()
        if conflict is not None:
            raise AnnotationError(409, "annotation range already exists for this annotation_type in the same paragraph")

    annotation = models.ReadingAnnotation(
        annotation_id=f"annotation-{uuid4().hex}",
        pack_db_id=pack.id,
        pack_id=pack.pack_id,
        passage_db_id=passage.id,
        passage_id=passage.passage_id,
        paragraph_db_id=paragraph.id,
        paragraph_id=paragraph.paragraph_id,
        question_db_id=question.id if question is not None else None,
        question_id=question.question_id if question is not None else None,
        annotation_type=annotation_type,
        selected_text=selected_text,
        start_offset=start_offset,
        end_offset=end_offset,
        note=note,
    )
    db.add(annotation)
    db.commit()
    db.refresh(annotation)
    return _to_annotation_out(annotation)


def list_annotations(db: Session, pack_id: str) -> list[schemas.AnnotationOut]:
    normalized_pack_id = pack_id.strip()
    pack = db.query(models.ReadingPack).filter(models.ReadingPack.pack_id == normalized_pack_id).one_or_none()
    if pack is None:
        raise AnnotationError(404, f"Reading pack not found: {normalized_pack_id}")

    annotations = db.query(models.ReadingAnnotation).filter(
        models.ReadingAnnotation.pack_db_id == pack.id
    ).order_by(models.ReadingAnnotation.id.asc()).all()
    return [_to_annotation_out(annotation) for annotation in annotations]


def delete_annotation(db: Session, annotation_id: str) -> schemas.AnnotationDeleteResponse:
    annotation = db.query(models.ReadingAnnotation).filter(models.ReadingAnnotation.annotation_id == annotation_id).one_or_none()
    if annotation is None:
        raise AnnotationError(404, f"Annotation not found: {annotation_id}")

    db.delete(annotation)
    db.commit()
    return schemas.AnnotationDeleteResponse(deleted=True, annotation_id=annotation_id)


def _to_annotation_out(annotation: models.ReadingAnnotation) -> schemas.AnnotationOut:
    return schemas.AnnotationOut(
        annotation_id=annotation.annotation_id,
        pack_id=annotation.pack_id,
        passage_id=annotation.passage_id,
        paragraph_id=annotation.paragraph_id,
        question_id=annotation.question_id,
        annotation_type=annotation.annotation_type,
        selected_text=annotation.selected_text,
        start_offset=annotation.start_offset,
        end_offset=annotation.end_offset,
        note=annotation.note,
        created_at=annotation.created_at,
    )


def _validate_offsets(paragraph_text: str, selected_text: str, start_offset: int, end_offset: int) -> None:
    if start_offset < 0:
        raise AnnotationError(400, "start_offset must be greater than or equal to 0")
    if end_offset < 0:
        raise AnnotationError(400, "end_offset must be greater than or equal to 0")
    if start_offset >= end_offset:
        raise AnnotationError(400, "start_offset must be less than end_offset")
    if end_offset > len(paragraph_text):
        raise AnnotationError(400, "end_offset exceeds paragraph text length")

    paragraph_slice = paragraph_text[start_offset:end_offset]
    if paragraph_slice != selected_text:
        raise AnnotationError(400, "selected_text must exactly match paragraph.text[start_offset:end_offset]")
    if not selected_text.strip():
        raise AnnotationError(400, "selected_text must not be only whitespace")
