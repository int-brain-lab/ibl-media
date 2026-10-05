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
