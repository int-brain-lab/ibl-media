"""Extract file facts and explicitly supplied provenance, without uploading anything."""

import hashlib
import json
import mimetypes
import re
import subprocess
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from jsonschema import Draft202012Validator, FormatChecker
from PIL import Image, UnidentifiedImageError

from .errors import MediaError


def checksum(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_metadata(path):
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise MediaError(f"Not a file: {path}")
    if path.stat().st_size == 0:
        raise MediaError(f"File is empty: {path.name}")
    result = {
        "filename": path.name,
        "mime_type": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
        "size_bytes": path.stat().st_size,
        "sha256": checksum(path),
    }
    try:
        with Image.open(path) as image:
            result.update(width_px=image.width, height_px=image.height)
    except (UnidentifiedImageError, OSError, ValueError):
        pass
    if result["mime_type"].startswith(("video/", "audio/")):
        try:
            probe = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration:stream=width,height",
                    "-of",
                    "json",
                    str(path),
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if probe.returncode == 0:
                info = json.loads(probe.stdout)
                if "duration" in info.get("format", {}):
                    result["duration_seconds"] = float(info["format"]["duration"])
                for stream in info.get("streams", []):
                    if stream.get("width") and stream.get("height"):
                        result.update(width_px=stream["width"], height_px=stream["height"])
                        break
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass  # ffprobe is optional; missing facts remain absent.
    return path, result


def clean_remote(remote):
    remote = remote.strip()
    scp = re.fullmatch(r"[^@/]+@([^:]+):(.+)", remote)
    if scp:
        host, path = scp.groups()
        return f"https://{host}/{path.removesuffix('.git')}"
    parsed = urlsplit(remote)
    if parsed.scheme not in {"http", "https", "ssh", "git"} or not parsed.netloc:
        return None  # Local filesystem remotes could disclose private directory names.
    return urlunsplit((parsed.scheme, parsed.netloc.rsplit("@", 1)[-1], parsed.path, "", ""))


def source_metadata(path):
    if path is None:
        return None
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise MediaError(f"Source script does not exist: {path}")

    def git(*args):
        try:
            result = subprocess.run(
                ["git", "-C", str(path.parent), *args],
                text=True,
                capture_output=True,
                timeout=10,
            )
            return result.stdout.strip() if result.returncode == 0 else None
        except (OSError, subprocess.TimeoutExpired):
            return None

    root = git("rev-parse", "--show-toplevel")
    result = {"path": path.name, "sha256": checksum(path)}
    if root:
        result["path"] = path.relative_to(root).as_posix()
        commit = git("rev-parse", "HEAD")
        if commit:
            result["commit"] = commit
        status = git("status", "--porcelain")
        if status is not None:
            result["working_tree_dirty"] = bool(status)
        remote = git("config", "--get", "remote.origin.url")
        if remote and (remote := clean_remote(remote)):
            result["repository"] = remote
    return result


def validate_asset(entry):
    schema = json.loads(Path(__file__).with_name("schema.json").read_text())
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(entry), key=lambda x: str(x.path))
    if errors:
        error = errors[0]
        raise MediaError(f"Invalid catalog entry at {list(error.path)}: {error.message}")
    versions = entry["versions"]
    numbers = [v["version"] for v in versions]
    if numbers != list(range(1, len(versions) + 1)):
        raise MediaError("Catalog versions must be ordered and consecutive, starting at 1.")
    uploads = [v["upload_id"] for v in versions]
    if len(uploads) != len(set(uploads)):
        raise MediaError("Catalog contains duplicate upload IDs.")


def validate_asset_id(value):
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,99}", value):
        raise MediaError("Asset ID must contain only letters, digits, underscores, or hyphens.")
    return value
