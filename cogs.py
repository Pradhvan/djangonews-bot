# src/cogs/volunteer.py
import asyncio

import aiosqlite
import arrow
from discord.ext import commands


class VolunteerCog(commands.Cog):
    def __init__(self, bot, cursor):
        self.bot = bot
        self.cursor = cursor

    async def _list_available_dates(self, conn: aiosqlite.Connection) -> str | None:
        current_date = arrow.utcnow().format("YYYY-MM-DD")

        async with conn.execute(
            """
            SELECT due_date
            FROM volunteers
            WHERE due_date > ? AND is_taken = 0
            LIMIT 10
            """,
            (current_date,),
        ) as cursor:
            rows = await cursor.fetchall()

        if not rows:
            return None

        return "\n".join(
            f"- {arrow.get(row[0]).format('Do MMMM YYYY')}" for row in rows
        )

    @commands.command(name="available")
    async def available(self, ctx):
        response = await self._list_available_dates(self.cursor)
        await ctx.send(response or "No available dates found.")

    async def _assign_volunteer(
        self, conn: aiosqlite.Connection, date: str, name: str
    ) -> bool:
        async with conn.execute(
            "UPDATE volunteers SET is_taken = 1, name = ? WHERE due_date = ?",
            (name, date),
        ) as cursor:
            await conn.commit()
            return cursor.rowcount > 0

    @commands.command(name="volunteer")
    async def volunteer(self, ctx):
        await ctx.send("Please provide a date in the format YYYY-MM-DD.")

        def check_date(m):
            try:
                # Check if the message content can be parsed as a valid date
                arrow.get(m.content.strip(), "YYYY-MM-DD")
                return True
            except arrow.parser.ParserMatchError:
                return False

        try:
            response = await self.bot.wait_for("message", check=check_date, timeout=60)
            date = arrow.get(response.content.strip(), "YYYY-MM-DD").format(
                "YYYY-MM-DD"
            )
            assigned = await self._assign_volunteer(self.cursor, date, ctx.author.name)
            if assigned:
                await ctx.send(f"You have been assigned to {date}.")
            else:
                await ctx.send("Could not assign you. Try again.")
        except asyncio.TimeoutError:
            await ctx.send("You took too long. Please try again.")
