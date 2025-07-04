"""
Migration 00: Initial migration - profile columns and indexes

This migration handles the original column additions and indexes:
- social_media_handle column
- preferred_reminder_time column
- volunteer_name column
- Performance indexes
"""

from pathlib import Path


async def check_migration_needed(conn):
    """Check if this migration is needed"""
    migrations_needed = []

    # Check if new columns exist
    async with conn.execute("PRAGMA table_info(volunteers)") as cursor:
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]

    # Check for each new column
    if "social_media_handle" not in column_names:
        migrations_needed.append("Add social_media_handle column")

    if "preferred_reminder_time" not in column_names:
        migrations_needed.append("Add preferred_reminder_time column")

    if "volunteer_name" not in column_names:
        migrations_needed.append("Add volunteer_name column")

    return migrations_needed


async def setup_initial_database_if_missing(conn):
    """Create initial database from schema if it doesn't exist"""
    # Check if volunteers table exists
    async with conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='volunteers'"
    ) as cursor:
        if await cursor.fetchone():
            return  # Table exists, no need to create

    print("🔧 Setting up initial database schema...")

    # Read schema - go up two levels from migrations/ to root
    schema_path = Path(__file__).parent.parent / "schema.sql"
    if not schema_path.exists():
        raise FileNotFoundError(f"❌ Schema file not found: {schema_path}")

    with open(schema_path, "r") as f:
        schema = f.read()

    await conn.executescript(schema)
    await conn.commit()
    print("✅ Initial database schema created")


async def apply_migration(conn):
    """Apply this migration"""
    print("📝 Applying Migration 00: Initial profile columns and indexes")

    # Check if new columns exist
    async with conn.execute("PRAGMA table_info(volunteers)") as cursor:
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]

    migrations = []

    # Check for each new column
    if "social_media_handle" not in column_names:
        migrations.append("ALTER TABLE volunteers ADD COLUMN social_media_handle TEXT")

    if "preferred_reminder_time" not in column_names:
        migrations.append(
            "ALTER TABLE volunteers ADD COLUMN preferred_reminder_time TEXT DEFAULT '09:00'"
        )

    if "volunteer_name" not in column_names:
        migrations.append("ALTER TABLE volunteers ADD COLUMN volunteer_name TEXT")

    # Run column migrations
    if migrations:
        print(f"  📝 Adding {len(migrations)} new columns...")

        for i, migration in enumerate(migrations, 1):
            try:
                await conn.execute(migration)
                print(f"    {i}. ✅ {migration}")
            except Exception as e:
                print(f"    {i}. ❌ {migration}")
                print(f"       Error: {e}")
                raise

        await conn.commit()
        print("  ✅ Column additions completed!")
    else:
        print("  ✅ All columns already exist")

    # Create indexes for performance
    print("  🔄 Creating database indexes...")

    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_volunteers_name ON volunteers(name)",
        "CREATE INDEX IF NOT EXISTS idx_volunteers_due_date ON volunteers(due_date)",
        "CREATE INDEX IF NOT EXISTS idx_volunteers_is_taken ON volunteers(is_taken)",
        "CREATE INDEX IF NOT EXISTS idx_volunteers_name_taken ON volunteers(name, is_taken)",
    ]

    for i, index_sql in enumerate(indexes, 1):
        try:
            await conn.execute(index_sql)
            index_name = index_sql.split("idx_")[1].split(" ")[0]
            print(f"    {i}. ✅ Created index: {index_name}")
        except Exception as e:
            print(f"    {i}. ❌ Index creation failed: {e}")

    await conn.commit()
    print("✅ Migration 00 completed successfully!")


# Migration metadata
MIGRATION_ID = "00"
MIGRATION_NAME = "initial_migration"
MIGRATION_DESCRIPTION = (
    "Add profile columns and performance indexes to volunteers table"
)
