#!/usr/bin/env python3
"""Initialize and migrate SQLite database for prescription_database.

This script:
- Ensures SQLite database file exists and is accessible.
- Enables foreign key enforcement.
- Creates or migrates required tables:
  - users: system users (doctor, pharmacist, admin)
  - prescriptions: prescription records issued by doctors
  - verification_logs: logs for verification attempts
  - transactions: blockchain transaction metadata (e.g., Solana)
- Creates appropriate indexes.
- Seeds initial doctor and pharmacist accounts with known passwords.
- Writes helpful connection info to db_connection.txt and db_visualizer/sqlite.env

Idempotency:
- Uses CREATE TABLE IF NOT EXISTS and CREATE INDEX IF NOT EXISTS.
- Uses ALTER TABLE ADD COLUMN for missing columns on existing tables.
- Seed inserts use INSERT OR IGNORE to avoid duplicates on re-run.
"""

import base64
import hashlib
import os
import sqlite3
from typing import Dict, Set

DB_NAME = "myapp.db"

# Seed users (documented in README)
SEED_USERS = [
    {"role": "doctor", "username": "drdev", "email": "doctor@example.com", "password": "doctor123"},
    {"role": "pharmacist", "username": "pharmdev", "email": "pharmacist@example.com", "password": "pharmacist123"},
]

# Supported enumerations
USER_ROLES = ("doctor", "pharmacist", "admin")
PRESCRIPTION_STATUS = ("created", "dispensed", "revoked", "expired")


def _connect(db_path: str) -> sqlite3.Connection:
    """Create a SQLite connection with foreign keys enabled."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _get_existing_columns(cursor: sqlite3.Cursor, table: str) -> Set[str]:
    """Return a set of existing column names for a table."""
    cursor.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in cursor.fetchall()}


def _table_exists(cursor: sqlite3.Cursor, table: str) -> bool:
    """Check whether a table exists."""
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
    return cursor.fetchone() is not None


def _create_table(cursor: sqlite3.Cursor, create_sql: str) -> None:
    """Execute CREATE TABLE IF NOT EXISTS DDL."""
    cursor.execute(create_sql)


def _add_column_if_missing(cursor: sqlite3.Cursor, table: str, column_name: str, column_def: str) -> None:
    """Add a column to a table if it's missing.

    Note: SQLite allows ADD COLUMN with constraints like NOT NULL only if a DEFAULT is provided.
    Avoid adding UNIQUE/FOREIGN KEY constraints here; use indexes or create-time constraints for new tables.
    """
    existing = _get_existing_columns(cursor, table)
    if column_name not in existing:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column_def}")


def _create_index(cursor: sqlite3.Cursor, name: str, table: str, columns: str, unique: bool = False) -> None:
    """Create an index if not exists."""
    unique_sql = "UNIQUE " if unique else ""
    cursor.execute(f"CREATE {unique_sql}INDEX IF NOT EXISTS {name} ON {table} ({columns});")


# PUBLIC_INTERFACE
def hash_password(password: str, salt: bytes = None, iterations: int = 100_000) -> str:
    """Return a PBKDF2-SHA256 hash for the given password.

    Stored format: pbkdf2_sha256$<iterations>$<base64(salt)>$<base64(hash)>
    """
    if salt is None:
        salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def _initialize_app_info(cursor: sqlite3.Cursor) -> None:
    """Create app_info table and populate basic metadata."""
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS app_info (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            value TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute("INSERT OR REPLACE INTO app_info (key, value) VALUES (?, ?)", ("project_name", "prescription_database"))
    cursor.execute("INSERT OR REPLACE INTO app_info (key, value) VALUES (?, ?)", ("version", "0.2.0"))
    cursor.execute("INSERT OR REPLACE INTO app_info (key, value) VALUES (?, ?)", ("author", "MedPrescribe Secure"))
    cursor.execute("INSERT OR REPLACE INTO app_info (key, value) VALUES (?, ?)", ("description", "SQLite DB for prescriptions"))


def _initialize_users(cursor: sqlite3.Cursor) -> None:
    """Create or migrate users table, and ensure indexes exist."""
    # Create full table if it doesn't exist
    _create_table(
        cursor,
        f"""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL CHECK (role IN {USER_ROLES}),
            email TEXT NOT NULL UNIQUE,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            solana_wallet TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
    )

    # If users table existed previously with fewer columns, add missing ones
    if _table_exists(cursor, "users"):
        # Definitions here must be ADD COLUMN compatible (provide DEFAULT if NOT NULL)
        _add_column_if_missing(cursor, "users", "role", f"role TEXT DEFAULT 'doctor' CHECK (role IN {USER_ROLES})")
        _add_column_if_missing(cursor, "users", "password_hash", "password_hash TEXT DEFAULT ''")
        _add_column_if_missing(cursor, "users", "solana_wallet", "solana_wallet TEXT")
        _add_column_if_missing(cursor, "users", "is_active", "is_active INTEGER NOT NULL DEFAULT 1")
        _add_column_if_missing(cursor, "users", "updated_at", "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")

    # Ensure uniqueness and useful indexes (redundant to table UNIQUE ok; IF NOT EXISTS avoids errors)
    _create_index(cursor, "idx_users_role", "users", "role")
    _create_index(cursor, "ux_users_email", "users", "email", unique=True)
    _create_index(cursor, "ux_users_username", "users", "username", unique=True)

    # Updated_at trigger
    cursor.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_users_updated_at
        AFTER UPDATE ON users
        FOR EACH ROW
        BEGIN
            UPDATE users SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
        END;
        """
    )


def _initialize_prescriptions(cursor: sqlite3.Cursor) -> None:
    """Create prescriptions table and indexes."""
    _create_table(
        cursor,
        f"""
        CREATE TABLE IF NOT EXISTS prescriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            doctor_id INTEGER NOT NULL,
            pharmacist_id INTEGER,
            patient_name TEXT NOT NULL,
            patient_dob TEXT,
            medication_name TEXT NOT NULL,
            dosage TEXT,
            quantity INTEGER,
            instructions TEXT,
            status TEXT NOT NULL DEFAULT 'created' CHECK (status IN {PRESCRIPTION_STATUS}),
            offchain_hash TEXT,
            issued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            dispensed_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (doctor_id) REFERENCES users(id) ON DELETE RESTRICT,
            FOREIGN KEY (pharmacist_id) REFERENCES users(id) ON DELETE SET NULL
        )
        """,
    )

    _create_index(cursor, "ux_prescriptions_code", "prescriptions", "code", unique=True)
    _create_index(cursor, "idx_prescriptions_doctor", "prescriptions", "doctor_id")
    _create_index(cursor, "idx_prescriptions_status", "prescriptions", "status")

    cursor.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_prescriptions_updated_at
        AFTER UPDATE ON prescriptions
        FOR EACH ROW
        BEGIN
            UPDATE prescriptions SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
        END;
        """
    )


