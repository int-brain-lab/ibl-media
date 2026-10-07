from unittest.mock import MagicMock

import httplib2
import pytest
from googleapiclient.errors import HttpError

from ibl_media import MediaError
from ibl_media.drive import Drive
from ibl_media.metadata import file_metadata


def test_drive_adapter_recovers_a_lost_final_response(image):
    _, facts = file_metadata(image)
    service = MagicMock()
    remote = {
        "id": "reserved-id",
        "parents": ["folder"],
        "size": facts["size_bytes"],
        "sha256Checksum": facts["sha256"],
    }
    service.files().get().execute.side_effect = [
        HttpError(httplib2.Response({"status": "404"}), b'{"error": "not found"}'),
        remote,
    ]
    service.files().create().next_chunk.side_effect = OSError("Final response lost")
    drive = Drive(service)
    result = drive.upload_file(image, facts, "folder", "reserved-id")
    assert result["file_id"] == "reserved-id"
    created = service.files().create.call_args.kwargs
    assert created["body"]["id"] == "reserved-id"
    assert created["supportsAllDrives"] is True


def test_private_folder_blocks_transfer_before_any_create():
    service = MagicMock()
    service.files().get().execute.return_value = {
        "id": "folder",
        "name": "Media",
        "mimeType": "application/vnd.google-apps.folder",
        "capabilities": {"canAddChildren": True},
        "driveId": "shared-drive",
    }
    service.permissions().list().execute.return_value = {
        "permissions": [{"type": "group", "role": "writer"}],
    }
    drive = Drive(service)
    assert drive.folder_info("folder")["shared_drive"] is True
    with pytest.raises(MediaError, match="not public"):
        drive.check("folder")
    assert not service.files().create.called


def test_folder_permissions_are_paginated():
    service = MagicMock()
    service.files().get().execute.return_value = {
        "id": "folder",
        "name": "Media",
        "mimeType": "application/vnd.google-apps.folder",
        "capabilities": {"canAddChildren": True},
    }
    service.permissions().list().execute.side_effect = [
        {"permissions": [{"type": "group", "role": "writer"}], "nextPageToken": "next"},
        {"permissions": [{"type": "anyone", "role": "reader"}]},
    ]
    assert Drive(service).check("folder")["public"] is True


def test_folder_creation_recovers_a_lost_response():
    service = MagicMock()
    service.files().get().execute.side_effect = [
        HttpError(httplib2.Response({"status": "404"}), b'{"error": "not found"}'),
        {
            "id": "reserved-folder",
            "mimeType": "application/vnd.google-apps.folder",
            "parents": ["collection"],
        },
    ]
    service.files().create().execute.side_effect = OSError("Response lost")
    service.files().create.reset_mock()
    drive = Drive(service)
    with pytest.raises(OSError):
        drive.ensure_folder("collection", "asset", "reserved-folder")
    assert drive.ensure_folder("collection", "asset", "reserved-folder") == "reserved-folder"
    assert service.files().create.call_count == 1
    created = service.files().create.call_args.kwargs
    assert created["body"] == {
        "id": "reserved-folder",
        "name": "asset",
        "mimeType": "application/vnd.google-apps.folder",
        "parents": ["collection"],
    }
    assert created["supportsAllDrives"] is True


def test_folder_search_includes_shared_drives_and_all_pages():
    service = MagicMock()
    service.files().list().execute.side_effect = [
        {"files": [], "nextPageToken": "next"},
        {"files": [{"id": "asset-folder"}]},
    ]
    assert Drive(service).find_folder("collection", "asset") == "asset-folder"
    options = service.files().list.call_args.kwargs
    assert options["pageToken"] == "next"
    assert options["supportsAllDrives"] and options["includeItemsFromAllDrives"]
    assert "'collection' in parents" in options["q"]
    assert "trashed = false" in options["q"]


def test_resume_rejects_a_moved_or_deleted_upload_folder():
    service = MagicMock()
    service.files().get().execute.return_value = {
        "id": "folder",
        "mimeType": "application/vnd.google-apps.folder",
        "parents": ["elsewhere"],
    }
    with pytest.raises(MediaError, match="expected parent"):
        Drive(service).ensure_folder("collection", "asset", "folder")
    assert not service.files().create.called
