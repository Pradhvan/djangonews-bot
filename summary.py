import glob
import json
import os
import re
import subprocess
import urllib.parse
from shlex import split as shlex_split

import arrow


def format_date_range_humanized(start, end):
    start = arrow.get(start, "YYYY-MM-DD")
    end = arrow.get(end, "YYYY-MM-DD")
    return f"{start.format('MMMM D')} to {end.format('MMMM D, YYYY')}"


def validate_pr_filename(filename, start_date=None, end_date=None):
    """
    Validates a PR summary filename for security and format correctness.

    Args:
        filename: The filename to validate
        start_date: Optional start date to check for consistency with filename
        end_date: Optional end date to check for consistency with filename

    Returns:
        A safe filename (basename only) if valid

    Raises:
        ValueError: If the filename is invalid or doesn't match the expected format
    """
    # Check if filename has the correct format
    pattern = r"^\d{4}-\d{2}-\d{2}-\d{4}-\d{2}-\d{2}_pr\.json$"
    if not re.match(pattern, os.path.basename(filename)):
        raise ValueError(
            f"Invalid filename format: {filename}. Expected format: YYYY-MM-DD-YYYY-MM-DD_pr.json"
        )

    # If dates are provided, ensure filename is consistent with them
    if start_date and end_date:
        expected_filename = f"{start_date}-{end_date}_pr.json"
        if os.path.basename(filename) != expected_filename:
            raise ValueError(
                f"Filename {filename} doesn't match the expected format for dates {start_date} to {end_date}"
            )

    # Return only the basename to prevent path traversal
    return os.path.basename(filename)


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


def get_django_welcome_message():
    """Get Django's current new contributor message, with caching"""
    cache_file = "django_welcome_cache.json"

    # Get current SHA from GitHub first
    try:
        command = "gh api repos/django/django/contents/.github/workflows/new_contributor_pr.yml"
        result = send_command(command)
        current_sha = result.get("sha", "unknown")
    except Exception as e:
        print(f"Error getting current SHA: {e}")
        return ""

    # Check cache and compare SHA
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r") as f:
                cached_data = json.load(f)

            cached_sha = cached_data.get("commit_sha", "")

            if cached_sha == current_sha and current_sha != "unknown":
                print(f"Cache up-to-date (SHA: {current_sha[:8]}...)")
                return cached_data.get("pr_message", "")
            else:
                print(f"SHA changed: {cached_sha[:8]}... → {current_sha[:8]}...")
        except Exception as e:
            print(f"Cache read error: {e}")

    # Fetch from GitHub (cache missing or SHA changed)
    try:
        print("Fetching Django workflow...")

        # Decode and find pr-message
        import base64

        content = base64.b64decode(result["content"]).decode("utf-8")

        # Parse pr-message
        lines = content.split("\n")
        pr_message = ""

        for i, line in enumerate(lines):
            if "pr-message:" in line:
                if "|" in line:  # Multi-line YAML
                    # Read the actual message content
                    message_parts = []
                    for j in range(i + 1, len(lines)):
                        next_line = lines[j]
                        if next_line.strip() and not next_line.startswith("  "):
                            break
                        if next_line.strip():
                            message_parts.append(next_line.strip())
                    pr_message = " ".join(message_parts)
                else:  # Single-line
                    pr_message = (
                        line.split("pr-message:")[1].strip().strip('"').strip("'")
                    )
                break

        # Save to cache
        cache_data = {
            "pr_message": pr_message,
            "commit_sha": current_sha,
            "last_updated": arrow.utcnow().isoformat(),
        }
        with open(cache_file, "w") as f:
            json.dump(cache_data, f, indent=2)

        print(f"Cached pr-message: {pr_message[:50]}...")
        return pr_message

    except Exception as e:
        print(f"Error fetching Django workflow: {e}")
        return ""


def identify_first_timers(merged_prs):
    """Identify first-time contributors by checking Django's GitHub Actions bot comments"""
    first_timers = []

    # Get Django's cached pr-message
    pr_message = get_django_welcome_message()

    print(
        "Checking Django's GitHub Actions for first-time contributor determinations..."
    )
    print(f"Looking for pr-message: {pr_message[:50]}...")

    for pr in merged_prs:
        pr_number = pr["number"]
        author = pr["author"]["login"]

        print(f"Checking for Django's welcome message on PR #{pr_number} by {author}")

        try:
            # Get all comments/reviews on the PR
            command = (
                f"gh pr view {pr_number} --repo django/django --json comments,reviews"
            )
            result = send_command(command)

            is_first_timer = False

            # Check comments for GitHub Actions bot
            for comment in result.get("comments", []):
                author_login = comment.get("author", {}).get("login", "")
                body = comment.get("body", "")

                # Look for Django's actual pr-message in comments
                if (
                    author_login == "github-actions[bot]"
                    and pr_message
                    and pr_message in body
                ):
                    is_first_timer = True
                    print(f"Found Django's welcome message for {author}")
                    break

            # Also check reviews (the bot might comment as a review)
            if not is_first_timer:
                for review in result.get("reviews", []):
                    author_login = review.get("author", {}).get("login", "")
                    body = review.get("body", "")

                    if (
                        author_login == "github-actions[bot]"
                        and pr_message
                        and pr_message in body
                    ):
                        is_first_timer = True
                        print(f"Found Django's welcome review for {author}")
                        break

            if is_first_timer:
                first_timers.append(f"[{author}](https://github.com/{author})")
            else:
                print(f"No Django welcome message found for {author}")

        except Exception as e:
            print(f"Error checking {author}: {str(e)}")
            # Fallback: don't include them if we can't verify

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
            f" – including {len(first_timers)} first time contributor{'s' if len(first_timers) > 1 else ''}! "
            f"Congratulations to {contributors_text} for having their first "
            f"commit{'s' if len(first_timers) > 1 else ''} merged into Django – welcome on board!"
        )
    else:
        synopsis += "."
    return synopsis


def cleanup_old_json_files(current_filename):
    # Ensure we're only dealing with the basename to prevent directory traversal

    for f in glob.glob("*_pr.json"):
        # Only delete files that match our expected pattern and aren't the current file
        try:
            if f != current_filename and os.path.dirname(f) == "":
                # Validate the file before deleting it
                validate_pr_filename(f)
                os.remove(f)
                print(f"Deleted old file: {f}")
        except ValueError:
            # Skip files that don't match our expected format
            print(f"Skipping invalid file: {f}")
        except Exception as e:
            print(f"Error deleting file {f}: {str(e)}")


def fetch_django_pr_summary(start_date, end_date, filename):
    """
    Fetches the merged pull requests from the Django repository on GitHub for the last week,
    identifies first-time contributors, and generates a summary JSON file.
    """

    query = build_github_search_query(start_date, end_date)
    encoded_query = urllib.parse.quote_plus(query)
    search_url = f"https://github.com/search?q={encoded_query}"

    print(f"Fetching PRs merged from {start_date} to {end_date}...")

    merged_prs = fetch_merged_prs(query)

    first_timers = identify_first_timers(merged_prs)

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

    # Validate the filename with error handling
    try:
        safe_filename = validate_pr_filename(filename, start_date, end_date)
    except ValueError as e:
        # Log the error but continue with the original filename
        print(f"Warning: {str(e)}")
        print(f"Using original filename: {filename} as fallback")
        safe_filename = os.path.basename(filename)

    # Use the safe filename for writing
    with open(safe_filename, "w") as f:
        json.dump(summary_json, f, indent=2)
        print(f"Saved: {safe_filename}")

    cleanup_old_json_files(safe_filename)
