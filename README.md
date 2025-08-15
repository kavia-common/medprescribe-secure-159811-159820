# medprescribe-secure-159811-159820

This workspace contains the prescription_database for the MedPrescribe Secure application.

Overview

- Database: SQLite
- Purpose: Stores users, prescriptions, verification logs, and blockchain transaction metadata for analytics and consistency.
- Entry script: prescription_database/init_db.py
- Seeded accounts: One doctor and one pharmacist for development

Setup and initialization

1) From the prescription_database directory, run the initializer
   - ./init_db.py or python3 init_db.py
   - The script is idempotent and safe to re-run:
     - Creates tables if they do not exist
     - Adds missing columns where possible
     - Creates indexes if missing
     - Seeds initial users (see credentials below)

2) Connection helpers are written for your convenience
   - prescription_database/db_connection.txt
     - Contains simple connection methods and absolute file path
   - prescription_database/db_visualizer/sqlite.env
     - Exports SQLITE_DB for the optional Node-based DB viewer

3) Confirm database availability (optional)
   - Run: python3 test_db.py
   - It will verify the database exists and prints the SQLite version

Environment variables

- Not required to run the initializer.
- Optional: The included db viewer uses SQLITE_DB from db_visualizer/sqlite.env. You can source it with:
  - source db_visualizer/sqlite.env

Schema (high level)

- users
  - role: doctor, pharmacist, or admin
  - email (unique), username (unique), password_hash
  - solana_wallet (optional)
  - is_active, created_at, updated_at

- prescriptions
  - code (unique)
  - doctor_id (FK to users), pharmacist_id (FK, nullable)
  - patient_name, patient_dob (optional)
  - medication_name, dosage, quantity, instructions
  - status: created, dispensed, revoked, expired
  - offchain_hash
  - issued_at, dispensed_at, created_at, updated_at

- verification_logs
  - One per verification attempt
  - prescription_id (FK), verifier_user_id (FK, nullable)
  - method (e.g., code or qr), success, reason, ip_address, user_agent, created_at

- transactions
  - Blockchain recording and confirmations
  - prescription_id (FK), tx_signature (unique), network, status, slot, error, created_at, confirmed_at

Seed accounts (development)

The initializer seeds two accounts for development and testing. Passwords are stored using a PBKDF2-SHA256 scheme.

- Doctor
  - username: drdev
  - email: doctor@example.com
  - password: doctor123

- Pharmacist
  - username: pharmdev
  - email: pharmacist@example.com
  - password: pharmacist123

Notes:
- If the script is run multiple times, these accounts will not duplicate (unique constraints plus INSERT OR IGNORE).
- You can log in with these credentials via the backend/frontend once connected to this database file.

How the database is used by the backend

- The FastAPI backend connects to SQLite via the SQLITE_DB environment variable.
- To use the seeded users in the backend, ensure SQLITE_DB points to this same file (the init_db.py default is myapp.db in this directory).
  - Example when running the backend:
    - export SQLITE_DB="/absolute/path/to/medprescribe-secure-159811-159820/prescription_database/myapp.db"
- If SQLITE_DB is not provided to the backend, it will default to a local myapp.db in the backend working directory, which will not include the seeded users unless you copy/migrate the file.

Using the DB viewer (optional)

1) From prescription_database/db_visualizer
   - source sqlite.env
   - npm install (first time)
   - npm start

2) Visit http://localhost:3000 to browse the SQLite database.

Typical usage flow in development

1) Initialize the database in this container
   - cd prescription_database
   - python3 init_db.py

2) Run the backend with SQLITE_DB pointed at the initialized file
   - export SQLITE_DB="/absolute/path/to/prescription_database/myapp.db"
   - uvicorn src.api.main:app --host 0.0.0.0 --port 8000

3) Start the frontend with NEXT_PUBLIC_BACKEND_URL pointing to your backend
   - export NEXT_PUBLIC_BACKEND_URL="http://localhost:8000"
   - npm run dev

4) Sign in with seeded credentials and proceed with creating/verifying prescriptions.

Troubleshooting

- Make sure the initializer is run from within the prescription_database directory so relative paths resolve correctly.
- SQLite foreign key enforcement is enabled during initialization (PRAGMA foreign_keys = ON).
- If you manually modify the DB and see schema mismatches, re-run init_db.py to attempt auto-migration of missing columns and indexes.
- If the backend reports “Incorrect username or password” for the seeded users, confirm that SQLITE_DB in the backend points to the same myapp.db initialized here.
