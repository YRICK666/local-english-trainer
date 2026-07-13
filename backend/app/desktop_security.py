from __future__ import annotations

import hmac
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


TOKEN_HEADER = b"x-local-english-trainer-token"
SHUTDOWN_PATH = "/desktop/shutdown"


def parse_allowed_origins(raw_origins: str | None) -> tuple[str, ...]:
    if not raw_origins:
        return ()
    return tuple(origin for origin in (item.strip() for item in raw_origins.split(",")) if origin and origin != "null")


class DesktopSecurityApp:
    """ASGI boundary used only by the desktop sidecar process."""

    def __init__(self, app: ASGIApp, *, startup_token: str, shutdown_callback: Callable[[], None]) -> None:
        self._app = app
        self._startup_token = startup_token
        self._shutdown_callback = shutdown_callback

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        if not self._has_valid_token(scope):
            await JSONResponse({"detail": "Unauthorized"}, status_code=401)(scope, receive, send)
            return

        if scope["path"] == SHUTDOWN_PATH and scope["method"] == "POST":
            self._shutdown_callback()
            await JSONResponse({"status": "shutting_down"})(scope, receive, send)
            return

        await self._app(scope, receive, send)

    def _has_valid_token(self, scope: Scope) -> bool:
        provided = next((value for name, value in scope.get("headers", []) if name.lower() == TOKEN_HEADER), None)
        if provided is None:
            return False
        try:
            provided_token = provided.decode("utf-8")
        except UnicodeDecodeError:
            return False
        return hmac.compare_digest(provided_token, self._startup_token)


def wrap_desktop_app(app: ASGIApp, *, startup_token: str, shutdown_callback: Callable[[], None], allowed_origins: Sequence[str] = ()) -> ASGIApp:
    protected_app = DesktopSecurityApp(app, startup_token=startup_token, shutdown_callback=shutdown_callback)
    return CORSMiddleware(
        protected_app,
        allow_origins=list(allowed_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["X-Local-English-Trainer-Token", "Content-Type"],
    )
