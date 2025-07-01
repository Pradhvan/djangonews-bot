import logging
import os
import re

import aiofiles
import aiosqlite
import arrow
import discord
from discord.ext import commands
from dotenv import load_dotenv

from cogs import VolunteerCog
from summary import fetch_django_pr_summary, get_django_welcome_message

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

    @staticmethod
    async def generate_pr_summary():
        # Get last week's date range using Arrow's span feature
        last_week = arrow.utcnow().shift(weeks=-1)
        last_monday, last_sunday = last_week.span("week")

        # Format dates for filename and API calls
        start_date = last_monday.format("YYYY-MM-DD")
        end_date = last_sunday.format("YYYY-MM-DD")
        filename = f"{start_date}-{end_date}_pr.json"

        if not os.path.exists(filename):
            fetch_django_pr_summary(
                start_date=start_date, end_date=end_date, filename=filename
            )
        return filename

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

    @staticmethod
    async def _setup_database(db_file_path: str):
        created = not os.path.exists(db_file_path)

        async with aiosqlite.connect(db_file_path) as conn:
            if created:
                schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
                async with aiofiles.open(schema_path, "r") as f:
                    await conn.executescript(await f.read())

                now = arrow.utcnow().floor("month")
                end = arrow.utcnow().ceil("year")
                current = now

                while current <= end:
                    monday = current.shift(weekday=0)
                    wednesday = monday.shift(days=2)
                    await conn.execute(
                        """INSERT INTO volunteers (reminder_date, due_date) VALUES (?, ?)""",
                        (monday.format("YYYY-MM-DD"), wednesday.format("YYYY-MM-DD")),
                    )
                    current = current.shift(weeks=1)
                await conn.commit()

    async def setup_hook(self):
        # Get and cache Django's welcome message
        welcome_phrases = get_django_welcome_message()

        if not welcome_phrases:
            # log these
            print("Cannot fetch Django welcome message")
            print("Check GitHub CLI authentication and network connectivity")

        # Store it as an instance variable for summary.py to use
        self.django_welcome_phrases = welcome_phrases

        await VolunteerBot.generate_pr_summary()
        await VolunteerBot._setup_database(self.db_path)
        self.cursor = await aiosqlite.connect(self.db_path)
        await self.add_cog(VolunteerCog(self, self.cursor))

    async def on_ready(self):
        print(f"Bot connected as {self.user}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    bot = VolunteerBot()
    bot.run(TOKEN)
