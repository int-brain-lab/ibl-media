"""Small, per-user configuration; secrets and receipts never enter the catalog."""

import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from platformdirs import user_config_path, user_state_path

from .errors import MediaError


def config_dir():
    override = os.environ.get("IBL_MEDIA_HOME")
    return (
        Path(override).expanduser() if override else user_config_path("ibl-media", appauthor=False)
    )


def state_dir():
    override = os.environ.get("IBL_MEDIA_HOME")
    return (
        Path(override).expanduser() / "state"
        if override
        else user_state_path("ibl-media", appauthor=False)
    )


def write_private(path, value):
    """Atomically write JSON with owner-only permissions, including the temporary file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".ibl-media-")
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


@dataclass
class Settings:
    repository: str = "int-brain-lab/ibl-media"
    branch: str = "main"
    folder: str = "1aWO70W8pRQDO6Ow-XFXNOSchAIm6ZolL"
    credit: str = ""
    reuse: str = "Permission required"

    def validate(self):
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", self.repository):
            raise MediaError("Repository must have the form OWNER/REPO.")
        if not re.fullmatch(r"[A-Za-z0-9_-]+", self.folder):
            raise MediaError("Drive destination must be a folder ID, not a browser URL.")
        if not self.branch or not self.reuse.strip():
            raise MediaError("Branch and default reuse terms cannot be empty.")

    @classmethod
    def load(cls):
        path = config_dir() / "config.json"
        try:
            result = cls(**json.loads(path.read_text())) if path.exists() else cls()
        except (ValueError, TypeError) as exc:
            raise MediaError(f"Invalid configuration at {path}: {exc}") from exc
        result.validate()
        return result

    def save(self):
        self.validate()
        write_private(config_dir() / "config.json", asdict(self))


def import_client(path):
    try:
        value = json.loads(Path(path).expanduser().read_text())
        client = value["installed"]
        if not client.get("client_id") or not client.get("client_secret"):
            raise ValueError("missing desktop client ID or client secret")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise MediaError(f"Expected a Google OAuth desktop-client JSON: {exc}") from exc
    write_private(config_dir() / "client.json", value)


def client_path():
    path = config_dir() / "client.json"
    if not path.exists():
        raise MediaError(
            "Google OAuth client is not configured. Follow docs/setup.md, then run "
            "ibl-media login --client-secrets /path/to/client_secret.json."
        )
    return path
