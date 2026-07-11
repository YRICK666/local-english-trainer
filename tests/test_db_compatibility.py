from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from sqlalchemy import create_engine

from backend.app import db as app_db
from backend.app import models  # noqa: F401


def _sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def _create_old_annotation_table(db_path: Path, create_table_sql: str) -> None:
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(create_table_sql)
        connection.commit()
    finally:
        connection.close()


def _annotation_table_sql(extra_columns: str = "") -> str:
    suffix = f", {extra_columns}" if extra_columns else ""
    return f"""
    CREATE TABLE reading_annotations (
        id INTEGER PRIMARY KEY,
        annotation_id VARCHAR(120) NOT NULL UNIQUE,
        pack_db_id INTEGER NOT NULL,
        pack_id VARCHAR(120) NOT NULL,
        passage_db_id INTEGER NOT NULL,
        passage_id VARCHAR(120) NOT NULL,
        paragraph_db_id INTEGER NOT NULL,
        paragraph_id VARCHAR(120) NOT NULL,
        question_db_id INTEGER,
        question_id VARCHAR(120),
        annotation_type VARCHAR(64) NOT NULL,
        selected_text TEXT NOT NULL,
        note TEXT,
        created_at DATETIME
        {suffix}
    )
    """


def _table_columns(engine) -> set[str]:
    with engine.connect() as connection:
        rows = connection.exec_driver_sql("PRAGMA table_info(reading_annotations)").mappings().all()
    return {str(row["name"]) for row in rows}


def test_init_db_upgrades_old_reading_annotations_table_and_preserves_data() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "legacy.sqlite3"
        _create_old_annotation_table(db_path, _annotation_table_sql())

        connection = sqlite3.connect(db_path)
        try:
            connection.execute(
                """
                INSERT INTO reading_annotations (
                    id, annotation_id, pack_db_id, pack_id, passage_db_id, passage_id,
                    paragraph_db_id, paragraph_id, question_db_id, question_id,
                    annotation_type, selected_text, note, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    1,
                    "annotation-legacy",
                    1,
                    "legacy-pack",
                    1,
                    "legacy-passage",
                    1,
                    "legacy-paragraph",
                    None,
                    None,
                    "vocabulary",
                    "legacy text",
                    "legacy note",
                    None,
                ),
            )
            connection.commit()
        finally:
            connection.close()

        original_url = app_db.DATABASE_URL
        try:
            app_db.configure_database(_sqlite_url(db_path))
            app_db.init_db()
            app_db.init_db()

            columns = _table_columns(app_db.engine)
            assert "start_offset" in columns
            assert "end_offset" in columns

            with app_db.engine.connect() as sql_connection:
                row = sql_connection.exec_driver_sql(
                    "SELECT annotation_id, selected_text, start_offset, end_offset FROM reading_annotations WHERE annotation_id = 'annotation-legacy'"
                ).mappings().one()
            assert row["annotation_id"] == "annotation-legacy"
            assert row["selected_text"] == "legacy text"
            assert row["start_offset"] is None
            assert row["end_offset"] is None
        finally:
            app_db.configure_database(original_url)


def test_compatibility_helper_adds_only_missing_end_offset_column() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "start-only.sqlite3"
        _create_old_annotation_table(db_path, _annotation_table_sql("start_offset INTEGER"))

        engine = create_engine(_sqlite_url(db_path), connect_args={"check_same_thread": False})
        try:
            app_db.ensure_reading_annotations_offset_columns(engine)
            app_db.ensure_reading_annotations_offset_columns(engine)
            columns = _table_columns(engine)
            assert "start_offset" in columns
            assert "end_offset" in columns
        finally:
            engine.dispose()


def test_compatibility_helper_adds_only_missing_start_offset_column() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "end-only.sqlite3"
        _create_old_annotation_table(db_path, _annotation_table_sql("end_offset INTEGER"))

        engine = create_engine(_sqlite_url(db_path), connect_args={"check_same_thread": False})
        try:
            app_db.ensure_reading_annotations_offset_columns(engine)
            app_db.ensure_reading_annotations_offset_columns(engine)
            columns = _table_columns(engine)
            assert "start_offset" in columns
            assert "end_offset" in columns
        finally:
            engine.dispose()


def test_new_database_create_all_has_offset_columns() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "fresh.sqlite3"
        engine = create_engine(_sqlite_url(db_path), connect_args={"check_same_thread": False})
        try:
            app_db.Base.metadata.create_all(bind=engine)
            app_db.ensure_reading_annotations_offset_columns(engine)
            columns = _table_columns(engine)
            assert "start_offset" in columns
            assert "end_offset" in columns
        finally:
            engine.dispose()
