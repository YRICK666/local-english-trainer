from __future__ import annotations

import json
import logging
import os
import socket
import sys
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Mapping
from uuid import uuid4


ENV_MODE = "LOCAL_ENGLISH_TRAINER_MODE"
ENV_USER_DATA_ROOT = "LOCAL_ENGLISH_TRAINER_USER_DATA_ROOT"
ENV_STARTUP_TOKEN = "LOCAL_ENGLISH_TRAINER_STARTUP_TOKEN"
ENV_READY_FILE = "LOCAL_ENGLISH_TRAINER_READY_FILE"
ENV_ALLOWED_ORIGINS = "LOCAL_ENGLISH_TRAINER_ALLOWED_ORIGINS"
ENV_PORT = "LOCAL_ENGLISH_TRAINER_PORT"
ENV_DATABASE_URL = "LOCAL_ENGLISH_TRAINER_DATABASE_URL"

DESKTOP_MODE = "desktop_production"
LOOPBACK_HOST = "127.0.0.1"
MINIMUM_TOKEN_LENGTH = 32
INSECURE_TOKENS = {"default", "default-token", "local-english-trainer-startup-token", "change-me"}


class SidecarConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class SidecarConfig:
    runtime_config: object
    startup_token: str
    ready_file: Path
    allowed_origins: tuple[str, ...]
    port: int


def load_sidecar_config(environ: Mapping[str, str] | None = None) -> SidecarConfig:
    env = os.environ if environ is None else environ
    mode = (env.get(ENV_MODE) or "").strip()
    if mode != DESKTOP_MODE:
        raise SidecarConfigError("desktop sidecar requires desktop_production mode")

    root_value = (env.get(ENV_USER_DATA_ROOT) or "").strip()
    if not root_value:
        raise SidecarConfigError("desktop sidecar requires an explicit user data root")

    token = env.get(ENV_STARTUP_TOKEN) or ""
    if len(token) < MINIMUM_TOKEN_LENGTH or any(character.isspace() for character in token) or token.lower() in INSECURE_TOKENS:
        raise SidecarConfigError("desktop sidecar requires a valid startup token")

    ready_value = (env.get(ENV_READY_FILE) or "").strip()
    if not ready_value:
        raise SidecarConfigError("desktop sidecar requires an explicit ready file")

    port = _parse_port(env.get(ENV_PORT))
    from backend.app.desktop_security import parse_allowed_origins
    from backend.app.runtime_config import build_runtime_config

    runtime_config = build_runtime_config(
        run_mode=DESKTOP_MODE,
        user_data_root=Path(root_value),
        environ=env,
    )
    if runtime_config.database_path is None or runtime_config.user_data_root not in runtime_config.database_path.parents:
        raise SidecarConfigError("desktop sidecar database must remain inside its user data root")

    return SidecarConfig(
        runtime_config=runtime_config,
        startup_token=token,
        ready_file=Path(ready_value),
        allowed_origins=parse_allowed_origins(env.get(ENV_ALLOWED_ORIGINS)),
        port=port,
    )


def _parse_port(raw_port: str | None) -> int:
    if raw_port is None or not raw_port.strip():
        return 0
    try:
        port = int(raw_port)
    except ValueError as exc:
        raise SidecarConfigError("desktop sidecar port must be an integer") from exc
    if not 0 <= port <= 65535:
        raise SidecarConfigError("desktop sidecar port must be between 0 and 65535")
    return port


def prepare_runtime_environment(config: SidecarConfig) -> None:
    """Set the only runtime values that db.py may observe during its import."""
    runtime_config = config.runtime_config
    os.environ[ENV_MODE] = DESKTOP_MODE
    os.environ[ENV_USER_DATA_ROOT] = str(runtime_config.user_data_root)
    os.environ[ENV_DATABASE_URL] = runtime_config.database_url


def create_loopback_socket(port: int) -> socket.socket:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        listener.bind((LOOPBACK_HOST, port))
        return listener
    except Exception:
        listener.close()
        raise