def _initialize_verification_logs(cursor: sqlite3.Cursor) -> None:
    """Create verification_logs table and indexes."""
    _create_table(
        cursor,
        """
        CREATE TABLE IF NOT EXISTS verification_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prescription_id INTEGER NOT NULL,
            verifier_user_id INTEGER,
            method TEXT NOT NULL, -- e.g., 'code', 'qr'
            success INTEGER NOT NULL DEFAULT 0, -- 0 false, 1 true
            reason TEXT,
            ip_address TEXT,
            user_agent TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (prescription_id) REFERENCES prescriptions(id) ON DELETE CASCADE,
            FOREIGN KEY (verifier_user_id) REFERENCES users(id) ON DELETE SET NULL
        )
        """,
    )
    _create_index(cursor, "idx_verification_logs_prescription", "verification_logs", "prescription_id")
    _create_index(cursor, "idx_verification_logs_verifier", "verification_logs", "verifier_user_id")


def _initialize_transactions(cursor: sqlite3.Cursor) -> None:
    """Create transactions table and indexes."""
    _create_table(
        cursor,
        """
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prescription_id INTEGER NOT NULL,
            tx_signature TEXT NOT NULL UNIQUE,
            network TEXT NOT NULL, -- devnet, testnet, mainnet
            status TEXT NOT NULL, -- submitted, confirmed, failed
            slot INTEGER,
            error TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            confirmed_at TIMESTAMP,
            FOREIGN KEY (prescription_id) REFERENCES prescriptions(id) ON DELETE CASCADE
        )
        """,
    )
    _create_index(cursor, "ux_transactions_signature", "transactions", "tx_signature", unique=True)
    _create_index(cursor, "idx_transactions_prescription", "transactions", "prescription_id")
    _create_index(cursor, "idx_transactions_status", "transactions", "status")


