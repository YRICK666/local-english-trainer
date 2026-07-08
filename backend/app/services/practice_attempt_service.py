from __future__ import annotations

from uuid import uuid4

from sqlalchemy.orm import Session, selectinload

from backend.app import models, schemas

VALID_LABELS = {"A", "B", "C", "D"}


class PracticeAttemptError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def create_practice_attempt(db: Session, payload: schemas.PracticeAttemptCreate) -> schemas.PracticeAttemptDetail:
    pack = db.query(models.ReadingPack).options(selectinload(models.ReadingPack.questions)).filter(models.ReadingPack.pack_id == payload.pack_id).one_or_none()
    if pack is None:
        raise PracticeAttemptError(404, f"Reading pack not found: {payload.pack_id}")
    if not payload.answers:
        raise PracticeAttemptError(400, "answers must include at least one item")

    question_map = {question.question_id: question for question in pack.questions}
    seen_questions: set[str] = set()
    normalized_answers: list[tuple[str, str, str, bool]] = []
    for item in payload.answers:
        question_id = item.question_id.strip()
        selected_answer = item.selected_answer.strip().upper()
        if question_id not in question_map:
            raise PracticeAttemptError(400, f"question_id does not belong to pack {payload.pack_id}: {question_id}")
        if question_id in seen_questions:
            raise PracticeAttemptError(400, f"duplicate answer for question_id: {question_id}")
        if selected_answer not in VALID_LABELS:
            raise PracticeAttemptError(400, f"selected_answer must be A/B/C/D for question_id: {question_id}")
        seen_questions.add(question_id)
        correct_answer = question_map[question_id].answer
        normalized_answers.append((question_id, selected_answer, correct_answer, selected_answer == correct_answer))

    total_questions = len(normalized_answers)
    correct_count = sum(1 for *_, is_correct in normalized_answers if is_correct)
    accuracy = correct_count / total_questions if total_questions else 0.0
    attempt_id = f"attempt-{uuid4().hex}"

    attempt = models.PracticeAttempt(
        attempt_id=attempt_id,
        pack_db_id=pack.id,
        pack_id=pack.pack_id,
        total_questions=total_questions,
        correct_count=correct_count,
        accuracy=accuracy,
    )
    db.add(attempt)
    db.flush()

    for question_id, selected_answer, correct_answer, is_correct in normalized_answers:
        db.add(models.PracticeAttemptAnswer(
            answer_id=f"answer-{uuid4().hex}",
            attempt_db_id=attempt.id,
            attempt_id=attempt.attempt_id,
            question_id=question_id,
            selected_answer=selected_answer,
            correct_answer=correct_answer,
            is_correct=is_correct,
        ))

    db.commit()
    created = get_practice_attempt(db, attempt_id)
    assert created is not None
    return created


def list_practice_attempts(db: Session) -> list[schemas.PracticeAttemptSummary]:
    attempts = db.query(models.PracticeAttempt).order_by(models.PracticeAttempt.id.desc()).all()
    return [_attempt_to_summary(attempt) for attempt in attempts]


def get_practice_attempt(db: Session, attempt_id: str) -> schemas.PracticeAttemptDetail | None:
    attempt = db.query(models.PracticeAttempt).options(selectinload(models.PracticeAttempt.answers)).filter(models.PracticeAttempt.attempt_id == attempt_id).one_or_none()
    if attempt is None:
        return None
    return schemas.PracticeAttemptDetail(
        **_attempt_to_summary(attempt).model_dump(),
        answers=[schemas.PracticeAttemptAnswerOut(
            answer_id=answer.answer_id,
            attempt_id=answer.attempt_id,
            question_id=answer.question_id,
            selected_answer=answer.selected_answer,
            correct_answer=answer.correct_answer,
            is_correct=answer.is_correct,
        ) for answer in sorted(attempt.answers, key=lambda item: item.id)],
    )


def _attempt_to_summary(attempt: models.PracticeAttempt) -> schemas.PracticeAttemptSummary:
    return schemas.PracticeAttemptSummary(
        attempt_id=attempt.attempt_id,
        pack_id=attempt.pack_id,
        total_questions=attempt.total_questions,
        correct_count=attempt.correct_count,
        accuracy=attempt.accuracy,
        created_at=attempt.created_at,
    )
