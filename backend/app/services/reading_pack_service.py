from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session, selectinload

from backend.app import models, schemas

REQUIRED_LABELS = ["A", "B", "C", "D"]


class ReadingPackImportError(Exception):
    def __init__(self, validation: schemas.ImportValidationResult) -> None:
        self.validation = validation
        super().__init__("Invalid reading_pack")


class DuplicateReadingPackError(Exception):
    def __init__(self, pack_id: str) -> None:
        self.pack_id = pack_id
        super().__init__(f"Reading pack already exists: {pack_id}")


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True)


def _json_loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _get_answer_map(payload: dict[str, Any]) -> dict[str, str]:
    answers: dict[str, str] = {}
    for item in _as_list(payload.get("answer_key")):
        if isinstance(item, dict) and item.get("question_id"):
            answer = item.get("correct_answer")
            if isinstance(answer, str):
                answers[str(item["question_id"])] = answer.strip().upper()
    return answers


def _resolve_answer(question: dict[str, Any], answer_map: dict[str, str]) -> str:
    question_id = str(question.get("question_id") or "")
    if question_id in answer_map:
        return answer_map[question_id]
    for key in ("answer", "correct_answer"):
        value = question.get(key)
        if isinstance(value, str):
            return value.strip().upper()
    return ""


def _question_analysis(question: dict[str, Any]) -> str:
    for key in ("analysis", "explanation"):
        value = question.get(key)
        if isinstance(value, str):
            return value
    return ""


def _question_evidence_hint(question: dict[str, Any]) -> str:
    value = question.get("evidence_hint")
    if isinstance(value, str):
        return value
    refs = _as_list(question.get("evidence_refs"))
    quotes = [str(item.get("quote") or "").strip() for item in refs if isinstance(item, dict)]
    return " / ".join([quote for quote in quotes if quote])


def validate_reading_pack(payload: dict[str, Any]) -> schemas.ImportValidationResult:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return schemas.ImportValidationResult(valid=False, errors=["reading_pack must be an object"])

    pack_id = str(payload.get("pack_id") or "").strip()
    title = str(payload.get("title") or "").strip()
    passages = [item for item in _as_list(payload.get("passages")) if isinstance(item, dict)]
    questions = [item for item in _as_list(payload.get("questions")) if isinstance(item, dict)]
    answer_map = _get_answer_map(payload)

    if not pack_id:
        errors.append("pack_id is required")
    if not title:
        errors.append("title is required")
    if not passages:
        errors.append("at least one passage is required")
    if not questions:
        errors.append("at least one question is required")

    passage_ids: set[str] = set()
    paragraph_count = 0
    for index, passage in enumerate(passages):
        passage_id = str(passage.get("passage_id") or "").strip()
        if not passage_id:
            errors.append(f"passages[{index}].passage_id is required")
            continue
        if passage_id in passage_ids:
            errors.append(f"duplicate passage_id: {passage_id}")
        passage_ids.add(passage_id)
        paragraphs = [item for item in _as_list(passage.get("paragraphs")) if isinstance(item, dict)]
        if not paragraphs:
            errors.append(f"passage {passage_id} must include at least one paragraph")
        paragraph_count += len(paragraphs)

    question_ids: set[str] = set()
    for index, question in enumerate(questions):
        question_id = str(question.get("question_id") or "").strip()
        passage_id = str(question.get("passage_id") or "").strip()
        options = [item for item in _as_list(question.get("options")) if isinstance(item, dict)]
        labels = sorted(str(option.get("label") or "").strip().upper() for option in options)
        answer = _resolve_answer(question, answer_map)
        if not question_id:
            errors.append(f"questions[{index}].question_id is required")
        elif question_id in question_ids:
            errors.append(f"duplicate question_id: {question_id}")
        question_ids.add(question_id)
        if passage_id not in passage_ids:
            errors.append(f"question {question_id or index} references missing passage_id: {passage_id}")
        if question.get("question_type") != "single_choice":
            errors.append(f"question {question_id or index} must be single_choice")
        if labels != REQUIRED_LABELS:
            errors.append(f"question {question_id or index} must include A/B/C/D options")
        if answer not in REQUIRED_LABELS:
            errors.append(f"question {question_id or index} answer must be A/B/C/D")

    return schemas.ImportValidationResult(
        valid=not errors,
        errors=errors,
        stats=schemas.ImportValidationStats(
            passage_count=len(passages), paragraph_count=paragraph_count, question_count=len(questions)
        ),
    )


