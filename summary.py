import glob
import json
import os
import sys
import urllib.parse

import arrow
import dotenv
from github import Github


def get_date_range():
    now = arrow.utcnow()
    last_monday = now.shift(weeks=-1).floor("week")
    last_sunday = last_monday.shift(days=6)
    return last_monday, last_sunday


def format_date_range_humanized(start, end):
    return f"{start.format('MMMM D')} to {end.format('MMMM D, YYYY')}"


def build_github_search_query(start_date, end_date):
    return f"repo:django/django is:pr is:merged merged:{start_date}..{end_date}"


def fetch_merged_prs(github_client, query):
    return list(github_client.search_issues(query, sort="created", order="desc"))


def identify_first_timers(github_client, merged_prs):
    first_timers = []
    for pr in merged_prs:
        user = pr.user
        query = f"repo:django/django is:pr is:merged author:{user.login}"
        user_merged = github_client.search_issues(query)
        if user_merged.totalCount <= 2:
            first_timers.append(f"[{user.login}](https://github.com/{user.login})")
    return first_timers


def generate_synopsis(merged_prs, first_timers, search_url):
    unique_contributors = len(set(pr.user.login for pr in merged_prs))
    synopsis = (
        f"Last week we had [{len(merged_prs)} pull requests]({search_url}) merged into Django by "
        f"{unique_contributors} different contributors"
    )
    if first_timers:
        synopsis += (
            f" – including {len(first_timers)} first time contributors! "
            f"Congratulations to {', '.join(first_timers)} for having their first commits merged into Django – welcome on board!"
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
    dotenv.load_dotenv()
    github_token = os.getenv("GITHUB_TOKEN")
    github_client = Github(github_token)

    start, end = get_date_range()
    start_date, end_date = start.format("YYYY-MM-DD"), end.format("YYYY-MM-DD")
    filename = f"{start_date}-{end_date}_pr.json"

    if os.path.exists(filename):
        print(f"File exist: {filename}")
        sys.exit(0)

    query = build_github_search_query(start_date, end_date)
    encoded_query = urllib.parse.quote_plus(query)
    search_url = f"https://github.com/search?q={encoded_query}"

    print(f"Fetching PRs merged from {start_date} to {end_date}...")
    merged_prs = fetch_merged_prs(github_client, query)
    first_timers = identify_first_timers(github_client, merged_prs)

    synopsis = generate_synopsis(
        merged_prs,
        first_timers,
        search_url,
    )
    pr_data = [
        {
            "number": pr.number,
            "title": pr.title,
            "author": pr.user.login,
            "url": pr.html_url,
        }
        for pr in merged_prs
    ]

    summary_json = {
        "synopsis": synopsis,
        "total_prs": len(merged_prs),
        "first_time_contributors_count": len(first_timers),
        "first_time_contributors": first_timers,
        "prs": pr_data,
        "date_range_humanized": format_date_range_humanized(start, end),
    }

    if not os.path.exists(filename):
        with open(filename, "w") as f:
            json.dump(summary_json, f, indent=2)
        print(f"Saved: {filename}")
    else:
        print(f"File already exists: {filename}")

    cleanup_old_json_files(filename)
