import dataclasses

import pytest
from fastapi.testclient import TestClient

from trellis import config
from trellis.api.app import create_app


@pytest.fixture
def settings(tmp_path):
    return dataclasses.replace(config.load(), data_dir=tmp_path, web_dir=tmp_path / "web", secure_cookies=False,
                               start_worker=False, nanogpt_api_key="", tmdb_token="", brave_api_key="",
                               igdb_client_id="", igdb_client_secret="")


@pytest.fixture
def app(settings):
    return create_app(settings)


@pytest.fixture
def client(app):
    with TestClient(app, headers={"X-Requested-With": "trellis"}) as c:
        yield c
