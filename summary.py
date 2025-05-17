import glob
import json
import os
import urllib.parse

import arrow
import dotenv
from github import Github


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


def pr_modifies_release_files(github_client, pr_number):
    repo = github_client.get_repo("django/django")
    pr = repo.get_pull(pr_number)

    for file in pr.get_files():
        path = file.filename.lower()
        if path.startswith("docs/releases/") and (
            path.endswith(".txt") or path.endswith(".rst")
        ):
            return True
    return False


def generate_synopsis(merged_prs, first_timers, search_url):
    unique_contributors = len({pr.user.login for pr in merged_prs})
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

    start_date, end_date = get_date_range()
    filename = f"{start_date}-{end_date}_pr.json"

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
    pr_data = []
    for pr in merged_prs:
        modifies_release = pr_modifies_release_files(github_client, pr.number)
        pr_data.append(
            {
                "number": pr.number,
                "title": pr.title,
                "author": pr.user.login,
                "url": pr.html_url,
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
