from types import SimpleNamespace as C

from trellis.match import best_match, is_match, norm_title


def test_norm():
    assert norm_title("The Lord of the Rings: The Fellowship of the Ring") == "lord of the rings the fellowship of the ring"
    assert norm_title("Rocky II") == "rocky 2"
    assert norm_title("Amélie") == "amelie"
    assert norm_title("Dune: Part One", keep_subtitle=False) == "dune"


def test_matches():
    assert is_match("The Name of the Wind", 2007, None, "Name of the Wind", 2007, ["Patrick Rothfuss"])[0]
    assert is_match("Dune", None, "Frank Herbert", "Dune", 1965, ["Frank Herbert"])[0]
    # same title, different decade, no creator: a remake must not match
    assert not is_match("Dune", 1984, None, "Dune", 2021, ["Denis Villeneuve"])[0]
    # sequels must not match the original
    assert not is_match("Alien", 1979, None, "Aliens", 1986, [])[0]
    assert not is_match("Toy Story 2", 1999, None, "Toy Story", 1995, [])[0]
    assert not is_match("Rocky II", 1979, None, "Rocky", 1976, [])[0]
    # subtitle omitted by the model
    assert is_match("Hollow Knight", 2017, None, "Hollow Knight", 2017, [])[0]
    assert is_match("Blade Runner", 1982, "Ridley Scott", "Blade Runner: The Final Cut", 2007, ["Ridley Scott"])[0]
    assert not is_match("Mass Effect", 2007, None, "Mass Effect: Andromeda", 2017, [])[0]


def test_best_match_prefers_year():
    cands = [C(title="Dune", year=2021, creators=["Denis Villeneuve"]), C(title="Dune", year=1984, creators=["David Lynch"])]
    assert best_match("Dune", 1984, "David Lynch", cands).year == 1984
    assert best_match("Dune", 2000, None, cands) is None
