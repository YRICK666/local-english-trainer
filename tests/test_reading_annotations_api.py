from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import db as app_db
from backend.app import models
from backend.app.main import app
from backend.app.services import sentence_service, vocabulary_service

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "reading_pack_minimal.json"
TEST_DB_URL = "sqlite:///:memory:"


@pytest.fixture()
def client() -> TestClient:
    app_db.configure_database(TEST_DB_URL)
    app_db.Base.metadata.drop_all(bind=app_db.engine)
    app_db.init_db()
    with TestClient(app) as test_client:
        yield test_client
    app_db.Base.metadata.drop_all(bind=app_db.engine)
    app_db.engine.dispose()


@pytest.fixture()
def imported_pack(client: TestClient) -> dict:
    payload = load_fixture_payload()
    response = client.post("/api/import/reading-pack", json=payload)
    assert response.status_code == 200
    return response.json()["pack"]


def load_fixture_payload() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def import_pack(client: TestClient, payload: dict) -> dict:
    response = client.post("/api/import/reading-pack", json=payload)
    assert response.status_code == 200
    return response.json()["pack"]


def build_annotation_payload(annotation_type: str, **overrides) -> dict:
    payload = {
        "pack_id": "attempt-reading-pack",
        "passage_id": "passage-attempt",
        "paragraph_id": "para-attempt-1",
        "question_id": "q-attempt-1",
        "annotation_type": annotation_type,
        "selected_text": "near the window",
        "note": "test note",
    }
    payload.update(overrides)
    return payload


def import_custom_pack(
    client: TestClient,
    *,
    pack_id: str,
    passage_id: str,
    paragraph_1_id: str,
    paragraph_1_text: str,
    paragraph_2_id: str = "para-custom-2",
    paragraph_2_text: str = "Backup paragraph.",
) -> dict:
    payload = copy.deepcopy(load_fixture_payload())
    payload["pack_id"] = pack_id
    payload["title"] = f"Pack {pack_id}"
    payload["passages"][0]["passage_id"] = passage_id
    payload["passages"][0]["content"] = f"{paragraph_1_text} {paragraph_2_text}"
    payload["passages"][0]["paragraphs"][0]["paragraph_id"] = paragraph_1_id
    payload["passages"][0]["paragraphs"][0]["text"] = paragraph_1_text
    payload["passages"][0]["paragraphs"][1]["paragraph_id"] = paragraph_2_id
    payload["passages"][0]["paragraphs"][1]["text"] = paragraph_2_text
    payload["questions"][0]["passage_id"] = passage_id
    payload["questions"][1]["passage_id"] = passage_id
    response = client.post("/api/import/reading-pack", json=payload)
    assert response.status_code == 200
    return response.json()["pack"]


def list_vocabulary(client: TestClient) -> list[dict]:
    response = client.get("/api/vocabulary")
    assert response.status_code == 200
    return response.json()


def list_sentences(client: TestClient) -> list[dict]:
    response = client.get("/api/sentences")
    assert response.status_code == 200
    return response.json()


@pytest.mark.parametrize("annotation_type", [
    "answer_evidence",
    "synonym_replacement",
])
def test_creates_non_library_annotation_types_without_auto_library_items(client: TestClient, imported_pack: dict, annotation_type: str) -> None:
    response = client.post("/api/annotations", json=build_annotation_payload(annotation_type))

    assert response.status_code == 200
    body = response.json()
    annotation = body["annotation"]
    assert annotation["annotation_id"].startswith("annotation-")
    assert annotation["annotation_type"] == annotation_type
    assert annotation["pack_id"] == "attempt-reading-pack"
    assert annotation["question_id"] == "q-attempt-1"
    assert annotation["start_offset"] is None
    assert annotation["end_offset"] is None
    assert body["created_vocabulary_item"] is None
    assert body["created_sentence_item"] is None
    assert list_vocabulary(client) == []
    assert list_sentences(client) == []


