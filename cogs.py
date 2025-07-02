import asyncio
import json
import logging
import os
import urllib.parse
import zoneinfo

import aiofiles
import aiosqlite
import arrow
import discord
from discord.ext import commands, tasks

from permissions import is_authorized_user
from summary import build_github_search_query
from views import TimezoneView


class VolunteerCog(commands.Cog):
    def __init__(self, bot, cursor):
        self.bot = bot
        self.cursor = cursor
        self.logger = logging.getLogger(__name__)

        # Weekly loop configuration - using environment variables
        self.forum_channel_id = os.getenv(
            "FORUM_CHANNEL_ID"
        )  # Forum channel ID from env
        self.placeholder_hour = int(
            os.getenv("PLACEHOLDER_CREATION_HOUR", "15")
        )  # Default to 3 PM UTC
        self.current_placeholder_thread = None

        if not self.forum_channel_id:
            self.logger.warning("FORUM_CHANNEL_ID not set in environment variables")

        self.logger.info("Placeholder creation time: %s:00 UTC", self.placeholder_hour)

    async def cog_load(self):
        """Start the weekly loop when cog loads"""
        self.logger.info("Starting weekly placeholder loop...")
        self.weekly_placeholder_loop.start()

    async def cog_unload(self):
        """Clean shutdown of the weekly loop"""
        self.weekly_placeholder_loop.cancel()

    def _get_next_monday_placeholder_time(self):
        """Calculate next Monday at the configured placeholder creation time"""
        now = arrow.utcnow()

        # Calculate days until next Monday
        days_until_monday = (7 - now.weekday()) % 7
        if days_until_monday == 0 and now.hour >= self.placeholder_hour:
            # Already past creation time on Monday, wait for next Monday
            days_until_monday = 7

        next_monday = now.shift(days=days_until_monday).replace(
            hour=self.placeholder_hour, minute=0, second=0, microsecond=0
        )

        return next_monday

    @tasks.loop(count=1)  # Run once, then reschedule itself
    async def weekly_placeholder_loop(self):
        """Lightweight weekly loop - runs once then reschedules itself"""
        try:
            # Calculate sleep time until next Monday at configured time
            next_monday = self._get_next_monday_placeholder_time()
            sleep_seconds = (next_monday - arrow.utcnow()).total_seconds()

            self.logger.info(
                "Sleeping until %s UTC (%.1f hours)",
                next_monday.format("YYYY-MM-DD HH:mm:ss"),
                sleep_seconds / 3600,
            )

            # Sleep until Monday
            await asyncio.sleep(sleep_seconds)

            # Execute Monday action
            await self._create_weekly_placeholder()

            # Clean up old placeholder from last week
            await self._cleanup_old_placeholder()

            # Reschedule for next week
            self.weekly_placeholder_loop.restart()

        except asyncio.CancelledError:
            self.logger.info("Weekly loop cancelled")
            raise
        except Exception as e:
            self.logger.error("Error in weekly loop: %s", e, exc_info=True)
            # Still reschedule even if there was an error
            await asyncio.sleep(3600)  # Wait 1 hour before retrying
            self.weekly_placeholder_loop.restart()

    async def _create_weekly_placeholder(self):
        """Create the weekly placeholder thread in a forum channel"""
        try:
            self.logger.info("Creating weekly placeholder thread in forum...")

            # Check if forum channel ID is configured
            if not self.forum_channel_id:
                self.logger.error("FORUM_CHANNEL_ID not configured in environment")
                return

            # Get forum channel by ID
            try:
                forum_channel = self.bot.get_channel(int(self.forum_channel_id))
                if not forum_channel:
                    # Try fetching if not in cache
                    forum_channel = await self.bot.fetch_channel(
                        int(self.forum_channel_id)
                    )
            except (ValueError, discord.NotFound):
                self.logger.error(
                    "Invalid or not found forum channel ID: %s", self.forum_channel_id
                )
                return

            # Verify it's a forum channel
            if not isinstance(forum_channel, discord.ForumChannel):
                self.logger.error(
                    "Channel %s is not a forum channel (type: %s)",
                    self.forum_channel_id,
                    type(forum_channel),
                )
                return

            # Generate thread name with date range
            last_week = arrow.utcnow().shift(weeks=-1)
            last_monday, last_sunday = last_week.span("week")
            start_date_str = last_monday.format("D,MMMM YYYY")
            end_date_str = last_sunday.format("D,MMMM YYYY")
            thread_name = f"Updates to Django from {start_date_str} to {end_date_str} [Placeholder]"

            # Generate content using existing report logic
            content = await self._generate_placeholder_content(last_monday, last_sunday)

            # Create forum post (thread)
            thread, _ = await forum_channel.create_thread(
                name=thread_name,
                content=content,
                reason="Weekly Django updates placeholder",
            )

            # Store reference for cleanup
            self.current_placeholder_thread = thread

            self.logger.info("Created forum post: %s (ID: %s)", thread_name, thread.id)

            # Add simple notification
            await thread.send(
                "📝 **Weekly Django News placeholder created!**\n"
                "This placeholder will be automatically deleted next Monday or earlier by a bot authorized user."
            )

        except Exception as e:
            self.logger.error(
                "Error creating placeholder forum post: %s", e, exc_info=True
            )

    async def _cleanup_old_placeholder(self):
        """Delete the previous week's placeholder thread"""
        try:
            if self.current_placeholder_thread:
                # Check if thread still exists and is not archived
                try:
                    if not self.current_placeholder_thread.archived:
                        await self.current_placeholder_thread.delete()
                        self.logger.info(
                            "Deleted old placeholder thread: %s",
                            self.current_placeholder_thread.name,
                        )
                    else:
                        self.logger.info(
                            "Old placeholder thread was already archived: %s",
                            self.current_placeholder_thread.name,
                        )

                except discord.NotFound:
                    self.logger.info("Old placeholder thread was already deleted")
                except discord.Forbidden:
                    self.logger.warning(
                        "Bot lacks permission to delete old placeholder thread"
                    )

        except Exception as e:
            self.logger.error("Error cleaning up old placeholder: %s", e)
        finally:
            # Clear the reference regardless
            self.current_placeholder_thread = None

    async def _generate_placeholder_content(self, last_monday, last_sunday):
        """Generate placeholder content using existing report logic"""
        try:
            # Reuse existing report generation
            filename = await self.bot.generate_pr_summary()
            async with aiofiles.open(filename, mode="r") as f:
                contents = await f.read()
                pr_data = json.loads(contents)

            start_date = last_monday.format("YYYY-MM-DD")
            end_date = last_sunday.format("YYYY-MM-DD")

            # Use the existing build_github_search_query function
            search_query = build_github_search_query(start_date, end_date)
            encoded_query = urllib.parse.quote_plus(search_query)
            search_url = f"https://github.com/search?q={encoded_query}"

            # Get the synopsis for the template
            discord_summary = await self.bot.disable_link_previews(pr_data["synopsis"])

            # Build the complete template
            content = (
                f'**Starting template for "Updates to Django" section**\n'
                f"```\n"
                f"Today 'Updates to Django' is presented by [your name here](your social or linkedin) from "
                f"the [Djangonaut Space](https://djangonaut.space/)!🚀\n\n"
                f"{discord_summary}"
                f"```"
                f"\n\n 🦄 [Weekly Pull Request Summary](<{search_url}>)"
            )

            return content

        except Exception as e:
            self.logger.error("Error generating placeholder content: %s", e)
            return (
                "Error generating template content. Please run `!report md` manually."
            )

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

    @commands.command(name="volunteer")
    async def volunteer(self, ctx, option: str = None):
        if option and option.lower() == "next":
            next_date = await VolunteerCog._get_next_available_date(self.cursor)
            if not next_date:
                await ctx.send("No available dates found.")
                return
            await self._handle_volunteer_action(
                ctx,
                action="assign",
                success_msg="You have been assigned to {date}.",
                failure_msg="Could not assign you to {date}. Try again.",
                date=next_date,
            )
        else:
            await self._handle_volunteer_action(
                ctx,
                action="assign",
                success_msg="You have been assigned to {date}.",
                failure_msg="Could not assign you. Try again.",
            )

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

    @commands.command(name="unvolunteer")
    async def unvolunteer(self, ctx, option: str = None):
        if option and option.lower() == "next":
            next_date = await VolunteerCog.get_user_first_assigned_date(
                self.cursor, ctx
            )
            if not next_date:
                await ctx.send("You don't have a shift yet.")
                return
            await self._handle_volunteer_action(
                ctx,
                action="unassign",
                success_msg="You have been unassigned to {date}.",
                failure_msg="Could not unassign you. Try again.",
                post_success_note="Please inform folks on django-news channel so others can pick it up.",
                date=next_date,
            )

        else:
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
            WHERE name = ? AND is_taken = 1
            """,
            (ctx.author.display_name,),
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
        contributors = len({pr["author"] for pr in data["prs"]})
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

    @staticmethod
    async def _format_list_prs(data):
        modifying_prs = [pr for pr in data["prs"] if pr["modifies_release"]]
        list_modifying_prs = "There are no PRs that modify the release."

        if modifying_prs:
            list_modifying_prs = ""
            for pr in modifying_prs:
                list_modifying_prs += f"\n🦄 [{pr['title']}](<{pr['url']}>)"

        return list_modifying_prs

    @commands.command(name="report")
    async def report(self, ctx, md: str = None):
        filename = await self.bot.generate_pr_summary()
        async with aiofiles.open(filename, mode="r") as f:
            contents = await f.read()
            pr_data = json.loads(contents)
        short_summary = await VolunteerCog._format_report(pr_data)
        list_modifiying_prs = await VolunteerCog._format_list_prs(pr_data)
        last_week = pr_data["date_range_humanized"]
        discord_summary = await self.bot.disable_link_previews(pr_data["synopsis"])
        if md and md.lower() == "md":
            await ctx.send(
                f"```Today 'Updates to Django' is presented by [your name her](your social or linkedin) from "
                f"the [Djangonaut Space](https://djangonaut.space/)!🚀"
                f"\n\n{discord_summary}```"
                f"\n{list_modifiying_prs}"
            )
        else:
            await ctx.send(f"📢 **Django Weekly Summary ({last_week})**")
            await ctx.send(f"{short_summary}")
            await ctx.send(f"🧑‍💻 **Synopsis**\n{discord_summary}")

    @commands.command(name="settimezone")
    async def set_timezone(self, ctx, *args):
        """
        Set a timezone from a list, or based on your input.
        """
        user_input = "_".join(args).lower()
        available_timezones = zoneinfo.available_timezones()
        cities_tz_id = {
            timezone.split("/")[-1].lower(): timezone
            for timezone in available_timezones
            if "/" in timezone
        }
        if not user_input:
            view = TimezoneView(self.cursor)
            await ctx.send("Select your timezone", view=view)
        elif user_input in cities_tz_id.keys():
            tz_identifier = cities_tz_id[user_input]
            user_name = ctx.author.display_name
            query = """
                        UPDATE volunteers
                        SET timezone = ?
                        WHERE name = ? AND is_taken = 1
                     """
            async with self.cursor.execute(query, (tz_identifier, user_name)) as cur:
                await self.cursor.commit()
                if cur.rowcount > 0:
                    await ctx.send(
                        f"Your timezone is set to **{tz_identifier}** ",
                    )
                else:
                    await ctx.send(
                        "Error: timezone not updated. Try to volunteer first. "
                    )

        else:
            await ctx.send(
                "Sorry, we don't support that timezone at the moment. \n"
                "Here is a list of timezones we [support](<https://gist.github.com/Pradhvan/9ce98c4feb25003100b81c496557eff1>)."
            )

    @commands.command(name="create_placeholder", hidden=True)
    @is_authorized_user()
    async def manual_placeholder(self, ctx):
        """Manual command to create placeholder (authorized users only)"""
        await self._create_weekly_placeholder()
        await ctx.send("✅ Placeholder thread created manually")

    @commands.command(name="delete_placeholder", hidden=True)
    @is_authorized_user()
    async def delete_placeholder(self, ctx):
        """Delete the current placeholder thread (authorized users only)"""
        try:
            if not self.current_placeholder_thread:
                await ctx.send(
                    "⚠️ No placeholder thread to delete (none currently tracked)"
                )
                return

            # Store thread info for confirmation message
            thread_name = self.current_placeholder_thread.name
            thread_id = self.current_placeholder_thread.id

            # Try to delete the thread
            try:
                # Check if thread is archived before trying to delete
                if self.current_placeholder_thread.archived:
                    await ctx.send(f"⚠️ Thread '{thread_name}' is already archived")
                    self.current_placeholder_thread = None
                    return

                # Delete the thread directly
                await self.current_placeholder_thread.delete()

                # Clear the reference
                self.current_placeholder_thread = None

                # Confirm deletion
                await ctx.send(f"✅ **Deleted placeholder thread:** {thread_name}")
                self.logger.info(
                    "Manually deleted placeholder thread: %s (ID: %s)",
                    thread_name,
                    thread_id,
                )

            except discord.NotFound:
                await ctx.send(f"⚠️ Thread '{thread_name}' was already deleted")
                self.current_placeholder_thread = None

            except discord.Forbidden:
                await ctx.send(
                    f"❌ **Permission denied!**\n"
                    f"Bot lacks permission to delete thread '{thread_name}'.\n"
                    f"Make sure the bot has 'Manage Threads' permission in the forum channel."
                )

        except Exception as e:
            await ctx.send(f"❌ **Error deleting placeholder:** {e}")
            self.logger.error(
                "Error in delete_placeholder command: %s", e, exc_info=True
            )

    @commands.command(name="placeholder_status", hidden=True)
    @is_authorized_user()
    async def placeholder_status(self, ctx):
        """Show current placeholder thread status (authorized users only)"""
        try:
            if not self.current_placeholder_thread:
                await ctx.send(
                    f"📝 **No placeholder currently tracked**\nℹ️ Next automatic placeholder will be created on Monday at {self.placeholder_hour}:00 UTC"
                )
                return

            # Get thread info
            thread_name = self.current_placeholder_thread.name
            thread_id = self.current_placeholder_thread.id
            thread_url = f"https://discord.com/channels/{ctx.guild.id}/{self.current_placeholder_thread.parent.id}/{thread_id}"

            # Check if thread still exists and get info
            try:
                if self.current_placeholder_thread.archived:
                    status = "📁 Archived"
                else:
                    status = "🟢 Active"

                # Get creation date
                created_at = self.current_placeholder_thread.created_at
                created_str = created_at.strftime("%Y-%m-%d %H:%M UTC")

                status_msg = (
                    f"📝 **Current Placeholder Status**\n"
                    f"🏷️ **Name:** {thread_name}\n"
                    f"🆔 **ID:** {thread_id}\n"
                    f"🟢 **Status:** {status}\n"
                    f"📅 **Created:** {created_str}\n"
                    f"🔗 **Link:** {thread_url}\n\n"
                    f"🔄 **Auto-deletion:** Next Monday at {self.placeholder_hour}:00 UTC"
                )

                await ctx.send(status_msg)

            except discord.NotFound:
                await ctx.send(
                    f"⚠️ **Tracked thread no longer exists:** {thread_name}\n🧽 Clearing reference..."
                )
                self.current_placeholder_thread = None

        except Exception as e:
            await ctx.send(f"❌ **Error checking placeholder status:** {e}")
            self.logger.error(
                "Error in placeholder_status command: %s", e, exc_info=True
            )
