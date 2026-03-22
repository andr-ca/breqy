"""SQLite connection management with WAL mode."""

import aiosqlite


async def create_connection(db_path: str) -> aiosqlite.Connection:
    """Create a new SQLite connection with WAL mode and foreign keys enabled."""
    conn = await aiosqlite.connect(db_path)
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA foreign_keys=ON")
    await conn.execute("PRAGMA busy_timeout=5000")
    return conn