def test_creates_vocabulary_annotation_and_auto_vocabulary_item(client: TestClient, imported_pack: dict) -> None:
    response = client.post("/api/annotations", json=build_annotation_payload("vocabulary", selected_text="near the window", start_offset=24, end_offset=39))

    assert response.status_code == 200
    body = response.json()
    annotation = body["annotation"]
    vocabulary_item = body["created_vocabulary_item"]
    assert annotation["start_offset"] == 24
    assert annotation["end_offset"] == 39
    assert vocabulary_item is not None
    assert body["created_sentence_item"] is None
    assert vocabulary_item["word"] == "near the window"
    assert vocabulary_item["meaning"] is None
    assert vocabulary_item["source_sentence"] == "Nora keeps a small desk near the window."
    assert vocabulary_item["source_pack_id"] == annotation["pack_id"]
    assert vocabulary_item["source_passage_id"] == annotation["passage_id"]
    assert vocabulary_item["source_paragraph_id"] == annotation["paragraph_id"]
    assert vocabulary_item["source_annotation_id"] == annotation["annotation_id"]
    assert vocabulary_item["review_status"] == "new"


def test_creates_difficult_sentence_annotation_and_auto_sentence_item(client: TestClient, imported_pack: dict) -> None:
    response = client.post("/api/annotations", json=build_annotation_payload(
        "difficult_sentence",
        selected_text="small desk near the window",
        start_offset=13,
        end_offset=39,
    ))

    assert response.status_code == 200
    body = response.json()
    annotation = body["annotation"]
    sentence_item = body["created_sentence_item"]
    assert sentence_item is not None
    assert body["created_vocabulary_item"] is None
    assert sentence_item["sentence_text"] == "small desk near the window"
    assert sentence_item["translation"] is None
    assert sentence_item["structure_note"] is None
    assert sentence_item["source_pack_id"] == annotation["pack_id"]
    assert sentence_item["source_passage_id"] == annotation["passage_id"]
    assert sentence_item["source_paragraph_id"] == annotation["paragraph_id"]
    assert sentence_item["source_annotation_id"] == annotation["annotation_id"]
    assert sentence_item["review_status"] == "new"


def test_creates_annotation_with_valid_offsets(client: TestClient, imported_pack: dict) -> None:
    response = client.post("/api/annotations", json=build_annotation_payload(
        "answer_evidence",
        selected_text="near the window",
        start_offset=24,
        end_offset=39,
    ))

    assert response.status_code == 200
    annotation = response.json()["annotation"]
    assert annotation["start_offset"] == 24
    assert annotation["end_offset"] == 39


def test_rejects_invalid_annotation_type(client: TestClient, imported_pack: dict) -> None:
    response = client.post("/api/annotations", json=build_annotation_payload("invalid_type"))

    assert response.status_code == 400
    assert "annotation_type is invalid" in response.json()["detail"]


def test_rejects_blank_selected_text(client: TestClient, imported_pack: dict) -> None:
    response = client.post("/api/annotations", json=build_annotation_payload("vocabulary", selected_text="   "))

    assert response.status_code == 400
    assert response.json()["detail"] == "selected_text must not be empty"


def test_legacy_request_without_offsets_still_succeeds(client: TestClient, imported_pack: dict) -> None:
    response = client.post("/api/annotations", json=build_annotation_payload("answer_evidence", question_id=None))

    assert response.status_code == 200
    annotation = response.json()["annotation"]
    assert annotation["start_offset"] is None
    assert annotation["end_offset"] is None


def test_list_returns_null_offsets_for_legacy_annotations(client: TestClient, imported_pack: dict) -> None:
    session = app_db.SessionLocal()
    try:
        pack = session.query(models.ReadingPack).filter(models.ReadingPack.pack_id == "attempt-reading-pack").one()
        passage = session.query(models.Passage).filter(models.Passage.pack_db_id == pack.id).one()
        paragraph = session.query(models.Paragraph).filter(models.Paragraph.passage_db_id == passage.id).first()
        annotation = models.ReadingAnnotation(
            annotation_id="annotation-legacy-test",
            pack_db_id=pack.id,
            pack_id=pack.pack_id,
            passage_db_id=passage.id,
            passage_id=passage.passage_id,
            paragraph_db_id=paragraph.id,
            paragraph_id=paragraph.paragraph_id,
            question_db_id=None,
            question_id=None,
            annotation_type="vocabulary",
            selected_text="small desk",
            note=None,
            start_offset=None,
            end_offset=None,
        )
        session.add(annotation)
        session.commit()
    finally:
        session.close()

    response = client.get("/api/annotations", params={"pack_id": "attempt-reading-pack"})
    assert response.status_code == 200
    body = response.json()
    legacy = next(item for item in body if item["annotation_id"] == "annotation-legacy-test")
    assert legacy["start_offset"] is None
    assert legacy["end_offset"] is None


