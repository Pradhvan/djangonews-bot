"""
Simple timezone selection view for basic timezone setting
"""

from discord import Interaction, SelectOption
from discord.ui import Select, View

from utils.timezone import get_popular_timezones, validate_timezone


class TimezoneView(View):
    """Simple timezone selector for !settimezone command"""

    def __init__(self, cursor):
        super().__init__()

        # Get popular timezones with improved visual indicators
        timezone_options = get_popular_timezones()
        dropdown_options = [
            SelectOption(label=display_name, description=tz_id, value=tz_id)
            for tz_id, display_name in timezone_options[:25]  # Discord limit
        ]

        self.timezone_select = Select(
            placeholder="Choose your timezone...",
            min_values=1,
            max_values=1,
            options=dropdown_options,
        )

        self.timezone_select.callback = self.select_callback
        self.cursor = cursor

        self.add_item(self.timezone_select)

    async def select_callback(self, interaction: Interaction):
        selected_timezone = self.timezone_select.values[0]
        user_name = interaction.user.display_name

        # Validate timezone using our utility function
        if not validate_timezone(selected_timezone):
            await interaction.response.send_message(
                f"❌ **Invalid timezone:** {selected_timezone}\n"
                "Please select a valid timezone from the list.",
                ephemeral=True,
            )
            return

        query = """
            UPDATE volunteers
            SET timezone = ?
            WHERE name = ? AND is_taken = 1
         """
        async with self.cursor.execute(query, (selected_timezone, user_name)) as cur:
            await self.cursor.commit()
            if cur.rowcount > 0:
                # Get friendly display name
                from utils.timezone import get_display_name

                display_name = get_display_name(selected_timezone)
                await interaction.response.send_message(
                    f"Your timezone is set to **{display_name}** ",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    f"Error: {user_name} you don't have any shift yet.",
                    ephemeral=True,
                )
