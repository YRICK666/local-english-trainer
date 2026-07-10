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


def build_sentence_payload(**overrides: str | None) -> dict:
    payload = {
        "sentence_text": " Nora keeps a small desk near the window. ",
        "translation": "诺拉把一张小书桌放在窗边。",
        "structure_note": "主句 + 介词短语作地点状语",
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
        "annotation_type": "difficult_sentence",
        "selected_text": "Nora keeps a small desk near the window.",
        "note": "annotation source"
    })
    assert response.status_code == 200
    return response.json()


def create_sentence(client: TestClient, **overrides: str | None) -> dict:
    response = client.post("/api/sentences", json=build_sentence_payload(**overrides))
    assert response.status_code == 200
    return response.json()


def test_creates_sentence_item(client: TestClient) -> None:
    response = client.post("/api/sentences", json=build_sentence_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["sentence_id"].startswith("sentence-")
    assert body["sentence_text"] == "Nora keeps a small desk near the window."
    assert body["review_status"] == "learning"


def test_rejects_empty_sentence_text(client: TestClient) -> None:
    response = client.post("/api/sentences", json=build_sentence_payload(sentence_text=""))

    assert response.status_code == 400
    assert response.json()["detail"] == "sentence_text must not be empty"


def test_rejects_blank_sentence_text(client: TestClient) -> None:
    response = client.post("/api/sentences", json=build_sentence_payload(sentence_text="   "))

    assert response.status_code == 400
    assert response.json()["detail"] == "sentence_text must not be empty"


def test_defaults_review_status_to_new(client: TestClient) -> None:
    response = client.post("/api/sentences", json=build_sentence_payload(review_status=None))

    assert response.status_code == 200
    assert response.json()["review_status"] == "new"


def test_rejects_invalid_review_status_on_create(client: TestClient) -> None:
    response = client.post("/api/sentences", json=build_sentence_payload(review_status="invalid"))

    assert response.status_code == 400
    assert "review_status is invalid" in response.json()["detail"]


def test_rejects_missing_source_annotation_id_on_create(client: TestClient) -> None:
    response = client.post("/api/sentences", json=build_sentence_payload(source_annotation_id="annotation-missing"))

    assert response.status_code == 400
    assert "source_annotation_id not found" in response.json()["detail"]


def test_can_create_with_valid_source_annotation_id(client: TestClient, imported_pack: dict) -> None:
    annotation = create_annotation(client)

    response = client.post("/api/sentences", json=build_sentence_payload(source_annotation_id=annotation["annotation_id"]))

    assert response.status_code == 200
    assert response.json()["source_annotation_id"] == annotation["annotation_id"]


def test_rejects_duplicate_source_annotation_id_on_create(client: TestClient, imported_pack: dict) -> None:
    annotation = create_annotation(client)
    first = client.post("/api/sentences", json=build_sentence_payload(sentence_text="Sentence one.", source_annotation_id=annotation["annotation_id"]))

    assert first.status_code == 200

    second = client.post("/api/sentences", json=build_sentence_payload(sentence_text="Sentence two.", source_annotation_id=annotation["annotation_id"]))

    assert second.status_code == 409
    assert "already linked to sentence item" in second.json()["detail"]


def test_duplicate_source_annotation_id_conflict_does_not_create_extra_sentence_item(client: TestClient, imported_pack: dict) -> None:
    annotation = create_annotation(client)
    create_sentence(client, sentence_text="Sentence one.", source_annotation_id=annotation["annotation_id"])

    duplicate = client.post("/api/sentences", json=build_sentence_payload(sentence_text="Sentence two.", source_annotation_id=annotation["annotation_id"]))

    assert duplicate.status_code == 409

    listing = client.get("/api/sentences")

    assert listing.status_code == 200
    body = listing.json()
    assert len(body) == 1
    assert body[0]["source_annotation_id"] == annotation["annotation_id"]


def test_patch_rejects_source_annotation_id_used_by_another_sentence_item(client: TestClient, imported_pack: dict) -> None:
    annotation_one = create_annotation(client)
    annotation_two = client.post("/api/annotations", json={
        "pack_id": "attempt-reading-pack",
        "passage_id": "passage-attempt",
        "paragraph_id": "para-attempt-1",
        "question_id": "q-attempt-1",
        "annotation_type": "difficult_sentence",
        "selected_text": "A second sentence for testing.",
        "note": "second annotation source"
    })
    assert annotation_two.status_code == 200

    first = create_sentence(client, sentence_text="Sentence one.", source_annotation_id=annotation_one["annotation_id"])
    second = create_sentence(client, sentence_text="Sentence two.", source_annotation_id=annotation_two.json()["annotation_id"])

    response = client.patch(
        f"/api/sentences/{second['sentence_id']}",
        json={"source_annotation_id": annotation_one["annotation_id"]}
    )

    assert response.status_code == 409
    assert "already linked to sentence item" in response.json()["detail"]


def test_patch_keeps_same_source_annotation_id_without_conflict(client: TestClient, imported_pack: dict) -> None:
    annotation = create_annotation(client)
    created = create_sentence(client, source_annotation_id=annotation["annotation_id"])

    response = client.patch(
        f"/api/sentences/{created['sentence_id']}",
        json={"source_annotation_id": annotation["annotation_id"], "translation": "updated translation"}
    )

    assert response.status_code == 200
    assert response.json()["source_annotation_id"] == annotation["annotation_id"]
    assert response.json()["translation"] == "updated translation"


def test_allows_multiple_sentence_items_without_source_annotation_id(client: TestClient) -> None:
    first = client.post("/api/sentences", json=build_sentence_payload(sentence_text="Sentence one.", source_annotation_id=None))
    second = client.post("/api/sentences", json=build_sentence_payload(sentence_text="Sentence two.", source_annotation_id=None))

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["source_annotation_id"] is None
    assert second.json()["source_annotation_id"] is None


def test_lists_sentence_items(client: TestClient) -> None:
    first = create_sentence(client, sentence_text="Sentence one.")
    second = create_sentence(client, sentence_text="Sentence two.", review_status="new")

    response = client.get("/api/sentences")

    assert response.status_code == 200
    body = response.json()
    assert [item["sentence_id"] for item in body] == [first["sentence_id"], second["sentence_id"]]


def test_reads_sentence_detail(client: TestClient) -> None:
    created = create_sentence(client)

    response = client.get(f"/api/sentences/{created['sentence_id']}")

    assert response.status_code == 200
    assert response.json()["sentence_id"] == created["sentence_id"]


def test_reads_missing_sentence_detail_returns_404(client: TestClient) -> None:
    response = client.get("/api/sentences/sentence-missing")

    assert response.status_code == 404
    assert "Sentence item not found" in response.json()["detail"]


def test_patch_updates_only_translation(client: TestClient) -> None:
    created = create_sentence(client, translation="old translation")

    response = client.patch(f"/api/sentences/{created['sentence_id']}", json={"translation": "new translation"})

    assert response.status_code == 200
    body = response.json()
    assert body["translation"] == "new translation"
    assert body["sentence_text"] == created["sentence_text"]


def test_patch_updates_only_structure_note(client: TestClient) -> None:
    created = create_sentence(client)

    response = client.patch(f"/api/sentences/{created['sentence_id']}", json={"structure_note": "Updated note."})

    assert response.status_code == 200
    assert response.json()["structure_note"] == "Updated note."


def test_patch_updates_only_review_status(client: TestClient) -> None:
    created = create_sentence(client, review_status="new")

    response = client.patch(f"/api/sentences/{created['sentence_id']}", json={"review_status": "familiar"})

    assert response.status_code == 200
    assert response.json()["review_status"] == "familiar"


def test_patch_rejects_invalid_review_status(client: TestClient) -> None:
    created = create_sentence(client)

    response = client.patch(f"/api/sentences/{created['sentence_id']}", json={"review_status": "invalid"})

    assert response.status_code == 400
    assert "review_status is invalid" in response.json()["detail"]


def test_patch_rejects_empty_sentence_text(client: TestClient) -> None:
    created = create_sentence(client)

    response = client.patch(f"/api/sentences/{created['sentence_id']}", json={"sentence_text": "   "})

    assert response.status_code == 400
    assert response.json()["detail"] == "sentence_text must not be empty"


def test_deletes_sentence_item(client: TestClient) -> None:
    created = create_sentence(client)

    response = client.delete(f"/api/sentences/{created['sentence_id']}")

    assert response.status_code == 200
    assert response.json() == {"deleted": True, "sentence_id": created["sentence_id"]}


def test_delete_missing_sentence_item_returns_404(client: TestClient) -> None:
    response = client.delete("/api/sentences/sentence-missing")

    assert response.status_code == 404
    assert "Sentence item not found" in response.json()["detail"]
