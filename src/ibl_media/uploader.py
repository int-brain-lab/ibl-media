"""Upload receipts bridge Drive and GitHub without duplicate completed uploads."""

import copy
import hashlib
import json
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

from filelock import FileLock, Timeout

from .config import Settings, state_dir, write_private
from .drive import Drive
from .errors import MediaError
from .github import GitHub, GitHubError
from .metadata import checksum, file_metadata, source_metadata, validate_asset, validate_asset_id


@dataclass
class UploadResult:
    id: str
    version: int | None
    url: str | None
    catalog_url: str | None
    dry_run: bool = False
    metadata: dict | None = None


def pending_dir():
    path = state_dir() / "pending"
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


def pending():
    return [json.loads(path.read_text()) for path in sorted(pending_dir().glob("*.json"))]


def _catalog_url(settings, asset_id):
    return (
        f"https://github.com/{settings.repository}/blob/"
        f"{quote(settings.branch, safe='')}/assets/{asset_id}.yaml"
    )


def _publish(github, receipt):
    for attempt in range(4):
        entry, sha = github.get_asset(receipt["asset_id"])
        if entry:
            validate_asset(entry)
            if entry["id"] != receipt["asset_id"]:
                raise MediaError("Catalog ID does not match its filename.")
            for version in entry["versions"]:
                if version["upload_id"] == receipt["upload_id"]:
                    return version  # A previous request succeeded but its response was lost.
        elif receipt["updating"]:
            raise MediaError("The existing asset disappeared; publication stopped.")
        else:
            entry = {
                "schema_version": 1,
                "id": receipt["asset_id"],
                **receipt["header"],
                "versions": [],
            }
        entry = copy.deepcopy(entry)
        for key, value in receipt["overrides"].items():
            if value is not None:
                entry[key] = value
        version = {
            "version": len(entry["versions"]) + 1,
            "upload_id": receipt["upload_id"],
            "uploaded_at": receipt["uploaded_at"],
            "uploaded_by": {"github": receipt["uploader"]},
            "credit": receipt["header"]["credit"],
            "reuse": receipt["header"]["reuse"],
            **receipt["context"],
            "files": [{**item["facts"], "storage": item["storage"]} for item in receipt["files"]],
        }
        entry["versions"].append(version)
        validate_asset(entry)
        try:
            github.put_asset(entry, sha)
            return version
        except GitHubError as exc:
            if exc.status not in {409, 422} or attempt == 3:
                raise
    raise MediaError("Could not publish metadata after concurrent updates.")


def _finish(receipt, receipt_path, settings, github, drive):
    info = github.check()
    if info["account"] != receipt["uploader"]:
        raise MediaError(f"Resume this upload using GitHub account {receipt['uploader']}.")
    drive.check(settings.folder)
    # Validate all remaining local files before sending any bytes.
    for item in receipt["files"]:
        if not item.get("storage"):
            path = Path(item["path"])
            if not path.is_file() or checksum(path) != item["facts"]["sha256"]:
                raise MediaError(f"Original upload file is missing or changed: {path.name}")
    for item in receipt["files"]:
        if item.get("storage"):
            remote = drive.get_file(item["file_id"])
            if not remote:
                raise MediaError("A completed Drive file has disappeared; publication stopped.")
            drive.verify(remote, item["facts"], settings.folder)
            continue
        if not item.get("file_id"):
            item["file_id"] = drive.reserve_id()
            write_private(receipt_path, receipt)  # Persist identity before starting the transfer.
        item["storage"] = drive.upload_file(
            Path(item["path"]),
            item["facts"],
            settings.folder,
            item["file_id"],
        )
        write_private(receipt_path, receipt)
    version = _publish(github, receipt)
    result = UploadResult(
        id=receipt["asset_id"],
        version=version["version"],
        url=version["files"][0]["storage"]["url"],
        catalog_url=_catalog_url(settings, receipt["asset_id"]),
    )
    archive = state_dir() / "completed" / f"{receipt['upload_id']}.json"
    write_private(archive, {**receipt, "result": asdict(result)})
    receipt_path.unlink()
    return result


def _execute(receipt_path, receipt, settings, github, drive):
    try:
        return _finish(receipt, receipt_path, settings, github, drive)
    except Exception as exc:
        raise MediaError(
            f"Upload is incomplete: {exc}\n"
            f"Resume with: ibl-media resume {receipt['upload_id']}\n"
            "Completed files and the pending receipt are retained."
        ) from exc