def test_rejects_missing_pack(client: TestClient, imported_pack: dict) -> None:
    response = client.post("/api/annotations", json=build_annotation_payload("answer_evidence", pack_id="missing-pack"))

    assert response.status_code == 404
    assert "Reading pack not found" in response.json()["detail"]


def test_rejects_passage_not_in_pack(client: TestClient, imported_pack: dict) -> None:
    response = client.post("/api/annotations", json=build_annotation_payload("answer_evidence", passage_id="missing-passage"))

    assert response.status_code == 400
    assert "passage_id does not belong" in response.json()["detail"]


def test_rejects_paragraph_not_in_passage(client: TestClient, imported_pack: dict) -> None:
    response = client.post("/api/annotations", json=build_annotation_payload("answer_evidence", paragraph_id="missing-paragraph"))

    assert response.status_code == 400
    assert "paragraph_id does not belong" in response.json()["detail"]


def test_rejects_question_not_in_pack(client: TestClient, imported_pack: dict) -> None:
    response = client.post("/api/annotations", json=build_annotation_payload("answer_evidence", question_id="missing-question"))

    assert response.status_code == 400
    assert "question_id does not belong" in response.json()["detail"]


def test_rejects_only_start_offset(client: TestClient, imported_pack: dict) -> None:
    response = client.post("/api/annotations", json=build_annotation_payload("vocabulary", start_offset=24))

    assert response.status_code == 400
    assert "must both be provided or both be null" in response.json()["detail"]


def test_rejects_only_end_offset(client: TestClient, imported_pack: dict) -> None:
    response = client.post("/api/annotations", json=build_annotation_payload("vocabulary", end_offset=39))

    assert response.status_code == 400
    assert "must both be provided or both be null" in response.json()["detail"]


def test_rejects_negative_start_offset(client: TestClient, imported_pack: dict) -> None:
    response = client.post("/api/annotations", json=build_annotation_payload(
        "vocabulary", selected_text="near the window", start_offset=-1, end_offset=39
    ))

    assert response.status_code == 400
    assert response.json()["detail"] == "start_offset must be greater than or equal to 0"


def test_rejects_negative_end_offset(client: TestClient, imported_pack: dict) -> None:
    response = client.post("/api/annotations", json=build_annotation_payload(
        "vocabulary", selected_text="near the window", start_offset=24, end_offset=-1
    ))

    assert response.status_code == 400
    assert response.json()["detail"] == "end_offset must be greater than or equal to 0"


def test_rejects_equal_offsets(client: TestClient, imported_pack: dict) -> None:
    response = client.post("/api/annotations", json=build_annotation_payload(
        "vocabulary", selected_text="n", start_offset=24, end_offset=24
    ))

    assert response.status_code == 400
    assert response.json()["detail"] == "start_offset must be less than end_offset"


def test_rejects_start_offset_greater_than_end_offset(client: TestClient, imported_pack: dict) -> None:
    response = client.post("/api/annotations", json=build_annotation_payload(
        "vocabulary", selected_text="n", start_offset=30, end_offset=24
    ))

    assert response.status_code == 400
    assert response.json()["detail"] == "start_offset must be less than end_offset"


def test_rejects_end_offset_out_of_bounds(client: TestClient, imported_pack: dict) -> None:
    response = client.post("/api/annotations", json=build_annotation_payload(
        "vocabulary", selected_text="near the window", start_offset=24, end_offset=99
    ))

    assert response.status_code == 400
    assert response.json()["detail"] == "end_offset exceeds paragraph text length"


def test_rejects_selected_text_that_does_not_match_slice(client: TestClient, imported_pack: dict) -> None:
    response = client.post("/api/annotations", json=build_annotation_payload(
        "vocabulary", selected_text="Near the window", start_offset=24, end_offset=39
    ))

    assert response.status_code == 400
    assert "must exactly match" in response.json()["detail"]


def test_rejects_whitespace_only_slice(client: TestClient, imported_pack: dict) -> None:
    response = client.post("/api/annotations", json=build_annotation_payload(
        "vocabulary", selected_text=" ", start_offset=23, end_offset=24
    ))

    assert response.status_code == 400
    assert response.json()["detail"] == "selected_text must not be only whitespace"


def test_rejects_paragraph_that_belongs_to_another_pack(client: TestClient, imported_pack: dict) -> None:
    import_custom_pack(
        client,
        pack_id="second-pack",
        passage_id="passage-second",
        paragraph_1_id="para-second-1",
        paragraph_1_text="This is a second pack paragraph.",
    )

    response = client.post("/api/annotations", json=build_annotation_payload(
        "answer_evidence",
        paragraph_id="para-second-1",
    ))

    assert response.status_code == 400
    assert "paragraph_id does not belong to passage" in response.json()["detail"]


