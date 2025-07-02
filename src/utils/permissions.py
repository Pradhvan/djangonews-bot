"""
Permission checks for Django News Bot commands.

This module contains custom permission decorators and checks for Discord commands.
"""

import os

from discord.ext import commands


def is_authorized_user():
    """
    Custom check for authorized users from environment variable.

    Reads AUTHORIZED_USER_IDS from environment - comma-separated Discord user IDs.
    Falls back to administrator permission if env var is not set or parsing fails.

    Usage:
        @commands.command()
        @is_authorized_user()
        async def my_command(self, ctx):
            ...

    Environment setup:
        AUTHORIZED_USER_IDS=123456789012345678,987654321098765432
    """

    def predicate(ctx):
        # Read authorized user IDs from environment
        authorized_ids_str = os.getenv("AUTHORIZED_USER_IDS", "")

        if not authorized_ids_str:
            # If no env var set, fall back to administrator permission
            return ctx.author.guild_permissions.administrator

        try:
            # Parse comma-separated user IDs
            authorized_ids = [
                int(uid.strip()) for uid in authorized_ids_str.split(",") if uid.strip()
            ]
            return ctx.author.id in authorized_ids

        except ValueError:
            # If parsing fails, fall back to administrator permission
            return ctx.author.guild_permissions.administrator

    return commands.check(predicate)


def is_admin():
    """
    Simple administrator permission check.

    Usage:
        @commands.command()
        @is_admin()
        async def admin_command(self, ctx):
            ...
    """

    async def predicate(ctx):
        return ctx.author.guild_permissions.administrator

    return commands.check(predicate)


def has_role(role_name):
    """
    Check if user has a specific role by name.

    Args:
        role_name (str): The name of the role to check for

    Usage:
        @commands.command()
        @has_role("django-maintainer")
        async def maintainer_command(self, ctx):
            ...
    """

    def predicate(ctx):
        return any(role.name == role_name for role in ctx.author.roles)

    return commands.check(predicate)


def has_role_id(role_id_env_var):
    """
    Check if user has a specific role by ID from environment variable.

    Args:
        role_id_env_var (str): Environment variable name containing the role ID

    Usage:
        @commands.command()
        @has_role_id("EDITOR_ROLE_ID")
        async def editor_command(self, ctx):
            ...
    """

    def predicate(ctx):
        role_id_str = os.getenv(role_id_env_var)
        if not role_id_str:
            return False

        try:
            role_id = int(role_id_str)
            return any(role.id == role_id for role in ctx.author.roles)
        except (ValueError, AttributeError):
            return False

    return commands.check(predicate)
