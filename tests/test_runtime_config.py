from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app import db as app_db
from backend.app.main import app
from backend.app.runtime_config import (
    APP_DATA_DIR_NAME,
    DATABASE_FILE_NAME,
    DEVELOPMENT_DATABASE_PATH,
    RUN_MODE_DESKTOP_PRODUCTION,
    RUN_MODE_DEVELOPMENT,
    RUN_MODE_TEST,
    RuntimeConfigError,
    build_runtime_config,
    ensure_user_directories,
    sqlite_url_from_path,
)
from backend.app.version import API_PROTOCOL_VERSION, APP_VERSION, SCHEMA_VERSION


@pytest.fixture()
def runtime_tmp() -> Path:
    root = Path.cwd() / ".runtime-test-tmp"
    root.mkdir(parents=True, exist_ok=True)
    temp_dir = root / f"runtime-{uuid4().hex}"
    temp_dir.mkdir()
    try:
        yield temp_dir
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_development_default_keeps_project_data_database_path() -> None:
    config = build_runtime_config(environ={})

    assert config.run_mode == RUN_MODE_DEVELOPMENT
    assert config.database_path == DEVELOPMENT_DATABASE_PATH
    assert config.database_url == sqlite_url_from_path(DEVELOPMENT_DATABASE_PATH)


def test_desktop_production_uses_local_appdata() -> None:
    local_appdata = Path("C:/Users/Test User/AppData/Local")
    config = build_runtime_config(
        run_mode=RUN_MODE_DESKTOP_PRODUCTION,
        environ={"LOCALAPPDATA": str(local_appdata)},
    )

    assert config.user_data_root == local_appdata / APP_DATA_DIR_NAME
    assert config.database_path == config.user_data_root / "data" / DATABASE_FILE_NAME


def test_explicit_user_data_root_overrides_mode_default(runtime_tmp: Path) -> None:
    root = runtime_tmp / "Custom Root"
    config = build_runtime_config(run_mode=RUN_MODE_DESKTOP_PRODUCTION, user_data_root=root, environ={})

    assert config.user_data_root == root
    assert config.backups_dir == root / "backups"
    assert config.settings_path == root / "settings.json"


def test_explicit_database_url_overrides_default(runtime_tmp: Path) -> None:
    database_path = runtime_tmp / "db folder" / "custom.sqlite3"
    database_url = sqlite_url_from_path(database_path)
    config = build_runtime_config(run_mode=RUN_MODE_DEVELOPMENT, database_url=database_url, environ={})

    assert config.database_url == database_url
    assert config.database_path == database_path


def test_test_mode_requires_database_url_or_temp_root() -> None:
    with pytest.raises(RuntimeConfigError, match="test mode requires"):
        build_runtime_config(run_mode=RUN_MODE_TEST, environ={})


def test_test_mode_accepts_explicit_temp_root(runtime_tmp: Path) -> None:
    config = build_runtime_config(run_mode=RUN_MODE_TEST, user_data_root=runtime_tmp, environ={})

    assert config.database_path == runtime_tmp / "data" / DATABASE_FILE_NAME


def test_test_mode_accepts_explicit_database_url(runtime_tmp: Path) -> None:
    database_path = runtime_tmp / "explicit.sqlite3"
    config = build_runtime_config(run_mode=RUN_MODE_TEST, database_url=sqlite_url_from_path(database_path), environ={})

    assert config.database_path == database_path
    assert config.user_data_root == runtime_tmp


def test_windows_path_with_spaces_round_trips_to_sqlite_url(runtime_tmp: Path) -> None:
    root = runtime_tmp / "Local English Trainer"
    config = build_runtime_config(run_mode=RUN_MODE_TEST, user_data_root=root, environ={})

    assert "Local English Trainer" in config.database_url
    assert config.database_path == root / "data" / DATABASE_FILE_NAME


def test_windows_path_with_chinese_characters_round_trips_to_sqlite_url(runtime_tmp: Path) -> None:
    root = runtime_tmp / "本地英语训练"
    config = build_runtime_config(run_mode=RUN_MODE_TEST, user_data_root=root, environ={})

    assert "本地英语训练" in config.database_url
    assert config.database_path == root / "data" / DATABASE_FILE_NAME


def test_ensure_user_directories_is_idempotent_and_does_not_create_settings_file(runtime_tmp: Path) -> None:
    config = build_runtime_config(run_mode=RUN_MODE_TEST, user_data_root=runtime_tmp / "runtime", environ={})

    ensure_user_directories(config)
    ensure_user_directories(config)

    for path in (config.user_data_root, config.data_dir, config.backups_dir, config.imports_dir, config.exports_dir, config.logs_dir, config.cache_dir):
        assert path.is_dir()
    assert not config.settings_path.exists()


def test_development_directory_initialization_does_not_create_local_appdata_root(runtime_tmp: Path) -> None:
    local_appdata = runtime_tmp / "LocalAppData"
    dev_root = runtime_tmp / "dev runtime"
    config = build_runtime_config(
        run_mode=RUN_MODE_DEVELOPMENT,
        user_data_root=dev_root,
        environ={"LOCALAPPDATA": str(local_appdata)},
    )

    ensure_user_directories(config)

    assert dev_root.exists()
    assert not local_appdata.exists()


def test_desktop_production_does_not_depend_on_current_working_directory(runtime_tmp: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    current = runtime_tmp / "cwd"
    local_appdata = runtime_tmp / "LocalAppData"
    current.mkdir()
    monkeypatch.chdir(current)

    config = build_runtime_config(
        run_mode=RUN_MODE_DESKTOP_PRODUCTION,
        environ={"LOCALAPPDATA": str(local_appdata)},
    )

    assert config.user_data_root == local_appdata / APP_DATA_DIR_NAME
    assert current not in config.database_path.parents


def test_health_response_exposes_versions_and_hides_sensitive_paths() -> None:
    original_config = app_db.get_runtime_config()
    try:
        app_db.configure_database("sqlite:///:memory:")
        with TestClient(app) as client:
            response = client.get("/health")
    finally:
        app_db.configure_runtime_database(original_config, create_parent=True)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app_version"] == APP_VERSION
    assert body["api_protocol_version"] == API_PROTOCOL_VERSION
    assert body["schema_version"] == SCHEMA_VERSION
    assert body["run_mode"] in {RUN_MODE_DEVELOPMENT, RUN_MODE_TEST, RUN_MODE_DESKTOP_PRODUCTION}
    assert "database_path" not in body
    assert "token" not in body