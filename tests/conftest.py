import dataclasses

import pytest
from fastapi.testclient import TestClient

from trellis import config
from trellis.api.app import create_app


@pytest.fixture
def settings(tmp_path):
    return dataclasses.replace(config.load(), data_dir=tmp_path, web_dir=tmp_path / "web", secure_cookies=False,
                               start_worker=False, nanogpt_api_key="", tmdb_token="test-token", brave_api_key="",
                               igdb_client_id="", igdb_client_secret="")


@pytest.fixture
def app(settings):
    return create_app(settings)


@pytest.fixture
def client(app):
    with TestClient(app, headers={"X-Requested-With": "trellis"}) as c:
        yield c


@pytest.fixture
def conn(settings, app):
    from trellis import db
    c = db.connect(settings.db_path)
    yield c
    c.close()


@pytest.fixture
def make_user(conn):
    from trellis import auth

    def _make(name: str, admin: bool = False) -> int:
        return auth.create_user(conn, name, "password123", is_admin=admin)
    return _make


def login(client, name: str):
    r = client.post("/api/login", json={"username": name, "password": "password123"})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def alice(client, make_user):
    make_user("alice")
    login(client, "alice")
    return client


@pytest.fixture
def two_clients(app, make_user):
    """(alice_client, bob_client), each logged in with its own cookie jar."""
    make_user("alice")
    make_user("bob")
    a = TestClient(app, headers={"X-Requested-With": "trellis"})
    b = TestClient(app, headers={"X-Requested-With": "trellis"})
    login(a, "alice")
    login(b, "bob")
    with a, b:
        yield a, b


FIXTURES = __import__("pathlib").Path(__file__).parent / "fixtures"


def fx(name: str):
    import json
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def route(request):
    """Map outgoing catalogue requests onto recorded fixtures."""
    import httpx
    u = request.url
    host, path = u.host, u.path
    table = [
        ("openlibrary.org", "/search.json", "ol_search.json"),
        ("openlibrary.org", "/works/OL893414W.json", "ol_work.json"),
        ("openlibrary.org", "/authors/OL79034A.json", "ol_author.json"),
        ("api.themoviedb.org", "/3/search/movie", "tmdb_search_movie.json"),
        ("api.themoviedb.org", "/3/search/tv", "tmdb_search_tv.json"),
        ("api.themoviedb.org", "/3/movie/438631", "tmdb_movie.json"),
        ("api.themoviedb.org", "/3/tv/95396", "tmdb_tv.json"),
        ("api.tvmaze.com", "/search/shows", "tvmaze_search.json"),
        ("api.tvmaze.com", "/shows/44933", "tvmaze_show.json"),
        ("musicbrainz.org", "/ws/2/release-group/", "mb_search_rg.json"),
        ("musicbrainz.org", "/ws/2/artist/", "mb_search_artist.json"),
        ("musicbrainz.org", "/ws/2/release-group/b1392450-e666-3926-a536-22c65f834433", "mb_rg.json"),
        ("en.wikipedia.org", "/api/rest_v1/page/summary/Hollow_Knight", "wp_summary.json"),
    ]
    for h, p, f in table:
        if host == h and path == p:
            return httpx.Response(200, json=fx(f))
    if host == "www.wikidata.org":
        action = u.params.get("action")
        if action == "wbsearchentities":
            return httpx.Response(200, json=fx("wd_search.json" if "hollow" in u.params["search"].lower()
                                               else "wd_search_film.json"))
        if action == "wbgetentities":
            return httpx.Response(200, json=fx("wd_entity.json" if u.params.get("props", "").startswith("claims")
                                               else "wd_labels.json"))
    return httpx.Response(404, json={"error": f"no fixture for {u}"})


@pytest.fixture(autouse=True)
def mock_http(monkeypatch):
    import httpx
    from trellis.catalogue import base
    import trellis.catalogue as cat
    monkeypatch.setattr(base, "TRANSPORT", httpx.MockTransport(route))
    monkeypatch.setattr(base.RateLimit, "wait", lambda self: None)
    cat._search_cache._d.clear()
    yield


@pytest.fixture
def fake_llm(monkeypatch):
    """Install a scripted LLM. Push responses (str or callable(model, messages) -> str) onto `.queue`."""
    from trellis import llm

    class Fake:
        def __init__(self):
            self.queue = []
            self.calls = []

        def __call__(self, model, messages):
            self.calls.append((model, messages))
            if not self.queue:
                raise AssertionError("fake LLM called with nothing queued")
            r = self.queue.pop(0)
            return r(model, messages) if callable(r) else r

    f = Fake()
    monkeypatch.setattr(llm, "FAKE", f)
    return f
