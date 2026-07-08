from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.orm import Session

from backend.app import schemas
from backend.app.db import get_db, init_db
from backend.app.services import practice_attempt_service, reading_pack_service

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
