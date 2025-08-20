import json
import subprocess
import urllib.parse
from shlex import split as shlex_split

import arrow


def format_date_range_humanized(start, end):
    start = arrow.get(start, "YYYY-MM-DD")
    end = arrow.get(end, "YYYY-MM-DD")
    return f"{start.format('MMMM D')} to {end.format('MMMM D, YYYY')}"


def build_github_search_query(start_date, end_date):
    return f"repo:django/django is:pr is:merged merged:{start_date}..{end_date}"


def send_command(command):
    """Execute a GitHub CLI command and return the JSON result"""
    # Split the command string into a list of arguments to avoid shell=True
    command_args = shlex_split(command)

    process = subprocess.Popen(
        command_args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,  # Explicitly set shell=False for security
    )

    output, error = process.communicate()

    if error and error.strip():
        error_text = error.decode("utf-8")
        print(f"Warning: Command produced error output: {error_text}")
        if process.returncode != 0:
            raise Exception(f"Command failed with error: {error_text}")

    return json.loads(output.decode("utf-8"))


def fetch_merged_prs(query, limit=200):
    """Fetch merged PRs using GitHub CLI instead of PyGithub"""
    command = (
        "gh pr list --repo django/django "
        f'-S "{query}" '
        f"-L {limit} "
        "--json number,title,url,author,createdAt"
    )
    return send_command(command)


async def get_full_name_contributors(first_timers):
    """
    Update the first_timers list with full names from GitHub when available.

    Args:
        first_timers: List of markdown-formatted contributor links

    Returns:
        Updated list with full names where available
    """
    updated_contributors = []

    for contributor in first_timers:
        # Extract username from markdown link format
        username = contributor.split("](")[0].replace("[", "")

        # Fetch user info from GitHub
        command = f"gh api users/{username}"
        try:
            user_info = send_command(command)

            # Use the name if available, otherwise use the login
            if user_info.get("name") and user_info["name"].strip():
                full_name = user_info["name"]
                updated_link = f"[{full_name}](https://github.com/{username})"
                updated_contributors.append(updated_link)
                print(f"Found full name for {username}: {full_name}")
            else:
                updated_contributors.append(contributor)
                print(f"No full name found for {username}, using login")
        except Exception as e:
            # If there's an error, keep the original link
            print(f"Error fetching info for {username}: {str(e)}")
            updated_contributors.append(contributor)

    return updated_contributors


async def identify_first_timers(merged_prs, start_date, db_connection):
    """Identify first-timers checking on database first then using GitHub CLI"""

    first_timers = []
    unique_authors = {pr["author"]["login"] for pr in merged_prs}

    for author in sorted(unique_authors):
        async with db_connection.execute(
            """
                SELECT login
                FROM contributors
                WHERE login = ?
                """,
            (author,),
        ) as cursor:
            row = await cursor.fetchone()

        if row:
            # already contributor
            print(f"This author {author} is already a contributor")
            continue
        else:
            try:
                cmd = (
                    "gh pr list --repo django/django "
                    f'-S "is:pr is:merged author:{author} merged:<{start_date}" '
                    "-L 1 --json number"
                )
                prev = send_command(cmd)
                if not prev:
                    first_timers.append(f"[{author}](https://github.com/{author})")
                else:
                    # is already a contributor
                    # saved on database
                    await db_connection.execute(
                        """
                        INSERT INTO contributors (login)
                        VALUES (?)
                        """,
                        (author,),
                    )
            except Exception as e:
                print(f"Error while checking {author}: {e}")

        await db_connection.commit()
    return first_timers


def pr_modifies_release_files(pr_number):
    """Check if a PR modifies release files using GitHub CLI"""
    command = f"gh pr view {pr_number} --repo django/django --json files"
    response = send_command(command)

    for file in response["files"]:
        path = file["path"].lower()
        if path.startswith("docs/releases/") and (
            path.endswith(".txt") or path.endswith(".rst")
        ):
            return True
    return False


