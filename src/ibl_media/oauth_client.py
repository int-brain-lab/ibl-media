"""Retrieve the shared desktop client through authenticated, private GitHub distribution."""

import hashlib
import json
import subprocess
from pathlib import Path
from urllib.parse import quote

from .config import Settings, client_path, config_dir, write_private
from .errors import MediaError
from .github import GitHub

MANIFEST_PATH = Path(__file__).with_name("oauth_client_manifest.json")
MAX_CLIENT_BYTES = 65_536


def manifest():
    return json.loads(MANIFEST_PATH.read_text())


def download_asset(repository, asset_id):
    """Delegate authenticated download and redirect handling to GitHub CLI."""
    try:
        result = subprocess.run(
            [
                "gh",
                "api",
                "--hostname",
                "github.com",
                f"repos/{repository}/releases/assets/{asset_id}",
                "-H",
                "Accept: application/octet-stream",
            ],
            capture_output=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MediaError(
            "Could not download the Google application configuration. Retry login."
        ) from exc
    if result.returncode:
        # Do not print response bodies or signed download URLs.
        raise MediaError("Could not download the Google application configuration. Retry login.")
    return result.stdout


def validate_download(data, expected):
    if len(data) > MAX_CLIENT_BYTES or hashlib.sha256(data).hexdigest() != expected["sha256"]:
        raise MediaError(
            "Google application configuration failed its checksum check. "
            "Nothing was saved; contact an IBL maintainer."
        )
    try:
        value = json.loads(data)
        client = value["installed"]
        allowed = {
            "client_id",
            "client_secret",
            "project_id",
            "auth_uri",
            "token_uri",
            "auth_provider_x509_cert_url",
            "redirect_uris",
        }
        valid = (
            set(value) == {"installed"}
            and set(client) <= allowed
            and client["client_id"] == expected["client_id"]
            and client["project_id"] == expected["project_id"]
            and isinstance(client["client_secret"], str)
            and bool(client["client_secret"])
            and client["auth_uri"] == "https://accounts.google.com/o/oauth2/auth"
            and client["token_uri"] == "https://oauth2.googleapis.com/token"
        )
    except (ValueError, KeyError, TypeError):
        valid = False
    if not valid:
        raise MediaError(
            "Unexpected Google application configuration. Nothing was saved; "
            "contact an IBL maintainer."
        )
    return value


def ensure_client():
    path = config_dir() / "client.json"
    if path.exists():
        return client_path()
    expected = manifest()
    repository = expected["repository"]
    github = GitHub(Settings(repository=repository))
    try:
        info = github.api(github.base)
        if info.get("visibility") != "private" or info.get("private") is not True:
            raise MediaError("The configuration repository must remain private.")
        release = github.api(f"{github.base}/releases/tags/{quote(expected['tag'], safe='')}")
        assets = [asset for asset in release["assets"] if asset["name"] == expected["asset"]]
        if len(assets) != 1 or not 0 < assets[0]["size"] <= MAX_CLIENT_BYTES:
            raise MediaError("The expected configuration attachment is missing or invalid.")
        data = download_asset(repository, assets[0]["id"])
    except (MediaError, KeyError, TypeError) as exc:
        detail = str(exc) if isinstance(exc, MediaError) and not hasattr(exc, "status") else ""
        raise MediaError(
            f"Cannot retrieve Google application configuration from {repository}. "
            "Run gh auth login --hostname github.com, accept any pending repository "
            "invitation, and authorize organization SSO if required. An IBL maintainer "
            "must grant your GitHub account Read access. " + detail
        ) from exc
    value = validate_download(data, expected)
    write_private(path, value)
    return path
