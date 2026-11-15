from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models import Base

engine = None
SessionLocal = None


def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def bind_engine() -> None:
    global engine, SessionLocal
    if engine is not None:
        engine.dispose()
    engine = create_engine(
        f"sqlite:///{settings.data_path / 'app.db'}",
        connect_args={"check_same_thread": False},
    )
    event.listen(engine, "connect", enable_foreign_keys)
    SessionLocal = sessionmaker(bind=engine)


def init_db() -> None:
    settings.data_path.mkdir(parents=True, exist_ok=True)
    (settings.data_path / "uploads").mkdir(exist_ok=True)
    Base.metadata.create_all(engine)


bind_engine()