def test_rejects_duplicate_vocabulary_annotation_range_without_creating_extra_library_item(client: TestClient, imported_pack: dict) -> None:
    first = client.post("/api/annotations", json=build_annotation_payload(
        "vocabulary", selected_text="near the window", start_offset=24, end_offset=39
    ))
    assert first.status_code == 200
    assert len(list_vocabulary(client)) == 1

    second = client.post("/api/annotations", json=build_annotation_payload(
        "vocabulary", selected_text="near the window", start_offset=24, end_offset=39
    ))

    assert second.status_code == 409
    assert "annotation range already exists" in second.json()["detail"]
    assert len(client.get("/api/annotations", params={"pack_id": "attempt-reading-pack"}).json()) == 1
    assert len(list_vocabulary(client)) == 1


def test_rejects_duplicate_sentence_annotation_range_without_creating_extra_library_item(client: TestClient, imported_pack: dict) -> None:
    first = client.post("/api/annotations", json=build_annotation_payload(
        "difficult_sentence", selected_text="small desk near the window", start_offset=13, end_offset=39
    ))
    assert first.status_code == 200
    assert len(list_sentences(client)) == 1

    second = client.post("/api/annotations", json=build_annotation_payload(
        "difficult_sentence", selected_text="small desk near the window", start_offset=13, end_offset=39
    ))

    assert second.status_code == 409
    assert "annotation range already exists" in second.json()["detail"]
    assert len(client.get("/api/annotations", params={"pack_id": "attempt-reading-pack"}).json()) == 1
    assert len(list_sentences(client)) == 1


def test_allows_same_range_for_different_annotation_types(client: TestClient, imported_pack: dict) -> None:
    first = client.post("/api/annotations", json=build_annotation_payload(
        "answer_evidence", selected_text="near the window", start_offset=24, end_offset=39
    ))
    second = client.post("/api/annotations", json=build_annotation_payload(
        "vocabulary", selected_text="near the window", start_offset=24, end_offset=39
    ))

    assert first.status_code == 200
    assert second.status_code == 200


def test_allows_partially_overlapping_ranges(client: TestClient, imported_pack: dict) -> None:
    first = client.post("/api/annotations", json=build_annotation_payload(
        "vocabulary", selected_text="small desk", start_offset=13, end_offset=23
    ))
    second = client.post("/api/annotations", json=build_annotation_payload(
        "vocabulary", selected_text="desk near", start_offset=19, end_offset=28
    ))

    assert first.status_code == 200
    assert second.status_code == 200


def test_allows_contained_ranges(client: TestClient, imported_pack: dict) -> None:
    first = client.post("/api/annotations", json=build_annotation_payload(
        "difficult_sentence", selected_text="small desk near the window", start_offset=13, end_offset=39
    ))
    second = client.post("/api/annotations", json=build_annotation_payload(
        "difficult_sentence", selected_text="near the window", start_offset=24, end_offset=39
    ))

    assert first.status_code == 200
    assert second.status_code == 200


def test_rolls_back_annotation_when_auto_vocabulary_creation_fails(client: TestClient, imported_pack: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args, **kwargs):
        raise vocabulary_service.VocabularyError(400, "forced vocabulary failure")

    monkeypatch.setattr(vocabulary_service, "create_vocabulary_item_no_commit", fail)

    response = client.post("/api/annotations", json=build_annotation_payload(
        "vocabulary", selected_text="near the window", start_offset=24, end_offset=39
    ))

    assert response.status_code == 400
    assert response.json()["detail"] == "forced vocabulary failure"
    assert client.get("/api/annotations", params={"pack_id": "attempt-reading-pack"}).json() == []
    assert list_vocabulary(client) == []


def test_rolls_back_annotation_when_auto_sentence_creation_fails(client: TestClient, imported_pack: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args, **kwargs):
        raise sentence_service.SentenceError(400, "forced sentence failure")

    monkeypatch.setattr(sentence_service, "create_sentence_item_no_commit", fail)

    response = client.post("/api/annotations", json=build_annotation_payload(
        "difficult_sentence", selected_text="small desk near the window", start_offset=13, end_offset=39
    ))

    assert response.status_code == 400
    assert response.json()["detail"] == "forced sentence failure"
    assert client.get("/api/annotations", params={"pack_id": "attempt-reading-pack"}).json() == []
    assert list_sentences(client) == []


