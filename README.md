# medprescribe-secure-159811-159820

This workspace contains the prescription_database for the MedPrescribe Secure application.

## Overview

- Database: SQLite
- Purpose: Stores users, prescriptions, verification logs, and blockchain transaction metadata for analytics and consistency.
- Entry script: `prescription_database/init_db.py`

## Initialize or Migrate the Database

From the `prescription_database` directory:

1. Run the initializer:
   - `./init_db.py` or `python3 init_db.py`
2. The script is idempotent:
   - Creates tables if they don't exist
   - Adds missing columns if needed
   - Creates indexes if missing
   - Seeds initial users (below)
3. Connection info is written to:
   - `prescription_database/db_connection.txt`
   - `prescription_database/db_visualizer/sqlite.env` (for the included Node-based DB viewer)

## Tables (high level)

- users
  - role: doctor, pharmacist, or admin
  - email (unique), username (unique), password_hash
  - solana_wallet (optional)
  - is_active, created_at, updated_at

- prescriptions
  - code (unique)
  - doctor_id (FK to users), pharmacist_id (FK, nullable when not dispensed)
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

## Seed Accounts

The initializer seeds two accounts for development and testing. Passwords are stored using PBKDF2-SHA256.

- Doctor
  - username: `drdev`
  - email: `doctor@example.com`
  - password: `doctor123`

- Pharmacist
  - username: `pharmdev`
  - email: `pharmacist@example.com`
  - password: `pharmacist123`

Notes:
- If the script is run multiple times, these accounts won't be duplicated because of unique constraints and `INSERT OR IGNORE`.
- You can log in with these credentials via the backend/frontend once those components are integrated.

## Using the DB Viewer (optional)

From `prescription_database/db_visualizer`, run:
- `source sqlite.env`
- `npm install` (first time)
- `npm start`

Then visit http://localhost:3000 to browse the SQLite database.

## Troubleshooting

- Ensure you run the initializer from within the `prescription_database` directory so paths resolve correctly.
- SQLite foreign key enforcement is enabled during initialization (`PRAGMA foreign_keys = ON`).
- If you manually modify the DB and encounter schema mismatches, re-run `init_db.py` to attempt auto-migration of missing columns and indexes.