def ready_payload(*, pid: int, port: int, runtime_config: object) -> dict[str, object]:
    return {
        "status": "ready",
        "pid": pid,
        "host": LOOPBACK_HOST,
        "port": port,
        "app_version": runtime_config.app_version,
        "api_protocol_version": runtime_config.api_protocol_version,
        "schema_version": runtime_config.schema_version,
        "run_mode": runtime_config.run_mode,
    }


def write_ready_file(ready_file: Path, payload: Mapping[str, object]) -> None:
    ready_file.parent.mkdir(parents=True, exist_ok=True)
    temporary_file = ready_file.with_name(f".{ready_file.name}.{uuid4().hex}.tmp")
    try:
        temporary_file.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        os.replace(temporary_file, ready_file)
    finally:
        temporary_file.unlink(missing_ok=True)


def remove_ready_file(ready_file: Path) -> None:
    ready_file.unlink(missing_ok=True)


def configure_sidecar_logging(runtime_config: object) -> logging.Logger:
    logger = logging.getLogger("local_english_trainer.sidecar")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for handler in logger.handlers[:]:
        handler.close()
        logger.removeHandler(handler)

    handler = RotatingFileHandler(
        Path(runtime_config.logs_dir) / "sidecar.log",
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    return logger


def close_sidecar_logging(logger: logging.Logger) -> None:
    for handler in logger.handlers[:]:
        handler.flush()
        handler.close()
        logger.removeHandler(handler)


def run_sidecar(config: SidecarConfig) -> int:
    """Run the server after every desktop-only path has been configured."""
    from backend.app.desktop_security import wrap_desktop_app
    from backend.app.runtime_config import ensure_user_directories

    prepare_runtime_environment(config)
    ensure_user_directories(config.runtime_config)
    logger = configure_sidecar_logging(config.runtime_config)
    listener: socket.socket | None = None
    try:
        remove_ready_file(config.ready_file)
        listener = create_loopback_socket(config.port)
        actual_port = int(listener.getsockname()[1])

        # These imports are intentionally delayed until their configuration is fixed above.
        from backend.app import db as app_db

        app_db.configure_runtime_database(config.runtime_config, create_parent=False)
        from backend.app.main import app
        import uvicorn

        server_holder: dict[str, object] = {}

        def request_shutdown() -> None:
            logger.info("shutdown requested")
            server = server_holder["server"]
            server.should_exit = True

        protected_app = wrap_desktop_app(
            app,
            startup_token=config.startup_token,
            shutdown_callback=request_shutdown,
            allowed_origins=config.allowed_origins,
        )

        class ReadyServer(uvicorn.Server):
            async def startup(self, sockets: list[socket.socket] | None = None) -> None:
                await super().startup(sockets=sockets)
                if self.started:
                    write_ready_file(
                        config.ready_file,
                        ready_payload(pid=os.getpid(), port=actual_port, runtime_config=config.runtime_config),
                    )
                    logger.info("sidecar ready on loopback port %s", actual_port)

        uvicorn_config = uvicorn.Config(
            protected_app,
            host=LOOPBACK_HOST,
            port=actual_port,
            log_config=None,
            access_log=False,
            lifespan="on",
        )
        server = ReadyServer(uvicorn_config)
        server_holder["server"] = server
        logger.info(
            "sidecar starting app_version=%s api_protocol_version=%s schema_version=%s",
            config.runtime_config.app_version,
            config.runtime_config.api_protocol_version,
            config.runtime_config.schema_version,
        )
        server.run(sockets=[listener])
        if not server.started:
            logger.error("sidecar startup did not complete")
            return 1
        return 0
    except Exception as exc:
        logger.error("sidecar failed with %s", type(exc).__name__)
        return 1
    finally:
        remove_ready_file(config.ready_file)
        if listener is not None:
            listener.close()
        logger.info("sidecar shutdown complete")
        close_sidecar_logging(logger)


def main() -> int:
    try:
        config = load_sidecar_config()
        return run_sidecar(config)
    except SidecarConfigError as exc:
        print(f"desktop sidecar configuration error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