def test_delete_vocabulary_annotation_keeps_vocabulary_item_and_clears_source_annotation_id(client: TestClient, imported_pack: dict) -> None:
    created = client.post("/api/annotations", json=build_annotation_payload(
        "vocabulary", selected_text="near the window", start_offset=24, end_offset=39
    ))
    assert created.status_code == 200
    body = created.json()
    annotation_id = body["annotation"]["annotation_id"]
    vocab_id = body["created_vocabulary_item"]["vocab_id"]

    delete_response = client.delete(f"/api/annotations/{annotation_id}")
    assert delete_response.status_code == 200

    vocabulary_detail = client.get(f"/api/vocabulary/{vocab_id}")
    assert vocabulary_detail.status_code == 200
    detail_body = vocabulary_detail.json()
    assert detail_body["source_annotation_id"] is None
    assert detail_body["source_pack_id"] == "attempt-reading-pack"
    assert detail_body["source_passage_id"] == "passage-attempt"
    assert detail_body["source_paragraph_id"] == "para-attempt-1"


def test_delete_difficult_sentence_annotation_keeps_sentence_item_and_clears_source_annotation_id(client: TestClient, imported_pack: dict) -> None:
    created = client.post("/api/annotations", json=build_annotation_payload(
        "difficult_sentence", selected_text="small desk near the window", start_offset=13, end_offset=39
    ))
    assert created.status_code == 200
    body = created.json()
    annotation_id = body["annotation"]["annotation_id"]
    sentence_id = body["created_sentence_item"]["sentence_id"]

    delete_response = client.delete(f"/api/annotations/{annotation_id}")
    assert delete_response.status_code == 200

    sentence_detail = client.get(f"/api/sentences/{sentence_id}")
    assert sentence_detail.status_code == 200
    detail_body = sentence_detail.json()
    assert detail_body["source_annotation_id"] is None
    assert detail_body["source_pack_id"] == "attempt-reading-pack"
    assert detail_body["source_passage_id"] == "passage-attempt"
    assert detail_body["source_paragraph_id"] == "para-attempt-1"


def test_delete_vocabulary_item_does_not_delete_annotation(client: TestClient, imported_pack: dict) -> None:
    created = client.post("/api/annotations", json=build_annotation_payload(
        "vocabulary", selected_text="near the window", start_offset=24, end_offset=39
    ))
    assert created.status_code == 200
    annotation_id = created.json()["annotation"]["annotation_id"]
    vocab_id = created.json()["created_vocabulary_item"]["vocab_id"]

    deleted = client.delete(f"/api/vocabulary/{vocab_id}")
    assert deleted.status_code == 200

    annotations = client.get("/api/annotations", params={"pack_id": "attempt-reading-pack"})
    assert annotations.status_code == 200
    assert annotations.json()[0]["annotation_id"] == annotation_id


def test_delete_sentence_item_does_not_delete_annotation(client: TestClient, imported_pack: dict) -> None:
    created = client.post("/api/annotations", json=build_annotation_payload(
        "difficult_sentence", selected_text="small desk near the window", start_offset=13, end_offset=39
    ))
    assert created.status_code == 200
    annotation_id = created.json()["annotation"]["annotation_id"]
    sentence_id = created.json()["created_sentence_item"]["sentence_id"]

    deleted = client.delete(f"/api/sentences/{sentence_id}")
    assert deleted.status_code == 200

    annotations = client.get("/api/annotations", params={"pack_id": "attempt-reading-pack"})
    assert annotations.status_code == 200
    assert annotations.json()[0]["annotation_id"] == annotation_id


def test_handles_smart_quotes_and_em_dash_with_code_point_offsets(client: TestClient, imported_pack: dict) -> None:
    paragraph_text = 'He said “go”—then left.'
    selected_text = '“go”—then'
    import_custom_pack(
        client,
        pack_id="unicode-pack",
        passage_id="passage-unicode",
        paragraph_1_id="para-unicode-1",
        paragraph_1_text=paragraph_text,
    )
    start_offset = paragraph_text.index(selected_text)
    end_offset = start_offset + len(selected_text)

    response = client.post("/api/annotations", json={
        "pack_id": "unicode-pack",
        "passage_id": "passage-unicode",
        "paragraph_id": "para-unicode-1",
        "question_id": "q-attempt-1",
        "annotation_type": "difficult_sentence",
        "selected_text": selected_text,
        "start_offset": start_offset,
        "end_offset": end_offset,
        "note": None,
    })

    assert response.status_code == 200
    body = response.json()["annotation"]
    assert body["selected_text"] == selected_text
    assert body["start_offset"] == start_offset
    assert body["end_offset"] == end_offset


