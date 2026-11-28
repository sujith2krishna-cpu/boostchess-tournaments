"""A tiny client for this repository's own GitHub issues and workflow runs (standard library
only). It is used by scripts/health.py from the workflows, with the built-in GITHUB_TOKEN; it
never reads a tournament site (those go through sources/polite.py)."""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.github.com"
USER_AGENT = "BoostchessBot (+https://github.com/sujith2krishna-cpu/boostchess-tournaments)"
TIMEOUT_SECONDS = 30


class GitHub:
    def __init__(self, repository: str, token: str, api: str = API):
        self.repository, self.token, self.api = repository, token, api

    def _call(self, method: str, path: str, data: dict | None = None, params: dict | None = None):
        url = f"{self.api}/repos/{self.repository}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        body = json.dumps(data).encode("utf-8") if data is not None else None
        request = urllib.request.Request(url, data=body, method=method, headers={
            "Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28", "User-Agent": USER_AGENT,
            "Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            text = response.read().decode("utf-8")
        return json.loads(text) if text else None

    # ---- issues ----------------------------------------------------------------------
    def ensure_label(self, name: str, color: str, description: str) -> None:
        """Make the label if the repository does not have it yet (the issues are found by it)."""
        try:
            self._call("GET", f"/labels/{urllib.parse.quote(name)}")
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
            self._call("POST", "/labels", {"name": name, "color": color, "description": description})

    def issues(self, label: str) -> list[dict]:
        """Every issue (open and closed) with this label, newest first; pull requests left out."""
        items = self._call("GET", "/issues", params={"state": "all", "labels": label,
                                                     "per_page": 100, "sort": "created"}) or []
        return [{"number": i["number"], "title": i["title"], "state": i["state"],
                 "body": i.get("body") or "", "url": i.get("html_url")}
                for i in items if "pull_request" not in i]

    def create(self, title: str, body: str, label: str) -> dict:
        issue = self._call("POST", "/issues", {"title": title, "body": body, "labels": [label]})
        return {"number": issue["number"], "url": issue.get("html_url")}

    def comment(self, number: int, body: str) -> str | None:
        return (self._call("POST", f"/issues/{number}/comments", {"body": body}) or {}).get("html_url")

    def edit(self, number: int, **fields) -> None:
        self._call("PATCH", f"/issues/{number}", fields)

    # ---- workflow runs -----------------------------------------------------------------
    def runs(self, workflow_file: str, count: int = 30) -> list[dict]:
        data = self._call("GET", f"/actions/workflows/{workflow_file}/runs",
                          params={"per_page": count}) or {}
        return [{"status": r.get("status"), "conclusion": r.get("conclusion"),
                 "created_at": r.get("created_at"), "event": r.get("event")}
                for r in data.get("workflow_runs", [])]