async def generate_synopsis(merged_prs, first_timers, search_url):
    unique_contributors = len({pr["author"]["login"] for pr in merged_prs})
    synopsis = (
        f"Last week we had [{len(merged_prs)} pull requests]({search_url}) merged into Django by "
        f"{unique_contributors} different contributors"
    )
    if first_timers:
        contributors_with_names = await get_full_name_contributors(first_timers)

        # Format the contributors list with "and" before the last item
        if len(contributors_with_names) == 1:
            contributors_text = contributors_with_names[0]
        elif len(contributors_with_names) == 2:
            contributors_text = (
                f"{contributors_with_names[0]} and {contributors_with_names[1]}"
            )
        else:
            contributors_text = (
                ", ".join(contributors_with_names[:-1])
                + f" and {contributors_with_names[-1]}"
            )

        synopsis += (
            f" – including {len(first_timers)} first time "
            f"contributor{'s' if len(first_timers) > 1 else ''}! "
            f"Congratulations to {contributors_text} for having their first "
            f"commit{'s' if len(first_timers) > 1 else ''} merged into Django "
            f"– welcome on board!"
        )
    else:
        synopsis += "."
    return synopsis


async def save_weekly_report_to_db(db_connection, start_date, end_date, report_data):
    """Save weekly report to database and cleanup old reports"""

    # Insert the new report
    await db_connection.execute(
        """
        INSERT OR REPLACE INTO weekly_reports
        (start_date, end_date, total_prs, first_time_contributors_count, synopsis, date_range_humanized, pr_data)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            start_date,
            end_date,
            report_data["total_prs"],
            report_data["first_time_contributors_count"],
            report_data["synopsis"],
            report_data["date_range_humanized"],
            json.dumps(report_data["prs"]),
        ),
    )

    # Auto-cleanup: keep only last 3 reports
    await db_connection.execute(
        """
        DELETE FROM weekly_reports
        WHERE id NOT IN (
            SELECT id FROM weekly_reports
            ORDER BY created_at DESC
            LIMIT 3
        )
        """
    )

    await db_connection.commit()
    print(f"📊 Saved weekly report to database: {start_date} to {end_date}")

    # Check how many reports we have now
    async with db_connection.execute("SELECT COUNT(*) FROM weekly_reports") as cursor:
        count = (await cursor.fetchone())[0]
        print(f"📈 Database now contains {count} weekly report(s)")


async def fetch_django_pr_summary(db_connection, start_date, end_date):
    """
    Fetches the merged pull requests from the Django repository on GitHub for the last week,
    identifies first-time contributors, and saves to database.
    """

    query = build_github_search_query(start_date, end_date)
    encoded_query = urllib.parse.quote_plus(query)
    search_url = f"https://github.com/search?q={encoded_query}"

    print(f"Fetching PRs merged from {start_date} to {end_date}...")

    merged_prs = fetch_merged_prs(query)

    first_timers = await identify_first_timers(merged_prs, start_date, db_connection)

    synopsis = await generate_synopsis(
        merged_prs,
        first_timers,
        search_url,
    )

    pr_data = []
    for pr in merged_prs:
        modifies_release = pr_modifies_release_files(pr["number"])
        pr_data.append(
            {
                "number": pr["number"],
                "title": pr["title"],
                "author": pr["author"]["login"],
                "url": pr["url"],
                "modifies_release": modifies_release,
            }
        )

    summary_data = {
        "synopsis": synopsis,
        "total_prs": len(merged_prs),
        "first_time_contributors_count": len(first_timers),
        "first_time_contributors": first_timers,
        "prs": pr_data,
        "date_range_humanized": format_date_range_humanized(start_date, end_date),
    }

    # Save to database instead of file
    await save_weekly_report_to_db(db_connection, start_date, end_date, summary_data)

    return summary_data


async def get_latest_weekly_report(db_connection):
    """Get the most recent weekly report from database"""
    async with db_connection.execute(
        """
        SELECT start_date, end_date, total_prs, first_time_contributors_count,
               synopsis, date_range_humanized, pr_data
        FROM weekly_reports
        ORDER BY created_at DESC
        LIMIT 1
        """
    ) as cursor:
        row = await cursor.fetchone()

        if not row:
            return None

        return {
            "start_date": row[0],
            "end_date": row[1],
            "total_prs": row[2],
            "first_time_contributors_count": row[3],
            "synopsis": row[4],
            "date_range_humanized": row[5],
            "prs": json.loads(row[6]) if row[6] else [],
        }
