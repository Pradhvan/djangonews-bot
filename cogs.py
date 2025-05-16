import asyncio
import json

import aiofiles
import aiosqlite
import arrow
from discord.ext import commands


class VolunteerCog(commands.Cog):
    def __init__(self, bot, cursor):
        self.bot = bot
        self.cursor = cursor

    @staticmethod
    def _is_date_correct(m):
        try:
            arrow.get(m.content.strip(), "YYYY-MM-DD")
            return True
        except arrow.parser.ParserMatchError:
            return False

    @staticmethod
    async def _list_available_dates(conn: aiosqlite.Connection) -> str | None:
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
        # Add Pagination here so user can see all the dates.
        return "\n".join(
            f"- {arrow.get(row[0]).format('Do MMMM YYYY')}" for row in rows
        )

    @commands.command(name="available")
    async def available(self, ctx):
        response = await VolunteerCog._list_available_dates(self.cursor)
        await ctx.send(response or "No available dates found.")

    @staticmethod
    async def _update_volunteer_status(
        conn: aiosqlite.Connection, date: str, name: str, is_taken: int
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
                "message", check=VolunteerCog._is_date_correct, timeout=60
            )
            date = arrow.get(response.content.strip(), "YYYY-MM-DD").format(
                "YYYY-MM-DD"
            )
            is_taken = 1 if action == "assign" else 0

            updated = await VolunteerCog._update_volunteer_status(
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

    @commands.command(name="mydates")
    async def get_user_assigned_dates(self, ctx):
        async with self.cursor.execute(
            """
            SELECT due_date, status
            FROM volunteers
            WHERE name = ?
            """,
            (ctx.author.name,),
        ) as cursor:
            rows = await cursor.fetchall()

        if not rows:
            await ctx.send("You have no assigned dates.")
            return

        messages = []
        for due_date, status in rows:
            date_str = arrow.get(due_date).format("Do MMM YYYY")
            messages.append(f"Date: `{date_str}`\nStatus: `{status}`")

        output = "\n\n".join(messages)
        await ctx.send(output)

    @commands.command(name="status")
    async def get_date_status(self, ctx):
        current_date = arrow.utcnow().format("YYYY-MM-DD")
        async with self.cursor.execute(
            """
            SELECT due_date, status, name
            FROM volunteers
            WHERE due_date >= ? AND is_taken = 1
            """,
            (current_date,),
        ) as cursor:
            rows = await cursor.fetchall()
        if not rows:
            await ctx.send("No upcoming dates has been assigned.")
            return
        messages = []
        for due_date, status, name in rows:
            date_str = arrow.get(due_date).format("Do MMM YYYY")
            messages.append(
                f"Date: `{date_str}`\nStatus: `{status}`\nTaken By: `{name}`"
            )
        output = "\n\n".join(messages)
        await ctx.send(output)

    @staticmethod
    async def _format_report(data):
        total_prs = data.get("total_prs", 0)
        contributors = len(set(pr["author"] for pr in data["prs"]))
        first_timers = data.get("first_time_contributors", [])
        modifying_prs = [pr for pr in data["prs"] if pr["modifies_release"]]

        first_timer_msg = ""
        if first_timers:
            first_timer_msg = f"\n🎉 {len(first_timers)} first-time contributor."

        summary = (
            f"✅ {total_prs} pull requests were merged by {contributors} contributors."
            f"{first_timer_msg}"
        )

        if modifying_prs:
            summary += (
                f"\n📦 {len(modifying_prs)} PRs updated the release notes or docs:"
            )
            for pr in modifying_prs:
                summary += f"\n🦄 [{pr['title']}](<{pr['url']}>)"

        return summary

    @commands.command(name="report")
    async def report(self, ctx):
        filename = await self.bot.generate_pr_summary()
        async with aiofiles.open(filename, mode="r") as f:
            contents = await f.read()
            pr_data = json.loads(contents)
        short_summary = await VolunteerCog._format_report(pr_data)
        last_week = pr_data["date_range_humanized"]
        discord_summary = await self.bot.disable_link_previews(pr_data["synopsis"])
        await ctx.send(f"📢 **Django Weekly Summary ({last_week})**")
        await ctx.send(f"{short_summary}")
        await ctx.send(f"🧑‍💻 **Synopsis**\n{discord_summary}")
