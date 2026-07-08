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


def submit_attempt(client: TestClient) -> dict:
    response = client.post("/api/practice-attempts", json={
        "pack_id": "attempt-reading-pack",
        "correct_count": 99,
        "answers": [
            {"question_id": "q-attempt-1", "selected_answer": "A"},
            {"question_id": "q-attempt-2", "selected_answer": "A"}
        ]
    })
    assert response.status_code == 200
    return response.json()


def test_successfully_submits_attempt(client: TestClient, imported_pack: dict) -> None:
    attempt = submit_attempt(client)

    assert attempt["pack_id"] == "attempt-reading-pack"
    assert attempt["total_questions"] == 2
    assert len(attempt["answers"]) == 2
    assert attempt["answers"][0]["question_id"] == "q-attempt-1"


def test_backend_calculates_correct_count_and_accuracy(client: TestClient, imported_pack: dict) -> None:
    attempt = submit_attempt(client)

    assert attempt["correct_count"] == 1
    assert attempt["accuracy"] == 0.5
    answer_map = {answer["question_id"]: answer for answer in attempt["answers"]}
    assert answer_map["q-attempt-1"]["is_correct"] is True
    assert answer_map["q-attempt-2"]["correct_answer"] == "B"
    assert answer_map["q-attempt-2"]["is_correct"] is False


def test_rejects_missing_pack_id(client: TestClient) -> None:
    response = client.post("/api/practice-attempts", json={
        "pack_id": "missing-pack",
        "answers": [{"question_id": "q-attempt-1", "selected_answer": "A"}]
    })

    assert response.status_code == 404
    assert "Reading pack not found" in response.json()["detail"]


def test_rejects_question_not_in_pack(client: TestClient, imported_pack: dict) -> None:
    response = client.post("/api/practice-attempts", json={
        "pack_id": "attempt-reading-pack",
        "answers": [{"question_id": "missing-question", "selected_answer": "A"}]
    })

    assert response.status_code == 400
    assert "does not belong" in response.json()["detail"]


def test_lists_and_reads_attempt_detail(client: TestClient, imported_pack: dict) -> None:
    attempt = submit_attempt(client)

    list_response = client.get("/api/practice-attempts")
    assert list_response.status_code == 200
    attempts = list_response.json()
    assert len(attempts) == 1
    assert attempts[0]["attempt_id"] == attempt["attempt_id"]

    detail_response = client.get(f"/api/practice-attempts/{attempt['attempt_id']}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["attempt_id"] == attempt["attempt_id"]
    assert detail["correct_count"] == 1
    assert [answer["question_id"] for answer in detail["answers"]] == ["q-attempt-1", "q-attempt-2"]
