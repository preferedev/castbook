import pytest


@pytest.fixture()
def client_setup(tmp_path, monkeypatch):
    from tests.test_server import _client

    return _client(tmp_path, monkeypatch), tmp_path
