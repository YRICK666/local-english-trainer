from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

DEFAULT_DB_PATH = Path("data/local_english_trainer.sqlite3")
DATABASE_URL = f"sqlite:///{DEFAULT_DB_PATH.as_posix()}"

Base = declarative_base()


def _make_engine(database_url: str):
    if database_url == "sqlite:///:memory:":
        return create_engine(database_url, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    if database_url.startswith("sqlite:///"):
        db_path = Path(database_url.removeprefix("sqlite:///"))
        if str(db_path) != ":memory:":
            db_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(database_url, connect_args={"check_same_thread": False})


engine = _make_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def configure_database(database_url: str) -> None:
    global DATABASE_URL, engine, SessionLocal
    DATABASE_URL = database_url
    engine.dispose()
    engine = _make_engine(database_url)
    SessionLocal.configure(bind=engine)


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
