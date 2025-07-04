import logging
import os
import re
import sys
from pathlib import Path

import aiofiles
import aiosqlite
import arrow
import discord
from discord.ext import commands
from dotenv import load_dotenv

# Add src directory to path for new imports
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from src.bot.cogs.automation import AutomationCog
from src.bot.cogs.profile import ProfileCog
from src.bot.cogs.reporting import ReportingCog
from src.bot.cogs.volunteer import VolunteerCog
from src.utils.github import fetch_django_pr_summary, get_django_welcome_message

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE = os.getenv("DATABASE")


class VolunteerBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        self.cursor = None
        self.django_welcome_phrases = None
        self.db_path = os.path.join(os.path.dirname(__file__), DATABASE)

    async def generate_pr_summary(self):
        """Generate weekly PR summary and store in database"""
        # Get last week's date range using Arrow's span feature
        last_week = arrow.utcnow().shift(weeks=-1)
        last_monday, last_sunday = last_week.span("week")

        # Format dates for API calls
        start_date = last_monday.format("YYYY-MM-DD")
        end_date = last_sunday.format("YYYY-MM-DD")

        # Check if we already have this week's report
        async with aiosqlite.connect(self.db_path) as conn:
            async with conn.execute(
                "SELECT id FROM weekly_reports WHERE start_date = ? AND end_date = ?",
                (start_date, end_date),
            ) as cursor:
                existing_report = await cursor.fetchone()

            if not existing_report:
                # Generate new report and save to database
                print(f"📊 Generating new weekly report for {start_date} to {end_date}")
                await fetch_django_pr_summary(conn, start_date, end_date)
            else:
                print(f"📊 Weekly report already exists for {start_date} to {end_date}")

    @staticmethod
    async def disable_link_previews(text: str) -> str:
        """
        Converts all markdown links in the given text from:
        [text](https://example.com)
        to:
        [text](<https://example.com>)
        which disables Discord's link preview.
        """
        return re.sub(r"\[(.*?)\]\((https?://.*?)\)", r"[\1](<\2>)", text)

    async def _check_database_setup(self):
        """Check if database exists and is properly set up"""
        if not os.path.exists(self.db_path):
            print("❌ Database not found!")
            print(f"   Expected: {self.db_path}")
            print("   Creating initial database from schema...")

            # Create initial database from schema
            await self._create_initial_database()
            return True

        # Check if migrations are needed
        async with aiosqlite.connect(self.db_path) as conn:
            # Check volunteers table columns
            async with conn.execute("PRAGMA table_info(volunteers)") as cursor:
                columns = await cursor.fetchall()
                column_names = [col[1] for col in columns]

            missing_columns = []
            required_columns = [
                "social_media_handle",
                "preferred_reminder_time",
                "volunteer_name",
            ]

            for col in required_columns:
                if col not in column_names:
                    missing_columns.append(col)

            # Check for new tables
            missing_tables = []
            required_tables = ["cache_entries", "weekly_reports"]

            for table in required_tables:
                async with conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (table,),
                ) as cursor:
                    if not await cursor.fetchone():
                        missing_tables.append(table)

            if missing_columns or missing_tables:
                print("⚠️  Database migrations needed!")
                if missing_columns:
                    print(f"   Missing columns: {', '.join(missing_columns)}")
                if missing_tables:
                    print(f"   Missing tables: {', '.join(missing_tables)}")
                print("   Run: python migrate.py")
                return False

        return True

    async def _create_initial_database(self):
        """Create initial database from schema.sql"""
        schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")

        if not os.path.exists(schema_path):
            print("❌ schema.sql not found!")
            print("   Run: python migrate.py")
            return False

        async with aiosqlite.connect(self.db_path) as conn:
            async with aiofiles.open(schema_path, "r") as f:
                schema_content = await f.read()
            await conn.executescript(schema_content)
            await conn.commit()
            print("✅ Initial database created from schema.sql")
        return True

    async def _setup_initial_volunteer_dates(self):
        """Set up initial volunteer dates if database is empty"""
        async with aiosqlite.connect(self.db_path) as conn:
            # Check if we already have volunteer dates
            async with conn.execute("SELECT COUNT(*) FROM volunteers") as cursor:
                count = (await cursor.fetchone())[0]

            if count == 0:
                print("📅 Setting up initial volunteer dates...")

                now = arrow.utcnow().floor("month")
                end = arrow.utcnow().ceil("year")
                current = now

                while current <= end:
                    monday = current.shift(weekday=0)
                    wednesday = monday.shift(days=2)
                    await conn.execute(
                        "INSERT INTO volunteers (reminder_date, due_date) VALUES (?, ?)",
                        (monday.format("YYYY-MM-DD"), wednesday.format("YYYY-MM-DD")),
                    )
                    current = current.shift(weeks=1)
                await conn.commit()
                print("✅ Initial volunteer dates created")

    async def setup_hook(self):
        """Bot setup - NO AUTO-MIGRATIONS"""
        print("🚀 Starting Django News Bot...")

        # Check database setup (don't auto-migrate!)
        if not await self._check_database_setup():
            print("❌ Bot startup failed - database not ready")
            print("   Please run: python migrate.py")
            return

        # Connect to database early for setup operations
        self.cursor = await aiosqlite.connect(self.db_path)

        # Get and cache Django's welcome message using database
        welcome_phrases = await get_django_welcome_message(self.cursor)
        if not welcome_phrases:
            print("⚠️  Cannot fetch Django welcome message")
            print("   Check GitHub CLI authentication and network connectivity")
        self.django_welcome_phrases = welcome_phrases

        # Generate PR summary (now stores in database)
        await self.generate_pr_summary()

        # Set up initial dates if needed
        await self._setup_initial_volunteer_dates()

        # Load cogs
        await self.add_cog(VolunteerCog(self, self.cursor))
        await self.add_cog(ProfileCog(self, self.cursor))
        await self.add_cog(ReportingCog(self, self.cursor))
        await self.add_cog(AutomationCog(self, self.cursor))

        print("✅ Bot setup completed successfully!")

    async def on_ready(self):
        print(f"🎉 Bot connected as {self.user}")
        print(f"📈 Connected to {len(self.guilds)} servers")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    bot = VolunteerBot()
    bot.run(TOKEN)
