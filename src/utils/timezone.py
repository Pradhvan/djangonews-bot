"""
Simple timezone utilities for Django News Bot
"""

import zoneinfo
from typing import List, Tuple


def get_popular_timezones() -> List[Tuple[str, str]]:
    """Get a curated list of popular timezones with better visual indicators"""
    return [
        # Americas
        ("America/New_York", "🏙️ New York (Eastern)"),
        ("America/Chicago", "🌆 Chicago (Central)"),
        ("America/Denver", "⛰️ Denver (Mountain)"),
        ("America/Los_Angeles", "🌴 Los Angeles (Pacific)"),
        ("America/Toronto", "🍁 Toronto"),
        ("America/Vancouver", "🍁 Vancouver"),
        ("America/Mexico_City", "🇲🇽 Mexico City"),
        ("America/Sao_Paulo", "🇧🇷 São Paulo"),
        # Europe
        ("Europe/London", "🇬🇧 London"),
        ("Europe/Paris", "🇫🇷 Paris"),
        ("Europe/Berlin", "🇩🇪 Berlin"),
        ("Europe/Rome", "🇮🇹 Rome"),
        ("Europe/Madrid", "🇪🇸 Madrid"),
        ("Europe/Amsterdam", "🇳🇱 Amsterdam"),
        # Asia
        ("Asia/Tokyo", "🇯🇵 Tokyo"),
        ("Asia/Seoul", "🇰🇷 Seoul"),
        ("Asia/Shanghai", "🇨🇳 Shanghai"),
        ("Asia/Kolkata", "🇮🇳 Mumbai/Delhi"),
        ("Asia/Dubai", "🇦🇪 Dubai"),
        ("Asia/Singapore", "🇸🇬 Singapore"),
        # Oceania
        ("Australia/Sydney", "🇦🇺 Sydney"),
        ("Australia/Melbourne", "🇦🇺 Melbourne"),
        ("Pacific/Auckland", "🇳🇿 Auckland"),
    ]


def validate_timezone(timezone: str) -> bool:
    """Validate if a timezone string is valid"""
    try:
        zoneinfo.ZoneInfo(timezone)
        return True
    except Exception:
        return False


def get_display_name(timezone: str) -> str:
    """Get friendly display name for a timezone"""
    popular_tz = dict(get_popular_timezones())
    return popular_tz.get(timezone, timezone)