def test_handles_non_bmp_characters_with_code_point_offsets(client: TestClient, imported_pack: dict) -> None:
    paragraph_text = "A 😀 smile appears."
    import_custom_pack(
        client,
        pack_id="emoji-pack",
        passage_id="passage-emoji",
        paragraph_1_id="para-emoji-1",
        paragraph_1_text=paragraph_text,
    )
    start_offset = paragraph_text.index("😀")
    end_offset = start_offset + 1

    response = client.post("/api/annotations", json={
        "pack_id": "emoji-pack",
        "passage_id": "passage-emoji",
        "paragraph_id": "para-emoji-1",
        "question_id": "q-attempt-1",
        "annotation_type": "vocabulary",
        "selected_text": "😀",
        "start_offset": start_offset,
        "end_offset": end_offset,
        "note": "emoji",
    })

    assert response.status_code == 200
    body = response.json()["annotation"]
    assert body["selected_text"] == "😀"
    assert body["start_offset"] == start_offset
    assert body["end_offset"] == end_offset


def test_lists_annotations_for_current_pack_only(client: TestClient, imported_pack: dict) -> None:
    first = client.post("/api/annotations", json=build_annotation_payload("answer_evidence", selected_text="near the window"))
    assert first.status_code == 200

    second_pack_payload = copy.deepcopy(load_fixture_payload())
    second_pack_payload["pack_id"] = "second-pack"
    second_pack_payload["title"] = "Second Pack"
    second_pack_payload["passages"][0]["passage_id"] = "passage-second"
    second_pack_payload["passages"][0]["paragraphs"][0]["paragraph_id"] = "para-second-1"
    second_pack_payload["passages"][0]["paragraphs"][1]["paragraph_id"] = "para-second-2"
    second_pack_payload["questions"][0]["question_id"] = "q-second-1"
    second_pack_payload["questions"][0]["passage_id"] = "passage-second"
    second_pack_payload["questions"][1]["question_id"] = "q-second-2"
    second_pack_payload["questions"][1]["passage_id"] = "passage-second"
    second_pack_payload["answer_key"][0]["question_id"] = "q-second-1"
    second_pack_payload["answer_key"][1]["question_id"] = "q-second-2"
    import_pack(client, second_pack_payload)

    third = client.post("/api/annotations", json={
        "pack_id": "second-pack",
        "passage_id": "passage-second",
        "paragraph_id": "para-second-1",
        "question_id": "q-second-1",
        "annotation_type": "answer_evidence",
        "selected_text": "small desk",
        "note": None,
    })
    assert third.status_code == 200

    list_response = client.get("/api/annotations", params={"pack_id": "attempt-reading-pack"})
    assert list_response.status_code == 200
    body = list_response.json()
    assert len(body) == 1
    assert body[0]["pack_id"] == "attempt-reading-pack"
    assert body[0]["annotation_id"] == first.json()["annotation"]["annotation_id"]
    assert "annotation" not in body[0]


def test_list_returns_404_for_missing_pack(client: TestClient) -> None:
    response = client.get("/api/annotations", params={"pack_id": "missing-pack"})

    assert response.status_code == 404
    assert "Reading pack not found" in response.json()["detail"]


def test_deletes_annotation_and_removes_it_from_list(client: TestClient, imported_pack: dict) -> None:
    created = client.post("/api/annotations", json=build_annotation_payload("answer_evidence", question_id=None))
    assert created.status_code == 200
    annotation_id = created.json()["annotation"]["annotation_id"]

    delete_response = client.delete(f"/api/annotations/{annotation_id}")
    assert delete_response.status_code == 200
    assert delete_response.json() == {"deleted": True, "annotation_id": annotation_id}

    list_response = client.get("/api/annotations", params={"pack_id": "attempt-reading-pack"})
    assert list_response.status_code == 200
    assert list_response.json() == []


def test_delete_returns_404_for_missing_annotation(client: TestClient, imported_pack: dict) -> None:
    response = client.delete("/api/annotations/annotation-missing")

    assert response.status_code == 404
    assert "Annotation not found" in response.json()["detail"]
