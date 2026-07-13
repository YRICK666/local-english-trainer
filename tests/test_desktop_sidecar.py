from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from backend import desktop_sidecar
from backend.app.runtime_config import DEVELOPMENT_DATABASE_PATH, ensure_user_directories
from backend.app.version import API_PROTOCOL_VERSION, APP_VERSION, SCHEMA_VERSION


TOKEN = "sidecar-token-" + "a" * 40


def sidecar_environment(tmp_path: Path, **overrides: str) -> dict[str, str]:
    environment = {
        desktop_sidecar.ENV_MODE: desktop_sidecar.DESKTOP_MODE,
        desktop_sidecar.ENV_USER_DATA_ROOT: str(tmp_path / "user-data"),
        desktop_sidecar.ENV_STARTUP_TOKEN: TOKEN,
        desktop_sidecar.ENV_READY_FILE: str(tmp_path / "ready" / "sidecar.json"),
        desktop_sidecar.ENV_PORT: "0",
    }
    environment.update(overrides)
    return environment


def test_import_has_no_user_data_or_database_side_effect(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "not-created-on-import"
    monkeypatch.setenv(desktop_sidecar.ENV_USER_DATA_ROOT, str(root))
    importlib.reload(desktop_sidecar)

    assert not root.exists()
    assert not DEVELOPMENT_DATABASE_PATH.exists()


@pytest.mark.parametrize(
    "override",
    [
        {desktop_sidecar.ENV_MODE: "development"},
        {desktop_sidecar.ENV_USER_DATA_ROOT: ""},
        {desktop_sidecar.ENV_STARTUP_TOKEN: "short"},
        {desktop_sidecar.ENV_STARTUP_TOKEN: "a" * 31},
        {desktop_sidecar.ENV_STARTUP_TOKEN: "a" * 31 + " "},
        {desktop_sidecar.ENV_READY_FILE: ""},
    ],
)
def test_missing_or_invalid_required_sidecar_configuration_is_rejected(tmp_path: Path, override: dict[str, str]) -> None:
    with pytest.raises(desktop_sidecar.SidecarConfigError):
        desktop_sidecar.load_sidecar_config(sidecar_environment(tmp_path, **override))


def test_runtime_configuration_uses_only_explicit_temporary_user_root(tmp_path: Path) -> None:
    config = desktop_sidecar.load_sidecar_config(sidecar_environment(tmp_path))

    assert config.runtime_config.run_mode == desktop_sidecar.DESKTOP_MODE
    assert config.runtime_config.user_data_root == tmp_path / "user-data"
    assert config.runtime_config.database_path == tmp_path / "user-data" / "data" / "local_english_trainer.sqlite3"
    assert config.runtime_config.database_path != DEVELOPMENT_DATABASE_PATH
    assert not (tmp_path / "user-data").exists()


def test_invalid_storage_root_does_not_create_ready_file_or_start_listener(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    invalid_root = tmp_path / "root-file"
    invalid_root.write_text("not a directory", encoding="utf-8")
    config = desktop_sidecar.load_sidecar_config(
        sidecar_environment(tmp_path, **{desktop_sidecar.ENV_USER_DATA_ROOT: str(invalid_root)})
    )
    monkeypatch.setattr(desktop_sidecar, "create_loopback_socket", lambda _port: pytest.fail("listener must not start"))

    assert desktop_sidecar.run_sidecar(config) == 1
    assert not config.ready_file.exists()


def test_loopback_socket_owns_random_port_without_reuse_window() -> None:
    first = desktop_sidecar.create_loopback_socket(0)
    second = desktop_sidecar.create_loopback_socket(0)
    try:
        first_host, first_port = first.getsockname()
        second_host, second_port = second.getsockname()
    finally:
        first.close()
        second.close()

    assert first_host == desktop_sidecar.LOOPBACK_HOST
    assert second_host == desktop_sidecar.LOOPBACK_HOST
    assert first_port > 0
    assert second_port > 0
    assert first_port != second_port


def test_ready_file_is_atomic_stale_safe_and_contains_no_sensitive_paths(tmp_path: Path) -> None:
    config = desktop_sidecar.load_sidecar_config(sidecar_environment(tmp_path))
    config.ready_file.parent.mkdir(parents=True)
    config.ready_file.write_text('{"status":"ready","stale":true}', encoding="utf-8")
    desktop_sidecar.remove_ready_file(config.ready_file)
    payload = desktop_sidecar.ready_payload(pid=123, port=45678, runtime_config=config.runtime_config)

    desktop_sidecar.write_ready_file(config.ready_file, payload)

    stored = json.loads(config.ready_file.read_text(encoding="utf-8"))
    assert stored == {
        "status": "ready",
        "pid": 123,
        "host": "127.0.0.1",
        "port": 45678,
        "app_version": APP_VERSION,
        "api_protocol_version": API_PROTOCOL_VERSION,
        "schema_version": SCHEMA_VERSION,
        "run_mode": "desktop_production",
    }
    assert TOKEN not in config.ready_file.read_text(encoding="utf-8")
    assert str(config.runtime_config.database_path) not in config.ready_file.read_text(encoding="utf-8")
    assert not list(config.ready_file.parent.glob("*.tmp"))

    desktop_sidecar.remove_ready_file(config.ready_file)
    assert not config.ready_file.exists()


def test_sidecar_log_is_under_explicit_user_root_and_does_not_contain_token(tmp_path: Path) -> None:
    config = desktop_sidecar.load_sidecar_config(sidecar_environment(tmp_path))
    ensure_user_directories(config.runtime_config)
    logger = desktop_sidecar.configure_sidecar_logging(config.runtime_config)
    logger.info("test sidecar startup")
    desktop_sidecar.close_sidecar_logging(logger)

    log_file = config.runtime_config.logs_dir / "sidecar.log"
    assert log_file.is_file()
    assert TOKEN not in log_file.read_text(encoding="utf-8")


def test_ready_version_contract_matches_python_constants(tmp_path: Path) -> None:
    config = desktop_sidecar.load_sidecar_config(sidecar_environment(tmp_path))
    payload = desktop_sidecar.ready_payload(pid=1, port=12345, runtime_config=config.runtime_config)

    assert payload["app_version"] == APP_VERSION
    assert payload["api_protocol_version"] == API_PROTOCOL_VERSION
    assert payload["schema_version"] == SCHEMA_VERSION
