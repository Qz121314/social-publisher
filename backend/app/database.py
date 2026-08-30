from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATABASE_PATH = DATA_DIR / "social_publisher.db"
DATABASE_URL = f"sqlite:///{DATABASE_PATH.as_posix()}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    # Import every mapped domain before create_all so SQLAlchemy can resolve the
    # full relationship graph and create newly introduced lightweight tables.
    from app.models import account, channel, content, execution, flow, publish_target, publishing, settings  # noqa: F401
    from app.services.domain_bootstrap import bootstrap_phase2_records, ensure_phase2_schema
    from app.services.platform_bootstrap import bootstrap_phase8_records

    Base.metadata.create_all(bind=engine)
    rebuilt_publish_jobs = ensure_phase2_schema(engine)
    if rebuilt_publish_jobs:
        Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        bootstrap_phase2_records(db)
        bootstrap_phase8_records(db)
