#!/usr/bin/env python3
"""
Manual database migration script for Django News Bot

Usage:
    python scripts/migrate.py [database_path]

This script should be run BEFORE starting the bot after any updates.
It will backup your database before applying migrations.
"""

import asyncio
import logging
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

import aiosqlite
from dotenv import load_dotenv

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


async def backup_database(db_path: str) -> str:
    """Create a backup of the database before migrations"""
    if not os.path.exists(db_path):
        print(f"⚠️  Database {db_path} does not exist. No backup needed.")
        return ""

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{db_path}.backup.{timestamp}"

    try:
        shutil.copy2(db_path, backup_path)
        print(f"✅ Database backed up to: {backup_path}")
        return backup_path
    except Exception as e:
        print(f"❌ Failed to backup database: {e}")
        raise


async def check_migrations_needed(db_path: str) -> list:
    """Check what migrations are needed"""
    if not os.path.exists(db_path):
        return ["Database does not exist - initial setup needed"]

    async with aiosqlite.connect(db_path) as conn:
        # Check if new columns exist
        async with conn.execute("PRAGMA table_info(volunteers)") as cursor:
            columns = await cursor.fetchall()
            column_names = [col[1] for col in columns]

        migrations_needed = []

        # Check for each new column
        if "social_media_handle" not in column_names:
            migrations_needed.append("Add social_media_handle column")

        if "preferred_reminder_time" not in column_names:
            migrations_needed.append("Add preferred_reminder_time column")

        if "volunteer_name" not in column_names:
            migrations_needed.append("Add volunteer_name column")

        return migrations_needed


async def migrate_database(db_path: str):
    """Run database migrations"""
    print(f"🔄 Running migrations on: {db_path}")

    async with aiosqlite.connect(db_path) as conn:
        # Check if new columns exist
        async with conn.execute("PRAGMA table_info(volunteers)") as cursor:
            columns = await cursor.fetchall()
            column_names = [col[1] for col in columns]

        migrations = []

        # Check for each new column
        if "social_media_handle" not in column_names:
            migrations.append(
                "ALTER TABLE volunteers ADD COLUMN social_media_handle TEXT"
            )

        if "preferred_reminder_time" not in column_names:
            migrations.append(
                "ALTER TABLE volunteers ADD COLUMN preferred_reminder_time TEXT DEFAULT '09:00'"
            )

        if "volunteer_name" not in column_names:
            migrations.append("ALTER TABLE volunteers ADD COLUMN volunteer_name TEXT")

        # Run migrations
        if migrations:
            print(f"📝 Applying {len(migrations)} migrations...")

            for i, migration in enumerate(migrations, 1):
                try:
                    await conn.execute(migration)
                    print(f"  {i}. ✅ {migration}")
                except Exception as e:
                    print(f"  {i}. ❌ {migration}")
                    print(f"     Error: {e}")
                    raise

            await conn.commit()
            print("✅ All migrations applied successfully!")
        else:
            print("✅ Database is up to date - no migrations needed")


async def create_indexes(db_path: str):
    """Create database indexes for better performance"""
    print("🔄 Creating database indexes...")

    async with aiosqlite.connect(db_path) as conn:
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
                print(f"  {i}. ✅ Created index: {index_name}")
            except Exception as e:
                print(f"  {i}. ❌ Index creation failed: {e}")

        await conn.commit()
        print("✅ Database indexes created successfully!")


async def setup_initial_database(db_path: str):
    """Create initial database if it doesn't exist"""
    print("🔧 Setting up initial database...")

    # Read schema
    schema_path = Path(__file__).parent.parent / "schema.sql"
    if not schema_path.exists():
        print(f"❌ Schema file not found: {schema_path}")
        return False

    async with aiosqlite.connect(db_path) as conn:
        with open(schema_path, "r") as f:
            schema = f.read()

        await conn.executescript(schema)
        await conn.commit()

        print("✅ Initial database schema created")
        return True


async def main():
    """Main migration script"""
    print("🚀 Django News Bot - Database Migration Tool")
    print("=" * 50)

    # Load environment
    load_dotenv()

    # Get database path
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    else:
        db_path = os.getenv("DATABASE", "newsbot.db")

    print(f"📂 Database: {db_path}")

    try:
        # Check if database exists
        if not os.path.exists(db_path):
            print("⚠️  Database does not exist. Creating initial setup...")
            await setup_initial_database(db_path)

        # Check what migrations are needed
        needed = await check_migrations_needed(db_path)

        if not needed:
            print("✅ Database is already up to date!")
            await create_indexes(db_path)
            return

        print("Migrations needed:")
        for migration in needed:
            print(f"  • {migration}")

        # Confirm with user
        response = input("\n🤔 Continue with migrations? [y/N]: ").strip().lower()
        if response not in ["y", "yes"]:
            print("❌ Migration cancelled by user")
            return

        # Backup database
        backup_path = await backup_database(db_path)

        # Run migrations
        await migrate_database(db_path)

        # Create indexes
        await create_indexes(db_path)

        print("\n" + "=" * 50)
        print("🎉 Migration completed successfully!")
        if backup_path:
            print(f"💾 Backup available at: {backup_path}")
        print("🚀 You can now start the bot safely!")

    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        print("⚠️  Bot startup may fail with current database state")
        sys.exit(1)


if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # Run the migration
    asyncio.run(main())
