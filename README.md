# 📰 Django News Bot 🤖

A Discord bot to help coordinate weekly volunteer efforts for the Django News newsletter. Volunteers can claim and unclaim upcoming dates, get reminders, and manage all that through Discord.

---

## 📌 Features

- ✅ List available dates to volunteer
- 🙋 Volunteer for a specific date
- 🙅 Un-volunteer from a date you claimed
- 📅 Auto-runs [`django-news-pr-filter`](https://github.com/sakhawy/django-news-pr-filter/tree/main) and sends results every Monday in your preferred timezone
- 🕓 Timezone-aware reminders via Discord DMs, sent every Monday with data of last week's merged PRs
- 👥 List of claimed dates showing which volunteer picked which date
- 🚨 Sends a reminder in the channel if no one has claimed the current week

---

## Commands
All commands use the prefix `!`. Dates format `YYYY-MM-DD` (example 2025-05-14)

| command         | description                                                           |
|-----------------|-----------------------------------------------------------------------|
| `!available`    | List up to 10 available dates for writing shifts (not yet assigned).  |
| `!volunteer`    | Assign you to a specific date. Date format `YYYY-MM-DD`.              |
| `!unvolunteer`  | Removes you from a specific date.                                     |
| `!mydates`      | Shows all dates assigned to you.                                      |
| `!status`       | Display the status of all assigned dates and who they're assigned to. |
| `!upcoming`     |  List upcoming assigned dates, showing the assignee and status.       |

---

## 🔕 No Spam Policy

We believe in a **no spam policy**.  Every reminder or message is sent **only once**—no repeated pings, no duplicates.