def _seed_users(cursor: sqlite3.Cursor) -> None:
    """Seed initial doctor and pharmacist accounts with deterministic secure hashes."""
    for u in SEED_USERS:
        # Use a deterministic salt for seeds to ensure reproducibility across runs
        # Note: In production for new users, use a random salt per user.
        deterministic_salt = hashlib.sha256(f"{u['email']}|{u['username']}".encode("utf-8")).digest()[:16]
        pwd_hash = hash_password(u["password"], salt=deterministic_salt)

        cursor.execute(
            """
            INSERT OR IGNORE INTO users (role, email, username, password_hash, solana_wallet, is_active)
            VALUES (?, ?, ?, ?, NULL, 1)
            """,
            (u["role"], u["email"], u["username"], pwd_hash),
        )


# PUBLIC_INTERFACE
def initialize_database(db_name: str = DB_NAME) -> Dict[str, int]:
    """Initialize or migrate database schema and seed data.

    Returns a summary dict with counts of tables and select records.
    """
    created_new = not os.path.exists(db_name)
    if created_new:
        print("Creating new SQLite database...")

    conn = _connect(db_name)
    try:
        cur = conn.cursor()

        # Ensure base metadata and all tables
        _initialize_app_info(cur)
        _initialize_users(cur)
        _initialize_prescriptions(cur)
        _initialize_verification_logs(cur)
        _initialize_transactions(cur)

        # Seed initial users
        _seed_users(cur)

        conn.commit()

        # Stats
        cur.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        table_count = cur.fetchone()[0]

        # Count seed users
        cur.execute("SELECT COUNT(*) FROM users")
        user_count = cur.fetchone()[0]

        return {"tables": table_count, "users": user_count}

    finally:
        conn.close()


def _write_connection_info(db_name: str) -> None:
    """Write connection info and db_visualizer env file."""
    current_dir = os.getcwd()
    connection_string = f"sqlite:///{current_dir}/{db_name}"

    try:
        with open("db_connection.txt", "w") as f:
            f.write("# SQLite connection methods:\n")
            f.write(f"# Python: sqlite3.connect('{db_name}')\n")
            f.write(f"# Connection string: {connection_string}\n")
            f.write(f"# File path: {current_dir}/{db_name}\n")
        print("Connection information saved to db_connection.txt")
    except Exception as e:
        print(f"Warning: Could not save connection info: {e}")

    # Ensure db_visualizer directory exists
    db_path = os.path.abspath(db_name)
    if not os.path.exists("db_visualizer"):
        os.makedirs("db_visualizer", exist_ok=True)
        print("Created db_visualizer directory")

    try:
        with open("db_visualizer/sqlite.env", "w") as f:
            f.write(f'export SQLITE_DB="{db_path}"\n')
        print("Environment variables saved to db_visualizer/sqlite.env")
    except Exception as e:
        print(f"Warning: Could not save environment variables: {e}")


def main() -> None:
    """Entrypoint: initialize DB, write connection helpers, and print stats/instructions."""
    print("Starting SQLite setup...")

    # Verify existing DB accessibility if present
    if os.path.exists(DB_NAME):
        try:
            conn = sqlite3.connect(DB_NAME)
            conn.execute("SELECT 1")
            conn.close()
            print(f"SQLite database already exists at {DB_NAME}")
            print("Database is accessible and working.")
        except Exception as e:
            print(f"Warning: Database exists but may be corrupted: {e}")

    # Initialize/migrate schema
    stats = initialize_database(DB_NAME)

    # Write connection info and sqlite.env for viewer
    _write_connection_info(DB_NAME)

    # Print stats and helper info
    print("\nSQLite setup complete!")
    print(f"Database: {DB_NAME}")
    print(f"Location: {os.path.abspath(DB_NAME)}\n")

    print("To use with Node.js viewer, run: source db_visualizer/sqlite.env\n")

    print("To connect to the database, use one of the following methods:")
    print(f"1. Python: sqlite3.connect('{DB_NAME}')")
    print(f"2. Connection string: sqlite:///{os.path.abspath(DB_NAME)}")
    print(f"3. Direct file access: {os.path.abspath(DB_NAME)}\n")

    print("Database statistics:")
    print(f"  Tables: {stats.get('tables', 0)}")
    print(f"  Users: {stats.get('users', 0)}")

    # If sqlite3 CLI is available, show how to use it
    try:
        import subprocess

        result = subprocess.run(["which", "sqlite3"], capture_output=True, text=True)
        if result.returncode == 0:
            print("\nSQLite CLI is available. You can also use:")
            print(f"  sqlite3 {DB_NAME}")
    except Exception:
        pass

    print("\nScript completed successfully.")


if __name__ == "__main__":
    main()
