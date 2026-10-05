import socket

import pytest
from PIL import Image


@pytest.fixture(autouse=True)
def isolated_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("IBL_MEDIA_HOME", str(tmp_path / "home"))
    original = socket.socket.connect

    def connect(sock, address):
        if isinstance(address, tuple) and address[0] not in {"127.0.0.1", "::1", "localhost"}:
            raise AssertionError("Tests must not access external services")
        return original(sock, address)

    monkeypatch.setattr(socket.socket, "connect", connect)


@pytest.fixture
def image(tmp_path):
    path = tmp_path / "coverage.png"
    Image.new("RGB", (32, 24), "white").save(path)
    return path
