#!/usr/bin/env python3
"""Backup PostgreSQL database before timezone migration.

This script creates a full backup of the database including all data and schema.
"""

import os
import subprocess
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

from src.shared.config import settings
from src.shared.utils.timezone import now_china


def create_backup():
    """Create PostgreSQL database backup."""
    # Parse database URL
    db_url = settings.database.database_url
    # Extract components from postgresql://user:password@host:port/dbname
    import re

    match = re.match(
        r"postgresql://(?P<user>[^:]+):(?P<password>[^@]+)@(?P<host>[^:]+):(?P<port>\d+)/(?P<dbname>.+)",
        db_url,
    )

    if not match:
        print("Error: Could not parse database URL")
        return False

    db_config = match.groupdict()

    # Create backup directory
    backup_dir = Path("backups")
    backup_dir.mkdir(exist_ok=True)

    # Generate backup filename with timestamp
    timestamp = now_china().strftime("%Y%m%d_%H%M%S")
    backup_file = backup_dir / f"ashareinsight_backup_{timestamp}.sql"

    print(f"Starting database backup to {backup_file}")
    print(f"Database: {db_config['dbname']} on {db_config['host']}:{db_config['port']}")

    # Set environment variables for pg_dump
    env = os.environ.copy()
    env["PGPASSWORD"] = db_config["password"]

    # Build pg_dump command
    cmd = [
        "pg_dump",
        "-h",
        db_config["host"],
        "-p",
        db_config["port"],
        "-U",
        db_config["user"],
        "-d",
        db_config["dbname"],
        "-f",
        str(backup_file),
        "--verbose",
        "--clean",
        "--no-owner",
        "--no-privileges",
        "--if-exists",
        "--create",
        "--no-sync",  # Don't wait for sync to disk (faster)
    ]

    try:
        # Execute pg_dump
        result = subprocess.run(
            cmd, env=env, capture_output=True, text=True, check=True
        )

        print("\nBackup completed successfully!")
        print(f"Backup file: {backup_file}")
        print(f"File size: {backup_file.stat().st_size / 1024 / 1024:.2f} MB")

        # Create backup info file
        info_file = backup_file.with_suffix(".info")
        with open(info_file, "w") as f:
            f.write(f"Backup created at: {now_china()}\n")
            f.write(f"Database: {db_config['dbname']}\n")
            f.write(f"Host: {db_config['host']}\n")
            f.write(f"Port: {db_config['port']}\n")
            f.write(f"User: {db_config['user']}\n")
            f.write(f"Backup file: {backup_file.name}\n")
            f.write(f"File size: {backup_file.stat().st_size} bytes\n")
            f.write("\nRestore command:\n")
            f.write(
                f"psql -h {db_config['host']} -p {db_config['port']} -U {db_config['user']} -d postgres < {backup_file.name}\n"
            )

        print(f"Backup info saved to: {info_file}")
        return True

    except subprocess.CalledProcessError as e:
        print("Error: Backup failed!")
        print(f"Command: {' '.join(cmd)}")
        print(f"Error output: {e.stderr}")
        return False
    except FileNotFoundError:
        print("Error: pg_dump not found. Please install PostgreSQL client tools.")
        print("On Ubuntu/Debian: sudo apt-get install postgresql-client")
        print("On macOS: brew install postgresql")
        return False


if __name__ == "__main__":
    load_dotenv()

    print("=== AShareInsight Database Backup ===")
    print(f"Current time: {now_china()}")
    print()

    # Check for --yes flag
    if "--yes" in sys.argv:
        print("Running in non-interactive mode (--yes flag detected)")
        success = create_backup()
    else:
        # Confirm backup
        response = input("Do you want to create a database backup? (yes/no): ")
        if response.lower() != "yes":
            print("Backup cancelled.")
            sys.exit(0)
        success = create_backup()

    sys.exit(0 if success else 1)
