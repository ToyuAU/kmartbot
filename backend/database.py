"""
SQLite database setup using aiosqlite.
Creates all tables on first run, provides configured connection helpers,
and keeps foreign key enforcement enabled for every connection.
"""

from pathlib import Path

import aiosqlite

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
    profile_id       TEXT REFERENCES profiles(id) ON DELETE RESTRICT,
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

CREATE TABLE IF NOT EXISTS task_runs (
    id             TEXT PRIMARY KEY,
    task_id        TEXT NOT NULL,
    task_name      TEXT,
    site           TEXT,
    sku            TEXT NOT NULL,
    profile_id     TEXT,
    card_id        TEXT,
    card_alias     TEXT,
    proxy          TEXT,
    watch_mode     INTEGER DEFAULT 0,
    quantity       INTEGER DEFAULT 1,
    started_at     TEXT NOT NULL,
    finished_at    TEXT,
    duration_ms    INTEGER,
    final_status   TEXT,
    order_number   TEXT,
    error_message  TEXT
);

CREATE TABLE IF NOT EXISTS task_run_steps (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id           TEXT NOT NULL REFERENCES task_runs(id) ON DELETE CASCADE,
    step             TEXT NOT NULL,
    started_at       TEXT NOT NULL,
    finished_at      TEXT,
    duration_ms      INTEGER,
    terminal_status  TEXT
);

CREATE TABLE IF NOT EXISTS task_run_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      TEXT NOT NULL REFERENCES task_runs(id) ON DELETE CASCADE,
    task_id     TEXT NOT NULL,
    event_seq   INTEGER NOT NULL,
    event_type  TEXT NOT NULL,
    status      TEXT,
    level       TEXT,
    step        TEXT,
    message     TEXT,
    payload     TEXT,
    ts          TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_task_logs_task_id ON task_logs(task_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_task_runs_task_id_started_at ON task_runs(task_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_task_run_steps_run_id ON task_run_steps(run_id);
CREATE INDEX IF NOT EXISTS idx_task_run_events_run_id_seq ON task_run_events(run_id, event_seq);
"""


# Lightweight migrations for existing databases (ALTER TABLE is idempotent-safe via try/except).
async def _migrate(db) -> None:
    try:
        await db.execute("ALTER TABLE tasks ADD COLUMN watch_mode INTEGER DEFAULT 0")
    except Exception:
        pass


async def connect_db(*, row_factory: bool = True) -> aiosqlite.Connection:
    """Open a configured SQLite connection for the app."""
    db = await aiosqlite.connect(DB_PATH)
    await db.execute("PRAGMA foreign_keys = ON")
    if row_factory:
        db.row_factory = aiosqlite.Row
    return db


async def init_db() -> None:
    """Create tables if they don't exist."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = await connect_db(row_factory=False)
    try:
        await db.executescript(SCHEMA)
        await _migrate(db)
        await db.commit()
    finally:
        await db.close()


async def get_db() -> aiosqlite.Connection:
    """
    FastAPI dependency that yields an aiosqlite connection with row_factory set.
    Commits on clean exit, rolls back on exception.
    """
    db = await connect_db()
    try:
        yield db
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    finally:
        await db.close()
