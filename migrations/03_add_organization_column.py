"""
Migration 03: Add organization columns to volunteers table

This migration adds:
- organization column to volunteers table for storing optional organization information
- organization_link column for storing optional organization website URLs
"""


async def check_migration_needed(conn):
    """Check if this migration is needed"""
    migrations_needed = []

    # Check if organization columns exist in volunteers table
    async with conn.execute("PRAGMA table_info(volunteers)") as cursor:
        columns = [row[1] for row in await cursor.fetchall()]
        if "organization" not in columns:
            migrations_needed.append("Add organization column to volunteers table")
        if "organization_link" not in columns:
            migrations_needed.append("Add organization_link column to volunteers table")

    return migrations_needed


async def apply_migration(conn):
    """Apply this migration"""
    print("Applying Migration 03: Add organization columns to volunteers table")

    # Get current column names
    async with conn.execute("PRAGMA table_info(volunteers)") as cursor:
        columns = [row[1] for row in await cursor.fetchall()]

    if "organization" not in columns:
        await conn.execute("ALTER TABLE volunteers ADD COLUMN organization TEXT")
        print("Added organization column to volunteers table")

    if "organization_link" not in columns:
        await conn.execute("ALTER TABLE volunteers ADD COLUMN organization_link TEXT")
        print("Added organization_link column to volunteers table")

    await conn.commit()
    print("Migration 03 completed successfully!")


# Migration metadata
MIGRATION_ID = "03"
MIGRATION_NAME = "add_organization_columns"
MIGRATION_DESCRIPTION = "Add organization columns to volunteers table"
