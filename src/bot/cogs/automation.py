"""
Automation and admin commands - weekly loops, placeholder creation
"""

import asyncio
import json
import logging
import os
import sys
import urllib.parse
from pathlib import Path

import arrow
import discord
from discord.ext import commands, tasks

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.github import build_github_search_query, get_latest_weekly_report
from utils.permissions import is_authorized_user


class AutomationCog(commands.Cog):
    """Background automation and admin commands"""

    def __init__(self, bot, cursor):
        self.bot = bot
        self.cursor = cursor
        self.logger = logging.getLogger(__name__)

        # Weekly loop configuration - using environment variables
        self.forum_channel_id = os.getenv("FORUM_CHANNEL_ID")
        self.placeholder_hour = int(os.getenv("PLACEHOLDER_CREATION_HOUR", "15"))
        self.current_placeholder_thread = None

        if not self.forum_channel_id:
            self.logger.warning("FORUM_CHANNEL_ID not set in environment variables")

        self.logger.info("Placeholder creation time: %s:00 UTC", self.placeholder_hour)

    async def cog_load(self):
        """Start the weekly loop when cog loads"""
        self.logger.info("Starting weekly placeholder loop...")

        # Restore placeholder thread reference from database
        await self._restore_placeholder_thread_from_db()

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

    async def _save_placeholder_state_to_db(
        self, thread_id: int, guild_id: int, channel_id: int, thread_name: str
    ):
        """Save current placeholder thread state to database"""
        try:
            placeholder_data = {
                "thread_id": thread_id,
                "guild_id": guild_id,
                "channel_id": channel_id,
                "thread_name": thread_name,
                "created_at": arrow.utcnow().isoformat(),
            }

            await self.cursor.execute(
                "INSERT OR REPLACE INTO bot_state (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
                ("current_placeholder_thread", json.dumps(placeholder_data)),
            )
            await self.cursor.commit()
            self.logger.info(
                "💾 Saved placeholder state to database: %s (ID: %s)",
                thread_name,
                thread_id,
            )
        except Exception as e:
            self.logger.error("❌ Failed to save placeholder state: %s", e)

    async def _restore_placeholder_thread_from_db(self):
        """Restore placeholder thread reference from database on startup"""
        try:
            async with self.cursor.execute(
                "SELECT value FROM bot_state WHERE key = ?",
                ("current_placeholder_thread",),
            ) as cursor:
                row = await cursor.fetchone()

            if not row:
                self.logger.info("📍 No placeholder thread state found in database")
                return

            placeholder_data = json.loads(row[0])
            thread_id = placeholder_data["thread_id"]
            guild_id = placeholder_data["guild_id"]
            thread_name = placeholder_data["thread_name"]
            created_at = placeholder_data.get("created_at", "unknown")

            self.logger.info(
                "🔄 Attempting to restore placeholder thread: %s (ID: %s)",
                thread_name,
                thread_id,
            )

            # Try to get the thread object
            try:
                guild = self.bot.get_guild(guild_id)
                if not guild:
                    guild = await self.bot.fetch_guild(guild_id)

                if guild:
                    # Try to fetch the thread
                    self.current_placeholder_thread = await guild.fetch_channel(
                        thread_id
                    )

                    if self.current_placeholder_thread:
                        self.logger.info(
                            "✅ Restored placeholder thread reference: %s (ID: %s)",
                            thread_name,
                            thread_id,
                        )
                        self.logger.info("   Created: %s", created_at)
                        self.logger.info(
                            "   Status: %s",
                            (
                                "Archived"
                                if self.current_placeholder_thread.archived
                                else "Active"
                            ),
                        )
                    else:
                        self.logger.warning(
                            "⚠️  Thread object is None for ID %s", thread_id
                        )
                        await self._clear_placeholder_state_from_db()
                else:
                    self.logger.warning(
                        "⚠️  Could not find guild %s to restore placeholder thread",
                        guild_id,
                    )
                    await self._clear_placeholder_state_from_db()

            except discord.NotFound:
                self.logger.warning(
                    "⚠️  Placeholder thread %s no longer exists - clearing state",
                    thread_id,
                )
                await self._clear_placeholder_state_from_db()
            except discord.Forbidden:
                self.logger.warning("⚠️  No permission to access thread %s", thread_id)
                await self._clear_placeholder_state_from_db()
            except Exception as e:
                self.logger.warning(
                    "⚠️  Could not restore placeholder thread %s: %s", thread_id, e
                )
                await self._clear_placeholder_state_from_db()

        except json.JSONDecodeError as e:
            self.logger.error("❌ Invalid JSON in placeholder state: %s", e)
            await self._clear_placeholder_state_from_db()
        except Exception as e:
            self.logger.error("❌ Failed to restore placeholder state: %s", e)

    async def _clear_placeholder_state_from_db(self):
        """Clear placeholder thread state from database"""
        try:
            await self.cursor.execute(
                "DELETE FROM bot_state WHERE key = ?", ("current_placeholder_thread",)
            )
            await self.cursor.commit()
            self.logger.info("🧹 Cleared placeholder state from database")
        except Exception as e:
            self.logger.error("❌ Failed to clear placeholder state: %s", e)

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

            if not self.forum_channel_id:
                self.logger.error("FORUM_CHANNEL_ID not configured in environment")
                return

            # Get forum channel by ID
            try:
                forum_channel = self.bot.get_channel(int(self.forum_channel_id))
                if not forum_channel:
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

            # Generate content using database-based report logic
            content = await self._generate_placeholder_content(last_monday, last_sunday)

            # Create forum post (thread)
            thread, _ = await forum_channel.create_thread(
                name=thread_name,
                content=content,
                reason="Weekly Django updates placeholder",
            )

            # Store reference for cleanup
            self.current_placeholder_thread = thread

            # Save state to database for restart reliability
            await self._save_placeholder_state_to_db(
                thread.id, forum_channel.guild.id, forum_channel.id, thread_name
            )

            self.logger.info("Created forum post: %s (ID: %s)", thread_name, thread.id)

            # Add simple notification
            await thread.send(
                "📝 **Weekly Django News placeholder created!**\n"
                "This placeholder will be automatically deleted next Monday "
                "or earlier by a bot authorized user."
            )

        except Exception as e:
            self.logger.error(
                "Error creating placeholder forum post: %s", e, exc_info=True
            )

    async def _cleanup_old_placeholder(self):
        """Delete the previous week's placeholder thread"""
        try:
            if self.current_placeholder_thread:
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
            self.current_placeholder_thread = None
            # Clear database state
            await self._clear_placeholder_state_from_db()

    async def _generate_placeholder_content(self, last_monday, last_sunday):
        """Generate placeholder content using database-based report logic"""
        try:
            # Ensure report exists in database
            await self.bot.generate_pr_summary()

            # Get report data from database
            pr_data = await get_latest_weekly_report(self.cursor)

            if not pr_data:
                self.logger.error("No weekly report available for placeholder content")
                return (
                    "Error generating template content. "
                    "Please run `!report md` manually."
                )

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
                f"Today 'Updates to Django' is presented by "
                f"[your name here](your social or linkedin) from "
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

    # ===== ADMIN COMMANDS =====

    @commands.command(name="create_placeholder", hidden=True)
    @is_authorized_user()
    async def manual_placeholder(self, ctx):
        """Manual command to create placeholder (authorized users only)"""
        # Check if old placeholder exists and delete it first
        if self.current_placeholder_thread:
            await ctx.send(
                f"🧹 Deleting old placeholder: {self.current_placeholder_thread.name}"
            )
            await self._cleanup_old_placeholder()
        else:
            # Also check database in case bot was restarted
            await self._restore_placeholder_thread_from_db()
            if self.current_placeholder_thread:
                await ctx.send(
                    f"🧹 Deleting old placeholder: {self.current_placeholder_thread.name}"
                )
                await self._cleanup_old_placeholder()

        # Create new placeholder
        await self._create_weekly_placeholder()
        await ctx.send("✅ New placeholder thread created manually!")

    @commands.command(name="delete_placeholder", hidden=True)
    @is_authorized_user()
    async def delete_placeholder(self, ctx):
        """Delete the current placeholder thread (authorized users only)"""
        try:
            # If no current placeholder, try to restore from database first
            if not self.current_placeholder_thread:
                await self._restore_placeholder_thread_from_db()

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
                if self.current_placeholder_thread.archived:
                    await ctx.send(f"⚠️ Thread '{thread_name}' is already archived")
                    self.current_placeholder_thread = None
                    return

                await self.current_placeholder_thread.delete()
                self.current_placeholder_thread = None
                # Clear database state
                await self._clear_placeholder_state_from_db()

                await ctx.send(f"✅ **Deleted placeholder thread:** {thread_name}")
                self.logger.info(
                    "Manually deleted placeholder thread: %s (ID: %s)",
                    thread_name,
                    thread_id,
                )

            except discord.NotFound:
                await ctx.send(f"⚠️ Thread '{thread_name}' was already deleted")
                self.current_placeholder_thread = None
                # Clear database state since thread no longer exists
                await self._clear_placeholder_state_from_db()

            except discord.Forbidden:
                await ctx.send(
                    f"❌ **Permission denied!**\n"
                    f"Bot lacks permission to delete thread '{thread_name}'.\n"
                    f"Make sure the bot has 'Manage Threads' permission "
                    f"in the forum channel."
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
            # If no current placeholder, try to restore from database first
            if not self.current_placeholder_thread:
                await self._restore_placeholder_thread_from_db()

                if not self.current_placeholder_thread:
                    await ctx.send(
                        f"📝 **No placeholder currently tracked**\n"
                        f"ℹ️ Next automatic placeholder will be created on "
                        f"Monday at {self.placeholder_hour}:00 UTC"
                    )
                    return

            # Get thread info
            thread_name = self.current_placeholder_thread.name
            thread_id = self.current_placeholder_thread.id
            thread_url = (
                f"https://discord.com/channels/{ctx.guild.id}/"
                f"{self.current_placeholder_thread.parent.id}/{thread_id}"
            )

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
                    f"🔄 **Auto-deletion:** Next Monday at "
                    f"{self.placeholder_hour}:00 UTC"
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


async def setup(bot):
    """Setup function for loading the cog"""
    cursor = getattr(bot, "cursor", None)
    if cursor is None:
        raise RuntimeError("Bot cursor not available")
    await bot.add_cog(AutomationCog(bot, cursor))
