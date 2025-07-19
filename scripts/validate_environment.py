#!/usr/bin/env python
"""
Environment validation script for AShareInsight.
Verifies that all components are properly set up and functioning.
"""

import sys
from pathlib import Path

import psycopg
import redis
from pydantic import SecretStr
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Environment settings."""

    postgres_user: str = "ashareinsight"
    postgres_password: SecretStr = SecretStr("ashareinsight_password")
    postgres_db: str = "ashareinsight_db"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


class EnvironmentValidator:
    """Validates the development environment setup."""

    def __init__(self):
        self.settings = Settings()
        self.errors = []
        self.warnings = []

    def check_project_structure(self) -> bool:
        """Check if project directory structure is correct."""
        print("Checking project structure...")

        required_dirs = [
            "src/domain",
            "src/application",
            "src/infrastructure",
            "src/interfaces",
            "src/shared",
            "tests/unit",
            "tests/integration",
            "tests/e2e",
            "scripts/migration",
            "config",
            "docker",
        ]

        project_root = Path(__file__).parents[1]
        missing_dirs = []

        for dir_path in required_dirs:
            full_path = project_root / dir_path
            if not full_path.exists():
                missing_dirs.append(dir_path)

        if missing_dirs:
            self.errors.append(f"Missing directories: {', '.join(missing_dirs)}")
            return False

        print("✓ Project structure is correct")
        return True

    def check_postgresql(self) -> bool:
        """Check PostgreSQL connection and setup."""
        print("\nChecking PostgreSQL...")

        try:
            conn_string = (
                f"postgresql://{self.settings.postgres_user}:"
                f"{self.settings.postgres_password.get_secret_value()}@"
                f"{self.settings.postgres_host}:{self.settings.postgres_port}/"
                f"{self.settings.postgres_db}"
            )

            with psycopg.connect(conn_string) as conn:
                with conn.cursor() as cur:
                    # Check PostgreSQL version
                    cur.execute("SELECT version()")
                    version = cur.fetchone()[0]
                    print(f"✓ PostgreSQL connected: {version.split(',')[0]}")

                    # Check pgvector extension
                    cur.execute(
                        "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
                    )
                    result = cur.fetchone()
                    if not result:
                        self.errors.append("pgvector extension not installed")
                        return False

                    print(f"✓ pgvector extension installed: v{result[0]}")

                    # Check tables
                    cur.execute(
                        """
                        SELECT tablename 
                        FROM pg_tables 
                        WHERE schemaname = 'public' 
                        AND tablename IN ('companies', 'source_documents', 'business_concepts_master')
                        ORDER BY tablename
                    """
                    )
                    tables = [row[0] for row in cur.fetchall()]

                    if len(tables) != 3:
                        self.errors.append(f"Missing tables. Found: {tables}")
                        return False

                    print("✓ All required tables exist")

                    # Check halfvec column
                    cur.execute(
                        """
                        SELECT column_name, udt_name 
                        FROM information_schema.columns 
                        WHERE table_name = 'business_concepts_master' 
                        AND column_name = 'embedding'
                    """
                    )
                    result = cur.fetchone()
                    if not result or "halfvec" not in result[1]:
                        self.errors.append(
                            "halfvec column not found in business_concepts_master"
                        )
                        return False

                    print("✓ halfvec(2560) column configured")

                    # Check HNSW index
                    cur.execute(
                        """
                        SELECT indexname 
                        FROM pg_indexes 
                        WHERE tablename = 'business_concepts_master' 
                        AND indexname = 'idx_concepts_embedding'
                    """
                    )
                    if not cur.fetchone():
                        self.errors.append("HNSW index not found")
                        return False

                    print("✓ HNSW index exists")

                    return True

        except Exception as e:
            self.errors.append(f"PostgreSQL connection failed: {str(e)}")
            return False

    def check_redis(self) -> bool:
        """Check Redis connection."""
        print("\nChecking Redis...")

        try:
            r = redis.Redis(
                host=self.settings.redis_host,
                port=self.settings.redis_port,
                db=self.settings.redis_db,
                decode_responses=True,
            )

            # Ping Redis
            r.ping()
            print("✓ Redis connected")

            # Get Redis info
            info = r.info()
            print(f"✓ Redis version: {info['redis_version']}")

            # Test basic operations
            test_key = "_ashareinsight_test"
            r.set(test_key, "test_value", ex=10)
            value = r.get(test_key)
            r.delete(test_key)

            if value != "test_value":
                self.errors.append("Redis read/write test failed")
                return False

            print("✓ Redis read/write test passed")
            return True

        except Exception as e:
            self.errors.append(f"Redis connection failed: {str(e)}")
            return False

    def check_configuration(self) -> bool:
        """Check configuration files."""
        print("\nChecking configuration files...")

        project_root = Path(__file__).parents[1]

        required_files = [
            ".env",
            ".env.example",
            "pyproject.toml",
            "README.md",
            ".gitignore",
            "config/development.yaml",
            "config/production.yaml",
        ]

        missing_files = []

        for file_path in required_files:
            full_path = project_root / file_path
            if not full_path.exists():
                missing_files.append(file_path)

        if missing_files:
            self.errors.append(
                f"Missing configuration files: {', '.join(missing_files)}"
            )
            return False

        print("✓ All configuration files exist")

        # Check if .env has required variables
        env_path = project_root / ".env"
        with open(env_path) as f:
            env_content = f.read()

        required_vars = [
            "POSTGRES_USER",
            "POSTGRES_PASSWORD",
            "POSTGRES_DB",
            "REDIS_HOST",
        ]

        missing_vars = []
        for var in required_vars:
            if f"{var}=" not in env_content:
                missing_vars.append(var)

        if missing_vars:
            self.warnings.append(
                f"Missing environment variables: {', '.join(missing_vars)}"
            )

        return True

    def check_docker(self) -> bool:
        """Check Docker containers."""
        print("\nChecking Docker containers...")

        import subprocess

        try:
            # Check if Docker is running
            result = subprocess.run(
                ["docker", "ps", "--format", "table {{.Names}}\t{{.Status}}"],
                capture_output=True,
                text=True,
                check=True,
            )

            output = result.stdout

            required_containers = [
                "ashareinsight-postgres",
                "ashareinsight-redis",
                "ashareinsight-adminer",
            ]

            running_containers = []
            for container in required_containers:
                if container in output and "Up" in output:
                    running_containers.append(container)

            if len(running_containers) != len(required_containers):
                missing = set(required_containers) - set(running_containers)
                self.errors.append(
                    f"Missing or stopped containers: {', '.join(missing)}"
                )
                return False

            print("✓ All Docker containers are running")
            return True

        except subprocess.CalledProcessError:
            self.errors.append("Docker command failed. Is Docker running?")
            return False
        except FileNotFoundError:
            self.errors.append("Docker not found. Please install Docker.")
            return False

    def run_validation(self) -> bool:
        """Run all validation checks."""
        print("=" * 50)
        print("AShareInsight Environment Validation")
        print("=" * 50)

        checks = [
            ("Project Structure", self.check_project_structure),
            ("Docker Containers", self.check_docker),
            ("PostgreSQL Database", self.check_postgresql),
            ("Redis Cache", self.check_redis),
            ("Configuration Files", self.check_configuration),
        ]

        all_passed = True

        for name, check_func in checks:
            try:
                if not check_func():
                    all_passed = False
            except Exception as e:
                self.errors.append(f"{name} check failed with exception: {str(e)}")
                all_passed = False

        print("\n" + "=" * 50)
        print("VALIDATION SUMMARY")
        print("=" * 50)

        if self.errors:
            print("\n❌ ERRORS:")
            for error in self.errors:
                print(f"  - {error}")

        if self.warnings:
            print("\n⚠️  WARNINGS:")
            for warning in self.warnings:
                print(f"  - {warning}")

        if all_passed and not self.errors:
            print("\n✅ All validation checks passed!")
            print("\nYour environment is ready for development.")
            print("\nNext steps:")
            print(
                "1. Run the API server: uv run uvicorn src.interfaces.api.main:app --reload"
            )
            print("2. Access Adminer at: http://localhost:8124")
            print("3. Access the API docs at: http://localhost:8000/docs")
            return True
        else:
            print("\n❌ Validation failed. Please fix the errors above.")
            return False


def main():
    """Main entry point."""
    validator = EnvironmentValidator()
    success = validator.run_validation()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
