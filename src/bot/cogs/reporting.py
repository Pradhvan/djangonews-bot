"""
Reporting commands - !report
"""

import sys
from pathlib import Path

from discord.ext import commands

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.github import get_latest_weekly_report


class ReportingCog(commands.Cog):
    """Commands for generating reports and summaries"""

    def __init__(self, bot, cursor):
        self.bot = bot
        self.cursor = cursor

    @staticmethod
    async def _format_report(data):
        total_prs = data.get("total_prs", 0)
        contributors = len({pr["author"] for pr in data["prs"]})
        first_timers = data.get("first_time_contributors", [])
        modifying_prs = [pr for pr in data["prs"] if pr["modifies_release"]]

        first_timer_msg = ""
        if first_timers:
            first_timer_msg = f"\n🎉 {len(first_timers)} first-time contributor."

        summary = (
            f"✅ {total_prs} pull requests were merged by {contributors} contributors."
            f"{first_timer_msg}"
        )

        if modifying_prs:
            summary += (
                f"\n📦 {len(modifying_prs)} PRs updated the release notes or docs:"
            )
            for pr in modifying_prs:
                summary += f"\n🦄 [{pr['title']}](<{pr['url']}>)"

        return summary

    @staticmethod
    async def _format_list_prs(data):
        modifying_prs = [pr for pr in data["prs"] if pr["modifies_release"]]
        list_modifying_prs = "There are no PRs that modify the release."

        if modifying_prs:
            list_modifying_prs = ""
            for pr in modifying_prs:
                list_modifying_prs += f"\n🦄 [{pr['title']}](<{pr['url']}>)"

        return list_modifying_prs

    async def _get_user_profile(self, user_name: str) -> dict:
        """Get user's profile for report attribution"""
        async with self.cursor.execute(
            """
            SELECT volunteer_name, social_media_handle
            FROM volunteers
            WHERE name = ?
            LIMIT 1
            """,
            (user_name,),
        ) as cursor:
            row = await cursor.fetchone()

            if row:
                return {
                    "volunteer_name": row[0] or "",
                    "social_media_handle": row[1] or "",
                }
            else:
                return {
                    "volunteer_name": "",
                    "social_media_handle": "",
                }

    # ===== COMMANDS =====

    @commands.command(name="report")
    async def report(self, ctx, md: str = None):
        """Generate weekly PR summary report"""
        # Ensure latest report exists in database
        await self.bot.generate_pr_summary()

        # Get report data from database
        pr_data = await get_latest_weekly_report(self.cursor)

        if not pr_data:
            await ctx.send(
                "❌ **No weekly report available**\nThere seems to be an issue generating the weekly PR summary. Please try again later."
            )
            return

        short_summary = await ReportingCog._format_report(pr_data)
        list_modifying_prs = await ReportingCog._format_list_prs(pr_data)
        last_week = pr_data["date_range_humanized"]
        discord_summary = await self.bot.disable_link_previews(pr_data["synopsis"])

        if md and md.lower() == "md":
            # Get user's profile information
            user_name = ctx.author.display_name
            profile = await self._get_user_profile(user_name)
            volunteer_name = profile.get("volunteer_name", "")
            social_handle = profile.get("social_media_handle", "")

            # Create the template with user's volunteer name and social handle
            if volunteer_name:
                if social_handle:
                    # Clean up the social handle for use in markdown
                    if social_handle.startswith(("@", "http")):
                        handle_link = (
                            social_handle
                            if social_handle.startswith("http")
                            else f"https://twitter.com/{social_handle.lstrip('@')}"
                        )
                        social_text = f"[{volunteer_name}]({handle_link})"
                    else:
                        social_text = f"[{volunteer_name}]({social_handle})"
                    author_text = f"{social_text} from"
                else:
                    author_text = f"{volunteer_name} from"
            elif social_handle:
                # Fallback to social handle if no volunteer name
                if social_handle.startswith(("@", "http")):
                    handle_link = (
                        social_handle
                        if social_handle.startswith("http")
                        else f"https://twitter.com/{social_handle.lstrip('@')}"
                    )
                    social_text = f"[{social_handle}]({handle_link})"
                else:
                    social_text = social_handle
                author_text = f"{social_text} from"  # use social handle/link directly
            else:
                author_text = "your name here from"

            await ctx.send(
                f"```Today 'Updates to Django' is presented by {author_text} "
                f"the [Djangonaut Space](https://djangonaut.space/)!🚀"
                f"\n\n{discord_summary}```"
                f"\n{list_modifying_prs}\n\n"
                f"💡 **Tip:** Use `!profile` to set your social media handle for automatic insertion!"
            )
        else:
            await ctx.send(f"📢 **Django Weekly Summary ({last_week})**")
            await ctx.send(f"{short_summary}")
            await ctx.send(f"🧑‍💻 **Synopsis**\n{discord_summary}")


async def setup(bot):
    """Setup function for loading the cog"""
    cursor = getattr(bot, "cursor", None)
    if cursor is None:
        raise RuntimeError("Bot cursor not available")
    await bot.add_cog(ReportingCog(bot, cursor))
