import discord


class TimezoneDropdown(discord.ui.Select):
    def __init__(self, cursor):
        self.cursor = cursor
        options = [
            discord.SelectOption(label="UTC", description="UTC", emoji="🌍"),
            discord.SelectOption(
                label="Europe/London", description="Europe/London", emoji="🇬🇧"
            ),
            discord.SelectOption(
                label="America/New_York", description="America/New_York", emoji="🇺🇸"
            ),
            discord.SelectOption(
                label="Asia/Kolkata", description="Asia/Kolkata", emoji="🇮🇳"
            ),
        ]
        super().__init__(
            placeholder="Choose your timezone...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        selected_timezone = self.values[0]
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
                    f"Your timezone is set to **{self.values[0]}** ", ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"Error: {user_name} you don't have any shift yet.", ephemeral=True
                )


class TimezoneView(discord.ui.View):
    def __init__(self, cursor):
        super().__init__()
        self.add_item(TimezoneDropdown(cursor))
