"""
Volunteer management commands - !volunteer, !unvolunteer, !available, !mydates, !status
"""

import asyncio
import sys
from pathlib import Path

import aiosqlite
import arrow
import discord
from discord.ext import commands

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ui import DatePickerView, UserDatesView, generate_date_list


class VolunteerCog(commands.Cog):
    """Commands for managing volunteer assignments"""

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
        return "\\n".join(
            f"- {arrow.get(row[0]).format('Do MMMM YYYY')}" for row in rows
        )

    @staticmethod
    async def _get_next_available_date(conn: aiosqlite.Connection) -> str | None:
        """Returns the next available date (the closer with is_taken = 0)."""
        current_date = arrow.utcnow().format("YYYY-MM-DD")

        async with conn.execute(
            """
            SELECT due_date
            FROM volunteers
            WHERE due_date > ? AND is_taken = 0
            ORDER BY due_date ASC
            LIMIT 1
            """,
            (current_date,),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

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

    @staticmethod
    async def get_user_first_assigned_date(conn: aiosqlite.Connection, ctx):
        """Return the next assigned date to the user."""
        async with conn.execute(
            """
            SELECT due_date
            FROM volunteers
            WHERE name = ? and is_taken = 1
            ORDER BY due_date ASC
            LIMIT 1
            """,
            (ctx.author.display_name,),
        ) as cursor:
            row = await cursor.fetchone()

        return row[0] if row else None

    async def _handle_volunteer_action(
        self,
        ctx,
        action: str,  # "assign" or "unassign"
        success_msg: str,
        failure_msg: str,
        date: str = None,
        post_success_note: str = "",
    ):
        if not date:
            await ctx.send("Please provide a date in the format YYYY-MM-DD.")
            try:
                response = await self.bot.wait_for(
                    "message", check=VolunteerCog._is_date_correct, timeout=60
                )
                date = arrow.get(response.content.strip(), "YYYY-MM-DD").format(
                    "YYYY-MM-DD"
                )

            except asyncio.TimeoutError:
                await ctx.send("You took too long. Please try again.")

        is_taken = 1 if action == "assign" else 0

        updated = await VolunteerCog._update_volunteer_status(
            self.cursor, date, ctx.author.display_name, is_taken
        )

        if updated:
            await ctx.send(success_msg.format(date=date))
            if post_success_note:
                await ctx.send(post_success_note)
        else:
            await ctx.send(failure_msg)

    async def _get_available_dates_list(self):
        """Get list of available dates"""
        current_date = arrow.utcnow().format("YYYY-MM-DD")
        async with self.cursor.execute(
            """
            SELECT due_date
            FROM volunteers
            WHERE due_date > ? AND is_taken = 0
            ORDER BY due_date ASC
            """,
            (current_date,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

    async def _get_user_dates_with_status(self, user_name):
        """Get user's assigned dates with status"""
        async with self.cursor.execute(
            """
            SELECT due_date, status
            FROM volunteers
            WHERE name = ? AND is_taken = 1
            ORDER BY due_date ASC
            """,
            (user_name,),
        ) as cursor:
            return await cursor.fetchall()

    # ===== COMMANDS =====

    @commands.command(name="available")
    async def available(self, ctx):
        """List available volunteer dates"""
        response = await VolunteerCog._list_available_dates(self.cursor)
        await ctx.send(response or "No available dates found.")

    @commands.command(name="volunteer")
    async def volunteer(self, ctx, option: str = None):
        """Volunteer for a date - shows interactive date picker"""
        await self._show_volunteer_picker(ctx)

    async def _show_volunteer_picker(self, ctx):
        """Show interactive date picker for volunteering"""
        picker_view = DatePickerView(self.cursor, action="assign")
        await picker_view.setup_options()

        available_dates = await self._get_available_dates_list()

        if not available_dates:
            await ctx.send(
                "📅 **No Available Dates**\\n"
                "There are currently no volunteer dates available. "
                "Check back later or contact an admin."
            )
            return

        preview = generate_date_list(available_dates, limit=5)

        if len(preview) > 3500:
            preview = generate_date_list(available_dates, limit=3)

        if len(available_dates) > 5:
            preview += f"\\n\\n📝 *Use the dropdown below to see all {len(available_dates)} available dates*"

        embed = discord.Embed(
            title="📅 Volunteer for Django News",
            description=preview,
            color=0x0C4B33,
        )
        embed.set_footer(text="📝 Select a date from the dropdown below to volunteer!")

        await ctx.send(embed=embed, view=picker_view)

    @commands.command(name="unvolunteer")
    async def unvolunteer(self, ctx, option: str = None):
        """Unvolunteer from a date - shows interactive picker"""

        if option and option.lower() == "next":
            next_date = await VolunteerCog.get_user_first_assigned_date(
                self.cursor, ctx
            )
            if not next_date:
                await ctx.send("📅 You don't have any assigned dates.")
                return

            await self._handle_volunteer_action(
                ctx,
                action="unassign",
                success_msg="You have been unassigned from {date}.",
                failure_msg="Could not unassign you. Try again.",
                post_success_note="Please inform folks on django-news channel so others can pick it up.",
                date=next_date,
            )
        elif option and option.lower() == "list":
            await self._show_user_dates_list(ctx)
        else:
            await self._show_unvolunteer_picker(ctx)

    async def _show_unvolunteer_picker(self, ctx):
        """Show interactive date picker for unvolunteering"""
        user_name = ctx.author.display_name

        user_dates_view = UserDatesView(self.cursor, user_name)
        await user_dates_view.setup_options()

        user_dates = await self._get_user_dates_with_status(user_name)

        if not user_dates:
            await ctx.send(
                "📅 **No Assigned Dates**\\n"
                "You currently have no volunteer assignments. "
                "Use `!volunteer` to sign up for dates!"
            )
            return

        from ui.calendar_view import generate_user_date_summary

        preview = generate_user_date_summary(user_dates)

        embed = discord.Embed(
            title="📅 Unvolunteer from Django News",
            description=preview,
            color=0xE74C3C,
        )
        embed.add_field(
            name="📝 Quick Options",
            value="• `!unvolunteer next` - Remove next assignment\\n"
            "• `!unvolunteer list` - Show text list\\n"
            "• `!mydates` - View all your dates",
            inline=False,
        )
        embed.set_footer(
            text="📝 Select a date from the dropdown below to unvolunteer!"
        )

        await ctx.send(embed=embed, view=user_dates_view)

    async def _show_user_dates_list(self, ctx):
        """Show text list of user's assigned dates"""
        user_name = ctx.author.display_name
        user_dates = await self._get_user_dates_with_status(user_name)

        if not user_dates:
            await ctx.send("📅 You have no assigned dates.")
            return

        from ui.calendar_view import generate_user_date_summary

        summary = generate_user_date_summary(user_dates)
        await ctx.send(summary)

    @commands.command(name="mydates")
    async def get_user_assigned_dates(self, ctx):
        """Show your assigned volunteer dates with enhanced UI"""
        user_name = ctx.author.display_name
        user_dates = await self._get_user_dates_with_status(user_name)

        if not user_dates:
            embed = discord.Embed(
                title="📅 Your Django News Assignments",
                description="You currently have no volunteer assignments.\\n\\n"
                "💡 **Get started:** Use `!volunteer` to sign up for dates!",
                color=0x95A5A6,
            )
            embed.add_field(
                name="📝 Available Commands",
                value="• `!volunteer` - Sign up for dates\\n"
                "• `!available` - See available dates\\n"
                "• `!status` - View all assignments",
                inline=False,
            )
            await ctx.send(embed=embed)
            return

        from ui.calendar_view import generate_user_date_summary

        summary = generate_user_date_summary(user_dates)

        embed = discord.Embed(
            title="📅 Your Django News Assignments",
            description=summary,
            color=0x0C4B33,
        )

        embed.add_field(
            name="📝 Quick Actions",
            value="• `!unvolunteer` - Remove assignments\\n"
            "• `!volunteer` - Add more dates\\n"
            "• `!settimezone` - Update timezone",
            inline=False,
        )

        next_assignment = min(user_dates, key=lambda x: x[0])
        next_date = arrow.get(next_assignment[0]).format("dddd, MMMM Do YYYY")
        days_until = (arrow.get(next_assignment[0]) - arrow.utcnow()).days

        if days_until >= 0:
            urgency_msg = f"Next assignment: **{next_date}** ({days_until} days)"
        else:
            urgency_msg = (
                f"Overdue assignment: **{next_date}** ({abs(days_until)} days ago)"
            )

        embed.set_footer(text=urgency_msg)
        await ctx.send(embed=embed)

    @commands.command(name="status")
    async def get_date_status(self, ctx):
        """Show status of all volunteer assignments"""
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
                f"Date: `{date_str}`\\nStatus: `{status}`\\nTaken By: `{name}`"
            )
        output = "\\n\\n".join(messages)
        await ctx.send(output)


async def setup(bot):
    """Setup function for loading the cog"""
    cursor = getattr(bot, "cursor", None)
    if cursor is None:
        raise RuntimeError("Bot cursor not available")
    await bot.add_cog(VolunteerCog(bot, cursor))
