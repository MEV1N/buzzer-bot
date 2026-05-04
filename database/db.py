# ──────────────────────────────────────────────────────────────────────────────
# database/db.py
# Async SQLite database layer using aiosqlite.
# Call init_db() once at startup to create all tables.
# ──────────────────────────────────────────────────────────────────────────────

import aiosqlite
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "buzzer.db")


async def get_db() -> aiosqlite.Connection:
    """Opens and returns an aiosqlite connection with row factory enabled."""
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    return db


async def init_db():
    """Creates all required tables if they do not already exist."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        # ── Users: XP, level, role, cooldowns ─────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id     TEXT NOT NULL,
                guild_id    TEXT NOT NULL,
                xp          INTEGER DEFAULT 0,
                level       INTEGER DEFAULT 0,
                role        TEXT    DEFAULT 'member',  -- 'owner'|'admin'|'member'
                last_xp_at  REAL    DEFAULT NULL,       -- Unix timestamp (seconds)
                warn_count  INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, guild_id)
            )
        """)

        # ── Tasks ──────────────────────────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                task_id           TEXT PRIMARY KEY,
                guild_id          TEXT NOT NULL,
                title             TEXT NOT NULL,
                assigned_to       TEXT NOT NULL,         -- user_id
                assigned_by       TEXT NOT NULL,         -- user_id
                due_date          REAL NOT NULL,         -- Unix timestamp (seconds)
                reminder_interval REAL NOT NULL,         -- seconds
                next_reminder     REAL NOT NULL,         -- Unix timestamp (seconds)
                reminder_count    INTEGER DEFAULT 0,
                escalated         INTEGER DEFAULT 0,     -- 0|1 boolean
                status            TEXT    DEFAULT 'pending', -- 'pending'|'completed'|'overdue'
                proof             TEXT    DEFAULT NULL,
                completed_at      REAL    DEFAULT NULL,
                last_update       TEXT    DEFAULT NULL
            )
        """)

        # ── Moderation log ─────────────────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS mod_logs (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id      TEXT NOT NULL,
                action        TEXT NOT NULL,
                moderator_id  TEXT NOT NULL,
                target_id     TEXT NOT NULL,
                reason        TEXT DEFAULT 'No reason provided.',
                extra         TEXT DEFAULT NULL,         -- JSON string for extra fields
                created_at    REAL DEFAULT (unixepoch('now'))
            )
        """)

        await db.commit()
