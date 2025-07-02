"""
Profile management commands - !profile, !settimezone
"""

import sys
from pathlib import Path

import discord
from discord.ext import commands

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ui import ProfileSetupView, TimezoneView


class ProfileCog(commands.Cog):
    """Commands for managing user profiles and settings"""

    def __init__(self, bot, cursor):
        self.bot = bot
        self.cursor = cursor

    async def _get_user_profile(self, user_name: str) -> dict:
        """Get user's current profile data"""
        async with self.cursor.execute(
            """
            SELECT timezone, social_media_handle, preferred_reminder_time, volunteer_name
            FROM volunteers
            WHERE name = ?
            LIMIT 1
            """,
            (user_name,),
        ) as cursor:
            row = await cursor.fetchone()

            if row:
                return {
                    "timezone": row[0] or "UTC",
                    "social_media_handle": row[1] or "",
                    "preferred_reminder_time": row[2] or "09:00",
                    "volunteer_name": row[3] or "",
                }
            else:
                return {
                    "timezone": "UTC",
                    "social_media_handle": "",
                    "preferred_reminder_time": "09:00",
                    "volunteer_name": "",
                }

    async def _create_profile_display_embed(
        self, user_name: str, profile: dict
    ) -> discord.Embed:
        """Create an embed showing profile information"""
        embed = discord.Embed(
            title="👤 Your Volunteer Profile",
            description=f"Profile settings for **{user_name}**",
            color=0x0C4B33,
        )

        # Get user's assignment count
        async with self.cursor.execute(
            "SELECT COUNT(*) FROM volunteers WHERE name = ? AND is_taken = 1",
            (user_name,),
        ) as cursor:
            assignment_count = (await cursor.fetchone())[0]

        embed.add_field(
            name="📅 Active Assignments",
            value=f"{assignment_count} volunteer dates",
            inline=True,
        )

        # Volunteer Name
        embed.add_field(
            name="📝 Volunteer Name",
            value=profile["volunteer_name"] or "Not set",
            inline=True,
        )

        # Timezone with friendly display
        timezone_display = profile["timezone"]
        if profile["timezone"] != "UTC":
            from utils.timezone import get_display_name

            timezone_display = get_display_name(profile["timezone"])

        embed.add_field(name="🌍 Timezone", value=timezone_display, inline=True)

        # Reminder time
        embed.add_field(
            name="⏰ Reminder Time",
            value=profile["preferred_reminder_time"] or "Not set",
            inline=True,
        )

        # Social media
        embed.add_field(
            name="📱 Social Handle",
            value=profile["social_media_handle"] or "Not set",
            inline=True,
        )

        embed.set_footer(text="📝 Use the buttons below to edit your profile")

        return embed

    # ===== COMMANDS =====

    @commands.command(name="profile")
    async def profile_command(self, ctx):
        """Manage your volunteer profile settings"""
        user_name = ctx.author.display_name

        # Create profile setup view
        profile_view = ProfileSetupView(self.cursor, user_name)

        # Get current profile for display
        current_profile = await self._get_user_profile(user_name)
        embed = await self._create_profile_display_embed(user_name, current_profile)

        await ctx.send(embed=embed, view=profile_view)

    @commands.command(name="settimezone")
    async def set_timezone(self, ctx, *args):
        """Update your timezone with interactive dropdown"""

        # Create timezone selection view
        view = TimezoneView(self.cursor)

        embed = discord.Embed(
            title="🌍 Update Your Timezone",
            description="Choose your timezone for accurate volunteer reminders:\\n\\n"
            "💡 **Tip:** Use `!profile` for comprehensive profile management including volunteer name, social handle, and reminder times.",
            color=0x0C4B33,
        )
        embed.set_footer(text="💡 This affects when you receive volunteer reminders")

        await ctx.send(embed=embed, view=view)


async def setup(bot):
    """Setup function for loading the cog"""
    cursor = getattr(bot, "cursor", None)
    if cursor is None:
        raise RuntimeError("Bot cursor not available")
    await bot.add_cog(ProfileCog(bot, cursor))
