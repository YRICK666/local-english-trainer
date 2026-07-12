from __future__ import annotations

import hashlib
import shutil
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest

from backend.app.database_safety import (
    DatabaseSafetyError,
    backup_sqlite_database,
    build_backup_file_name,
    check_sqlite_integrity,
    prepare_database_for_upgrade,
)


@pytest.fixture()
def safety_tmp() -> Path:
    root = Path.cwd() / ".runtime-test-tmp"
    root.mkdir(parents=True, exist_ok=True)
    temp_dir = root / f"safety-{uuid4().hex}"
    temp_dir.mkdir()
    try:
        yield temp_dir
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def create_sqlite_database(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute("INSERT INTO sample (value) VALUES (?)", ("hello",))
        connection.commit()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_integrity_check_passes_for_healthy_sqlite(safety_tmp: Path) -> None:
    database = safety_tmp / "healthy.sqlite3"
    create_sqlite_database(database)

    result = check_sqlite_integrity(database)

    assert result.ok is True
    assert result.message == "ok"
    assert result.database_path == database


def test_integrity_check_rejects_corrupt_file(safety_tmp: Path) -> None:
    database = safety_tmp / "corrupt.sqlite3"
    database.write_bytes(b"not a sqlite database")

    result = check_sqlite_integrity(database)

    assert result.ok is False
    assert "database" in result.message.lower() or "failed" in result.message.lower()


def test_integrity_check_rejects_missing_file(safety_tmp: Path) -> None:
    result = check_sqlite_integrity(safety_tmp / "missing.sqlite3")

    assert result.ok is False
    assert result.message == "database file does not exist"


def test_sqlite_backup_succeeds_and_preserves_data(safety_tmp: Path) -> None:
    source = safety_tmp / "source.sqlite3"
    backup = safety_tmp / "backups" / "backup.sqlite3"
    create_sqlite_database(source)

    result = backup_sqlite_database(source, backup)

    assert result.backup_path == backup
    assert result.integrity_check.ok is True
    with sqlite3.connect(backup) as connection:
        row = connection.execute("SELECT value FROM sample WHERE id = 1").fetchone()
    assert row == ("hello",)


def test_backup_integrity_check_passes(safety_tmp: Path) -> None:
    source = safety_tmp / "source.sqlite3"
    backup = safety_tmp / "backup.sqlite3"
    create_sqlite_database(source)

    backup_sqlite_database(source, backup)
    result = check_sqlite_integrity(backup)

    assert result.ok is True


def test_backup_refuses_to_overwrite_existing_target(safety_tmp: Path) -> None:
    source = safety_tmp / "source.sqlite3"
    backup = safety_tmp / "backup.sqlite3"
    create_sqlite_database(source)
    backup.write_text("existing", encoding="utf-8")

    with pytest.raises(DatabaseSafetyError, match="already exists"):
        backup_sqlite_database(source, backup)

    assert backup.read_text(encoding="utf-8") == "existing"


def test_backup_failure_does_not_leave_partial_target_for_bad_source(safety_tmp: Path) -> None:
    source = safety_tmp / "bad.sqlite3"
    backup = safety_tmp / "backup.sqlite3"
    source.write_bytes(b"not sqlite")

    with pytest.raises(DatabaseSafetyError):
        backup_sqlite_database(source, backup)

    assert not backup.exists()


def test_prepare_upgrade_checks_and_creates_backup(safety_tmp: Path) -> None:
    source = safety_tmp / "source.sqlite3"
    backups_dir = safety_tmp / "backups"
    create_sqlite_database(source)
    now = datetime(2026, 7, 12, 10, 30, 45)

    result = prepare_database_for_upgrade(source, backups_dir, target_schema_version=2, now=now)

    assert result.target_schema_version == 2
    assert result.backup_path.name == "local_english_trainer-before-schema-2-20260712-103045.sqlite3"
    assert result.backup_path.exists()
    assert result.integrity_check.ok is True


def test_prepare_upgrade_rejects_bad_database_before_backup(safety_tmp: Path) -> None:
    source = safety_tmp / "bad.sqlite3"
    backups_dir = safety_tmp / "backups"
    source.write_bytes(b"bad")

    with pytest.raises(DatabaseSafetyError):
        prepare_database_for_upgrade(source, backups_dir, target_schema_version=2)

    assert not backups_dir.exists()


def test_backup_does_not_modify_source_database(safety_tmp: Path) -> None:
    source = safety_tmp / "source.sqlite3"
    backup = safety_tmp / "backup.sqlite3"
    create_sqlite_database(source)
    before_hash = file_hash(source)

    backup_sqlite_database(source, backup)

    assert file_hash(source) == before_hash


def test_backup_name_can_use_injected_time() -> None:
    name = build_backup_file_name(3, now=datetime(2026, 1, 2, 3, 4, 5))

    assert name == "local_english_trainer-before-schema-3-20260102-030405.sqlite3"


def test_database_safety_uses_only_explicit_tmp_paths(safety_tmp: Path) -> None:
    source = safety_tmp / "source.sqlite3"
    backup = safety_tmp / "backup.sqlite3"
    create_sqlite_database(source)

    result = backup_sqlite_database(source, backup)

    assert safety_tmp in result.source_path.parents
    assert safety_tmp in result.backup_path.parents