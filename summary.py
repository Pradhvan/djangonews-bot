import glob
import json
import os
import subprocess
import urllib.parse

import arrow


def get_date_range():
    now = arrow.utcnow()
    last_monday = now.shift(weeks=-1).floor("week")
    last_sunday = last_monday.shift(days=6)
    return last_monday.format("YYYY-MM-DD"), last_sunday.format("YYYY-MM-DD")


def format_date_range_humanized(start, end):
    start = arrow.get(start, "YYYY-MM-DD")
    end = arrow.get(end, "YYYY-MM-DD")
    return f"{start.format('MMMM D')} to {end.format('MMMM D, YYYY')}"


def build_github_search_query(start_date, end_date):
    return f"repo:django/django is:pr is:merged merged:{start_date}..{end_date}"


def send_command(command):
    """Execute a GitHub CLI command and return the JSON result"""
    process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE)
    output, error = process.communicate()

    if error:
        raise Exception(error)

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


def get_full_name_contributors(first_timers):
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


def identify_first_timers(merged_prs, end_date):
    """Identify first-time contributors using GitHub CLI"""
    first_timers = []

    # First, get all PRs for the current period to analyze
    current_prs_by_author = {}
    for pr in merged_prs:
        login = pr["author"]["login"]
        if login not in current_prs_by_author:
            current_prs_by_author[login] = []
        current_prs_by_author[login].append(pr["number"])

    # Now check each author
    for login, pr_numbers in current_prs_by_author.items():
        # Check if this author has previous PRs before the current period
        command = (
            "gh pr list --repo django/django "
            f'-S "is:pr is:merged author:{login}" '
            "--json number,mergedAt"
        )
        all_user_prs = send_command(command)

        # Count PRs before this period
        previous_prs_count = 0
        for pr in all_user_prs:
            # Skip PRs from the current period
            if str(pr["number"]) in map(str, pr_numbers):
                continue

            # Check if the PR was merged before our start date
            if "mergedAt" in pr and pr["mergedAt"]:
                merged_date = pr["mergedAt"].split("T")[0]  # Get just the date part
                if merged_date < end_date.split("T")[0]:
                    previous_prs_count += 1

        # If they have no PRs before this period, they're a first-time contributor
        if previous_prs_count == 0:
            print(
                f"Found new contributor: {login} with {len(all_user_prs)} total PRs, {previous_prs_count} previous PRs"
            )
            first_timers.append(f"[{login}](https://github.com/{login})")

    return first_timers


def pr_modifies_release_files(pr_number):
    """Check if a PR modifies release files using GitHub CLI"""
    command = f"gh pr view {pr_number} --repo django/django " "--json files"
    response = send_command(command)

    for file in response["files"]:
        path = file["path"].lower()
        if path.startswith("docs/releases/") and (
            path.endswith(".txt") or path.endswith(".rst")
        ):
            return True
    return False


def generate_synopsis(merged_prs, first_timers, search_url):
    unique_contributors = len({pr["author"]["login"] for pr in merged_prs})
    synopsis = (
        f"Last week we had [{len(merged_prs)} pull requests]({search_url}) merged into Django by "
        f"{unique_contributors} different contributors"
    )
    if first_timers:
        contributors_with_names = get_full_name_contributors(first_timers)

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
            f" – including {len(first_timers)} first time contributors! "
            f"Congratulations to {contributors_text} for having their first commits merged into Django – welcome on board!"
        )
    else:
        synopsis += "."
    return synopsis


def cleanup_old_json_files(current_filename):
    for f in glob.glob("*_pr.json"):
        if f != current_filename:
            os.remove(f)
            print(f"Deleted old file: {f}")


def fetch_django_pr_summary():
    """
    Fetches the merged pull requests from the Django repository on GitHub for the last week,
    identifies first-time contributors, and generates a summary JSON file.
    """

    start_date, end_date = get_date_range()
    filename = f"{start_date}-{end_date}_pr.json"

    query = build_github_search_query(start_date, end_date)
    encoded_query = urllib.parse.quote_plus(query)
    search_url = f"https://github.com/search?q={encoded_query}"

    print(f"Fetching PRs merged from {start_date} to {end_date}...")

    merged_prs = fetch_merged_prs(query)

    first_timers = identify_first_timers(merged_prs, end_date)

    synopsis = generate_synopsis(
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

    summary_json = {
        "synopsis": synopsis,
        "total_prs": len(merged_prs),
        "first_time_contributors_count": len(first_timers),
        "first_time_contributors": first_timers,
        "prs": pr_data,
        "date_range_humanized": format_date_range_humanized(start_date, end_date),
    }

    with open(filename, "w") as f:
        json.dump(summary_json, f, indent=2)
        print(f"Saved: {filename}")

    cleanup_old_json_files(filename)
