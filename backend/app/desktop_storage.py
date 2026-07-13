from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence
from uuid import uuid4


BOOTSTRAP_CONFIG_VERSION = 1
BOOTSTRAP_DIRECTORY_NAME = "LocalEnglishTrainer"
BOOTSTRAP_FILE_NAME = "bootstrap.json"
DATABASE_FILE_NAME = "local_english_trainer.sqlite3"
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class DesktopStorageError(RuntimeError):
    """Base error for desktop storage configuration and migration."""


class InvalidDesktopStorageRoot(DesktopStorageError):
    pass


class BootstrapConfigError(DesktopStorageError):
    pass


class UnsupportedBootstrapConfigVersion(BootstrapConfigError):
    pass


class DatabaseMigrationError(DesktopStorageError):
    pass


@dataclass(frozen=True)
class DesktopStorageLayout:
    root: Path
    data_dir: Path
    backups_dir: Path
    imports_dir: Path
    exports_dir: Path
    logs_dir: Path
    cache_dir: Path
    database_path: Path


@dataclass(frozen=True)
class BootstrapConfig:
    config_version: int
    data_root: Path


@dataclass(frozen=True)
class DatabaseMigrationResult:
    status: str
    destination_database: Path
    source_integrity: str
    destination_integrity: str
    source_preserved: bool


def build_desktop_storage_layout(root: str | Path) -> DesktopStorageLayout:
    normalized_root = _normalize_absolute_path(root, error_type=InvalidDesktopStorageRoot)
    data_dir = normalized_root / "data"
    database_path = data_dir / DATABASE_FILE_NAME
    if data_dir not in database_path.parents or normalized_root not in database_path.parents:
        raise InvalidDesktopStorageRoot("desktop database path must remain inside the data root")
    return DesktopStorageLayout(
        root=normalized_root,
        data_dir=data_dir,
        backups_dir=normalized_root / "backups",
        imports_dir=normalized_root / "imports",
        exports_dir=normalized_root / "exports",
        logs_dir=normalized_root / "logs",
        cache_dir=normalized_root / "cache",
        database_path=database_path,
    )


def validate_desktop_storage_root(
    root: str | Path,
    *,
    forbidden_roots: Sequence[str | Path] | None = None,
) -> DesktopStorageLayout:
    layout = build_desktop_storage_layout(root)
    if layout.root.exists() and not layout.root.is_dir():
        raise InvalidDesktopStorageRoot("desktop data root must not be a regular file")

    prohibited = tuple(forbidden_roots or ()) + (PROJECT_ROOT, PROJECT_ROOT / "data")
    for forbidden_root in prohibited:
        normalized_forbidden = _normalize_absolute_path(forbidden_root, error_type=InvalidDesktopStorageRoot)
        if layout.root == normalized_forbidden:
            raise InvalidDesktopStorageRoot("desktop data root must not be a repository source or data directory")
    return layout


def prepare_desktop_storage(
    root: str | Path,
    *,
    forbidden_roots: Sequence[str | Path] | None = None,
) -> DesktopStorageLayout:
    layout = validate_desktop_storage_root(root, forbidden_roots=forbidden_roots)
    for directory in (
        layout.root,
        layout.data_dir,
        layout.backups_dir,
        layout.imports_dir,
        layout.exports_dir,
        layout.logs_dir,
        layout.cache_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)
        verify_directory_writable(directory)
    return layout


def verify_directory_writable(path: str | Path) -> None:
    directory = Path(path)
    if not directory.exists() or not directory.is_dir():
        raise InvalidDesktopStorageRoot("desktop storage directory is not available")
    probe = directory / f".desktop-storage-write-{uuid4().hex}.tmp"
    try:
        with probe.open("x", encoding="utf-8") as handle:
            handle.write("")
    except OSError as exc:
        raise InvalidDesktopStorageRoot("desktop storage directory is not writable") from exc
    finally:
        probe.unlink(missing_ok=True)