def upload(
    *files,
    title=None,
    description=None,
    credit=None,
    reuse=None,
    source=None,
    dataset=None,
    asset=None,
    dry_run=False,
):
    """Publish files as one asset; dry_run extracts metadata without network access or writes."""
    settings = Settings.load()
    if not files:
        raise MediaError("Supply at least one file to upload.")
    if asset:
        validate_asset_id(asset)
    for name, value in {"title": title, "credit": credit, "reuse": reuse}.items():
        if value is not None and not value.strip():
            raise MediaError(f"{name.capitalize()} cannot be empty.")
    prepared = [file_metadata(path) for path in files]
    if len({facts["filename"] for _, facts in prepared}) != len(prepared):
        raise MediaError("Files in one upload must have distinct filenames.")
    context = {
        key: value
        for key, value in {
            "description": description,
            "dataset": dataset,
            "source": source_metadata(source),
        }.items()
        if value is not None
    }
    inferred_title = prepared[0][0].stem.replace("_", " ").replace("-", " ")
    if dry_run:
        return UploadResult(
            id=asset or "(assigned on upload)",
            version=None,
            url=None,
            catalog_url=None,
            dry_run=True,
            metadata={
                "repository": settings.repository,
                "branch": settings.branch,
                "folder": settings.folder,
                "asset": asset,
                "title": title or inferred_title,
                "credit": credit or settings.credit or "(resolved from GitHub on upload)",
                "reuse": reuse or settings.reuse,
                **context,
                "files": [facts for _, facts in prepared],
            },
        )

    github = GitHub(settings)
    user = github.check()
    fingerprint_data = {
        "repository": settings.repository,
        "branch": settings.branch,
        "folder": settings.folder,
        "uploader": user["account"],
        "asset": asset,
        "files": [{"path": str(path), "facts": facts} for path, facts in prepared],
        "title": title,
        "credit": credit,
        "reuse": reuse,
        "context": context,
    }
    fingerprint = hashlib.sha256(json.dumps(fingerprint_data, sort_keys=True).encode()).hexdigest()
    receipt_path = pending_dir() / f"{fingerprint}.json"
    try:
        with FileLock(str(receipt_path.with_suffix(".lock")), timeout=0):
            if receipt_path.exists():
                receipt = json.loads(receipt_path.read_text())
            else:
                existing, _ = github.get_asset(asset) if asset else (None, None)
                if asset and existing is None:
                    raise MediaError(f"Asset {asset} does not exist; omit --asset for a new asset.")
                if existing:
                    validate_asset(existing)
                    if existing["id"] != asset:
                        raise MediaError("Catalog ID does not match its filename.")
                header = {
                    "title": title or (existing["title"] if existing else inferred_title),
                    "credit": credit
                    or (existing["credit"] if existing else settings.credit or user["name"]),
                    "reuse": reuse or (existing["reuse"] if existing else settings.reuse),
                }
                drive = Drive()
                drive.check(settings.folder)  # Fail before recording a job or uploading media.
                receipt = {
                    "upload_id": uuid.uuid4().hex,
                    "asset_id": asset or uuid.uuid4().hex,
                    "updating": bool(asset),
                    "uploader": user["account"],
                    "uploaded_at": datetime.now(UTC).isoformat(),
                    "target": {
                        key: getattr(settings, key) for key in ("repository", "branch", "folder")
                    },
                    "header": header,
                    "overrides": {"title": title, "credit": credit, "reuse": reuse},
                    "context": context,
                    "files": [{"path": str(path), "facts": facts} for path, facts in prepared],
                }
                write_private(receipt_path, receipt)
                return _execute(receipt_path, receipt, settings, github, drive)
            return _execute(receipt_path, receipt, settings, github, Drive())
    except Timeout as exc:
        raise MediaError("This upload is already running in another process.") from exc


def resume(upload_id):
    validate_asset_id(upload_id)
    settings = Settings.load()
    for path in pending_dir().glob("*.json"):
        receipt = json.loads(path.read_text())
        if receipt["upload_id"] != upload_id:
            continue
        if receipt["target"] != {
            key: getattr(settings, key) for key in ("repository", "branch", "folder")
        }:
            raise MediaError(
                "Configuration differs from the receipt's destination; restore it to resume."
            )
        try:
            with FileLock(str(path.with_suffix(".lock")), timeout=0):
                # Another process may have completed between discovery and locking.
                if not path.exists():
                    raise MediaError("Upload has already completed; check the catalog.")
                receipt = json.loads(path.read_text())
                return _execute(path, receipt, settings, GitHub(settings), Drive())
        except Timeout as exc:
            raise MediaError("This upload is already running in another process.") from exc
    raise MediaError(f"No pending upload found with ID {upload_id}.")
