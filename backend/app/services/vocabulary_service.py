from __future__ import annotations

from uuid import uuid4

from sqlalchemy.orm import Session

from backend.app import models, schemas

VALID_REVIEW_STATUSES = {"new", "learning", "familiar"}


class VocabularyError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def create_vocabulary_item(db: Session, payload: schemas.VocabularyItemCreate, *, commit: bool = True) -> schemas.VocabularyItemOut:
    item = create_vocabulary_item_no_commit(db, payload)
    if commit:
        db.commit()
        db.refresh(item)
    return _to_vocabulary_out(item)


def create_vocabulary_item_no_commit(db: Session, payload: schemas.VocabularyItemCreate) -> models.VocabularyItem:
    word = _normalize_required_word(payload.word)
    review_status = _normalize_review_status(payload.review_status)
    source_annotation_id = _normalize_optional_text(payload.source_annotation_id)
    _ensure_annotation_exists(db, source_annotation_id)
    _ensure_source_annotation_available(db, source_annotation_id)

    item = models.VocabularyItem(
        vocab_id=f"vocab-{uuid4().hex}",
        word=word,
        meaning=_normalize_optional_text(payload.meaning),
        source_sentence=_normalize_optional_text(payload.source_sentence),
        source_pack_id=_normalize_optional_text(payload.source_pack_id),
        source_passage_id=_normalize_optional_text(payload.source_passage_id),
        source_paragraph_id=_normalize_optional_text(payload.source_paragraph_id),
        source_annotation_id=source_annotation_id,
        review_status=review_status,
    )
    db.add(item)
    db.flush()
    return item


def list_vocabulary_items(db: Session) -> list[schemas.VocabularyItemOut]:
    items = db.query(models.VocabularyItem).order_by(models.VocabularyItem.id.asc()).all()
    return [_to_vocabulary_out(item) for item in items]


def get_vocabulary_item(db: Session, vocab_id: str) -> schemas.VocabularyItemOut:
    item = db.query(models.VocabularyItem).filter(models.VocabularyItem.vocab_id == vocab_id).one_or_none()
    if item is None:
        raise VocabularyError(404, f"Vocabulary item not found: {vocab_id}")
    return _to_vocabulary_out(item)


def update_vocabulary_item(db: Session, vocab_id: str, payload: schemas.VocabularyItemUpdate) -> schemas.VocabularyItemOut:
    item = db.query(models.VocabularyItem).filter(models.VocabularyItem.vocab_id == vocab_id).one_or_none()
    if item is None:
        raise VocabularyError(404, f"Vocabulary item not found: {vocab_id}")

    data = payload.model_dump(exclude_unset=True)
    if "word" in data:
        item.word = _normalize_required_word(data["word"])
    if "meaning" in data:
        item.meaning = _normalize_optional_text(data["meaning"])
    if "source_sentence" in data:
        item.source_sentence = _normalize_optional_text(data["source_sentence"])
    if "source_pack_id" in data:
        item.source_pack_id = _normalize_optional_text(data["source_pack_id"])
    if "source_passage_id" in data:
        item.source_passage_id = _normalize_optional_text(data["source_passage_id"])
    if "source_paragraph_id" in data:
        item.source_paragraph_id = _normalize_optional_text(data["source_paragraph_id"])
    if "source_annotation_id" in data:
        source_annotation_id = _normalize_optional_text(data["source_annotation_id"])
        _ensure_annotation_exists(db, source_annotation_id)
        _ensure_source_annotation_available(db, source_annotation_id, exclude_vocab_id=item.vocab_id)
        item.source_annotation_id = source_annotation_id
    if "review_status" in data:
        item.review_status = _normalize_review_status(data["review_status"])

    db.commit()
    db.refresh(item)
    return _to_vocabulary_out(item)


def delete_vocabulary_item(db: Session, vocab_id: str) -> schemas.VocabularyDeleteResponse:
    item = db.query(models.VocabularyItem).filter(models.VocabularyItem.vocab_id == vocab_id).one_or_none()
    if item is None:
        raise VocabularyError(404, f"Vocabulary item not found: {vocab_id}")

    db.delete(item)
    db.commit()
    return schemas.VocabularyDeleteResponse(deleted=True, vocab_id=vocab_id)


def _normalize_required_word(value: str | None) -> str:
    normalized = (value or "").strip()
    if not normalized:
        raise VocabularyError(400, "word must not be empty")
    return normalized


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_review_status(value: str | None) -> str:
    normalized = _normalize_optional_text(value) or "new"
    if normalized not in VALID_REVIEW_STATUSES:
        raise VocabularyError(400, f"review_status is invalid: {normalized}")
    return normalized


def _ensure_annotation_exists(db: Session, annotation_id: str | None) -> None:
    if annotation_id is None:
        return
    annotation = db.query(models.ReadingAnnotation).filter(models.ReadingAnnotation.annotation_id == annotation_id).one_or_none()
    if annotation is None:
        raise VocabularyError(400, f"source_annotation_id not found: {annotation_id}")


def _ensure_source_annotation_available(db: Session, annotation_id: str | None, exclude_vocab_id: str | None = None) -> None:
    if annotation_id is None:
        return

    query = db.query(models.VocabularyItem).filter(models.VocabularyItem.source_annotation_id == annotation_id)
    if exclude_vocab_id is not None:
        query = query.filter(models.VocabularyItem.vocab_id != exclude_vocab_id)

    conflict = query.one_or_none()
    if conflict is not None:
        raise VocabularyError(409, f"source_annotation_id already linked to vocabulary item: {annotation_id}")


def _to_vocabulary_out(item: models.VocabularyItem) -> schemas.VocabularyItemOut:
    return schemas.VocabularyItemOut(
        vocab_id=item.vocab_id,
        word=item.word,
        meaning=item.meaning,
        source_sentence=item.source_sentence,
        source_pack_id=item.source_pack_id,
        source_passage_id=item.source_passage_id,
        source_paragraph_id=item.source_paragraph_id,
        source_annotation_id=item.source_annotation_id,
        review_status=item.review_status,
        created_at=item.created_at,
    )
