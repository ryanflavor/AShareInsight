#!/usr/bin/env python3
"""
Quick import checker - catches errors like DocType that would break the code.
This is a focused check that only looks for undefined names and import errors.
"""

import subprocess
import sys


def main():
    print("🔍 Running import checks (this would have caught the DocType error)...\n")

    # Run mypy with focus on undefined names and imports
    cmd = [
        "mypy",
        "src/",
        "--config-file=mypy_imports.ini",
        "--no-error-summary",
        "--show-error-codes",
        "--show-column-numbers",
        "--no-pretty",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    # Filter for import and name errors
    import_errors = []
    name_errors = []

    for line in result.stdout.split("\n"):
        if "[attr-defined]" in line or "[name-defined]" in line:
            if "has no attribute" in line or "is not defined" in line:
                # This is the kind of error that would catch DocType
                name_errors.append(line)
        elif "[import]" in line:
            import_errors.append(line)

    if name_errors or import_errors:
        print("❌ Found import/name errors that would break the code:\n")

        if name_errors:
            print("🚨 Undefined names (like DocType):")
            for error in name_errors:
                print(f"  {error}")
            print()

        if import_errors:
            print("🚨 Import errors:")
            for error in import_errors:
                print(f"  {error}")
            print()

        print("💡 Fix these errors before committing!")
        return 1
    else:
        print("✅ No import or undefined name errors found!")
        print("   The DocType issue would have been caught by this check.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
