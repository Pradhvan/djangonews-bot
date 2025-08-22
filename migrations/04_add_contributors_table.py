"""
Migration 04: Create contributors table if not exists

This migration adds:
- contributors table to track people who have contributed PRs
"""


async def check_migration_needed(conn):
    """Check if this migration is needed"""
    migrations_needed = []

    # Check if bot_state table exists
    async with conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='contributors'"
    ) as cursor:
        if not await cursor.fetchone():
            migrations_needed.append("Create contributors table")

    return migrations_needed


async def apply_migration(conn):
    """Apply this migration"""
    print("Applying Migration 04: Create contributors table")

    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS contributors (
            id INTEGER PRIMARY KEY,
            login TEXT NOT NULL UNIQUE
        )
        """
    )
    print("Contributors table created")

    await conn.commit()
    print("Migration 04 completed successfully!")


# Migration metadata
MIGRATION_ID = "04"
MIGRATION_NAME = "create_contributors_table"
MIGRATION_DESCRIPTION = "Create contributors table if it does not exist"
