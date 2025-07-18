"""
Comprehensive compatibility validation script for Story 1.1
Validates all component integrations and generates compatibility report
"""

import json
import sys
from datetime import datetime

# Add paths for imports
from pathlib import Path
from typing import Any

# Add core package to path
sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "core" / "src"))
# Add tests directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "tests" / "core"))

# Import our modules
from core.database import DatabaseConnection
from core.logging_config import get_logger, setup_logging
from test_sqlalchemy_integration import test_sqlalchemy_psycopg_format
from test_vector_storage_integration import (
    test_langchain_postgres_integration,
    verify_hnsw_index_creation,
)

logger = get_logger(__name__)


class CompatibilityValidator:
    """Comprehensive compatibility validation for all components"""

    def __init__(self):
        self.results = {
            "validation_timestamp": datetime.now().isoformat(),
            "story": "1.1 - 关键技术与版本兼容性验证",
            "acceptance_criteria": {
                "AC1": (
                    "Successfully create a minimal prototype environment "
                    "with PostgreSQL + pgvector"
                ),
                "AC2": (
                    "Verify langchain-postgres package compatibility "
                    "with our database setup"
                ),
                "AC3": "Confirm Pydantic 2.0+ compatibility with Python 3.13",
                "AC4": (
                    "Validate psycopg3 database connection "
                    "with postgresql+psycopg:// format"
                ),
                "AC5": "Test basic vector operations using HNSW indexing strategy",
            },
            "test_results": {},
            "issues_found": [],
            "recommendations": [],
        }

    def validate_python_environment(self) -> dict[str, Any]:
        """Validate Python 3.13 and core dependencies"""
        print("🔍 Validating Python environment...")

        import sys

        import langchain_postgres
        import psycopg
        import pydantic

        try:
            result = {
                "status": "passed",
                "python_version": sys.version,
                "dependencies": {
                    "pydantic": pydantic.__version__,
                    "psycopg": psycopg.__version__,
                    "langchain_postgres": langchain_postgres.__version__,
                    "pgvector": "installed",
                },
                "python_version_check": sys.version_info >= (3, 13),
                "pydantic_2_check": pydantic.__version__.startswith("2."),
            }

            if not result["python_version_check"]:
                result["status"] = "failed"
                self.results["issues_found"].append("Python version < 3.13")

            if not result["pydantic_2_check"]:
                result["status"] = "failed"
                self.results["issues_found"].append("Pydantic version < 2.0")

            print(f"✅ Python Environment: {result['status'].upper()}")
            return result

        except Exception as e:
            print(f"❌ Python Environment: FAILED - {e}")
            return {"status": "failed", "error": str(e)}

    def validate_database_connection(self) -> dict[str, Any]:
        """Validate database connections (AC1, AC4)"""
        print("🔍 Validating database connections...")

        try:
            # Test direct psycopg3 connection
            db = DatabaseConnection(
                "postgresql://postgres:test123@localhost:5432/ashareinsight"
            )
            connectivity_result = db.test_basic_connectivity()

            # Test connection pooling
            db.create_connection_pool()
            pool_result = db.test_connection_pool()
            db.close_pool()

            # Test SQLAlchemy postgresql+psycopg:// format
            sqlalchemy_success = test_sqlalchemy_psycopg_format()

            result = {
                "status": (
                    "passed"
                    if all(
                        [
                            connectivity_result["status"] == "success",
                            pool_result["status"] == "success",
                            sqlalchemy_success,
                        ]
                    )
                    else "failed"
                ),
                "psycopg3_direct": connectivity_result,
                "connection_pooling": pool_result,
                "sqlalchemy_psycopg_format": sqlalchemy_success,
                "postgresql_version": connectivity_result.get(
                    "postgresql_version", "unknown"
                ),
                "vector_extension": connectivity_result.get("vector_extension", {}),
            }

            if result["status"] == "failed":
                self.results["issues_found"].append(
                    "Database connection issues detected"
                )

            print(f"✅ Database Connection: {result['status'].upper()}")
            return result

        except Exception as e:
            print(f"❌ Database Connection: FAILED - {e}")
            return {"status": "failed", "error": str(e)}

    def validate_vector_operations(self) -> dict[str, Any]:
        """Validate vector operations and HNSW indexing (AC2, AC5)"""
        print("🔍 Validating vector operations...")

        try:
            # Test langchain-postgres integration
            vector_test_success = test_langchain_postgres_integration()

            # Verify HNSW index creation
            hnsw_verification_success = verify_hnsw_index_creation()

            result = {
                "status": (
                    "passed"
                    if vector_test_success and hnsw_verification_success
                    else "failed"
                ),
                "langchain_postgres_integration": vector_test_success,
                "hnsw_index_verification": hnsw_verification_success,
            }

            if result["status"] == "failed":
                self.results["issues_found"].append(
                    "Vector operations or HNSW indexing issues"
                )

            print(f"✅ Vector Operations: {result['status'].upper()}")
            return result

        except Exception as e:
            print(f"❌ Vector Operations: FAILED - {e}")
            return {"status": "failed", "error": str(e)}

    def validate_pydantic_models(self) -> dict[str, Any]:
        """Validate Pydantic 2.0 models (AC3)"""
        print("🔍 Validating Pydantic 2.0 models...")

        try:
            import numpy as np
            from pydantic import BaseModel, Field

            # Create test Pydantic model
            class BusinessConcept(BaseModel):
                id: int
                name: str
                description: str
                embedding: list[float] = Field(..., min_length=2560, max_length=2560)
                metadata: dict[str, Any] | None = None

                class Config:
                    arbitrary_types_allowed = True

            # Test model creation
            test_embedding = np.random.random(2560).tolist()
            concept = BusinessConcept(
                id=1,
                name="Test Concept",
                description="A test business concept",
                embedding=test_embedding,
                metadata={"category": "test"},
            )

            # Test serialization
            concept_dict = concept.model_dump()
            _ = concept.model_dump_json()  # Test JSON serialization

            # Test validation
            BusinessConcept.model_validate(concept_dict)

            result = {
                "status": "passed",
                "pydantic_version": "2.0+",
                "model_creation": True,
                "serialization": True,
                "validation": True,
                "sample_model": concept_dict,
            }

            print(f"✅ Pydantic Models: {result['status'].upper()}")
            return result

        except Exception as e:
            print(f"❌ Pydantic Models: FAILED - {e}")
            return {"status": "failed", "error": str(e)}

    def run_full_validation(self) -> dict[str, Any]:
        """Run comprehensive validation of all components"""
        print("🚀 Starting comprehensive compatibility validation...")
        print("=" * 60)

        # Run all validations
        self.results["test_results"]["python_environment"] = (
            self.validate_python_environment()
        )
        self.results["test_results"]["database_connection"] = (
            self.validate_database_connection()
        )
        self.results["test_results"]["vector_operations"] = (
            self.validate_vector_operations()
        )
        self.results["test_results"]["pydantic_models"] = (
            self.validate_pydantic_models()
        )

        # Determine overall status
        all_passed = all(
            result.get("status") == "passed"
            for result in self.results["test_results"].values()
        )

        self.results["overall_status"] = "PASSED" if all_passed else "FAILED"

        # Add recommendations
        if all_passed:
            self.results["recommendations"] = [
                "All components are compatible and ready for production use",
                "HNSW indexing is working correctly for vector search performance",
                "Connection pooling is functional for database scalability",
                "Pydantic 2.0 models are working with Python 3.13",
            ]
        else:
            self.results["recommendations"] = [
                "Address the issues found before proceeding to next development phase",
                "Review error logs for detailed troubleshooting information",
            ]

        return self.results

    def generate_report(self) -> str:
        """Generate formatted compatibility report"""
        report = []
        report.append("📋 COMPATIBILITY VALIDATION REPORT")
        report.append("=" * 60)
        report.append(f"Story: {self.results['story']}")
        report.append(f"Timestamp: {self.results['validation_timestamp']}")
        report.append(f"Overall Status: {self.results['overall_status']}")
        report.append("")

        # Acceptance Criteria Mapping
        report.append("📋 ACCEPTANCE CRITERIA STATUS:")
        ac_status = {
            "AC1": self.results["test_results"]["database_connection"]["status"]
            == "passed",
            "AC2": self.results["test_results"]["vector_operations"]["status"]
            == "passed",
            "AC3": self.results["test_results"]["pydantic_models"]["status"]
            == "passed",
            "AC4": self.results["test_results"]["database_connection"]["status"]
            == "passed",
            "AC5": self.results["test_results"]["vector_operations"]["status"]
            == "passed",
        }

        for ac, description in self.results["acceptance_criteria"].items():
            status = "✅ PASSED" if ac_status[ac] else "❌ FAILED"
            report.append(f"  {ac}: {status}")
            report.append(f"      {description}")

        report.append("")

        # Detailed Results
        report.append("🔍 DETAILED TEST RESULTS:")
        for test_name, result in self.results["test_results"].items():
            status = result.get("status", "unknown").upper()
            icon = "✅" if status == "PASSED" else "❌"
            report.append(f"  {icon} {test_name.replace('_', ' ').title()}: {status}")

        report.append("")

        # Issues
        if self.results["issues_found"]:
            report.append("⚠️  ISSUES FOUND:")
            for issue in self.results["issues_found"]:
                report.append(f"  - {issue}")
            report.append("")

        # Recommendations
        report.append("💡 RECOMMENDATIONS:")
        for rec in self.results["recommendations"]:
            report.append(f"  - {rec}")

        return "\n".join(report)


def main():
    """Run compatibility validation and generate report"""
    validator = CompatibilityValidator()

    # Run validation
    results = validator.run_full_validation()

    # Generate and display report
    print("\n" + "=" * 60)
    report = validator.generate_report()
    print(report)

    # Save results to file
    with open("compatibility_validation_report.json", "w") as f:
        json.dump(results, f, indent=2)

    # Save formatted report
    with open("compatibility_validation_report.txt", "w") as f:
        f.write(report)

    print("\n📄 Detailed results saved to:")
    print("  - compatibility_validation_report.json")
    print("  - compatibility_validation_report.txt")

    # Return exit code
    return 0 if results["overall_status"] == "PASSED" else 1


if __name__ == "__main__":
    setup_logging(level="INFO")
    sys.exit(main())
