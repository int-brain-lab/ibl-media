"""Check a wheel installation in fresh profiles; Google/GitHub responses are simulated.

Run with the isolated environment's Python, using -I to exclude the checkout.
The wheel contains only public configuration metadata. Authenticated retrieval
and OAuth URL generation are exercised with synthetic credentials. No live
login, uploads, GitHub credentials, or OS keyring are used.
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import urlopen


def check_wheel():
    """Build and install the production package; simulate protected retrieval at runtime."""
    repository = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="ibl-media-wheel-fixture-") as temporary:
        root = Path(temporary)
        staged = root / "source"
        staged.mkdir()
        shutil.copytree(
            repository / "src", staged / "src", ignore=shutil.ignore_patterns("__pycache__")
        )
        for name in ("pyproject.toml", "README.md"):
            shutil.copy(repository / name, staged / name)
        subprocess.run(["uv", "build", "--directory", str(staged)], check=True)
        environment = root / "venv"
        subprocess.run(["uv", "venv", "--python", sys.executable, str(environment)], check=True)
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        wheel = next((staged / "dist").glob("*.whl"))
        import zipfile

        with zipfile.ZipFile(wheel) as archive:
            assert "ibl_media/oauth_client.json" not in archive.namelist()
            assert "ibl_media/oauth_client_manifest.json" in archive.namelist()
        subprocess.run(["uv", "pip", "install", "--python", str(python), str(wheel)], check=True)
        subprocess.run([str(python), "-I", str(Path(__file__).resolve())], check=True)
    print("Installed production wheel passed with simulated private configuration retrieval.")


def check_phase(phase):
    import keyring

    from ibl_media import google_auth, oauth_client
    from ibl_media.cli import main
    from ibl_media.config import Settings, config_dir

    assert "site-packages" in oauth_client.__file__, "Must test the installed wheel"
    assert not Path(oauth_client.__file__).with_name("oauth_client.json").exists()
    expected = oauth_client.manifest()
    assert expected["repository"] == "int-brain-lab/ibl-media-config"
    client = {
        "client_id": expected["client_id"],
        "client_secret": "synthetic-test-only",
        "project_id": "ibl-media",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost"],
    }
    data = json.dumps({"installed": client}).encode()
    import hashlib

    expected["sha256"] = hashlib.sha256(data).hexdigest()
    oauth_client.manifest = lambda: expected

    def forbidden(*args, **kwargs):
        raise AssertionError("The isolated check must not access the OS keyring")

    for method in ("get_password", "set_password", "delete_password"):
        setattr(keyring, method, forbidden)
    original_connect = socket.socket.connect

    def connect(sock, address):
        if not isinstance(address, tuple) or address[0] != "127.0.0.1":
            raise AssertionError("The isolated check must not access external services")
        return original_connect(sock, address)

    socket.socket.connect = connect
    settings = Settings.load()
    account = "contributor@internationalbrainlab.org"

    def github_check(self):
        return {
            "account": "test-contributor",
            "name": "Test Contributor",
            "repository": settings.repository,
            "branch": settings.branch,
            "protected": False,
        }

    def folder_info(self, folder):
        assert folder == settings.folder
        assert google_auth.credentials().valid
        return {"name": "Media", "can_upload": True, "public": True, "shared_drive": True}

    from ibl_media.drive import Drive
    from ibl_media.github import GitHub, GitHubError

    GitHub.check = github_check
    Drive.folder_info = folder_info

    def configuration_api(self, endpoint):
        if endpoint == self.base:
            return {"visibility": "private", "private": True}
        return {"assets": [{"id": 42, "name": expected["asset"], "size": len(data)}]}

    GitHub.api = configuration_api
    oauth_client.download_asset = lambda *args: data
    if phase == "denied":

        def denied(*args):
            raise GitHubError("Access denied", 404)

        GitHub.api = denied
        google_auth.webbrowser.open = forbidden
        assert main(["login", "--account", account]) == 1
        assert not (config_dir() / "client.json").exists()
        return
    if phase == "doctor":
        assert main(["doctor"]) == 0
        assert Settings.load().credit == "Test Contributor"
        assert main(["logout"]) == 0
        assert google_auth.TokenStore().load() is None
        return

    assert not config_dir().exists(), "Must start without application configuration or tokens"
    assert main(["doctor"]) == 1, "Fresh profiles must require personal login"
    original_flow = google_auth.InstalledAppFlow.from_client_secrets_file
    flows = []

    def create_flow(*args, **kwargs):
        flow = original_flow(*args, **kwargs)

        def fetch_token(**options):
            assert options["code"] == "simulated-code"
            flow.oauth2session.token = {
                "access_token": "simulated-access-token",
                "refresh_token": "simulated-refresh-token",
                "token_type": "Bearer",
                "expires_at": time.time() + 3600,
                "scope": google_auth.SCOPE,
            }

        flow.fetch_token = fetch_token
        flows.append(flow)
        return flow

    google_auth.InstalledAppFlow.from_client_secrets_file = create_flow
    returned_account = "wrong@internationalbrainlab.org"
    google_auth.build = lambda *args, **kwargs: SimpleNamespace(
        about=lambda: SimpleNamespace(
            get=lambda **kwargs: SimpleNamespace(
                execute=lambda: {"user": {"emailAddress": returned_account}}
            )
        )
    )
    workers = []
    responses = []

    def browser(url):
        parsed = urlsplit(url)
        assert parsed.hostname == "accounts.google.com"
        query = parse_qs(parsed.query)
        assert query["client_id"] == [client["client_id"]]
        assert query["scope"] == [google_auth.SCOPE]
        assert query["login_hint"] == [account]
        assert query["code_challenge_method"] == ["S256"]
        assert query["code_challenge"][0]
        assert query["trigger_onepick"] == ["true"]
        assert query["file_ids"] == [settings.folder]

        def callback():
            values = urlencode(
                {
                    "state": query["state"][0],
                    "code": "simulated-code",
                    "picked_file_ids": settings.folder,
                }
            )
            with urlopen(flows[-1].redirect_uri + "?" + values, timeout=5) as response:
                responses.append(response.status)

        worker = threading.Thread(target=callback)
        workers.append(worker)
        worker.start()
        return True

    google_auth.webbrowser.open = browser
    assert main(["login", "--account", account]) == 1
    assert google_auth.TokenStore().load() is None, "Wrong accounts must not save tokens"
    returned_account = account
    assert main(["login", "--account", account]) == 0
    for worker in workers:
        worker.join(timeout=5)
        assert not worker.is_alive()
    assert responses == [200, 200]
    store = google_auth.TokenStore()
    assert store.load()["refresh_token"] == "simulated-refresh-token"
    if os.name != "nt":
        assert store.path.stat().st_mode & 0o777 == 0o600


if __name__ == "__main__":
    if sys.argv[1:] in (["--fixture"], ["--wheel"]):
        check_wheel()
    elif len(sys.argv) == 2:
        check_phase(sys.argv[1])
    else:
        with tempfile.TemporaryDirectory(prefix="ibl-media-installed-") as temporary:
            env = {
                key: value
                for key, value in os.environ.items()
                if key in {"PATH", "SYSTEMROOT", "WINDIR", "SSL_CERT_FILE"}
            }
            env["IBL_MEDIA_HOME"] = str(Path(temporary) / "profile")
            env["HOME"] = temporary
            env["XDG_CONFIG_HOME"] = str(Path(temporary) / "config")
            env["XDG_STATE_HOME"] = str(Path(temporary) / "state")
            for phase in ("denied", "login", "doctor"):
                subprocess.run(
                    [sys.executable, "-I", str(Path(__file__).resolve()), phase],
                    cwd=temporary,
                    env=env,
                    check=True,
                    timeout=30,
                )
        print("Installed package: fresh-profile login and separate-process doctor passed.")
