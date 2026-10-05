"""Catalog operations through the user's existing GitHub CLI authentication."""

import base64
import json
import re
import subprocess
from urllib.parse import quote

import yaml

from .errors import MediaError


class GitHubError(MediaError):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class GitHub:
    def __init__(self, settings):
        self.settings = settings

    def api(self, endpoint, method="GET", payload=None):
        command = ["gh", "api", "--method", method, endpoint]
        if payload is not None:
            command.extend(["--input", "-"])
        try:
            result = subprocess.run(
                command,
                input=json.dumps(payload) if payload is not None else None,
                text=True,
                capture_output=True,
                timeout=60,
            )
        except FileNotFoundError as exc:
            raise MediaError("Install GitHub CLI (gh), then run gh auth login.") from exc
        except subprocess.TimeoutExpired as exc:
            raise GitHubError("GitHub request timed out. Retry the command.") from exc
        if result.returncode:
            status = re.search(r"HTTP (\d+)", result.stderr)
            raise GitHubError(
                f"GitHub request failed: {result.stderr.strip()}",
                int(status[1]) if status else None,
            )
        return json.loads(result.stdout) if result.stdout.strip() else None

    @property
    def base(self):
        return f"repos/{self.settings.repository}"

    def check(self):
        repository = self.api(self.base)
        user = self.api("user")
        if not repository.get("permissions", {}).get("push"):
            raise MediaError(
                f"GitHub account {user['login']} needs Write access to {self.settings.repository}."
            )
        branch = self.api(f"{self.base}/branches/{quote(self.settings.branch, safe='')}")
        return {
            "account": user["login"],
            "name": user.get("name") or user["login"],
            "repository": repository["full_name"],
            "branch": branch["name"],
            "protected": branch["protected"],
        }

    def get_asset(self, asset_id):
        endpoint = f"{self.base}/contents/assets/{asset_id}.yaml"
        try:
            response = self.api(f"{endpoint}?ref={quote(self.settings.branch, safe='')}")
        except GitHubError as exc:
            if exc.status == 404:
                return None, None
            raise
        if response.get("encoding") != "base64" or response.get("size", 0) > 1_000_000:
            raise MediaError(f"Unsupported or oversized catalog entry: {asset_id}")
        try:
            content = yaml.safe_load(base64.b64decode(response["content"]).decode())
        except (ValueError, yaml.YAMLError, UnicodeError) as exc:
            raise MediaError(f"Invalid catalog YAML: {asset_id}") from exc
        return content, response["sha"]

    def put_asset(self, entry, sha):
        content = yaml.safe_dump(entry, sort_keys=False, allow_unicode=True)
        if len(content.encode()) > 1_000_000:
            raise MediaError("Catalog entry exceeds the supported 1 MB size.")
        payload = {
            "message": f"Catalog {entry['id']} version {entry['versions'][-1]['version']}",
            "branch": self.settings.branch,
            "content": base64.b64encode(content.encode()).decode(),
        }
        if sha:
            payload["sha"] = sha
        return self.api(f"{self.base}/contents/assets/{entry['id']}.yaml", "PUT", payload)

    def list_assets(self):
        try:
            entries = self.api(
                f"{self.base}/contents/assets?ref={quote(self.settings.branch, safe='')}"
            )
        except GitHubError as exc:
            if exc.status == 404:
                return []
            raise
        return [
            x["name"][:-5] for x in entries if x["type"] == "file" and x["name"].endswith(".yaml")
        ]
