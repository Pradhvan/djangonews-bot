"""
Date list utilities for displaying available dates
"""

from typing import List, Tuple

import arrow


def generate_date_list(available_dates: List[str], limit: int = 10) -> str:
    """
    Generate a simple list of available dates

    Args:
        available_dates: List of available dates in YYYY-MM-DD format
        limit: Maximum number of dates to show

    Returns:
        Formatted date list string
    """
    if not available_dates:
        return "📅 No available dates found."

    date_lines = []

    for i, date_str in enumerate(available_dates[:limit]):
        date_obj = arrow.get(date_str)
        formatted_date = date_obj.format("dddd, MMMM Do YYYY")
        days_until = (date_obj - arrow.utcnow()).days

        if days_until < 0:
            continue  # Skip past dates

        # Create urgency indicator
        if days_until == 0:
            urgency = "📍 Due Today!"
        elif days_until <= 3:
            urgency = f"🔴 {days_until} days - Urgent!"
        elif days_until <= 7:
            urgency = f"🟡 {days_until} days"
        else:
            urgency = f"🟢 {days_until} days"

        # Format as a single line to avoid embed issues
        date_lines.append(f"`{i + 1:2d}.` **{formatted_date}** - {urgency}")

    result = "📅 **Available Volunteer Dates:**\n\n" + "\n".join(date_lines)

    if len(available_dates) > limit:
        result += f"\n\n*... and {len(available_dates) - limit} more dates available*"

    return result


def generate_user_date_summary(user_dates: List[Tuple[str, str]]) -> str:
    """
    Generate a summary of user's assigned dates

    Args:
        user_dates: List of tuples (date, status)

    Returns:
        Formatted summary string
    """
    if not user_dates:
        return "📅 You have no assigned volunteer dates."

    summary_lines = []

    for i, (date_str, status) in enumerate(user_dates):
        date_obj = arrow.get(date_str)
        formatted_date = date_obj.format("dddd, MMMM Do YYYY")
        days_until = (date_obj - arrow.utcnow()).days

        # Status emoji
        status_emoji = {
            "pending": "📝",
            "in_progress": "⚙️",
            "completed": "✅",
            "overdue": "❗",
        }.get(status.lower(), "📝")

        # Urgency indicator
        if days_until < 0:
            urgency = f"🔴 Overdue ({abs(days_until)} days)"
        elif days_until == 0:
            urgency = "📍 Due Today!"
        elif days_until <= 3:
            urgency = f"🟡 Due in {days_until} days"
        else:
            urgency = f"🟢 {days_until} days away"

        summary_lines.append(
            f"`{i + 1:2d}.` {status_emoji} **{formatted_date}** - {status.title()} - {urgency}"
        )

    result = f"📋 **Your Django News Assignments** ({len(user_dates)} total)\n\n"
    result += "\n".join(summary_lines)

    return result
