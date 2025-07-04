#!/usr/bin/env python3
"""
Django News Bot Migration Runner

Usage:
    python migrate.py                    # Run all pending migrations
    python migrate.py --list             # List all available migrations
    python migrate.py --run 01           # Run specific migration
    python migrate.py --status           # Show migration status
"""

import asyncio
import importlib.util
import logging
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

import aiosqlite
from dotenv import load_dotenv


class MigrationRunner:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.migrations_dir = Path(__file__).parent / "migrations"

    async def backup_database(self) -> str:
        """Create a backup of the database before migrations"""
        if not os.path.exists(self.db_path):
            print(f"⚠️  Database {self.db_path} does not exist. No backup needed.")
            return ""

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"{self.db_path}.backup.{timestamp}"

        try:
            shutil.copy2(self.db_path, backup_path)
            print(f"✅ Database backed up to: {backup_path}")
            return backup_path
        except Exception as e:
            print(f"❌ Failed to backup database: {e}")
            raise

    @staticmethod
    async def ensure_migrations_table(conn):
        """Create migrations tracking table if it doesn't exist"""
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS applied_migrations (
                migration_id TEXT PRIMARY KEY,
                migration_name TEXT NOT NULL,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )
        await conn.commit()

    async def get_applied_migrations(self, conn) -> set:
        """Get list of already applied migrations"""
        await self.ensure_migrations_table(conn)

        async with conn.execute(
            "SELECT migration_id FROM applied_migrations"
        ) as cursor:
            rows = await cursor.fetchall()
            return {row[0] for row in rows}

    def discover_migrations(self) -> list:
        """Discover all migration files"""
        migrations = []

        for file_path in self.migrations_dir.glob("[0-9][0-9]_*.py"):
            migration_id = file_path.stem[:2]
            migration_name = file_path.stem[3:]
            migrations.append(
                {
                    "id": migration_id,
                    "name": migration_name,
                    "file": file_path,
                    "module_name": file_path.stem,
                }
            )

        return sorted(migrations, key=lambda x: x["id"])

    @staticmethod
    async def load_migration_module(migration_file):
        """Load a migration module dynamically"""
        spec = importlib.util.spec_from_file_location(
            "migration_module", migration_file
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    async def check_migration_needed(self, conn, migration):
        """Check if a specific migration is needed"""
        module = await self.load_migration_module(migration["file"])

        if hasattr(module, "check_migration_needed"):
            return await module.check_migration_needed(conn)
        return []

    async def apply_migration(self, conn, migration):
        """Apply a specific migration"""
        module = await self.load_migration_module(migration["file"])

        # Check if migration has setup_initial_database_if_missing (for migration 00)
        if hasattr(module, "setup_initial_database_if_missing"):
            await module.setup_initial_database_if_missing(conn)

        await module.apply_migration(conn)

        # Mark migration as applied
        await conn.execute(
            "INSERT OR REPLACE INTO applied_migrations (migration_id, migration_name) VALUES (?, ?)",
            (migration["id"], migration["name"]),
        )
        await conn.commit()

    async def run_migration(self, migration_id: str):
        """Run a specific migration"""
        migrations = self.discover_migrations()
        migration = next((m for m in migrations if m["id"] == migration_id), None)

        if not migration:
            print(f"❌ Migration {migration_id} not found")
            return False

        print(f"🚀 Running Migration {migration['id']}: {migration['name']}")
        print("=" * 60)

        try:
            # Backup database
            backup_path = await self.backup_database()

            async with aiosqlite.connect(self.db_path) as conn:
                applied = await self.get_applied_migrations(conn)

                if migration["id"] in applied:
                    print(f"⚠️  Migration {migration['id']} already applied")
                    return True

                await self.apply_migration(conn, migration)

            print("=" * 60)
            print("🎉 Migration completed successfully!")
            if backup_path:
                print(f"💾 Backup available at: {backup_path}")
            return True

        except Exception as e:
            print(f"❌ Migration failed: {e}")
            return False

    async def run_all_pending(self):
        """Run all pending migrations"""
        print("🚀 Django News Bot - Migration Runner")
        print("=" * 50)
        print(f"📂 Database: {self.db_path}")

        try:
            migrations = self.discover_migrations()

            if not migrations:
                print("📭 No migrations found")
                return True

            async with aiosqlite.connect(self.db_path) as conn:
                applied = await self.get_applied_migrations(conn)
                pending = [m for m in migrations if m["id"] not in applied]

                if not pending:
                    print("✅ All migrations already applied!")
                    return True

                print(f"📝 Found {len(pending)} pending migrations:")
                for migration in pending:
                    print(f"  • {migration['id']}: {migration['name']}")

                # Check what each migration will do
                print("\n🔍 Checking what needs to be done...")
                for migration in pending:
                    needed = await self.check_migration_needed(conn, migration)
                    if needed:
                        print(f"  {migration['id']}: {', '.join(needed)}")

                # Confirm with user
                response = (
                    input("\n🤔 Continue with migrations? [y/N]: ").strip().lower()
                )
                if response not in ["y", "yes"]:
                    print("❌ Migration cancelled by user")
                    return False

                # Backup database
                backup_path = await self.backup_database()

                # Run all pending migrations
                for migration in pending:
                    print(
                        f"\n🔄 Applying Migration {migration['id']}: {migration['name']}"
                    )
                    await self.apply_migration(conn, migration)

                print("\n" + "=" * 50)
                print("🎉 All migrations completed successfully!")
                if backup_path:
                    print(f"💾 Backup available at: {backup_path}")
                print("🚀 You can now start the bot safely!")
                return True

        except Exception as e:
            print(f"\n❌ Migration failed: {e}")
            print("⚠️  Bot startup may fail with current database state")
            return False

    async def list_migrations(self):
        """List all available migrations and their status"""
        migrations = self.discover_migrations()

        if not migrations:
            print("📭 No migrations found")
            return

        print("📋 Available Migrations:")
        print("=" * 50)

        try:
            async with aiosqlite.connect(self.db_path) as conn:
                applied = await self.get_applied_migrations(conn)

                for migration in migrations:
                    status = (
                        "✅ Applied" if migration["id"] in applied else "⏳ Pending"
                    )
                    print(f"{migration['id']}: {migration['name']} - {status}")

        except Exception as e:
            print("❌ Could not check migration status:", e)
            for migration in migrations:
                print(f"{migration['id']}: {migration['name']} - ❓ Unknown")

    async def show_status(self):
        """Show detailed migration status"""
        migrations = self.discover_migrations()

        print("📊 Migration Status Report")
        print("=" * 50)
        print(f"📂 Database: {self.db_path}")
        print(f"📁 Migrations directory: {self.migrations_dir}")
        print(f"🔢 Total migrations: {len(migrations)}")

        if not migrations:
            print("📭 No migrations found")
            return

        try:
            async with aiosqlite.connect(self.db_path) as conn:
                applied = await self.get_applied_migrations(conn)
                pending = [m for m in migrations if m["id"] not in applied]

                print(f"✅ Applied: {len(applied)}")
                print(f"⏳ Pending: {len(pending)}")

                if pending:
                    print("\n⏳ Pending migrations:")
                    for migration in pending:
                        print(f"  • {migration['id']}: {migration['name']}")

        except Exception as e:
            print(f"❌ Could not read migration status: {e}")


async def main():
    """Main entry point"""
    # Load environment
    load_dotenv()

    # Parse arguments
    args = sys.argv[1:]

    # Get database path
    db_path = os.getenv("DATABASE", "newsbot.db")
    if args and not args[0].startswith("--"):
        db_path = args[0]
        args = args[1:]

    runner = MigrationRunner(db_path)

    # Handle commands
    if "--list" in args:
        await runner.list_migrations()
    elif "--status" in args:
        await runner.show_status()
    elif "--run" in args:
        try:
            run_index = args.index("--run")
            migration_id = args[run_index + 1]
            success = await runner.run_migration(migration_id)
            sys.exit(0 if success else 1)
        except (IndexError, ValueError):
            print("❌ Usage: --run <migration_id>")
            sys.exit(1)
    else:
        # Run all pending migrations
        success = await runner.run_all_pending()
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # Run the migration
    asyncio.run(main())
