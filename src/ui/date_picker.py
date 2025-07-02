"""
Date picker UI components for volunteer management
"""

import arrow
import discord
from discord import SelectOption
from discord.ui import Select, View


class DatePickerView(View):
    """Interactive date picker for volunteering"""

    def __init__(self, cursor, action="assign", user_name=None):
        super().__init__(timeout=300)  # 5 minute timeout
        self.cursor = cursor
        self.action = action  # "assign" or "unassign"
        self.user_name = user_name
        self.selected_date = None
        self.date_select = None

    async def setup_options(self):
        """Setup the dropdown options based on action type"""
        if self.action == "assign":
            dates = await self._get_available_dates()
            placeholder = "📅 Choose a date to volunteer for..."
            options = [
                SelectOption(
                    label=arrow.get(date).format("dddd, MMMM Do YYYY"),
                    description=f"Due: {arrow.get(date).format('MMM D')} • Available",
                    value=date,
                    emoji="📅",
                )
                for date in dates[:25]  # Discord limit of 25 options
            ]
        else:  # unassign
            dates = await self._get_user_assigned_dates()
            placeholder = "📅 Choose a date to unvolunteer from..."
            options = [
                SelectOption(
                    label=arrow.get(date).format("dddd, MMMM Do YYYY"),
                    description=f"Due: {arrow.get(date).format('MMM D')} • Your assignment",
                    value=date,
                    emoji="📝",
                )
                for date in dates[:25]
            ]

        if not options:
            # Create a disabled option to show no dates available
            if self.action == "assign":
                options = [
                    SelectOption(label="No available dates", value="none", emoji="❌")
                ]
            else:
                options = [
                    SelectOption(label="No assigned dates", value="none", emoji="❌")
                ]

        self.date_select = Select(
            placeholder=placeholder,
            options=options,
            disabled=len(options) == 1 and options[0].value == "none",
        )
        self.date_select.callback = self.date_selected
        self.add_item(self.date_select)

    async def _get_available_dates(self):
        """Get list of available volunteer dates"""
        current_date = arrow.utcnow().format("YYYY-MM-DD")
        async with self.cursor.execute(
            """
            SELECT due_date
            FROM volunteers
            WHERE due_date > ? AND is_taken = 0
            ORDER BY due_date ASC
            LIMIT 25
            """,
            (current_date,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

    async def _get_user_assigned_dates(self):
        """Get list of user's assigned dates"""
        current_date = arrow.utcnow().format("YYYY-MM-DD")
        async with self.cursor.execute(
            """
            SELECT due_date
            FROM volunteers
            WHERE name = ? AND is_taken = 1 AND due_date > ?
            ORDER BY due_date ASC
            LIMIT 25
            """,
            (self.user_name, current_date),
        ) as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

    async def date_selected(self, interaction: discord.Interaction):
        """Handle date selection"""
        if self.date_select.values[0] == "none":
            if self.action == "assign":
                await interaction.response.send_message(
                    "❌ No available dates to volunteer for.", ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "❌ You have no assigned dates to unvolunteer from.", ephemeral=True
                )
            return

        self.selected_date = self.date_select.values[0]
        await self._process_volunteer_action(interaction)

    async def _process_volunteer_action(self, interaction):
        """Process the volunteer assign/unassign action"""
        date = self.selected_date
        user_name = interaction.user.display_name
        is_taken = 1 if self.action == "assign" else 0

        # Update database
        query = """
            UPDATE volunteers
            SET
                is_taken = ?,
                name = CASE WHEN ? THEN ? ELSE name END
            WHERE
                due_date = ? AND (? = 1 OR name = ?)
        """
        async with self.cursor.execute(
            query, (is_taken, is_taken, user_name, date, is_taken, user_name)
        ) as cursor:
            await self.cursor.commit()
            success = cursor.rowcount > 0

        # Send response
        formatted_date = arrow.get(date).format("dddd, MMMM Do YYYY")

        if success:
            if self.action == "assign":
                await interaction.response.send_message(
                    f"✅ **Successfully volunteered!**\n"
                    f"📅 You've been assigned to: **{formatted_date}**\n"
                    f"📝 You'll receive reminders as the date approaches.",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    f"✅ **Successfully unvolunteered!**\n"
                    f"📅 You've been removed from: **{formatted_date}**\n"
                    f"💬 Please inform folks on django-news channel so others can pick it up.",
                    ephemeral=True,
                )
        else:
            await interaction.response.send_message(
                f"❌ **Action failed!**\n"
                f"Could not {'assign you to' if self.action == 'assign' else 'remove you from'} {formatted_date}. "
                f"Please try again or contact an admin.",
                ephemeral=True,
            )

        # Disable the view after use
        for item in self.children:
            item.disabled = True
        await interaction.edit_original_response(view=self)


class UserDatesView(View):
    """View to show user's assigned dates with options to unvolunteer"""

    def __init__(self, cursor, user_name):
        super().__init__(timeout=300)
        self.cursor = cursor
        self.user_name = user_name
        # Placeholder for the dropdown select; initialized in setup_options()
        self.date_select = None

    async def setup_options(self):
        """Setup the dropdown with user's assigned dates"""
        dates_data = await self._get_user_dates_with_status()

        if not dates_data:
            options = [
                SelectOption(label="No assigned dates", value="none", emoji="❌")
            ]
        else:
            options = []
            for date, status in dates_data[:25]:
                formatted_date = arrow.get(date).format("MMM D, YYYY")
                options.append(
                    SelectOption(
                        label=f"{formatted_date} - {status.title()}",
                        description=arrow.get(date).format("dddd, MMMM Do YYYY"),
                        value=date,
                        emoji="📝" if status == "pending" else "✅",
                    )
                )

        self.date_select = Select(
            placeholder="📋 Your assigned dates (select to unvolunteer)...",
            options=options,
            disabled=len(options) == 1 and options[0].value == "none",
        )
        self.date_select.callback = self.date_selected
        self.add_item(self.date_select)

    async def _get_user_dates_with_status(self):
        """Get user's assigned dates with their status"""
        async with self.cursor.execute(
            """
            SELECT due_date, status
            FROM volunteers
            WHERE name = ? AND is_taken = 1
            ORDER BY due_date ASC
            """,
            (self.user_name,),
        ) as cursor:
            return await cursor.fetchall()

    async def date_selected(self, interaction: discord.Interaction):
        """Handle date selection for unvolunteering"""
        if self.date_select.values[0] == "none":
            await interaction.response.send_message(
                "❌ You have no assigned dates.", ephemeral=True
            )
            return

        selected_date = self.date_select.values[0]
        formatted_date = arrow.get(selected_date).format("dddd, MMMM Do YYYY")

        # Create confirmation view
        confirm_view = ConfirmUnvolunteerView(
            self.cursor, selected_date, self.user_name
        )

        await interaction.response.send_message(
            f"🤔 **Confirm Unvolunteer**\n"
            f"Are you sure you want to unvolunteer from:\n"
            f"📅 **{formatted_date}**\n\n"
            f"💡 *Others will be able to volunteer for this date once you confirm.*",
            view=confirm_view,
            ephemeral=True,
        )


class ConfirmUnvolunteerView(View):
    """Confirmation dialog for unvolunteering"""

    def __init__(self, cursor, date, user_name):
        super().__init__(timeout=60)
        self.cursor = cursor
        self.date = date
        self.user_name = user_name

    @discord.ui.button(
        label="Yes, Unvolunteer", style=discord.ButtonStyle.danger, emoji="✅"
    )
    async def confirm_unvolunteer(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Confirm and process unvolunteering"""
        # Update database
        async with self.cursor.execute(
            """
            UPDATE volunteers
            SET is_taken = 0, name = NULL
            WHERE due_date = ? AND name = ?
            """,
            (self.date, self.user_name),
        ) as cursor:
            await self.cursor.commit()
            success = cursor.rowcount > 0

        formatted_date = arrow.get(self.date).format("dddd, MMMM Do YYYY")

        if success:
            await interaction.response.send_message(
                f"✅ **Successfully unvolunteered!**\n"
                f"📅 You've been removed from: **{formatted_date}**\n"
                f"💬 Please inform folks on django-news channel so others can pick it up.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                f"❌ **Failed to unvolunteer from {formatted_date}**\n"
                f"Please try again or contact an admin.",
                ephemeral=True,
            )

        # Disable buttons
        for item in self.children:
            item.disabled = True
        await interaction.edit_original_response(view=self)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel_unvolunteer(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Cancel the unvolunteer action"""
        await interaction.response.send_message(
            "🚫 **Cancelled** - You're still volunteered for this date.", ephemeral=True
        )

        # Disable buttons
        for item in self.children:
            item.disabled = True
        await interaction.edit_original_response(view=self)
