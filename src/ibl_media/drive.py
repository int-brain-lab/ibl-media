"""Drive uploads never change sharing; the collection folder sets access."""

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from .errors import MediaError
from .google_auth import credentials
from .metadata import checksum

FIELDS = "id,name,mimeType,trashed,parents,size,sha256Checksum,webViewLink"
FOLDER_MIME = "application/vnd.google-apps.folder"


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

    def find_folder(self, parent, name):
        """Find a named child, including folders in Shared Drives."""

        def escape(value):
            return value.replace("\\", "\\\\").replace("'", "\\'")

        folders = []
        token = None
        while True:
            page = (
                self.service.files()
                .list(
                    q=(
                        f"'{escape(parent)}' in parents and name = '{escape(name)}' "
                        f"and mimeType = '{FOLDER_MIME}' and trashed = false"
                    ),
                    spaces="drive",
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                    pageToken=token,
                    fields="nextPageToken,files(id)",
                )
                .execute()
            )
            folders.extend(item["id"] for item in page.get("files", []))
            token = page.get("nextPageToken")
            if not token:
                return min(folders) if folders else None

    def ensure_folder(self, parent, name, folder_id):
        """Use a persisted ID so retrying an ambiguous create cannot duplicate a folder."""
        existing = self.get_file(folder_id)
        if existing:
            if (
                existing.get("mimeType") != FOLDER_MIME
                or existing.get("trashed")
                or parent not in existing.get("parents", [])
            ):
                raise MediaError("The upload folder is missing or outside its expected parent.")
            return folder_id
        self.service.files().create(
            body={"id": folder_id, "name": name, "mimeType": FOLDER_MIME, "parents": [parent]},
            supportsAllDrives=True,
            fields="id",
        ).execute()
        return folder_id

    def rename_folder(self, folder_id, name):
        self.service.files().update(
            fileId=folder_id,
            body={"name": name},
            supportsAllDrives=True,
            fields="id",
        ).execute()

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
