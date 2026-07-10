from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.orm import Session

from backend.app import schemas
from backend.app.db import get_db, init_db
from backend.app.services import annotation_service, practice_attempt_service, reading_pack_service, sentence_service, vocabulary_service

app = FastAPI(title="local-english-trainer API")


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/import/reading-pack/validate", response_model=schemas.ImportValidationResult)
def validate_reading_pack(payload: dict[str, Any]) -> schemas.ImportValidationResult:
    return reading_pack_service.validate_reading_pack(payload)


@app.post("/api/import/reading-pack", response_model=schemas.ReadingPackImportResponse)
def import_reading_pack(payload: dict[str, Any], db: Session = Depends(get_db)) -> schemas.ReadingPackImportResponse:
    try:
        return reading_pack_service.import_reading_pack(db, payload)
    except reading_pack_service.DuplicateReadingPackError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except reading_pack_service.ReadingPackImportError as exc:
        raise HTTPException(status_code=400, detail=exc.validation.model_dump()) from exc


@app.get("/api/reading-packs", response_model=list[schemas.ReadingPackSummary])
def list_reading_packs(db: Session = Depends(get_db)) -> list[schemas.ReadingPackSummary]:
    return reading_pack_service.list_reading_packs(db)


@app.get("/api/reading-packs/{pack_id}", response_model=schemas.ReadingPackDetail)
def get_reading_pack(pack_id: str, db: Session = Depends(get_db)) -> schemas.ReadingPackDetail:
    pack = reading_pack_service.get_reading_pack(db, pack_id)
    if pack is None:
        raise HTTPException(status_code=404, detail="Reading pack not found")
    return pack


@app.post("/api/practice-attempts", response_model=schemas.PracticeAttemptDetail)
def create_practice_attempt(payload: schemas.PracticeAttemptCreate, db: Session = Depends(get_db)) -> schemas.PracticeAttemptDetail:
    try:
        return practice_attempt_service.create_practice_attempt(db, payload)
    except practice_attempt_service.PracticeAttemptError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@app.get("/api/practice-attempts", response_model=list[schemas.PracticeAttemptSummary])
def list_practice_attempts(db: Session = Depends(get_db)) -> list[schemas.PracticeAttemptSummary]:
    return practice_attempt_service.list_practice_attempts(db)


@app.get("/api/practice-attempts/{attempt_id}", response_model=schemas.PracticeAttemptDetail)
def get_practice_attempt(attempt_id: str, db: Session = Depends(get_db)) -> schemas.PracticeAttemptDetail:
    attempt = practice_attempt_service.get_practice_attempt(db, attempt_id)
    if attempt is None:
        raise HTTPException(status_code=404, detail="Practice attempt not found")
    return attempt


@app.post("/api/annotations", response_model=schemas.AnnotationOut)
def create_annotation(payload: schemas.AnnotationCreate, db: Session = Depends(get_db)) -> schemas.AnnotationOut:
    try:
        return annotation_service.create_annotation(db, payload)
    except annotation_service.AnnotationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@app.get("/api/annotations", response_model=list[schemas.AnnotationOut])
def list_annotations(pack_id: str, db: Session = Depends(get_db)) -> list[schemas.AnnotationOut]:
    try:
        return annotation_service.list_annotations(db, pack_id)
    except annotation_service.AnnotationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@app.delete("/api/annotations/{annotation_id}", response_model=schemas.AnnotationDeleteResponse)
def delete_annotation(annotation_id: str, db: Session = Depends(get_db)) -> schemas.AnnotationDeleteResponse:
    try:
        return annotation_service.delete_annotation(db, annotation_id)
    except annotation_service.AnnotationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc



@app.post("/api/vocabulary", response_model=schemas.VocabularyItemOut)
def create_vocabulary_item(payload: schemas.VocabularyItemCreate, db: Session = Depends(get_db)) -> schemas.VocabularyItemOut:
    try:
        return vocabulary_service.create_vocabulary_item(db, payload)
    except vocabulary_service.VocabularyError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@app.get("/api/vocabulary", response_model=list[schemas.VocabularyItemOut])
def list_vocabulary_items(db: Session = Depends(get_db)) -> list[schemas.VocabularyItemOut]:
    return vocabulary_service.list_vocabulary_items(db)


@app.get("/api/vocabulary/{vocab_id}", response_model=schemas.VocabularyItemOut)
def get_vocabulary_item(vocab_id: str, db: Session = Depends(get_db)) -> schemas.VocabularyItemOut:
    try:
        return vocabulary_service.get_vocabulary_item(db, vocab_id)
    except vocabulary_service.VocabularyError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@app.patch("/api/vocabulary/{vocab_id}", response_model=schemas.VocabularyItemOut)
def update_vocabulary_item(vocab_id: str, payload: schemas.VocabularyItemUpdate, db: Session = Depends(get_db)) -> schemas.VocabularyItemOut:
    try:
        return vocabulary_service.update_vocabulary_item(db, vocab_id, payload)
    except vocabulary_service.VocabularyError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@app.delete("/api/vocabulary/{vocab_id}", response_model=schemas.VocabularyDeleteResponse)
def delete_vocabulary_item(vocab_id: str, db: Session = Depends(get_db)) -> schemas.VocabularyDeleteResponse:
    try:
        return vocabulary_service.delete_vocabulary_item(db, vocab_id)
    except vocabulary_service.VocabularyError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@app.post("/api/sentences", response_model=schemas.SentenceItemOut)
def create_sentence_item(payload: schemas.SentenceItemCreate, db: Session = Depends(get_db)) -> schemas.SentenceItemOut:
    try:
        return sentence_service.create_sentence_item(db, payload)
    except sentence_service.SentenceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@app.get("/api/sentences", response_model=list[schemas.SentenceItemOut])
def list_sentence_items(db: Session = Depends(get_db)) -> list[schemas.SentenceItemOut]:
    return sentence_service.list_sentence_items(db)


@app.get("/api/sentences/{sentence_id}", response_model=schemas.SentenceItemOut)
def get_sentence_item(sentence_id: str, db: Session = Depends(get_db)) -> schemas.SentenceItemOut:
    try:
        return sentence_service.get_sentence_item(db, sentence_id)
    except sentence_service.SentenceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@app.patch("/api/sentences/{sentence_id}", response_model=schemas.SentenceItemOut)
def update_sentence_item(sentence_id: str, payload: schemas.SentenceItemUpdate, db: Session = Depends(get_db)) -> schemas.SentenceItemOut:
    try:
        return sentence_service.update_sentence_item(db, sentence_id, payload)
    except sentence_service.SentenceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@app.delete("/api/sentences/{sentence_id}", response_model=schemas.SentenceDeleteResponse)
def delete_sentence_item(sentence_id: str, db: Session = Depends(get_db)) -> schemas.SentenceDeleteResponse:
    try:
        return sentence_service.delete_sentence_item(db, sentence_id)
    except sentence_service.SentenceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

