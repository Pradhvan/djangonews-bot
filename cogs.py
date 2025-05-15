import asyncio

import aiosqlite
import arrow
from discord.ext import commands


class VolunteerCog(commands.Cog):
    def __init__(self, bot, cursor):
        self.bot = bot
        self.cursor = cursor

    def _is_date_correct(self, m):
        try:
            arrow.get(m.content.strip(), "YYYY-MM-DD")
            return True
        except arrow.parser.ParserMatchError:
            return False

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

    async def _update_volunteer_status(
        self, conn: aiosqlite.Connection, date: str, name: str, is_taken: int
    ) -> bool:
        query = """
            UPDATE volunteers
            SET 
                is_taken = ?, 
                name = CASE WHEN ? THEN ? ELSE name END
            WHERE 
                due_date = ? AND (? = 1 OR name = ?)"""
        async with conn.execute(
            query, (is_taken, is_taken, name, date, is_taken, name)
        ) as cursor:
            await conn.commit()
            return cursor.rowcount > 0

    async def _handle_volunteer_action(
        self,
        ctx,
        action: str,  # "assign" or "unassign"
        success_msg: str,
        failure_msg: str,
        post_success_note: str = "",
    ):
        await ctx.send("Please provide a date in the format YYYY-MM-DD.")
        try:
            response = await self.bot.wait_for(
                "message", check=self._is_date_correct, timeout=60
            )
            date = arrow.get(response.content.strip(), "YYYY-MM-DD").format(
                "YYYY-MM-DD"
            )
            is_taken = 1 if action == "assign" else 0

            updated = await self._update_volunteer_status(
                self.cursor, date, ctx.author.name, is_taken
            )

            if updated:
                await ctx.send(success_msg.format(date=date))
                if post_success_note:
                    await ctx.send(post_success_note)
            else:
                await ctx.send(failure_msg)
        except asyncio.TimeoutError:
            await ctx.send("You took too long. Please try again.")

    @commands.command(name="volunteer")
    async def volunteer(self, ctx):
        await self._handle_volunteer_action(
            ctx,
            action="assign",
            success_msg="You have been assigned to {date}.",
            failure_msg="Could not assign you. Try again.",
        )

    @commands.command(name="unvolunteer")
    async def unvolunteer(self, ctx):
        await self._handle_volunteer_action(
            ctx,
            action="unassign",
            success_msg="You have been unassigned from {date}.",
            failure_msg="Could not unassign you. Try again.",
            post_success_note="Please inform folks on django-news channel so others can pick it up.",
        )
