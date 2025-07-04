"""
Migration 02: Add bot state tracking table

This migration adds:
- bot_state table for tracking persistent bot state (current placeholder thread, etc.)
"""


async def check_migration_needed(conn):
    """Check if this migration is needed"""
    migrations_needed = []

    # Check if bot_state table exists
    async with conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='bot_state'"
    ) as cursor:
        if not await cursor.fetchone():
            migrations_needed.append("Create bot_state table")

    return migrations_needed


async def apply_migration(conn):
    """Apply this migration"""
    print("📝 Applying Migration 02: Add bot state tracking table")

    # Create bot_state table
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS bot_state (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    )
    print("  ✅ Created bot_state table")

    await conn.commit()
    print("✅ Migration 02 completed successfully!")


# Migration metadata
MIGRATION_ID = "02"
MIGRATION_NAME = "add_bot_state_table"
MIGRATION_DESCRIPTION = "Add bot_state table for tracking persistent bot state"
