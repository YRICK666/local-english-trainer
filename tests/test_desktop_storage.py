from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from backend.app.desktop_storage import (
    BOOTSTRAP_CONFIG_VERSION,
    BootstrapConfigError,
    DatabaseMigrationError,
    InvalidDesktopStorageRoot,
    UnsupportedBootstrapConfigVersion,
    build_desktop_storage_layout,
    clear_bootstrap_config,
    get_bootstrap_config_path,
    load_bootstrap_config,
    migrate_selected_database,
    prepare_desktop_storage,
    save_bootstrap_config,
    validate_desktop_storage_root,
    verify_directory_writable,
)


def create_sqlite_database(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute("INSERT INTO sample (value) VALUES ('hello')")


def test_storage_layout_normalizes_an_absolute_unicode_root(tmp_path: Path) -> None:
    layout = build_desktop_storage_layout(tmp_path / "学习 数据")
    assert layout.root == (tmp_path / "学习 数据").resolve()
    assert layout.database_path == layout.data_dir / "local_english_trainer.sqlite3"
    assert layout.root in layout.database_path.parents


@pytest.mark.parametrize("root", ["", "relative-data"])
def test_storage_layout_rejects_empty_or_relative_roots(root: str) -> None:
    with pytest.raises(InvalidDesktopStorageRoot):
        build_desktop_storage_layout(root)


def test_storage_layout_rejects_file_and_forbidden_roots(tmp_path: Path) -> None:
    file_root = tmp_path / "root-file"
    file_root.write_text("not a directory", encoding="utf-8")
    forbidden = tmp_path / "forbidden"
    with pytest.raises(InvalidDesktopStorageRoot):
        validate_desktop_storage_root(file_root)
    with pytest.raises(InvalidDesktopStorageRoot):
        validate_desktop_storage_root(forbidden, forbidden_roots=(forbidden,))


def test_prepare_storage_creates_full_layout_is_idempotent_and_writable(tmp_path: Path) -> None:
    root = tmp_path / "desktop data"
    layout = prepare_desktop_storage(root)
    repeated = prepare_desktop_storage(root)
    assert repeated == layout
    for path in (layout.root, layout.data_dir, layout.backups_dir, layout.imports_dir, layout.exports_dir, layout.logs_dir, layout.cache_dir):
        assert path.is_dir()
        verify_directory_writable(path)
    assert not layout.database_path.exists()


def test_verify_directory_writable_rejects_a_file(tmp_path: Path) -> None:
    path = tmp_path / "not-directory"
    path.write_text("x", encoding="utf-8")
    with pytest.raises(InvalidDesktopStorageRoot):
        verify_directory_writable(path)


def test_bootstrap_config_is_atomic_utf8_and_contains_only_root_pointer(tmp_path: Path) -> None:
    app_data = tmp_path / "Local AppData"
    root = tmp_path / "外部数据"
    saved = save_bootstrap_config(root, local_app_data=app_data)
    path = get_bootstrap_config_path(app_data)
    assert saved.data_root == root.resolve()
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "config_version": BOOTSTRAP_CONFIG_VERSION,
        "data_root": str(root.resolve()),
    }
    assert "token" not in path.read_text(encoding="utf-8")
    assert "port" not in path.read_text(encoding="utf-8")
    assert not list(path.parent.glob("*.tmp"))


def test_bootstrap_load_validates_content_ignores_stale_temp_and_does_not_prepare_storage(tmp_path: Path) -> None:
    app_data = tmp_path / "appdata"
    root = tmp_path / "selected"
    save_bootstrap_config(root, local_app_data=app_data)
    path = get_bootstrap_config_path(app_data)
    path.with_name(f".{path.name}.stale.tmp").write_text("not json", encoding="utf-8")
    loaded = load_bootstrap_config(local_app_data=app_data)
    assert loaded is not None and loaded.data_root == root.resolve()
    assert not root.exists()


@pytest.mark.parametrize(
    ("payload", "error"),
    [
        ("{", BootstrapConfigError),
        (json.dumps({"config_version": 2, "data_root": "C:/data"}), UnsupportedBootstrapConfigVersion),
        (json.dumps({"config_version": 1}), BootstrapConfigError),
        (json.dumps({"config_version": 1, "data_root": "relative"}), BootstrapConfigError),
    ],
)
def test_bootstrap_rejects_invalid_payloads(tmp_path: Path, payload: str, error: type[Exception]) -> None:
    app_data = tmp_path / "appdata"
    path = get_bootstrap_config_path(app_data)
    path.parent.mkdir(parents=True)
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(error):
        load_bootstrap_config(local_app_data=app_data)


def test_clear_bootstrap_only_removes_the_pointer_file(tmp_path: Path) -> None:
    app_data = tmp_path / "appdata"
    root = tmp_path / "selected"
    prepare_desktop_storage(root)
    save_bootstrap_config(root, local_app_data=app_data)
    clear_bootstrap_config(local_app_data=app_data)
    assert not get_bootstrap_config_path(app_data).exists()
    assert root.is_dir()


def test_database_migration_uses_backup_integrity_checks_and_preserves_source(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite3"
    destination_root = tmp_path / "destination"
    create_sqlite_database(source)
    source_bytes = source.read_bytes()
    result = migrate_selected_database(source, destination_root)
    assert result.status == "migrated"
    assert result.source_integrity == result.destination_integrity == "ok"
    assert result.source_preserved is True
    assert source.read_bytes() == source_bytes
    with sqlite3.connect(result.destination_database) as connection:
        assert connection.execute("SELECT value FROM sample").fetchone() == ("hello",)


def test_database_migration_rejects_existing_relative_missing_same_or_corrupt_databases(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite3"
    create_sqlite_database(source)
    destination_root = tmp_path / "destination"
    existing_layout = prepare_desktop_storage(destination_root)
    existing_layout.database_path.write_bytes(b"existing")
    with pytest.raises(DatabaseMigrationError):
        migrate_selected_database(source, destination_root)
    with pytest.raises(DatabaseMigrationError):
        migrate_selected_database("relative.sqlite3", tmp_path / "other")
    with pytest.raises(DatabaseMigrationError):
        migrate_selected_database(tmp_path / "missing.sqlite3", tmp_path / "other")
    with pytest.raises(DatabaseMigrationError):
        migrate_selected_database(existing_layout.database_path, destination_root)
    corrupt = tmp_path / "corrupt.sqlite3"
    corrupt.write_bytes(b"not sqlite")
    corrupt_destination = tmp_path / "corrupt-destination"
    with pytest.raises(DatabaseMigrationError):
        migrate_selected_database(corrupt, corrupt_destination)
    assert not (corrupt_destination / "data" / "local_english_trainer.sqlite3").exists()
    assert not list((corrupt_destination / "data").glob("*.tmp"))


def test_database_migration_supports_unicode_paths_and_result_has_no_sensitive_content(tmp_path: Path) -> None:
    source = tmp_path / "来源.sqlite3"
    create_sqlite_database(source)
    result = migrate_selected_database(source, tmp_path / "迁移目标")
    assert result.destination_database.exists()
    assert "token" not in repr(result).lower()
    assert "hello" not in repr(result)
