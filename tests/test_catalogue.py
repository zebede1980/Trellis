from trellis.catalogue.igdb import IGDB
from trellis.catalogue.musicbrainz import MusicBrainz
from trellis.catalogue.openlibrary import OpenLibrary
from trellis.catalogue.tmdb import TMDB
from trellis.catalogue.tvmaze import TVmaze
from trellis.catalogue.wikidata import Wikidata


def test_openlibrary():
    c = OpenLibrary().search("dune")[0]
    assert (c.title, c.creators, c.year, c.source_id) == ("Dune", ["Frank Herbert"], 1965, "OL893414W")
    assert c.cover_url.endswith("-M.jpg")
    w = OpenLibrary().fetch("OL893414W")
    assert w.creators == ["Frank Herbert"]
    assert "Arrakis" in w.summary
    assert w.raw_tags and not any(t.lower() == "fiction" for t in w.raw_tags)


def test_tmdb_movie_and_tv():
    m = TMDB("tok", "movie")
    c = m.search("dune")[0]
    assert c.source_id == "movie:438631" and c.year == 2021
    w = m.fetch("movie:438631")
    assert w.creators == ["Denis Villeneuve"]
    assert "Science Fiction" in w.raw_tags
    t = TMDB("tok", "tv")
    assert t.search("severance")[0].source_id == "tv:95396"
    tw = t.fetch("tv:95396")
    assert tw.title == "Severance" and tw.creators


def test_tvmaze():
    c = TVmaze().search("severance")[0]
    assert c.title == "Severance" and c.year == 2022
    w = TVmaze().fetch("44933")
    assert "Drama" in w.raw_tags and "<p>" not in (w.summary or "")


def test_musicbrainz():
    cs = MusicBrainz().search("ok computer")
    assert cs[0].creators == ["Radiohead"], "the real album should outrank a same-titled single"
    w = MusicBrainz().fetch("rg:b1392450-e666-3926-a536-22c65f834433")
    assert w.year == 1997 and w.raw_tags
    assert not any("wochen" in t for t in w.raw_tags)


def test_wikidata_game():
    cs = Wikidata("game").search("hollow knight")
    titles = [c.title for c in cs]
    assert titles[0] == "Hollow Knight" and "Hollow Knight Wiki" not in titles
    w = Wikidata("game").fetch("Q29300592")
    assert w.creators == ["Team Cherry"] and w.year == 2017
    assert "Metroidvania" in w.raw_tags
    assert w.cover_url and "Hollow Knight" in w.summary


def test_wikidata_mul_label(monkeypatch):
    import httpx
    from conftest import fx, route
    from trellis.catalogue import base

    def handler(req):
        if req.url.params.get("action") == "wbgetentities" and req.url.params.get("props", "").startswith("claims"):
            d = fx("wd_entity.json")
            e = d["entities"]["Q29300592"]
            e["labels"] = {"mul": {"language": "mul", "value": "Hollow Knight"}}
            return httpx.Response(200, json=d)
        return route(req)

    monkeypatch.setattr(base, "TRANSPORT", httpx.MockTransport(handler))
    assert Wikidata("game").fetch("Q29300592").title == "Hollow Knight"


def test_wikidata_film_filter():
    cs = Wikidata("film").search("the matrix")
    assert [c.source_id for c in cs][:1] == ["Q83495"]
    assert all("album" not in (c.blurb or "") for c in cs)


def test_igdb_mocked(monkeypatch):
    import httpx
    from trellis.catalogue import base, igdb

    def handler(req):
        if req.url.host == "id.twitch.tv":
            return httpx.Response(200, json={"access_token": "abc", "expires_in": 3600})
        assert req.headers["Authorization"] == "Bearer abc"
        return httpx.Response(200, json=[{"id": 14593, "name": "Hollow Knight", "first_release_date": 1487894400,
                                           "cover": {"image_id": "co93cr"}, "url": "https://www.igdb.com/games/hollow-knight",
                                           "summary": "A bug kingdom.", "genres": [{"name": "Platform"}],
                                           "themes": [{"name": "Action"}],
                                           "involved_companies": [{"developer": True, "company": {"name": "Team Cherry"}}]}])

    monkeypatch.setattr(base, "TRANSPORT", httpx.MockTransport(handler))
    igdb._token.update(value=None, expires=0)
    g = IGDB("id", "secret")
    c = g.search("hollow knight")[0]
    assert (c.title, c.year, c.creators) == ("Hollow Knight", 2017, ["Team Cherry"])
    w = g.fetch("14593")
    assert w.raw_tags == ["Platform", "Action"]
