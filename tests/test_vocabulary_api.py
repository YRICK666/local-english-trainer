from __future__ import annotations

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
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    response = client.post("/api/import/reading-pack", json=payload)
    assert response.status_code == 200
    return response.json()["pack"]


def build_vocabulary_payload(**overrides: str | None) -> dict:
    payload = {
        "word": " window ",
        "meaning": "窗户",
        "source_sentence": "Nora keeps a small desk near the window.",
        "source_pack_id": "attempt-reading-pack",
        "source_passage_id": "passage-attempt",
        "source_paragraph_id": "para-attempt-1",
        "source_annotation_id": None,
        "review_status": "learning",
    }
    payload.update(overrides)
    return payload


def create_annotation(client: TestClient) -> dict:
    response = client.post("/api/annotations", json={
        "pack_id": "attempt-reading-pack",
        "passage_id": "passage-attempt",
        "paragraph_id": "para-attempt-1",
        "question_id": "q-attempt-1",
        "annotation_type": "vocabulary",
        "selected_text": "window",
        "note": "annotation source"
    })
    assert response.status_code == 200
    return response.json()


def create_vocabulary(client: TestClient, **overrides: str | None) -> dict:
    response = client.post("/api/vocabulary", json=build_vocabulary_payload(**overrides))
    assert response.status_code == 200
    return response.json()


def test_creates_vocabulary_item(client: TestClient) -> None:
    response = client.post("/api/vocabulary", json=build_vocabulary_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["vocab_id"].startswith("vocab-")
    assert body["word"] == "window"
    assert body["review_status"] == "learning"


def test_rejects_empty_word_string(client: TestClient) -> None:
    response = client.post("/api/vocabulary", json=build_vocabulary_payload(word=""))

    assert response.status_code == 400
    assert response.json()["detail"] == "word must not be empty"


def test_rejects_blank_word_string(client: TestClient) -> None:
    response = client.post("/api/vocabulary", json=build_vocabulary_payload(word="   "))

    assert response.status_code == 400
    assert response.json()["detail"] == "word must not be empty"


def test_defaults_review_status_to_new(client: TestClient) -> None:
    response = client.post("/api/vocabulary", json=build_vocabulary_payload(review_status=None))

    assert response.status_code == 200
    assert response.json()["review_status"] == "new"


def test_rejects_invalid_review_status_on_create(client: TestClient) -> None:
    response = client.post("/api/vocabulary", json=build_vocabulary_payload(review_status="invalid"))

    assert response.status_code == 400
    assert "review_status is invalid" in response.json()["detail"]


def test_rejects_missing_source_annotation_id_on_create(client: TestClient) -> None:
    response = client.post("/api/vocabulary", json=build_vocabulary_payload(source_annotation_id="annotation-missing"))

    assert response.status_code == 400
    assert "source_annotation_id not found" in response.json()["detail"]


def test_can_create_with_valid_source_annotation_id(client: TestClient, imported_pack: dict) -> None:
    annotation = create_annotation(client)

    response = client.post("/api/vocabulary", json=build_vocabulary_payload(source_annotation_id=annotation["annotation_id"]))

    assert response.status_code == 200
    assert response.json()["source_annotation_id"] == annotation["annotation_id"]


def test_lists_vocabulary_items(client: TestClient) -> None:
    first = create_vocabulary(client, word="window")
    second = create_vocabulary(client, word="desk", review_status="new")

    response = client.get("/api/vocabulary")

    assert response.status_code == 200
    body = response.json()
    assert [item["vocab_id"] for item in body] == [first["vocab_id"], second["vocab_id"]]


def test_reads_vocabulary_detail(client: TestClient) -> None:
    created = create_vocabulary(client)

    response = client.get(f"/api/vocabulary/{created['vocab_id']}")

    assert response.status_code == 200
    assert response.json()["vocab_id"] == created["vocab_id"]


def test_reads_missing_vocabulary_detail_returns_404(client: TestClient) -> None:
    response = client.get("/api/vocabulary/vocab-missing")

    assert response.status_code == 404
    assert "Vocabulary item not found" in response.json()["detail"]


def test_patch_updates_only_meaning(client: TestClient) -> None:
    created = create_vocabulary(client, meaning="old meaning")

    response = client.patch(f"/api/vocabulary/{created['vocab_id']}", json={"meaning": "new meaning"})

    assert response.status_code == 200
    body = response.json()
    assert body["meaning"] == "new meaning"
    assert body["word"] == created["word"]


def test_patch_updates_only_source_sentence(client: TestClient) -> None:
    created = create_vocabulary(client)

    response = client.patch(f"/api/vocabulary/{created['vocab_id']}", json={"source_sentence": "Updated source sentence."})

    assert response.status_code == 200
    assert response.json()["source_sentence"] == "Updated source sentence."


def test_patch_updates_only_review_status(client: TestClient) -> None:
    created = create_vocabulary(client, review_status="new")

    response = client.patch(f"/api/vocabulary/{created['vocab_id']}", json={"review_status": "familiar"})

    assert response.status_code == 200
    assert response.json()["review_status"] == "familiar"


def test_patch_rejects_invalid_review_status(client: TestClient) -> None:
    created = create_vocabulary(client)

    response = client.patch(f"/api/vocabulary/{created['vocab_id']}", json={"review_status": "invalid"})

    assert response.status_code == 400
    assert "review_status is invalid" in response.json()["detail"]


def test_patch_rejects_empty_word(client: TestClient) -> None:
    created = create_vocabulary(client)

    response = client.patch(f"/api/vocabulary/{created['vocab_id']}", json={"word": "   "})

    assert response.status_code == 400
    assert response.json()["detail"] == "word must not be empty"


def test_patch_rejects_missing_source_annotation_id(client: TestClient) -> None:
    created = create_vocabulary(client)

    response = client.patch(f"/api/vocabulary/{created['vocab_id']}", json={"source_annotation_id": "annotation-missing"})

    assert response.status_code == 400
    assert "source_annotation_id not found" in response.json()["detail"]


def test_deletes_vocabulary_item(client: TestClient) -> None:
    created = create_vocabulary(client)

    response = client.delete(f"/api/vocabulary/{created['vocab_id']}")

    assert response.status_code == 200
    assert response.json() == {"deleted": True, "vocab_id": created["vocab_id"]}


def test_delete_missing_vocabulary_item_returns_404(client: TestClient) -> None:
    response = client.delete("/api/vocabulary/vocab-missing")

    assert response.status_code == 404
    assert "Vocabulary item not found" in response.json()["detail"]