def import_reading_pack(db: Session, payload: dict[str, Any]) -> schemas.ReadingPackImportResponse:
    validation = validate_reading_pack(payload)
    if not validation.valid:
        raise ReadingPackImportError(validation)
    pack_id = str(payload["pack_id"]).strip()
    if db.query(models.ReadingPack).filter(models.ReadingPack.pack_id == pack_id).one_or_none():
        raise DuplicateReadingPackError(pack_id)

    pack = models.ReadingPack(
        pack_id=pack_id,
        title=str(payload["title"]).strip(),
        description=str(payload.get("description") or ""),
        language=str(payload.get("language") or "en"),
        level=str(payload.get("level") or ""),
        tags_json=_json_dumps(_as_list(payload.get("tags"))),
        source_json=_json_dumps(payload.get("source") if isinstance(payload.get("source"), dict) else {}),
        metadata_json=_json_dumps(payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}),
    )
    db.add(pack)
    db.flush()

    passage_by_id: dict[str, models.Passage] = {}
    for passage_index, item in enumerate(_as_list(payload.get("passages"))):
        passage = models.Passage(
            pack_db_id=pack.id,
            passage_id=str(item["passage_id"]).strip(),
            material_id=str(item.get("material_id") or ""),
            title=str(item.get("title") or ""),
            content=str(item.get("content") or ""),
            order_index=int(item.get("order") or passage_index + 1),
            tags_json=_json_dumps(_as_list(item.get("tags"))),
            metadata_json=_json_dumps(item.get("metadata") if isinstance(item.get("metadata"), dict) else {}),
        )
        db.add(passage)
        db.flush()
        passage_by_id[passage.passage_id] = passage
        for paragraph_index, paragraph_item in enumerate(_as_list(item.get("paragraphs"))):
            db.add(models.Paragraph(
                passage_db_id=passage.id,
                paragraph_id=str(paragraph_item.get("paragraph_id") or f"{passage.passage_id}:p:{paragraph_index + 1}"),
                text=str(paragraph_item.get("text") or ""),
                order_index=int(paragraph_item.get("order") or paragraph_index + 1),
            ))

    answer_map = _get_answer_map(payload)
    for item in _as_list(payload.get("questions")):
        passage_id = str(item["passage_id"]).strip()
        question = models.Question(
            pack_db_id=pack.id,
            passage_db_id=passage_by_id[passage_id].id,
            question_id=str(item["question_id"]).strip(),
            passage_id=passage_id,
            question_no=str(item.get("question_no") or ""),
            question_type="single_choice",
            stem=str(item.get("stem") or ""),
            answer=_resolve_answer(item, answer_map),
            analysis=_question_analysis(item),
            evidence_hint=_question_evidence_hint(item),
            tags_json=_json_dumps(_as_list(item.get("tags"))),
            score_points=item.get("score_points"),
        )
        db.add(question)
        db.flush()
        option_by_label = {str(option.get("label") or "").strip().upper(): option for option in _as_list(item.get("options"))}
        for option_index, label in enumerate(REQUIRED_LABELS):
            option = option_by_label[label]
            db.add(models.QuestionOption(
                question_db_id=question.id,
                option_id=str(option.get("option_id") or ""),
                label=label,
                text=str(option.get("text") or ""),
                order_index=option_index + 1,
            ))

    db.commit()
    imported = get_reading_pack(db, pack_id)
    assert imported is not None
    return schemas.ReadingPackImportResponse(imported=True, pack=imported, validation=validation)


def list_reading_packs(db: Session) -> list[schemas.ReadingPackSummary]:
    packs = db.query(models.ReadingPack).options(selectinload(models.ReadingPack.passages), selectinload(models.ReadingPack.questions)).order_by(models.ReadingPack.id.asc()).all()
    return [_pack_to_summary(pack) for pack in packs]


def get_reading_pack(db: Session, pack_id: str) -> schemas.ReadingPackDetail | None:
    pack = db.query(models.ReadingPack).options(
        selectinload(models.ReadingPack.passages).selectinload(models.Passage.paragraphs),
        selectinload(models.ReadingPack.questions).selectinload(models.Question.options),
    ).filter(models.ReadingPack.pack_id == pack_id).one_or_none()
    if not pack:
        return None
    return _pack_to_detail(pack)


def _pack_to_summary(pack: models.ReadingPack) -> schemas.ReadingPackSummary:
    return schemas.ReadingPackSummary(
        pack_id=pack.pack_id,
        title=pack.title,
        description=pack.description or "",
        language=pack.language or "en",
        level=pack.level or "",
        tags=_json_loads(pack.tags_json, []),
        source=_json_loads(pack.source_json, {}),
        passage_count=len(pack.passages),
        question_count=len(pack.questions),
    )


def _pack_to_detail(pack: models.ReadingPack) -> schemas.ReadingPackDetail:
    summary = _pack_to_summary(pack)
    return schemas.ReadingPackDetail(
        **summary.model_dump(),
        metadata=_json_loads(pack.metadata_json, {}),
        passages=[schemas.PassageOut(
            passage_id=passage.passage_id,
            material_id=passage.material_id or "",
            title=passage.title or "",
            content=passage.content,
            order=passage.order_index,
            tags=_json_loads(passage.tags_json, []),
            metadata=_json_loads(passage.metadata_json, {}),
            paragraphs=[schemas.ParagraphOut(paragraph_id=p.paragraph_id, text=p.text, order=p.order_index) for p in sorted(passage.paragraphs, key=lambda item: item.order_index)],
        ) for passage in sorted(pack.passages, key=lambda item: item.order_index)],
        questions=[schemas.QuestionOut(
            question_id=question.question_id,
            passage_id=question.passage_id,
            question_no=question.question_no or "",
            question_type=question.question_type,
            stem=question.stem,
            answer=question.answer,
            analysis=question.analysis or "",
            explanation=question.analysis or "",
            evidence_hint=question.evidence_hint or "",
            tags=_json_loads(question.tags_json, []),
            score_points=question.score_points,
            options=[schemas.QuestionOptionOut(option_id=o.option_id or "", label=o.label, text=o.text) for o in sorted(question.options, key=lambda item: item.order_index)],
        ) for question in sorted(pack.questions, key=lambda item: item.id)],
    )
