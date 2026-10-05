import hashlib
import json
import subprocess
import threading
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen

import pytest
from keyring.errors import NoKeyringError

from ibl_media import MediaError, google_auth
from ibl_media.cli import main
from ibl_media.config import Settings, config_dir, import_client
from ibl_media.drive import Drive
from ibl_media.metadata import clean_remote, file_metadata, source_metadata, validate_asset_id


def configure_client(tmp_path):
    path = tmp_path / "desktop.json"
    path.write_text(
        json.dumps(
            {
                "installed": {
                    "client_id": "example.apps.googleusercontent.com",
                    "client_secret": "example",
                }
            }
        )
    )
    import_client(path)


def test_google_callback_validates_state_and_selected_folder(tmp_path, monkeypatch):
    configure_client(tmp_path)
    flow = SimpleNamespace(redirect_uri=None, credentials="credentials")
    captured = {}

    def authorization_url(**options):
        captured.update(options)
        return "https://accounts.google.com/example", "state-value"

    flow.authorization_url = authorization_url
    flow.fetch_token = lambda **options: captured.update(options)
    monkeypatch.setattr(
        google_auth.InstalledAppFlow, "from_client_secrets_file", lambda *a, **kw: flow
    )
    monkeypatch.setattr(
        google_auth.TokenStore, "save", lambda self, creds: captured.update(saved=creds)
    )
    worker = None

    def browser(url):
        nonlocal worker

        def callback():
            query = urlencode(
                {
                    "state": "state-value",
                    "code": "authorization-code",
                    "picked_file_ids": "folder-id",
                }
            )
            with urlopen(flow.redirect_uri + "?" + query, timeout=5) as response:
                assert response.status == 200

        worker = threading.Thread(target=callback)
        worker.start()
        return True

    monkeypatch.setattr(google_auth.webbrowser, "open", browser)
    assert google_auth.login("folder-id", timeout=5) == "credentials"
    worker.join(timeout=5)
    assert captured["trigger_onepick"] == "true"
    assert captured["file_ids"] == "folder-id"
    assert captured["code"] == "authorization-code"
    assert captured["saved"] == "credentials"


def test_token_storage_falls_back_to_private_file(tmp_path, monkeypatch):
    configure_client(tmp_path)

    def unavailable(*args):
        raise NoKeyringError("No backend")

    monkeypatch.setattr(google_auth.keyring, "set_password", unavailable)
    monkeypatch.setattr(google_auth.keyring, "get_password", unavailable)
    monkeypatch.setattr(google_auth.keyring, "delete_password", unavailable)
    store = google_auth.TokenStore()
    store.save(SimpleNamespace(to_json=lambda: '{"token": "example-only"}'))
    assert store.load() == {"token": "example-only"}
    assert store.path.stat().st_mode & 0o777 == 0o600
    store.clear()
    assert store.load() is None


def test_missing_client_has_actionable_message():
    with pytest.raises(MediaError, match="login --client-secrets"):
        google_auth.credentials()


@pytest.mark.parametrize("picked", ["wrong-folder", ""])
def test_login_rejects_invalid_state_and_wrong_selection(tmp_path, monkeypatch, picked):
    configure_client(tmp_path)
    flow = SimpleNamespace(redirect_uri=None)
    flow.authorization_url = lambda **kw: ("https://accounts.google.com/example", "state-value")

    def forbidden(*args, **kwargs):
        raise AssertionError("Invalid callbacks must not exchange codes or save tokens")

    flow.fetch_token = forbidden
    monkeypatch.setattr(
        google_auth.InstalledAppFlow, "from_client_secrets_file", lambda *a, **kw: flow
    )
    monkeypatch.setattr(google_auth.TokenStore, "save", forbidden)
    responses = []
    worker = None

    def browser(url):
        nonlocal worker

        def callback():
            for state in ("wrong-state", "state-value"):
                query = urlencode({"state": state, "code": "example", "picked_file_ids": picked})
                try:
                    with urlopen(flow.redirect_uri + "?" + query, timeout=5) as response:
                        responses.append(response.status)
                except HTTPError as exc:
                    responses.append(exc.code)

        worker = threading.Thread(target=callback)
        worker.start()
        return True

    monkeypatch.setattr(google_auth.webbrowser, "open", browser)
    with pytest.raises(MediaError, match="not selected"):
        google_auth.login("folder-id", timeout=5)
    worker.join(timeout=5)
    assert responses == [400, 200]


def test_web_client_is_rejected(tmp_path):
    path = tmp_path / "client.json"
    path.write_text('{"web": {"client_id": "example"}}')
    with pytest.raises(MediaError, match="desktop-client"):
        import_client(path)
    assert not (config_dir() / "client.json").exists()


def test_extract_image_and_checksum(image):
    _, facts = file_metadata(image)
    assert (facts["width_px"], facts["height_px"]) == (32, 24)
    assert facts["mime_type"] == "image/png"
    assert facts["sha256"] == hashlib.sha256(image.read_bytes()).hexdigest()


@pytest.mark.parametrize(
    "remote, expected",
    [
        (
            "https://user:secret@github.com/org/repo.git?token=secret#secret",
            "https://github.com/org/repo.git",
        ),
        ("git@github.com:org/repo.git", "https://github.com/org/repo"),
        ("/private/home/repository", None),
    ],
)
def test_remote_credentials_and_private_paths_are_removed(remote, expected):
    assert clean_remote(remote) == expected


def test_source_records_relative_path_commit_and_dirty_state(tmp_path):
    def git(*args):
        return subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)

    git("init")
    git("config", "user.name", "Example")
    git("config", "user.email", "example@example.org")
    script = tmp_path / "plot.py"
    script.write_text("print('original')\n")
    git("add", "plot.py")
    git("commit", "-m", "Initial")
    git("remote", "add", "origin", "https://user:secret@github.com/example/analysis")
    script.write_text("print('changed')\n")
    facts = source_metadata(script)
    assert facts["path"] == "plot.py"
    assert len(facts["commit"]) == 40 and facts["working_tree_dirty"]
    assert facts["repository"] == "https://github.com/example/analysis"
    assert "secret" not in json.dumps(facts)


@pytest.mark.parametrize("value", ["../other", "a/b", "a.yaml?ref=main", "", ".hidden"])
def test_asset_ids_cannot_escape_catalog_directory(value):
    with pytest.raises(MediaError):
        validate_asset_id(value)


def test_drive_rejects_checksum_or_destination_mismatch(image):
    _, facts = file_metadata(image)
    item = {
        "id": "file",
        "parents": ["folder"],
        "size": facts["size_bytes"],
        "sha256Checksum": "0" * 64,
    }
    with pytest.raises(MediaError, match="checksum"):
        Drive.verify(item, facts, "folder")
    with pytest.raises(MediaError, match="outside"):
        Drive.verify(item, facts, "other-folder")


def test_cli_dry_run_and_bad_configuration(image, capsys):
    assert main(["upload", str(image), "--dry-run"]) == 0
    assert "no network requests" in capsys.readouterr().out
    assert main(["configure", "--folder", "https://drive.google.com/folders/example"]) == 1
    assert "folder ID" in capsys.readouterr().err
    assert Settings.load().folder == "1aWO70W8pRQDO6Ow-XFXNOSchAIm6ZolL"
