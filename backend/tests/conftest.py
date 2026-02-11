import sys
from pathlib import Path

# Add backend directory to Python path FIRST
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

# Now import after path is set
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base


@pytest.fixture
def db_session():
    """Create in-memory database for testing"""
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()
