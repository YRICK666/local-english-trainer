from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


class DatabaseSafetyError(RuntimeError):
    pass


@dataclass(frozen=True)
class IntegrityCheckResult:
    database_path: Path
    ok: bool
    message: str


@dataclass(frozen=True)
class BackupResult:
    source_path: Path
    backup_path: Path
    integrity_check: IntegrityCheckResult


@dataclass(frozen=True)
class PrepareUpgradeResult:
    database_path: Path
    backup_path: Path
    target_schema_version: int
    integrity_check: IntegrityCheckResult


def check_sqlite_integrity(database_path: str | Path) -> IntegrityCheckResult:
    path = Path(database_path)
    if not path.exists():
        return IntegrityCheckResult(database_path=path, ok=False, message="database file does not exist")
    if not path.is_file():
        return IntegrityCheckResult(database_path=path, ok=False, message="database path is not a file")

    try:
        with sqlite3.connect(path) as connection:
            row = connection.execute("PRAGMA integrity_check").fetchone()
    except sqlite3.DatabaseError as exc:
        return IntegrityCheckResult(database_path=path, ok=False, message=f"integrity check failed: {exc}")
    except OSError as exc:
        return IntegrityCheckResult(database_path=path, ok=False, message=f"cannot open database: {exc}")

    message = str(row[0]) if row else "empty integrity check result"
    return IntegrityCheckResult(database_path=path, ok=message.lower() == "ok", message=message)


def build_backup_file_name(target_schema_version: int, *, now: datetime | None = None, prefix: str = "local_english_trainer") -> str:
    timestamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    return f"{prefix}-before-schema-{target_schema_version}-{timestamp}.sqlite3"


def backup_sqlite_database(
    source_path: str | Path,
    backup_path: str | Path,
    *,
    overwrite: bool = False,
    create_parent: bool = True,
) -> BackupResult:
    source = Path(source_path)
    target = Path(backup_path)
    source_check = check_sqlite_integrity(source)
    if not source_check.ok:
        raise DatabaseSafetyError(source_check.message)
    if target.exists() and not overwrite:
        raise DatabaseSafetyError(f"backup already exists: {target}")
    if create_parent:
        target.parent.mkdir(parents=True, exist_ok=True)

    try:
        with sqlite3.connect(source) as source_connection:
            with sqlite3.connect(target) as target_connection:
                source_connection.backup(target_connection)
        backup_check = check_sqlite_integrity(target)
        if not backup_check.ok:
            raise DatabaseSafetyError(f"backup integrity check failed: {backup_check.message}")
    except Exception:
        if target.exists():
            target.unlink()
        raise

    return BackupResult(source_path=source, backup_path=target, integrity_check=backup_check)


def prepare_database_for_upgrade(
    database_path: str | Path,
    backups_dir: str | Path,
    *,
    target_schema_version: int,
    now: datetime | None = None,
) -> PrepareUpgradeResult:
    database = Path(database_path)
    check = check_sqlite_integrity(database)
    if not check.ok:
        raise DatabaseSafetyError(check.message)

    backup_path = Path(backups_dir) / build_backup_file_name(target_schema_version, now=now)
    backup = backup_sqlite_database(database, backup_path)
    return PrepareUpgradeResult(
        database_path=database,
        backup_path=backup.backup_path,
        target_schema_version=target_schema_version,
        integrity_check=backup.integrity_check,
    )