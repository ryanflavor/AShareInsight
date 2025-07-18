"""
Test SQLAlchemy with postgresql+psycopg:// format as required in AC 4
"""

import sys
from pathlib import Path

# Add core package to path for imports
sys.path.insert(
    0, str(Path(__file__).parent.parent.parent / "packages" / "core" / "src")
)

from core.logging_config import get_logger
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

logger = get_logger(__name__)


def test_sqlalchemy_psycopg_format():
    """Test SQLAlchemy with postgresql+psycopg:// format"""
    # Use postgresql+psycopg:// format as specified in acceptance criteria
    connection_string = (
        "postgresql+psycopg://postgres:test123@localhost:5432/ashareinsight"
    )

    try:
        # Create engine
        engine = create_engine(connection_string, echo=True)

        # Test connection
        with engine.connect() as conn:
            # Test basic query
            result = conn.execute(text("SELECT version();"))
            version = result.fetchone()[0]

            # Test pgvector extension
            result = conn.execute(
                text(
                    "SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';"
                )
            )
            vector_ext = result.fetchone()

            # Test database info
            result = conn.execute(text("SELECT current_database(), current_user;"))
            db_info = result.fetchone()

            print("✅ SQLAlchemy postgresql+psycopg:// connection successful!")
            print(f"PostgreSQL Version: {version}")
            print(f"Vector Extension: {vector_ext[0]} v{vector_ext[1]}")
            print(f"Database: {db_info[0]}, User: {db_info[1]}")

        # Test session maker
        Session = sessionmaker(bind=engine)
        session = Session()

        result = session.execute(text("SELECT 'Session test successful' as result;"))
        session_result = result.fetchone()[0]
        print(f"✅ Session test: {session_result}")

        session.close()

        # All tests passed if we got here
        assert version is not None, "Failed to get PostgreSQL version"
        assert vector_ext is not None, "pgvector extension not found"
        assert db_info is not None, "Failed to get database info"
        assert session_result == "Session test successful", "Session test failed"

        return True  # Keep return for backward compatibility with caller

    except Exception as e:
        logger.error(f"SQLAlchemy test failed: {e}")
        print(f"❌ SQLAlchemy test failed: {e}")
        raise  # Re-raise the exception instead of returning False


if __name__ == "__main__":
    from core.logging_config import setup_logging

    setup_logging(level="INFO")
    print("Testing SQLAlchemy with postgresql+psycopg:// format...")
    test_sqlalchemy_psycopg_format()
