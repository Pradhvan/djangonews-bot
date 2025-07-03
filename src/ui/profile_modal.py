"""
Profile modal UI components for volunteer profile management
"""

import discord
from discord import SelectOption
from discord.ui import Modal, Select, TextInput, View

from utils.timezone import get_popular_timezones, validate_timezone


class ProfileModal(Modal):
    """Modal for editing volunteer profile information"""

    def __init__(self, cursor, user_name: str, current_profile: dict = None):
        super().__init__(title="📋 Edit Your Volunteer Profile")
        self.cursor = cursor
        self.user_name = user_name
        self.current_profile = current_profile or {}

        # Volunteer Name input (replaces bio)
        self.volunteer_name = TextInput(
            label="Volunteer Name (for report attribution)",
            placeholder="e.g., Your Full Name, @handle, or preferred credit",
            default=self.current_profile.get("volunteer_name", ""),
            max_length=100,
            required=False,
        )
        self.add_item(self.volunteer_name)

        # Social Media Handle input
        self.social_handle = TextInput(
            label="Social Media Handle",
            placeholder="e.g., @username, linkedin.com/in/username, yourwebsite.com",
            default=self.current_profile.get("social_media_handle", ""),
            max_length=100,
            required=False,
        )
        self.add_item(self.social_handle)

        # Preferred reminder time input
        self.reminder_time = TextInput(
            label="Preferred Reminder Time (24-hour format)",
            placeholder="e.g., 09:00, 14:30, 18:00",
            default=self.current_profile.get("preferred_reminder_time", "09:00"),
            max_length=5,
            required=False,
        )
        self.add_item(self.reminder_time)

        # Note: Timezone selection is handled separately via buttons
        # Discord modals can only contain TextInput components

    async def on_submit(self, interaction: discord.Interaction, *args, **kwargs):
        """Handle profile submission"""
        # Validate reminder time format
        reminder_time = self.reminder_time.value.strip()
        if reminder_time and not self._validate_time_format(reminder_time):
            await interaction.response.send_message(
                "❌ **Invalid time format!**\n"
                "Please use 24-hour format like: 09:00, 14:30, 18:00",
                ephemeral=True,
            )
            return

        # Get form values
        volunteer_name = self.volunteer_name.value.strip()
        social_handle = self.social_handle.value.strip()

        try:
            # Update or create profile (timezone handled separately)
            await self._save_profile(volunteer_name, social_handle, reminder_time)

            # Create success embed
            embed = discord.Embed(
                title="✅ Profile Updated Successfully!",
                description="Your volunteer profile has been saved.",
                color=0x0C4B33,
            )

            if volunteer_name:
                embed.add_field(
                    name="📝 Volunteer Name", value=volunteer_name, inline=True
                )
            if social_handle:
                embed.add_field(
                    name="📱 Social Handle", value=social_handle, inline=True
                )
            if reminder_time:
                embed.add_field(
                    name="⏰ Reminder Time", value=reminder_time, inline=True
                )

            embed.add_field(
                name="🌍 Timezone",
                value="Use 'Update Timezone' button to set timezone",
                inline=True,
            )

            embed.set_footer(
                text="💡 Use !profile to view or edit your profile anytime"
            )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            await interaction.response.send_message(
                f"❌ **Error saving profile:** {str(e)}\n"
                "Please try again or contact an admin.",
                ephemeral=True,
            )

    @staticmethod
    def _validate_time_format(time_str: str) -> bool:
        """Validate 24-hour time format (HH:MM)"""
        try:
            if ":" not in time_str:
                return False
            hours, minutes = time_str.split(":")
            hour = int(hours)
            minute = int(minutes)
            return (
                0 <= hour <= 23
                and 0 <= minute <= 59
                and len(hours) == 2
                and len(minutes) == 2
            )
        except (ValueError, IndexError):
            return False

    async def _save_profile(
        self, volunteer_name: str, social_handle: str, reminder_time: str
    ):
        """Save profile to database"""
        # First check if user has any volunteer entries
        async with self.cursor.execute(
            "SELECT id FROM volunteers WHERE name = ? LIMIT 1", (self.user_name,)
        ) as cursor:
            user_exists = await cursor.fetchone()

        if user_exists:
            # Update existing user's profile in all their volunteer entries
            await self.cursor.execute(
                """
                UPDATE volunteers
                SET volunteer_name = ?, social_media_handle = ?, preferred_reminder_time = ?
                WHERE name = ?
                """,
                (
                    volunteer_name or None,
                    social_handle or None,
                    reminder_time or None,
                    self.user_name,
                ),
            )
        else:
            # Create a profile entry (this shouldn't happen often, but just in case)
            await self.cursor.execute(
                """
                INSERT INTO volunteers (name, reminder_date, due_date, volunteer_name, social_media_handle, preferred_reminder_time, is_taken)
                VALUES (?, '1970-01-01', '1970-01-01', ?, ?, ?, 0)
                """,
                (
                    self.user_name,
                    volunteer_name or None,
                    social_handle or None,
                    reminder_time or None,
                ),
            )

        await self.cursor.commit()


