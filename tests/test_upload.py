import copy
import json

import pytest

from ibl_media import MediaError, upload, uploader
from ibl_media.drive import Drive
from ibl_media.github import GitHubError


class FakeGitHub:
    def __init__(self):
        self.entries = {}
        self.writes = 0
        self.fail = False
        self.ambiguous = False
        self.conflict = False
        self.account = "cyrille"

    def check(self):
        return {"account": self.account, "name": "Cyrille Rossant"}

    def get_asset(self, asset_id):
        entry = self.entries.get(asset_id)
        return copy.deepcopy(entry), str(len(entry["versions"])) if entry else None

    def put_asset(self, entry, sha):
        if self.fail:
            raise GitHubError("Temporarily unavailable", 503)
        if self.conflict:
            self.conflict = False
            other = copy.deepcopy(self.entries[entry["id"]]["versions"][-1])
            other["version"] += 1
            other["upload_id"] = "another-contributor"
            self.entries[entry["id"]]["versions"].append(other)
            raise GitHubError("Concurrent update", 409)
        self.entries[entry["id"]] = copy.deepcopy(entry)
        self.writes += 1
        if self.ambiguous:
            self.ambiguous = False
            raise GitHubError("Final response was lost", 503)


class FakeDrive:
    verify = staticmethod(Drive.verify)

    def __init__(self):
        self.files = {}
        self.reserved = 0
        self.transfers = 0
        self.fail_after_complete = False
        self.fail_on_transfer = None

    def check(self, folder):
        return {"public": True, "can_upload": True}

    def reserve_id(self):
        self.reserved += 1
        return f"drive-{self.reserved}"

    def get_file(self, file_id):
        return self.files.get(file_id)

    def upload_file(self, path, facts, folder, file_id):
        if file_id in self.files:
            return self.verify(self.files[file_id], facts, folder)
        self.transfers += 1
        if self.transfers == self.fail_on_transfer:
            raise OSError("Connection lost before transfer completed")
        item = {
            "id": file_id,
            "parents": [folder],
            "size": str(facts["size_bytes"]),
            "sha256Checksum": facts["sha256"],
        }
        self.files[file_id] = item
        if self.fail_after_complete:
            self.fail_after_complete = False
            raise OSError("Final Drive response lost")
        return self.verify(item, facts, folder)


@pytest.fixture
def services(monkeypatch):
    github, drive = FakeGitHub(), FakeDrive()
    monkeypatch.setattr(uploader, "GitHub", lambda settings: github)
    monkeypatch.setattr(uploader, "Drive", lambda: drive)
    return github, drive


def test_dry_run_needs_no_login_network_or_state(image, monkeypatch, tmp_path):
    def forbidden(*args):
        raise AssertionError("Dry run must not initialize network clients")

    monkeypatch.setattr(uploader, "GitHub", forbidden)
    monkeypatch.setattr(uploader, "Drive", forbidden)
    result = upload(image, title="Coverage", dry_run=True)
    assert result.dry_run and result.url is None
    assert result.metadata["files"][0]["width_px"] == 32
    assert not (tmp_path / "home").exists()


def test_new_upload_and_grouped_sources_have_one_catalog_entry(image, tmp_path, services):
    github, drive = services
    source = tmp_path / "editable.psd"
    source.write_bytes(b"fake editable source, used only by mocked services")
    result = upload(image, source, credit="Creator; Collaborator", dataset="Release 2026")
    entry = github.entries[result.id]
    assert len(entry["versions"]) == 1
    assert len(entry["versions"][0]["files"]) == 2
    assert entry["versions"][0]["dataset"] == "Release 2026"
    assert drive.transfers == 2
    assert result.version == 1 and result.url and result.catalog_url
    assert uploader.pending() == []


def test_metadata_failure_resumes_without_reuploading(image, services):
    github, drive = services
    github.fail = True
    with pytest.raises(MediaError, match="ibl-media resume"):
        upload(image)
    receipt = uploader.pending()[0]
    assert drive.transfers == 1
    github.fail = False
    result = uploader.resume(receipt["upload_id"])
    assert result.version == 1 and drive.transfers == 1
    assert uploader.pending() == []


