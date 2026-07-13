from __future__ import annotations

import asyncio
import inspect

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app import desktop_security


TOKEN = "a" * 40


def make_application(*, allowed_origins: tuple[str, ...] = ()):
    app = FastAPI()
    app.get("/health")(lambda: {"status": "ok"})
    shutdown_calls: list[str] = []
    protected = desktop_security.wrap_desktop_app(
        app,
        startup_token=TOKEN,
        shutdown_callback=lambda: shutdown_calls.append("called"),
        allowed_origins=allowed_origins,
    )
    return protected, shutdown_calls


def token_headers(token: str = TOKEN) -> dict[str, str]:
    return {"X-Local-English-Trainer-Token": token}


def test_missing_and_incorrect_tokens_are_rejected_without_leaking_token() -> None:
    protected, _ = make_application()
    with TestClient(protected) as client:
        missing = client.get("/health")
        incorrect = client.get("/health", headers=token_headers("b" * 40))

    assert missing.status_code == 401
    assert incorrect.status_code == 401
    assert TOKEN not in missing.text
    assert TOKEN not in incorrect.text


def test_correct_token_forwards_to_original_application() -> None:
    protected, _ = make_application()
    with TestClient(protected) as client:
        response = client.get("/health", headers=token_headers())

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert TOKEN not in response.text


def test_shutdown_requires_token_and_never_enters_original_application() -> None:
    calls: list[str] = []

    async def original_application(scope, receive, send):
        if scope["type"] == "lifespan":
            await receive()
            await send({"type": "lifespan.startup.complete"})
            await receive()
            await send({"type": "lifespan.shutdown.complete"})
            return
        calls.append(scope["path"])
        await send({"type": "http.response.start", "status": 404, "headers": []})
        await send({"type": "http.response.body", "body": b"original"})

    shutdown_calls: list[str] = []
    protected = desktop_security.wrap_desktop_app(
        original_application,
        startup_token=TOKEN,
        shutdown_callback=lambda: shutdown_calls.append("called"),
    )
    with TestClient(protected) as client:
        assert client.post("/desktop/shutdown").status_code == 401
        assert client.post("/desktop/shutdown", headers=token_headers("b" * 40)).status_code == 401
        accepted = client.post("/desktop/shutdown", headers=token_headers())

    assert accepted.status_code == 200
    assert accepted.json() == {"status": "shutting_down"}
    assert shutdown_calls == ["called"]
    assert calls == []


def test_token_comparison_uses_hmac_compare_digest(monkeypatch) -> None:
    protected, _ = make_application()
    observed: list[tuple[str, str]] = []

    def compare_digest(provided: str, expected: str) -> bool:
        observed.append((provided, expected))
        return True

    monkeypatch.setattr(desktop_security.hmac, "compare_digest", compare_digest)
    with TestClient(protected) as client:
        response = client.get("/health", headers=token_headers())

    assert response.status_code == 200
    assert observed == [(TOKEN, TOKEN)]
    assert "compare_digest" in inspect.getsource(desktop_security.DesktopSecurityApp._has_valid_token)


def test_lifespan_scope_bypasses_token_check() -> None:
    received = []
    sent = []
    messages = iter(({"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}))

    async def original_application(scope, receive, send):
        assert scope["type"] == "lifespan"
        startup = await receive()
        received.append(startup["type"])
        await send({"type": "lifespan.startup.complete"})
        shutdown = await receive()
        received.append(shutdown["type"])
        await send({"type": "lifespan.shutdown.complete"})

    async def receive():
        return next(messages)

    async def send(message):
        sent.append(message["type"])

    protected = desktop_security.wrap_desktop_app(original_application, startup_token=TOKEN, shutdown_callback=lambda: None)
    asyncio.run(protected({"type": "lifespan", "asgi": {"version": "3.0"}}, receive, send))

    assert received == ["lifespan.startup", "lifespan.shutdown"]
    assert sent == ["lifespan.startup.complete", "lifespan.shutdown.complete"]


def test_allowed_origin_preflight_bypasses_token_and_disallowed_origin_is_not_wildcarded() -> None:
    protected, _ = make_application(allowed_origins=("http://desktop.local",))
    with TestClient(protected) as client:
        allowed = client.options(
            "/health",
            headers={"Origin": "http://desktop.local", "Access-Control-Request-Method": "GET"},
        )
        blocked = client.options(
            "/health",
            headers={"Origin": "http://untrusted.local", "Access-Control-Request-Method": "GET"},
        )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://desktop.local"
    assert blocked.headers.get("access-control-allow-origin") != "*"


def test_empty_allowlist_and_null_origin_never_become_wildcards() -> None:
    protected, _ = make_application()
    with TestClient(protected) as client:
        response = client.get("/health", headers={**token_headers(), "Origin": "null"})

    assert response.headers.get("access-control-allow-origin") != "*"
    assert desktop_security.parse_allowed_origins("null, http://desktop.local, ") == ("http://desktop.local",)
