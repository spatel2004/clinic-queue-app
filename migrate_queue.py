
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "instance" / "clinic.db"


def migrate():
    conn = sqlite3.connect(DB_PATH)

    # Check whether the queue table exists.
    table_exists = conn.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type = 'table' AND name = 'queue'"
    ).fetchone()

    if not table_exists:
        print("No existing queue table. Migration skipped.")
        conn.close()
        return

    # Check whether the database already has the new queue structure.
    columns = {
        row[1]
        for row in conn.execute("PRAGMA table_info(queue)")
    }

    if {"patient_id", "doctor_id", "entry_type", "called_at"}.issubset(columns):
        print("Queue table already migrated. No changes needed.")
        conn.close()
        return

    new_columns = {
        "patient_id",
        "doctor_id",
        "entry_type",
        "called_at"
    }

    if columns.intersection(new_columns):
        print(
            "Partially migrated queue table detected. "
            "Migration stopped to prevent data loss."
        )
        conn.close()
        return



    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("BEGIN")

        # Rename the existing queue table
        conn.execute("ALTER TABLE queue RENAME TO queue_old")

        # Create the updated queue table
        conn.execute("""
            CREATE TABLE queue (
                id INTEGER PRIMARY KEY,
                appointment_id INTEGER UNIQUE,
                patient_id INTEGER,
                doctor_id INTEGER,
                entry_type VARCHAR(20) NOT NULL DEFAULT 'appointment',
                called_at DATETIME,
                queue_number INTEGER NOT NULL,
                queue_date DATE NOT NULL,
                status VARCHAR(50) NOT NULL DEFAULT 'waiting',
                checked_in_at DATETIME NOT NULL,
                FOREIGN KEY (appointment_id) REFERENCES appointment(id),
                FOREIGN KEY (patient_id) REFERENCES patient(id),
                FOREIGN KEY (doctor_id) REFERENCES doctor(id),
                CONSTRAINT uq_daily_queue_number
                    UNIQUE (queue_date, queue_number),
                CONSTRAINT ck_queue_patient_source
                    CHECK (
                        (appointment_id IS NOT NULL AND patient_id IS NULL)
                        OR
                        (appointment_id IS NULL AND patient_id IS NOT NULL)
                    ),
                CONSTRAINT ck_queue_entry_type
                    CHECK (
                        (entry_type = 'appointment'
                         AND appointment_id IS NOT NULL)
                        OR
                        (entry_type = 'walk_in'
                         AND patient_id IS NOT NULL)
                    )
            )
        """)


        # Copy existing records and preserve check-in timestamps
        checked_in_expression = (
            "checked_in_at"
            if "checked_in_at" in columns
            else "CURRENT_TIMESTAMP"
        )

        conn.execute(f"""
            INSERT INTO queue (
                id,
                appointment_id,
                patient_id,
                doctor_id,
                entry_type,
                called_at,
                queue_number,
                queue_date,
                status,
                checked_in_at
            )
            SELECT
                id,
                appointment_id,
                NULL,
                NULL,
                'appointment',
                NULL,
                queue_number,
                queue_date,
                status,
                {checked_in_expression}
            FROM queue_old
        """)


        conn.execute("DROP TABLE queue_old")
        conn.execute(
            "CREATE INDEX ix_queue_queue_date ON queue(queue_date)"
        )

        conn.commit()
        print("Queue database migration successful!")

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