def test_lost_github_response_does_not_publish_twice(image, services):
    github, drive = services
    github.ambiguous = True
    with pytest.raises(MediaError):
        upload(image)
    receipt = uploader.pending()[0]
    uploader.resume(receipt["upload_id"])
    assert github.writes == 1
    assert drive.transfers == 1
    assert len(github.entries[receipt["asset_id"]]["versions"]) == 1


def test_lost_drive_response_reuses_reserved_id(image, services):
    github, drive = services
    drive.fail_after_complete = True
    with pytest.raises(MediaError):
        upload(image)
    receipt = uploader.pending()[0]
    assert receipt["files"][0]["file_id"] == "drive-1"
    assert "storage" not in receipt["files"][0]
    uploader.resume(receipt["upload_id"])
    assert drive.transfers == drive.reserved == 1


def test_partial_group_resumes_only_incomplete_files(image, tmp_path, services):
    _, drive = services
    other = tmp_path / "source.psd"
    other.write_bytes(b"mock source")
    drive.fail_on_transfer = 2
    with pytest.raises(MediaError):
        upload(image, other)
    receipt = uploader.pending()[0]
    assert receipt["files"][0]["storage"]
    assert "storage" not in receipt["files"][1]
    drive.fail_on_transfer = None
    uploader.resume(receipt["upload_id"])
    assert drive.transfers == 3 and len(drive.files) == 2 and drive.reserved == 2


def test_repeated_command_resumes_matching_pending_job(image, services):
    github, drive = services
    github.fail = True
    with pytest.raises(MediaError):
        upload(image, title="Coverage")
    original = uploader.pending()[0]["asset_id"]
    github.fail = False
    assert upload(image, title="Coverage").id == original
    assert drive.transfers == 1


def test_versions_preserve_prior_credits_and_reuse(image, services):
    github, _ = services
    first = upload(image, credit="First creator", reuse="Permission required")
    second = upload(image, asset=first.id, credit="Second creator", reuse="CC-BY-4.0")
    entry = github.entries[first.id]
    assert second.version == 2
    assert entry["versions"][0]["credit"] == "First creator"
    assert entry["versions"][0]["reuse"] == "Permission required"
    assert entry["versions"][1]["reuse"] == "CC-BY-4.0"
    assert (
        entry["versions"][0]["files"][0]["storage"]["file_id"]
        != entry["versions"][1]["files"][0]["storage"]["file_id"]
    )


def test_concurrent_catalog_update_preserves_other_version(image, services):
    github, _ = services
    original = upload(image)
    github.conflict = True
    result = upload(image, asset=original.id)
    entry = github.entries[original.id]
    assert result.version == 3
    assert entry["versions"][1]["upload_id"] == "another-contributor"
    assert len(entry["versions"]) == 3


def test_unknown_asset_fails_before_media_transfer(image, services):
    _, drive = services
    with pytest.raises(MediaError, match="does not exist"):
        upload(image, asset="unknown")
    assert drive.transfers == 0 and uploader.pending() == []


def test_changed_file_and_wrong_account_cannot_resume(image, services):
    github, drive = services
    drive.fail_on_transfer = 1
    with pytest.raises(MediaError):
        upload(image)
    receipt = uploader.pending()[0]
    image.write_bytes(b"changed")
    with pytest.raises(MediaError, match="missing or changed"):
        uploader.resume(receipt["upload_id"])
    github.account = "other-user"
    with pytest.raises(MediaError, match="GitHub account cyrille"):
        uploader.resume(receipt["upload_id"])
    assert drive.transfers == 1


def test_completed_upload_can_resume_after_local_file_deleted(image, services):
    github, drive = services
    github.fail = True
    with pytest.raises(MediaError):
        upload(image)
    receipt = uploader.pending()[0]
    image.unlink()
    github.fail = False
    uploader.resume(receipt["upload_id"])
    assert drive.transfers == 1


def test_receipts_are_owner_only(image, services):
    github, _ = services
    github.fail = True
    with pytest.raises(MediaError):
        upload(image)
    path = next(uploader.pending_dir().glob("*.json"))
    assert path.stat().st_mode & 0o777 == 0o600
    assert json.loads(path.read_text())["uploader"] == "cyrille"