def get_bootstrap_config_path(
    local_app_data: str | Path | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> Path:
    source = local_app_data
    if source is None:
        source = (os.environ if environ is None else environ).get("LOCALAPPDATA")
    try:
        app_data = _normalize_absolute_path(source, error_type=BootstrapConfigError)
    except InvalidDesktopStorageRoot as exc:
        raise BootstrapConfigError(str(exc)) from exc
    return app_data / BOOTSTRAP_DIRECTORY_NAME / BOOTSTRAP_FILE_NAME


def save_bootstrap_config(
    data_root: str | Path,
    *,
    local_app_data: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> BootstrapConfig:
    layout = validate_desktop_storage_root(data_root)
    path = get_bootstrap_config_path(local_app_data, environ=environ)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    payload = {"config_version": BOOTSTRAP_CONFIG_VERSION, "data_root": str(layout.root)}
    try:
        temporary_path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return BootstrapConfig(config_version=BOOTSTRAP_CONFIG_VERSION, data_root=layout.root)


def load_bootstrap_config(
    *,
    local_app_data: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> BootstrapConfig | None:
    path = get_bootstrap_config_path(local_app_data, environ=environ)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BootstrapConfigError("bootstrap configuration is malformed") from exc
    if not isinstance(raw, dict) or set(raw) != {"config_version", "data_root"}:
        raise BootstrapConfigError("bootstrap configuration has invalid fields")
    if raw["config_version"] != BOOTSTRAP_CONFIG_VERSION:
        raise UnsupportedBootstrapConfigVersion("unsupported bootstrap configuration version")
    if not isinstance(raw["data_root"], str):
        raise BootstrapConfigError("bootstrap data root must be a string")
    try:
        layout = validate_desktop_storage_root(raw["data_root"])
    except InvalidDesktopStorageRoot as exc:
        raise BootstrapConfigError("bootstrap data root is invalid") from exc
    return BootstrapConfig(config_version=BOOTSTRAP_CONFIG_VERSION, data_root=layout.root)


def clear_bootstrap_config(
    *,
    local_app_data: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> None:
    get_bootstrap_config_path(local_app_data, environ=environ).unlink(missing_ok=True)


def migrate_selected_database(
    source_database: str | Path,
    destination_root: str | Path,
    *,
    forbidden_roots: Sequence[str | Path] | None = None,
) -> DatabaseMigrationResult:
    source = _require_explicit_source_database(source_database)
    layout = prepare_desktop_storage(destination_root, forbidden_roots=forbidden_roots)
    destination = layout.database_path
    if source == destination:
        raise DatabaseMigrationError("source and destination database must be different files")
    if destination.exists():
        raise DatabaseMigrationError("destination database already exists")

    temporary_destination = layout.data_dir / f".{DATABASE_FILE_NAME}.{uuid4().hex}.tmp"
    try:
        source_integrity = _sqlite_integrity_check(source)
        source_connection = _connect_read_only(source)
        destination_connection = sqlite3.connect(temporary_destination)
        try:
            source_connection.backup(destination_connection)
        finally:
            destination_connection.close()
            source_connection.close()
        destination_integrity = _sqlite_integrity_check(temporary_destination)
        os.replace(temporary_destination, destination)
    except Exception as exc:
        temporary_destination.unlink(missing_ok=True)
        if isinstance(exc, DatabaseMigrationError):
            raise
        raise DatabaseMigrationError("selected database migration failed") from exc

    return DatabaseMigrationResult(
        status="migrated",
        destination_database=destination,
        source_integrity=source_integrity,
        destination_integrity=destination_integrity,
        source_preserved=True,
    )


def _normalize_absolute_path(
    value: str | Path | None,
    *,
    error_type: type[DesktopStorageError],
) -> Path:
    if value is None or (isinstance(value, str) and not value.strip()):
        raise error_type("path must not be empty")
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise error_type("path must be absolute")
    return path.resolve(strict=False)


def _require_explicit_source_database(source_database: str | Path) -> Path:
    source = _normalize_absolute_path(source_database, error_type=DatabaseMigrationError)
    if not source.exists() or not source.is_file():
        raise DatabaseMigrationError("source database must be an existing regular file")
    return source


def _connect_read_only(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)


def _sqlite_integrity_check(path: Path) -> str:
    try:
        connection = _connect_read_only(path)
        try:
            rows = connection.execute("PRAGMA integrity_check").fetchall()
        finally:
            connection.close()
    except (sqlite3.DatabaseError, OSError) as exc:
        raise DatabaseMigrationError("SQLite integrity check failed") from exc
    if rows != [("ok",)]:
        raise DatabaseMigrationError("SQLite integrity check did not return ok")
    return "ok"
