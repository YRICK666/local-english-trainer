from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from backend.app import db as app_db
from backend.app import models  # noqa: F401
from backend.app.runtime_config import RUN_MODE_TEST, build_runtime_config

def _make_memory_engine():
    return create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)


def _create_old_annotation_table(engine, create_table_sql: str) -> None:
    with engine.begin() as connection:
        connection.exec_driver_sql(create_table_sql)

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
    original_url = app_db.DATABASE_URL
    try:
        app_db.configure_database("sqlite:///:memory:")
        _create_old_annotation_table(app_db.engine, _annotation_table_sql())

        with app_db.engine.begin() as connection:
            connection.exec_driver_sql(
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
    engine = _make_memory_engine()
    try:
        _create_old_annotation_table(engine, _annotation_table_sql("start_offset INTEGER"))
        app_db.ensure_reading_annotations_offset_columns(engine)
        app_db.ensure_reading_annotations_offset_columns(engine)
        columns = _table_columns(engine)
        assert "start_offset" in columns
        assert "end_offset" in columns
    finally:
        engine.dispose()

def test_compatibility_helper_adds_only_missing_start_offset_column() -> None:
    engine = _make_memory_engine()
    try:
        _create_old_annotation_table(engine, _annotation_table_sql("end_offset INTEGER"))
        app_db.ensure_reading_annotations_offset_columns(engine)
        app_db.ensure_reading_annotations_offset_columns(engine)
        columns = _table_columns(engine)
        assert "start_offset" in columns
        assert "end_offset" in columns
    finally:
        engine.dispose()

def test_new_database_create_all_has_offset_columns() -> None:
    engine = _make_memory_engine()
    try:
        app_db.Base.metadata.create_all(bind=engine)
        app_db.ensure_reading_annotations_offset_columns(engine)
        columns = _table_columns(engine)
        assert "start_offset" in columns
        assert "end_offset" in columns
    finally:
        engine.dispose()

def test_configure_database_can_rebind_memory_engine_multiple_times() -> None:
    original_config = app_db.get_runtime_config()
    try:
        app_db.configure_database("sqlite:///:memory:")
        first_engine = app_db.engine
        app_db.configure_database("sqlite:///:memory:")
        assert app_db.engine is not first_engine
        app_db.init_db()
        columns = _table_columns(app_db.engine)
        assert "start_offset" in columns
        assert "end_offset" in columns
    finally:
        app_db.configure_runtime_database(original_config, create_parent=True)


def test_configure_runtime_database_accepts_test_memory_config() -> None:
    original_config = app_db.get_runtime_config()
    try:
        config = build_runtime_config(run_mode=RUN_MODE_TEST, database_url="sqlite:///:memory:", environ={})
        app_db.configure_runtime_database(config)
        assert app_db.get_runtime_config().run_mode == RUN_MODE_TEST
        assert app_db.DATABASE_URL == "sqlite:///:memory:"
        app_db.init_db()
        columns = _table_columns(app_db.engine)
        assert "start_offset" in columns
        assert "end_offset" in columns
    finally:
        app_db.configure_runtime_database(original_config, create_parent=True)
