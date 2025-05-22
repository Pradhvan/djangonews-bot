from discord import Interaction, SelectOption
from discord.ui import Select, View

TIMEZONE_OPTIONS = frozenset(
    {
        ("America/New_York", "🇺🇸"),
        ("America/Los_Angeles", "🇺🇸"),
        ("America/Chicago", "🇺🇸"),
        ("Europe/London", "🇬🇧"),
        ("Europe/Paris", "🇫🇷"),
        ("Asia/Kolkata", "🇮🇳"),
        ("Asia/Tokyo", "🇯🇵"),
        ("Asia/Shanghai", "🇨🇳"),
        ("Australia/Sydney", "🇦🇺"),
        ("America/Sao_Paulo", "🇧🇷"),
    }
)


class TimezoneView(View):
    def __init__(self, cursor):
        super().__init__()

        dropdown_options = [
            SelectOption(label=timezone, description=timezone, emoji=emoji)
            for timezone, emoji in sorted(TIMEZONE_OPTIONS)
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
        query = """
            UPDATE volunteers
            SET timezone = ?
            WHERE name = ? AND is_taken = 1
         """
        async with self.cursor.execute(query, (selected_timezone, user_name)) as cur:
            await self.cursor.commit()
            if cur.rowcount > 0:
                await interaction.response.send_message(
                    f"Your timezone is set to **{selected_timezone}** ", ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"Error: {user_name} you don't have any shift yet.", ephemeral=True
                )
