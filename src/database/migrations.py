"""
Database migration utilities for Django News Bot
"""

import logging

import aiosqlite


async def migrate_database(db_path: str):
    """
    Run database migrations to add new columns for profile functionality
    """
    logger = logging.getLogger(__name__)

    async with aiosqlite.connect(db_path) as conn:
        migrations_needed = []

        # Check if new columns exist
        async with conn.execute("PRAGMA table_info(volunteers)") as cursor:
            columns = await cursor.fetchall()
            column_names = [col[1] for col in columns]

        # Check for each new column
        if "social_media_handle" not in column_names:
            migrations_needed.append(
                "ALTER TABLE volunteers ADD COLUMN social_media_handle TEXT"
            )

        if "preferred_reminder_time" not in column_names:
            migrations_needed.append(
                "ALTER TABLE volunteers ADD COLUMN preferred_reminder_time TEXT DEFAULT '09:00'"
            )

        if "volunteer_name" not in column_names:
            migrations_needed.append(
                "ALTER TABLE volunteers ADD COLUMN volunteer_name TEXT"
            )

        async with conn.execute("PRAGMA table_info(contributors)") as cursor:
            rows = await cursor.fetchall()

        if not rows:
            migrations_needed.append(
                "CREATE TABLE contributors (id INTEGER PRIMARY KEY AUTOINCREMENT login TEXT NOT NULL UNIQUE)"
            )

        # Run migrations
        if migrations_needed:
            logger.info("Running %s database migrations...", len(migrations_needed))

            for migration in migrations_needed:
                try:
                    await conn.execute(migration)
                    logger.info("Executed: %s", migration)
                except Exception as e:
                    logger.error("Migration failed: %s - %s", migration, e)
                    raise

            await conn.commit()
            logger.info("Database migrations completed successfully!")
        else:
            logger.info("No database migrations needed - schema is up to date")


async def create_indexes(db_path: str):
    """
    Create database indexes for better performance
    """
    logger = logging.getLogger(__name__)

    async with aiosqlite.connect(db_path) as conn:
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_volunteers_name ON volunteers(name)",
            "CREATE INDEX IF NOT EXISTS idx_volunteers_due_date ON volunteers(due_date)",
            "CREATE INDEX IF NOT EXISTS idx_volunteers_is_taken ON volunteers(is_taken)",
            "CREATE INDEX IF NOT EXISTS idx_volunteers_name_taken ON volunteers(name, is_taken)",
            "CREATE INDEX IF NOT EXISTS idx_contributors_login ON contributors(login)",
        ]

        for index_sql in indexes:
            try:
                await conn.execute(index_sql)
                logger.debug("Created index: %s", index_sql)
            except Exception as e:
                logger.error("Index creation failed: %s - %s", index_sql, e)

        await conn.commit()
        logger.info("Database indexes created successfully!")
