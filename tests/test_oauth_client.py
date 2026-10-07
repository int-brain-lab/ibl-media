import hashlib
import json
from types import SimpleNamespace

import pytest

from ibl_media import MediaError, oauth_client
from ibl_media.config import config_dir
from ibl_media.github import GitHub, GitHubError


@pytest.fixture
def distribution(tmp_path, monkeypatch):
    value = {
        "installed": {
            "client_id": "example.apps.googleusercontent.com",
            "client_secret": "test-only",
            "project_id": "ibl-media",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }
    data = json.dumps(value).encode()
    expected = {
        "repository": "example/private-config",
        "tag": "client-v1",
        "asset": "desktop.json",
        "sha256": hashlib.sha256(data).hexdigest(),
        "client_id": value["installed"]["client_id"],
        "project_id": "ibl-media",
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(expected))
    monkeypatch.setattr(oauth_client, "MANIFEST_PATH", path)
    calls = []

    def api(self, endpoint):
        calls.append(endpoint)
        if endpoint == self.base:
            return {"visibility": "private", "private": True}
        return {"assets": [{"name": "desktop.json", "id": 42, "size": len(data)}]}

    monkeypatch.setattr(GitHub, "api", api)
    monkeypatch.setattr(oauth_client, "download_asset", lambda *args: data)
    return SimpleNamespace(data=data, expected=expected, value=value, calls=calls)


def test_authenticated_download_is_validated_and_cached(distribution, monkeypatch):
    path = oauth_client.ensure_client()
    assert path == config_dir() / "client.json"
    assert json.loads(path.read_text()) == distribution.value
    assert path.stat().st_mode & 0o777 == 0o600
    assert distribution.calls == [
        "repos/example/private-config",
        "repos/example/private-config/releases/tags/client-v1",
    ]

    def forbidden(*args):
        raise AssertionError("Cached configuration must not require another download")

    monkeypatch.setattr(GitHub, "api", forbidden)
    assert oauth_client.ensure_client() == path


def test_access_denied_gives_onboarding_steps_without_response_body(distribution, monkeypatch):
    def denied(*args):
        raise GitHubError("sensitive-response-example", 404)

    monkeypatch.setattr(GitHub, "api", denied)
    with pytest.raises(MediaError, match="Read access") as error:
        oauth_client.ensure_client()
    assert "sensitive-response-example" not in str(error.value)
    assert "invitation" in str(error.value)
    assert not (config_dir() / "client.json").exists()


def test_public_source_is_rejected_before_download(distribution, monkeypatch):
    monkeypatch.setattr(GitHub, "api", lambda *args: {"visibility": "public", "private": False})

    def forbidden(*args):
        raise AssertionError("Public distribution must never be used")

    monkeypatch.setattr(oauth_client, "download_asset", forbidden)
    with pytest.raises(MediaError, match="must remain private"):
        oauth_client.ensure_client()


def test_corrupt_download_is_not_saved(distribution, monkeypatch):
    monkeypatch.setattr(oauth_client, "download_asset", lambda *args: b"corrupt")
    with pytest.raises(MediaError, match="checksum"):
        oauth_client.ensure_client()
    assert not (config_dir() / "client.json").exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("client_id", "other"),
        ("project_id", "other"),
        ("auth_uri", "https://attacker.example/auth"),
        ("token_uri", "https://attacker.example/token"),
        ("client_secret", ""),
        ("refresh_token", "must-not-distribute"),
    ],
)
def test_unexpected_client_is_rejected_even_with_matching_checksum(distribution, field, value):
    distribution.value["installed"][field] = value
    data = json.dumps(distribution.value).encode()
    distribution.expected["sha256"] = hashlib.sha256(data).hexdigest()
    with pytest.raises(MediaError, match="Unexpected Google application"):
        oauth_client.validate_download(data, distribution.expected)


@pytest.mark.parametrize("data", [b"invalid-json", b"[]", b'{"installed":null}'])
def test_malformed_download_is_rejected(distribution, data):
    distribution.expected["sha256"] = hashlib.sha256(data).hexdigest()
    with pytest.raises(MediaError, match="Unexpected Google application"):
        oauth_client.validate_download(data, distribution.expected)


def test_download_errors_do_not_print_credentials_or_urls(monkeypatch):
    captured = []

    def run(command, **kwargs):
        captured.append(command)
        return SimpleNamespace(returncode=1, stdout=b"secret", stderr=b"signed-url-secret")

    monkeypatch.setattr(oauth_client.subprocess, "run", run)
    with pytest.raises(MediaError) as error:
        oauth_client.download_asset("example/private", 42)
    assert "secret" not in str(error.value)
    assert captured[0][:4] == ["gh", "api", "--hostname", "github.com"]