class TimezoneSelectView(View):
    """View for selecting timezone in profile setup"""

    def __init__(self, cursor, user_name: str):
        super().__init__(timeout=300)
        self.cursor = cursor
        self.user_name = user_name

        # Create timezone dropdown using popular timezones
        timezone_options = get_popular_timezones()
        options = [
            SelectOption(label=display_name, value=tz_id, description=tz_id)
            for tz_id, display_name in timezone_options[
                :24
            ]  # Leave room for "Other" option
        ]

        # Add "Other" option
        options.append(
            SelectOption(
                label="Other Timezone",
                value="__other__",
                description="Enter a custom timezone",
                emoji="⚙️",
            )
        )

        self.timezone_select = Select(
            placeholder="🌍 Choose your timezone...",
            options=options,
            min_values=1,
            max_values=1,
        )
        self.timezone_select.callback = self.timezone_selected
        self.add_item(self.timezone_select)

    async def timezone_selected(self, interaction: discord.Interaction):
        """Handle timezone selection"""
        selected_timezone = self.timezone_select.values[0]

        if selected_timezone == "__other__":
            # Show custom timezone modal
            modal = CustomTimezoneModal(self.cursor, self.user_name)
            await interaction.response.send_modal(modal)
        else:
            # Save the selected timezone
            await self._save_timezone(interaction, selected_timezone)

    async def _save_timezone(self, interaction: discord.Interaction, timezone: str):
        """Save timezone to database"""
        # Validate timezone using our utility function
        if not validate_timezone(timezone):
            await interaction.response.send_message(
                f"❌ **Invalid timezone:** {timezone}\n"
                "Please select a valid timezone from the list.",
                ephemeral=True,
            )
            return

        # Update user's timezone
        async with self.cursor.execute(
            "UPDATE volunteers SET timezone = ? WHERE name = ?",
            (timezone, self.user_name),
        ) as cursor:
            await self.cursor.commit()
            success = cursor.rowcount > 0

        if success:
            # Get display name for timezone
            from utils.timezone import get_display_name

            display_name = get_display_name(timezone)

            embed = discord.Embed(
                title="✅ Timezone Updated!",
                description=f"Your timezone has been set to **{display_name}**",
                color=0x0C4B33,
            )
            embed.set_footer(
                text="💡 This affects your reminder times for volunteer assignments"
            )

            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(
                "❌ **Error:** Could not update timezone. Make sure you have volunteer assignments first.\n"
                "Use `!volunteer` to sign up for dates.",
                ephemeral=True,
            )


class CustomTimezoneModal(Modal):
    """Modal for entering custom timezone"""

    def __init__(self, cursor, user_name: str):
        super().__init__(title="🌍 Enter Custom Timezone")
        self.cursor = cursor
        self.user_name = user_name

        self.timezone_input = TextInput(
            label="Timezone ID (e.g., America/New_York)",
            placeholder="Enter timezone identifier...",
            max_length=50,
            required=True,
        )
        self.add_item(self.timezone_input)

    async def on_submit(self, interaction: discord.Interaction, *args, **kwargs):
        """Handle custom timezone submission"""
        timezone = self.timezone_input.value.strip()

        # Validate timezone using our utility function
        if not validate_timezone(timezone):
            await interaction.response.send_message(
                f"❌ **Invalid timezone:** {timezone}\n"
                "Please enter a valid timezone identifier like 'America/New_York' or 'Europe/London'.\n"
                "See [timezone list](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones) for valid options.",
                ephemeral=True,
            )
            return

        # Update user's timezone
        async with self.cursor.execute(
            "UPDATE volunteers SET timezone = ? WHERE name = ?",
            (timezone, self.user_name),
        ) as cursor:
            await self.cursor.commit()
            success = cursor.rowcount > 0

        if success:
            embed = discord.Embed(
                title="✅ Custom Timezone Set!",
                description=f"Your timezone has been set to **{timezone}**",
                color=0x0C4B33,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(
                "❌ **Error:** Could not update timezone. Make sure you have volunteer assignments first.",
                ephemeral=True,
            )


class ProfileSetupView(View):
    """Complete profile setup flow with multiple steps"""

    def __init__(self, cursor, user_name: str):
        super().__init__(timeout=600)  # 10 minute timeout for full setup
        self.cursor = cursor
        self.user_name = user_name

    @discord.ui.button(
        label="Edit Profile", style=discord.ButtonStyle.primary, emoji="📝"
    )
    async def edit_profile(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Open profile editing modal"""
        # Get current profile data
        current_profile = await self._get_current_profile()
        modal = ProfileModal(self.cursor, self.user_name, current_profile)
        await interaction.response.send_modal(modal)

    @discord.ui.button(
        label="Update Timezone", style=discord.ButtonStyle.secondary, emoji="🌍"
    )
    async def quick_timezone(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Open timezone selection (separate from full profile)"""
        view = TimezoneSelectView(self.cursor, self.user_name)

        embed = discord.Embed(
            title="🌍 Update Your Timezone",
            description="Choose your timezone for accurate reminder times:\n\n💡 **Note:** Timezone is managed separately from other profile settings due to Discord interface limitations.",
            color=0x0C4B33,
        )
        embed.set_footer(text="💡 This affects when you receive volunteer reminders")

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(
        label="View Profile", style=discord.ButtonStyle.success, emoji="👀"
    )
    async def view_profile(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Show current profile"""
        profile = await self._get_current_profile()
        embed = await self._create_profile_embed(profile)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _get_current_profile(self) -> dict:
        """Get current profile data from database"""
        async with self.cursor.execute(
            """
            SELECT timezone, social_media_handle, preferred_reminder_time, volunteer_name
            FROM volunteers
            WHERE name = ?
            LIMIT 1
            """,
            (self.user_name,),
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

    async def _create_profile_embed(self, profile: dict) -> discord.Embed:
        """Create an embed showing profile information"""
        embed = discord.Embed(
            title="👤 Your Volunteer Profile",
            description=f"Profile for **{self.user_name}**",
            color=0x0C4B33,
        )

        # Volunteer Name
        embed.add_field(
            name="📝 Volunteer Name",
            value=profile["volunteer_name"] or "Not set",
            inline=True,
        )

        # Timezone
        timezone_display = profile["timezone"]
        if profile["timezone"] != "UTC":
            # Try to get a more friendly display name
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

        embed.set_footer(text="💡 Use the buttons above to edit your profile")

        return embed
