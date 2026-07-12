from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.runtime_config import RuntimeConfig, build_runtime_config

RUNTIME_CONFIG = build_runtime_config()
DEFAULT_DB_PATH = RUNTIME_CONFIG.database_path or Path(":memory:")
DATABASE_URL = RUNTIME_CONFIG.database_url

Base = declarative_base()


def _make_engine(database_url: str, *, create_parent: bool = True):
    if database_url == "sqlite:///:memory:":
        return create_engine(database_url, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    if database_url.startswith("sqlite:///") and create_parent:
        db_path = Path(database_url.removeprefix("sqlite:///"))
        if str(db_path) != ":memory:":
            db_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(database_url, connect_args={"check_same_thread": False})


engine = _make_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def configure_database(database_url: str) -> None:
    global DATABASE_URL, DEFAULT_DB_PATH, RUNTIME_CONFIG, engine, SessionLocal
    DATABASE_URL = database_url
    RUNTIME_CONFIG = build_runtime_config(
        run_mode=RUNTIME_CONFIG.run_mode,
        database_url=database_url,
        user_data_root=RUNTIME_CONFIG.user_data_root,
    )
    DEFAULT_DB_PATH = RUNTIME_CONFIG.database_path or Path(":memory:")
    engine.dispose()
    engine = _make_engine(database_url)
    SessionLocal.configure(bind=engine)


def configure_runtime_database(config: RuntimeConfig, *, create_parent: bool = False) -> None:
    global DATABASE_URL, DEFAULT_DB_PATH, RUNTIME_CONFIG, engine, SessionLocal
    RUNTIME_CONFIG = config
    DATABASE_URL = config.database_url
    DEFAULT_DB_PATH = config.database_path or Path(":memory:")
    engine.dispose()
    engine = _make_engine(config.database_url, create_parent=create_parent)
    SessionLocal.configure(bind=engine)


def get_runtime_config() -> RuntimeConfig:
    return RUNTIME_CONFIG


def ensure_reading_annotations_offset_columns(bind: Engine) -> None:
    if bind.dialect.name != "sqlite":
        return

    with bind.begin() as connection:
        rows = connection.exec_driver_sql("PRAGMA table_info(reading_annotations)").mappings().all()
        if not rows:
            return

        existing_columns = {str(row["name"]) for row in rows}
        if "start_offset" not in existing_columns:
            connection.exec_driver_sql("ALTER TABLE reading_annotations ADD COLUMN start_offset INTEGER")
        if "end_offset" not in existing_columns:
            connection.exec_driver_sql("ALTER TABLE reading_annotations ADD COLUMN end_offset INTEGER")


def init_db() -> None:
    from backend.app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    ensure_reading_annotations_offset_columns(engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()