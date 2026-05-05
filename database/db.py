# ──────────────────────────────────────────────────────────────────────────────
# database/db.py
# Async PostgreSQL database layer using asyncpg + Neon.
#
# Uses a connection pool so every cog can safely acquire its own connection
# concurrently — no manual locking needed.
#
# Call init_db() once at startup; use get_db() as an async context manager.
# ──────────────────────────────────────────────────────────────────────────────

import asyncpg
import os
from contextlib import asynccontextmanager
from urllib.parse import urlparse, urlencode, urlunparse, parse_qs

_pool: asyncpg.Pool | None = None


def _clean_url(url: str) -> str:
    """
    Strip parameters that asyncpg doesn't recognise (e.g. channel_binding)
    and remove sslmode so we can pass ssl='require' explicitly.
    """
    parsed = urlparse(url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    for key in ('channel_binding', 'sslmode'):
        params.pop(key, None)
    new_query = urlencode({k: v[0] for k, v in params.items()})
    return urlunparse(parsed._replace(query=new_query))


async def init_db():
    """Opens the connection pool and creates all tables/indexes."""
    global _pool

    raw_url = os.environ.get('DATABASE_URL', '')
    if not raw_url:
        raise RuntimeError('DATABASE_URL environment variable is not set.')

    _pool = await asyncpg.create_pool(
        dsn=_clean_url(raw_url),
        ssl='require',
        min_size=1,
        max_size=10,
    )

    async with _pool.acquire() as conn:
        # ── Users ─────────────────────────────────────────────────────────────
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id     TEXT NOT NULL,
                guild_id    TEXT NOT NULL,
                xp          INTEGER          DEFAULT 0,
                level       INTEGER          DEFAULT 0,
                role        TEXT             DEFAULT 'member',
                last_xp_at  DOUBLE PRECISION DEFAULT NULL,
                warn_count  INTEGER          DEFAULT 0,
                PRIMARY KEY (user_id, guild_id)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_users_guild_xp
            ON users (guild_id, xp DESC)
        """)

        # ── Tasks ─────────────────────────────────────────────────────────────
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                task_id           TEXT             PRIMARY KEY,
                guild_id          TEXT             NOT NULL,
                title             TEXT             NOT NULL,
                assigned_to       TEXT             NOT NULL,
                assigned_by       TEXT             NOT NULL,
                due_date          DOUBLE PRECISION NOT NULL,
                reminder_interval DOUBLE PRECISION NOT NULL,
                next_reminder     DOUBLE PRECISION NOT NULL,
                reminder_count    INTEGER          DEFAULT 0,
                escalated         INTEGER          DEFAULT 0,
                status            TEXT             DEFAULT 'pending',
                proof             TEXT             DEFAULT NULL,
                completed_at      DOUBLE PRECISION DEFAULT NULL,
                last_update       TEXT             DEFAULT NULL
            )
        """)

        # ── Moderation log ────────────────────────────────────────────────────
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mod_logs (
                id            SERIAL           PRIMARY KEY,
                guild_id      TEXT             NOT NULL,
                action        TEXT             NOT NULL,
                moderator_id  TEXT             NOT NULL,
                target_id     TEXT             NOT NULL,
                reason        TEXT             DEFAULT 'No reason provided.',
                extra         TEXT             DEFAULT NULL,
                created_at    DOUBLE PRECISION DEFAULT extract(epoch from now())
            )
        """)


async def close_db():
    """Closes the connection pool gracefully (call on bot shutdown)."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


@asynccontextmanager
async def get_db():
    """
    Async context manager that acquires a connection from the pool.

    Usage:
        async with get_db() as db:
            await db.execute(...)
            row = await db.fetchrow(...)
    """
    if _pool is None:
        raise RuntimeError('Database not initialised — call await init_db() first.')
    async with _pool.acquire() as conn:
        yield conn
