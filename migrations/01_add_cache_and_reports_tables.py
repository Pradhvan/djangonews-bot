"""
Migration 01: Add cache and weekly reports tables

This migration adds:
- cache_entries table for storing cached data (like Django welcome message)
- weekly_reports table for storing weekly PR reports with auto-cleanup
"""


async def check_migration_needed(conn):
    """Check if this migration is needed"""
    migrations_needed = []

    # Check if cache_entries table exists
    async with conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='cache_entries'"
    ) as cursor:
        if not await cursor.fetchone():
            migrations_needed.append("Create cache_entries table")

    # Check if weekly_reports table exists
    async with conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='weekly_reports'"
    ) as cursor:
        if not await cursor.fetchone():
            migrations_needed.append("Create weekly_reports table")

    return migrations_needed


async def apply_migration(conn):
    """Apply this migration"""
    print("📝 Applying Migration 01: Add cache and weekly reports tables")

    # Create cache_entries table
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cache_entries (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            commit_sha TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    )
    print("  ✅ Created cache_entries table")

    # Create weekly_reports table
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS weekly_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start_date DATE NOT NULL,
            end_date DATE NOT NULL,
            total_prs INTEGER,
            first_time_contributors_count INTEGER,
            synopsis TEXT,
            date_range_humanized TEXT,
            pr_data JSON,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(start_date, end_date)
        )
    """
    )
    print("  ✅ Created weekly_reports table")

    # Create indexes for better performance
    await conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_cache_entries_key
        ON cache_entries(key)
    """
    )

    await conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_weekly_reports_dates
        ON weekly_reports(start_date, end_date)
    """
    )

    await conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_weekly_reports_created
        ON weekly_reports(created_at)
    """
    )
    print("  ✅ Created indexes for new tables")

    await conn.commit()
    print("✅ Migration 01 completed successfully!")


# Migration metadata
MIGRATION_ID = "01"
MIGRATION_NAME = "add_cache_and_reports_tables"
MIGRATION_DESCRIPTION = (
    "Add cache_entries and weekly_reports tables for better data management"
)
