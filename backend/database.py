from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base
from pathlib import Path

# Database location
DB_PATH = Path.home() / "Library/Application Support/StudioPipeline/pipeline.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# Create engine with WAL mode and larger connection pool
engine = create_engine(
    f'sqlite:///{DB_PATH}',
    connect_args={'check_same_thread': False},
    echo=False,
    pool_size=20,  # Increased from default 5 to handle concurrent workers + API requests
    max_overflow=30,  # Increased from default 10 for peak load
    pool_pre_ping=True,  # Verify connections are alive before using
    pool_recycle=3600  # Recycle connections after 1 hour to prevent stale connections
)

# Enable WAL mode on connection
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=5000")  # Wait up to 5s for locks instead of failing immediately
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

def get_db():
    """Dependency for FastAPI routes"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
