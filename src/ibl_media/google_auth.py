"""Desktop OAuth with Google's built-in folder picker and local token storage."""

import hashlib
import json
import secrets
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlsplit

import keyring
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from keyring.errors import KeyringError

from .config import client_path, config_dir, write_private
from .errors import MediaError

SCOPE = "https://www.googleapis.com/auth/drive.file"
SERVICE = "ibl-media.google"


class TokenStore:
    def __init__(self):
        client = json.loads(client_path().read_text())["installed"]["client_id"]
        self.account = hashlib.sha256(client.encode()).hexdigest()
        self.path = config_dir() / f"token-{self.account[:16]}.json"

    def load(self):
        # A fallback file is newer than any keyring value left after a failed keyring write.
        if self.path.exists():
            return json.loads(self.path.read_text())
        try:
            value = keyring.get_password(SERVICE, self.account)
            if value:
                return json.loads(value)
        except (KeyringError, RuntimeError):
            pass
        return None

    def save(self, credentials):
        value = credentials.to_json()
        try:
            keyring.set_password(SERVICE, self.account, value)
        except (KeyringError, RuntimeError):
            write_private(self.path, json.loads(value))
        else:
            self.path.unlink(missing_ok=True)

    def clear(self):
        try:
            keyring.delete_password(SERVICE, self.account)
        except (KeyringError, RuntimeError):
            pass
        self.path.unlink(missing_ok=True)


def credentials():
    store = TokenStore()
    try:
        value = store.load()
        if not value:
            raise MediaError("Google login is missing. Run ibl-media login first.")
        creds = Credentials.from_authorized_user_info(value, scopes=[SCOPE])
        if not creds.valid:
            if not creds.refresh_token:
                raise MediaError("Google login has expired. Run ibl-media login again.")
            creds.refresh(Request())
            store.save(creds)
        return creds
    except (RefreshError, ValueError) as exc:
        raise MediaError("Google authorization is invalid. Run ibl-media login again.") from exc


def authorization_options(folder, account=None):
    options = {
        "access_type": "offline",
        "prompt": "consent select_account",
        "include_granted_scopes": "false",
        "trigger_onepick": "true",
        "allow_folder_selection": "true",
        "allow_multiple": "false",
        "mimetypes": "application/vnd.google-apps.folder",
        "file_ids": folder,
    }
    if account:
        options["login_hint"] = account
    return options


def login(folder, timeout=180, account=None):
    flow = InstalledAppFlow.from_client_secrets_file(
        str(client_path()), scopes=[SCOPE], autogenerate_code_verifier=True
    )
    callback = {}
    expected_state = ""

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def log_message(self, *args):
            pass  # Callback URLs contain authorization codes; never log them.

        def do_GET(self):
            parsed = urlsplit(self.path)
            query = parse_qs(parsed.query)
            state = query.get("state", [""])[0]
            if parsed.path != "/" or not secrets.compare_digest(state, expected_state):
                self.send_error(400, "Invalid OAuth callback")
                return
            callback.update(query)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(
                b"Return to the terminal to see the login result. You can close this tab."
            )

    with HTTPServer(("127.0.0.1", 0), Handler) as server:
        server.timeout = 0.5
        flow.redirect_uri = f"http://127.0.0.1:{server.server_port}/"
        url, expected_state = flow.authorization_url(**authorization_options(folder, account))
        if not webbrowser.open(url):
            raise MediaError("Could not open a browser. Run login on a machine with a browser.")
        deadline = time.monotonic() + timeout
        while not callback and time.monotonic() < deadline:
            server.handle_request()

    if not callback:
        raise MediaError("Google login timed out. Run ibl-media login again.")
    if "error" in callback:
        raise MediaError("Google authorization was cancelled or denied.")
    picked = callback.get("picked_file_ids", [""])[0].split(",")
    if picked != [folder]:
        raise MediaError("The configured media folder was not selected. Run login again.")
    code = callback.get("code", [""])[0]
    if not code:
        raise MediaError("Google returned no authorization code. Run login again.")
    try:
        flow.fetch_token(code=code)
    except Exception as exc:
        raise MediaError(
            "Google could not exchange the authorization code. Check the desktop-client "
            "configuration and run login again."
        ) from exc
    if account:
        service = build("drive", "v3", credentials=flow.credentials, cache_discovery=False)
        actual = service.about().get(fields="user(emailAddress)").execute()["user"]["emailAddress"]
        if actual.casefold() != account.casefold():
            raise MediaError(f"Google authorized {actual}; expected {account}. Run login again.")
    TokenStore().save(flow.credentials)
    return flow.credentials
