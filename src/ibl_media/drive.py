"""Drive uploads never change sharing; the collection folder sets access."""

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from .errors import MediaError
from .google_auth import credentials
from .metadata import checksum

FIELDS = "id,name,parents,size,sha256Checksum,webViewLink"


class Drive:
    def __init__(self, service=None):
        self.service = service or build(
            "drive", "v3", credentials=credentials(), cache_discovery=False
        )

    def folder_info(self, folder):
        try:
            item = (
                self.service.files()
                .get(
                    fileId=folder,
                    supportsAllDrives=True,
                    fields="id,name,mimeType,driveId,capabilities(canAddChildren),trashed",
                )
                .execute()
            )
            permissions = []
            token = None
            while True:
                page = (
                    self.service.permissions()
                    .list(
                        fileId=folder,
                        supportsAllDrives=True,
                        pageToken=token,
                        fields="nextPageToken,permissions(type,role)",
                    )
                    .execute()
                )
                permissions.extend(page.get("permissions", []))
                token = page.get("nextPageToken")
                if not token:
                    break
        except HttpError as exc:
            raise MediaError(
                "Cannot inspect the Drive destination. Check your account's folder access, "
                "enable the Drive API, and select the folder with ibl-media login."
            ) from exc
        if item["mimeType"] != "application/vnd.google-apps.folder" or item.get("trashed"):
            raise MediaError("The configured Drive destination is not an active folder.")
        return {
            "folder": item["id"],
            "name": item["name"],
            "shared_drive": bool(item.get("driveId")),
            "can_upload": item.get("capabilities", {}).get("canAddChildren", False),
            "public": any(
                p["type"] == "anyone" and p["role"] in {"reader", "writer"} for p in permissions
            ),
        }

    def check(self, folder):
        info = self.folder_info(folder)
        if not info["can_upload"]:
            raise MediaError("Your Google account needs upload access to the collection folder.")
        if not info["public"]:
            raise MediaError(
                "The collection folder is not public. A maintainer must set "
                "Anyone with the link: Viewer before publishing media."
            )
        return info

    def reserve_id(self):
        return (
            self.service.files()
            .generateIds(count=1, space="drive", type="files")
            .execute()["ids"][0]
        )

    def get_file(self, file_id):
        try:
            return (
                self.service.files()
                .get(
                    fileId=file_id,
                    supportsAllDrives=True,
                    fields=FIELDS,
                )
                .execute()
            )
        except HttpError as exc:
            if exc.resp.status == 404:
                return None
            raise

    @staticmethod
    def verify(item, facts, folder):
        if folder not in item.get("parents", []):
            raise MediaError("Uploaded file is outside the configured Drive folder.")
        if int(item.get("size", -1)) != facts["size_bytes"]:
            raise MediaError("Drive file size does not match the local file.")
        if item.get("sha256Checksum") != facts["sha256"]:
            raise MediaError("Drive checksum does not match the local file; publication stopped.")
        return {
            "provider": "google-drive",
            "file_id": item["id"],
            "url": item.get("webViewLink") or f"https://drive.google.com/file/d/{item['id']}/view",
        }

    def upload_file(self, path, facts, folder, file_id):
        existing = self.get_file(file_id)
        if existing:
            return self.verify(existing, facts, folder)
        if checksum(path) != facts["sha256"]:
            raise MediaError(f"File changed while preparing the upload: {path.name}")
        request = self.service.files().create(
            body={"id": file_id, "name": facts["filename"], "parents": [folder]},
            media_body=MediaFileUpload(
                str(path),
                mimetype=facts["mime_type"],
                chunksize=8 * 1024 * 1024,
                resumable=True,
            ),
            supportsAllDrives=True,
            fields=FIELDS,
        )
        response = None
        try:
            while response is None:
                _, response = request.next_chunk(num_retries=3)
        except Exception:
            # The server may have finished even if its final response was lost.
            existing = self.get_file(file_id)
            if existing:
                return self.verify(existing, facts, folder)
            raise
        return self.verify(response, facts, folder)
