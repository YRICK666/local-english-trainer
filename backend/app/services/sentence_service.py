from __future__ import annotations

from uuid import uuid4

from sqlalchemy.orm import Session

from backend.app import models, schemas

VALID_REVIEW_STATUSES = {"new", "learning", "familiar"}


class SentenceError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def create_sentence_item(db: Session, payload: schemas.SentenceItemCreate, *, commit: bool = True) -> schemas.SentenceItemOut:
    item = create_sentence_item_no_commit(db, payload)
    if commit:
        db.commit()
        db.refresh(item)
    return _to_sentence_out(item)


def create_sentence_item_no_commit(db: Session, payload: schemas.SentenceItemCreate) -> models.SentenceItem:
    sentence_text = _normalize_required_sentence_text(payload.sentence_text)
    review_status = _normalize_review_status(payload.review_status)
    source_annotation_id = _normalize_optional_text(payload.source_annotation_id)
    _ensure_annotation_exists(db, source_annotation_id)
    _ensure_source_annotation_available(db, source_annotation_id)

    item = models.SentenceItem(
        sentence_id=f"sentence-{uuid4().hex}",
        sentence_text=sentence_text,
        translation=_normalize_optional_text(payload.translation),
        structure_note=_normalize_optional_text(payload.structure_note),
        source_pack_id=_normalize_optional_text(payload.source_pack_id),
        source_passage_id=_normalize_optional_text(payload.source_passage_id),
        source_paragraph_id=_normalize_optional_text(payload.source_paragraph_id),
        source_annotation_id=source_annotation_id,
        review_status=review_status,
    )
    db.add(item)
    db.flush()
    return item


def list_sentence_items(db: Session) -> list[schemas.SentenceItemOut]:
    items = db.query(models.SentenceItem).order_by(models.SentenceItem.id.asc()).all()
    return [_to_sentence_out(item) for item in items]


def get_sentence_item(db: Session, sentence_id: str) -> schemas.SentenceItemOut:
    item = db.query(models.SentenceItem).filter(models.SentenceItem.sentence_id == sentence_id).one_or_none()
    if item is None:
        raise SentenceError(404, f"Sentence item not found: {sentence_id}")
    return _to_sentence_out(item)


def update_sentence_item(db: Session, sentence_id: str, payload: schemas.SentenceItemUpdate) -> schemas.SentenceItemOut:
    item = db.query(models.SentenceItem).filter(models.SentenceItem.sentence_id == sentence_id).one_or_none()
    if item is None:
        raise SentenceError(404, f"Sentence item not found: {sentence_id}")

    data = payload.model_dump(exclude_unset=True)
    if "sentence_text" in data:
        item.sentence_text = _normalize_required_sentence_text(data["sentence_text"])
    if "translation" in data:
        item.translation = _normalize_optional_text(data["translation"])
    if "structure_note" in data:
        item.structure_note = _normalize_optional_text(data["structure_note"])
    if "source_pack_id" in data:
        item.source_pack_id = _normalize_optional_text(data["source_pack_id"])
    if "source_passage_id" in data:
        item.source_passage_id = _normalize_optional_text(data["source_passage_id"])
    if "source_paragraph_id" in data:
        item.source_paragraph_id = _normalize_optional_text(data["source_paragraph_id"])
    if "source_annotation_id" in data:
        source_annotation_id = _normalize_optional_text(data["source_annotation_id"])
        _ensure_annotation_exists(db, source_annotation_id)
        _ensure_source_annotation_available(db, source_annotation_id, exclude_sentence_id=item.sentence_id)
        item.source_annotation_id = source_annotation_id
    if "review_status" in data:
        item.review_status = _normalize_review_status(data["review_status"])

    db.commit()
    db.refresh(item)
    return _to_sentence_out(item)


def delete_sentence_item(db: Session, sentence_id: str) -> schemas.SentenceDeleteResponse:
    item = db.query(models.SentenceItem).filter(models.SentenceItem.sentence_id == sentence_id).one_or_none()
    if item is None:
        raise SentenceError(404, f"Sentence item not found: {sentence_id}")

    db.delete(item)
    db.commit()
    return schemas.SentenceDeleteResponse(deleted=True, sentence_id=sentence_id)


def _normalize_required_sentence_text(value: str | None) -> str:
    normalized = (value or "").strip()
    if not normalized:
        raise SentenceError(400, "sentence_text must not be empty")
    return normalized


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_review_status(value: str | None) -> str:
    normalized = _normalize_optional_text(value) or "new"
    if normalized not in VALID_REVIEW_STATUSES:
        raise SentenceError(400, f"review_status is invalid: {normalized}")
    return normalized


def _ensure_annotation_exists(db: Session, annotation_id: str | None) -> None:
    if annotation_id is None:
        return
    annotation = db.query(models.ReadingAnnotation).filter(models.ReadingAnnotation.annotation_id == annotation_id).one_or_none()
    if annotation is None:
        raise SentenceError(400, f"source_annotation_id not found: {annotation_id}")


def _ensure_source_annotation_available(db: Session, annotation_id: str | None, exclude_sentence_id: str | None = None) -> None:
    if annotation_id is None:
        return

    query = db.query(models.SentenceItem).filter(models.SentenceItem.source_annotation_id == annotation_id)
    if exclude_sentence_id is not None:
        query = query.filter(models.SentenceItem.sentence_id != exclude_sentence_id)

    conflict = query.one_or_none()
    if conflict is not None:
        raise SentenceError(409, f"source_annotation_id already linked to sentence item: {annotation_id}")


def _to_sentence_out(item: models.SentenceItem) -> schemas.SentenceItemOut:
    return schemas.SentenceItemOut(
        sentence_id=item.sentence_id,
        sentence_text=item.sentence_text,
        translation=item.translation,
        structure_note=item.structure_note,
        source_pack_id=item.source_pack_id,
        source_passage_id=item.source_passage_id,
        source_paragraph_id=item.source_paragraph_id,
        source_annotation_id=item.source_annotation_id,
        review_status=item.review_status,
        created_at=item.created_at,
    )
