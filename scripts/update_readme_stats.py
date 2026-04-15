#!/usr/bin/env python3
"""
Updates <!-- STATS:AUTO:START --> ... <!-- STATS:AUTO:END --> in README.md
using GitHub GraphQL (contributions in rolling windows). Requires GITHUB_TOKEN.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone


GRAPHQL = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      totalCommitContributions
      totalPullRequestContributions
      totalPullRequestReviewContributions
      commitContributionsByRepository {
        repository {
          nameWithOwner
          primaryLanguage { name }
        }
        contributions {
          totalCount
        }
      }
    }
  }
}
"""


def graphql(query: str, variables: dict) -> dict:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        print("GITHUB_TOKEN missing", file=sys.stderr)
        sys.exit(1)
    body = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "readme-stats-updater",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(e.read().decode("utf-8", errors="replace"), file=sys.stderr)
        raise


def collect_window(login: str, start: datetime, end: datetime) -> dict:
    data = graphql(
        GRAPHQL,
        {
            "login": login,
            "from": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "to": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
    )
    if data.get("errors"):
        print(json.dumps(data["errors"], indent=2), file=sys.stderr)
        sys.exit(1)
    coll = data["data"]["user"]["contributionsCollection"]
    repos = coll.get("commitContributionsByRepository") or []
    langs = set()
    for row in repos:
        pl = row.get("repository") or {}
        lang = (pl.get("primaryLanguage") or {}) or {}
        name = lang.get("name")
        if name:
            langs.add(name)
    return {
        "commits": coll["totalCommitContributions"],
        "prs": coll["totalPullRequestContributions"],
        "reviews": coll["totalPullRequestReviewContributions"],
        "distinct_repos": len(repos),
        "distinct_languages": len(langs),
        "languages": sorted(langs),
    }


def build_table(login: str, w30: dict, w365: dict, generated_at: str) -> str:
    langs_y = ", ".join(w365["languages"]) if w365["languages"] else "—"
    # No github-readme-stats images (public instance is often rate-limited). Table only.
    return f"""### Activity (auto-updated)

<sub>Last refresh: {generated_at} UTC · windows: last 30 / last 365 days</sub>

| Window | Commits | PRs opened | PR reviews | Repos with commits | Distinct languages |
|--------|--------:|-----------:|-----------:|-------------------:|-------------------:|
| **Last 30 days** | {w30["commits"]} | {w30["prs"]} | {w30["reviews"]} | {w30["distinct_repos"]} | {w30["distinct_languages"]} |
| **Last 365 days** | {w365["commits"]} | {w365["prs"]} | {w365["reviews"]} | {w365["distinct_repos"]} | {w365["distinct_languages"]} |

<details>
<summary><b>Languages (365d — primary language per repo where you had commits)</b></summary>

{langs_y}

</details>
"""


def main() -> None:
    login = os.environ.get("GH_USER", "toprak1771")
    readme_path = os.environ.get("README_PATH", "README.md")
    now = datetime.now(timezone.utc)
    start_30 = now - timedelta(days=30)
    start_365 = now - timedelta(days=365)

    w30 = collect_window(login, start_30, now)
    w365 = collect_window(login, start_365, now)

    gen = now.strftime("%Y-%m-%d %H:%M")
    block = build_table(login, w30, w365, gen)

    path = readme_path
    if not os.path.isfile(path):
        print(f"README not found: {path}", file=sys.stderr)
        sys.exit(1)

    text = open(path, encoding="utf-8").read()
    pattern = (
        r"<!-- STATS:AUTO:START -->.*?<!-- STATS:AUTO:END -->"
    )
    replacement = f"<!-- STATS:AUTO:START -->\n{block}\n<!-- STATS:AUTO:END -->"
    if not re.search(pattern, text, flags=re.DOTALL):
        print(
            "Markers <!-- STATS:AUTO:START --> ... <!-- STATS:AUTO:END --> not found in README.md",
            file=sys.stderr,
        )
        sys.exit(1)
    new_text = re.sub(pattern, replacement, text, count=1, flags=re.DOTALL)
    open(path, "w", encoding="utf-8").write(new_text)
    print("README stats section updated.")


if __name__ == "__main__":
    main()
