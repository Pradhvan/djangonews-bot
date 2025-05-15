import logging
import os

import aiofiles
import aiosqlite
import arrow
import discord
from discord.ext import commands
from dotenv import load_dotenv

from cogs import VolunteerCog

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE = os.getenv("DATABASE")


class VolunteerBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        self.db_path = os.path.join(os.path.dirname(__file__), DATABASE)
        self.cursor = None

    async def setup_database(self, db_file_path: str):
        created = not os.path.exists(db_file_path)

        async with aiosqlite.connect(db_file_path) as conn:
            if created:
                schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
                async with aiofiles.open(schema_path, "r") as f:
                    await conn.executescript(f.read())

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
        await self.setup_database(self.db_path)
        self.cursor = await aiosqlite.connect(self.db_path)
        await self.add_cog(VolunteerCog(self, self.cursor))

    async def on_ready(self):
        print(f"Bot connected as {self.user}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    bot = VolunteerBot()
    bot.run(TOKEN)
