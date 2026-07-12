from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from backend.app.version import API_PROTOCOL_VERSION, APP_VERSION, SCHEMA_VERSION

RUN_MODE_DEVELOPMENT = "development"
RUN_MODE_TEST = "test"
RUN_MODE_DESKTOP_PRODUCTION = "desktop_production"
VALID_RUN_MODES = {RUN_MODE_DEVELOPMENT, RUN_MODE_TEST, RUN_MODE_DESKTOP_PRODUCTION}

ENV_RUN_MODE = "LOCAL_ENGLISH_TRAINER_MODE"
ENV_DATABASE_URL = "LOCAL_ENGLISH_TRAINER_DATABASE_URL"
ENV_USER_DATA_ROOT = "LOCAL_ENGLISH_TRAINER_USER_DATA_ROOT"
ENV_LOCAL_APPDATA = "LOCALAPPDATA"

APP_DATA_DIR_NAME = "LocalEnglishTrainer"
DATABASE_FILE_NAME = "local_english_trainer.sqlite3"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEVELOPMENT_DATABASE_PATH = PROJECT_ROOT / "data" / DATABASE_FILE_NAME


class RuntimeConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class RuntimeConfig:
    run_mode: str
    app_version: str
    api_protocol_version: int
    schema_version: int
    user_data_root: Path
    database_path: Path | None
    database_url: str
    data_dir: Path
    backups_dir: Path
    imports_dir: Path
    exports_dir: Path
    logs_dir: Path
    cache_dir: Path
    settings_path: Path


def sqlite_url_from_path(path: Path) -> str:
    return f"sqlite:///{path.expanduser().as_posix()}"


def sqlite_path_from_url(database_url: str) -> Path | None:
    if database_url == "sqlite:///:memory:":
        return None
    if not database_url.startswith("sqlite:///"):
        raise RuntimeConfigError("Only sqlite database URLs are supported")
    return Path(database_url.removeprefix("sqlite:///"))


def build_runtime_config(
    *,
    run_mode: str | None = None,
    database_url: str | None = None,
    user_data_root: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> RuntimeConfig:
    env = os.environ if environ is None else environ
    resolved_mode = (run_mode or env.get(ENV_RUN_MODE) or RUN_MODE_DEVELOPMENT).strip()
    if resolved_mode not in VALID_RUN_MODES:
        raise RuntimeConfigError(f"Unsupported run mode: {resolved_mode}")

    env_database_url = env.get(ENV_DATABASE_URL)
    env_user_data_root = env.get(ENV_USER_DATA_ROOT)
    resolved_database_url = database_url or env_database_url

    explicit_user_data_root = user_data_root if user_data_root is not None else env_user_data_root
    if resolved_mode == RUN_MODE_TEST and explicit_user_data_root is None and resolved_database_url is not None:
        root = _derive_test_root_from_database_url(resolved_database_url)
    else:
        root = _resolve_user_data_root(resolved_mode, explicit_user_data_root, env)

    if resolved_database_url is None:
        if resolved_mode == RUN_MODE_TEST and explicit_user_data_root is None:
            raise RuntimeConfigError("test mode requires an explicit database URL or temporary user data root")
        database_path = _default_database_path(resolved_mode, root)
        resolved_database_url = sqlite_url_from_path(database_path)
    else:
        database_path = sqlite_path_from_url(resolved_database_url)

    data_dir = root / "data"
    return RuntimeConfig(
        run_mode=resolved_mode,
        app_version=APP_VERSION,
        api_protocol_version=API_PROTOCOL_VERSION,
        schema_version=SCHEMA_VERSION,
        user_data_root=root,
        database_path=database_path,
        database_url=resolved_database_url,
        data_dir=data_dir,
        backups_dir=root / "backups",
        imports_dir=root / "imports",
        exports_dir=root / "exports",
        logs_dir=root / "logs",
        cache_dir=root / "cache",
        settings_path=root / "settings.json",
    )


def ensure_user_directories(config: RuntimeConfig) -> None:
    for path in (
        config.user_data_root,
        config.data_dir,
        config.backups_dir,
        config.imports_dir,
        config.exports_dir,
        config.logs_dir,
        config.cache_dir,
    ):
        path.mkdir(parents=True, exist_ok=True)


def _derive_test_root_from_database_url(database_url: str) -> Path:
    database_path = sqlite_path_from_url(database_url)
    if database_path is None:
        return Path(":memory:")
    if database_path.parent.name == "data":
        return database_path.parent.parent
    return database_path.parent

def _resolve_user_data_root(run_mode: str, explicit_root: str | Path | None, env: Mapping[str, str]) -> Path:
    if explicit_root is not None:
        return Path(explicit_root).expanduser()
    if run_mode == RUN_MODE_DESKTOP_PRODUCTION:
        local_appdata = env.get(ENV_LOCAL_APPDATA)
        if not local_appdata:
            raise RuntimeConfigError("LOCALAPPDATA is required for desktop_production mode")
        return Path(local_appdata).expanduser() / APP_DATA_DIR_NAME
    if run_mode == RUN_MODE_TEST:
        raise RuntimeConfigError("test mode requires an explicit database URL or temporary user data root")
    return PROJECT_ROOT


def _default_database_path(run_mode: str, user_data_root: Path) -> Path:
    if run_mode == RUN_MODE_DEVELOPMENT:
        return DEVELOPMENT_DATABASE_PATH
    return user_data_root / "data" / DATABASE_FILE_NAME