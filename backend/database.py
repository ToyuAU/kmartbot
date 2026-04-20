"""
SQLite database setup using aiosqlite.
Creates all tables on first run, provides a context-managed connection helper.
"""

import aiosqlite
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "kmartbot.db"


SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    first_name  TEXT,
    last_name   TEXT,
    email       TEXT,
    mobile      TEXT,
    address1    TEXT,
    address2    TEXT,
    city        TEXT,
    state       TEXT,
    postcode    TEXT,
    country     TEXT DEFAULT 'AU',
    flybuys     TEXT,
    created_at  TEXT
);

CREATE TABLE IF NOT EXISTS cards (
    id            TEXT PRIMARY KEY,
    alias         TEXT NOT NULL,
    cardholder    TEXT,
    number        TEXT NOT NULL,
    expiry_month  TEXT,
    expiry_year   TEXT,
    cvv           TEXT,
    created_at    TEXT
);

CREATE TABLE IF NOT EXISTS tasks (
    id               TEXT PRIMARY KEY,
    name             TEXT,
    site             TEXT DEFAULT 'kmart',
    sku              TEXT NOT NULL,
    profile_id       TEXT REFERENCES profiles(id),
    card_ids         TEXT,
    quantity         INTEGER DEFAULT 1,
    use_staff_codes  INTEGER DEFAULT 1,
    use_flybuys      INTEGER DEFAULT 1,
    watch_mode       INTEGER DEFAULT 0,
    status           TEXT DEFAULT 'idle',
    error_message    TEXT,
    order_number     TEXT,
    created_at       TEXT,
    updated_at       TEXT
);

CREATE TABLE IF NOT EXISTS task_logs (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id  TEXT REFERENCES tasks(id) ON DELETE CASCADE,
    level    TEXT,
    message  TEXT,
    step     TEXT,
    ts       TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS settings (
    key    TEXT PRIMARY KEY,
    value  TEXT
);

CREATE INDEX IF NOT EXISTS idx_task_logs_task_id ON task_logs(task_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
"""


# Lightweight migrations for existing databases (ALTER TABLE is idempotent-safe via try/except).
async def _migrate(db) -> None:
    try:
        await db.execute("ALTER TABLE tasks ADD COLUMN watch_mode INTEGER DEFAULT 0")
    except Exception:
        pass


async def init_db() -> None:
    """Create tables if they don't exist."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await _migrate(db)
        await db.commit()


async def get_db() -> aiosqlite.Connection:
    """
    FastAPI dependency that yields an aiosqlite connection with row_factory set.
    Commits on clean exit, rolls back on exception.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        try:
            yield db
            await db.commit()
        except Exception:
            await db.rollback()
            raise
