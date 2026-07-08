from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import db as app_db
from backend.app.main import app

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


def build_annotation_payload(annotation_type: str, **overrides: str | None) -> dict:
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


@pytest.mark.parametrize("annotation_type", [
    "answer_evidence",
    "synonym_replacement",
    "vocabulary",
    "difficult_sentence",
])
def test_creates_supported_annotation_types(client: TestClient, imported_pack: dict, annotation_type: str) -> None:
    response = client.post("/api/annotations", json=build_annotation_payload(annotation_type))

    assert response.status_code == 200
    body = response.json()
    assert body["annotation_id"].startswith("annotation-")
    assert body["annotation_type"] == annotation_type
    assert body["pack_id"] == "attempt-reading-pack"
    assert body["question_id"] == "q-attempt-1"


def test_rejects_invalid_annotation_type(client: TestClient, imported_pack: dict) -> None:
    response = client.post("/api/annotations", json=build_annotation_payload("invalid_type"))

    assert response.status_code == 400
    assert "annotation_type is invalid" in response.json()["detail"]


def test_rejects_blank_selected_text(client: TestClient, imported_pack: dict) -> None:
    response = client.post("/api/annotations", json=build_annotation_payload("vocabulary", selected_text="   "))

    assert response.status_code == 400
    assert response.json()["detail"] == "selected_text must not be empty"


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
        "annotation_type": "vocabulary",
        "selected_text": "small desk",
        "note": None,
    })
    assert third.status_code == 200

    list_response = client.get("/api/annotations", params={"pack_id": "attempt-reading-pack"})
    assert list_response.status_code == 200
    body = list_response.json()
    assert len(body) == 1
    assert body[0]["pack_id"] == "attempt-reading-pack"
    assert body[0]["annotation_id"] == first.json()["annotation_id"]


def test_list_returns_404_for_missing_pack(client: TestClient) -> None:
    response = client.get("/api/annotations", params={"pack_id": "missing-pack"})

    assert response.status_code == 404
    assert "Reading pack not found" in response.json()["detail"]


def test_deletes_annotation_and_removes_it_from_list(client: TestClient, imported_pack: dict) -> None:
    created = client.post("/api/annotations", json=build_annotation_payload("difficult_sentence", question_id=None))
    assert created.status_code == 200
    annotation_id = created.json()["annotation_id"]

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
