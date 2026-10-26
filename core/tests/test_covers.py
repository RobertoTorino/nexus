# SPDX-License-Identifier: GPL-3.0-or-later
"""The artwork from SteamGridDB (covers.py) with SteamGridDB's answers recorded here, never the network: the key
kept for the suite, the title looked up, the game by its exact name or the first found, the picture with the highest
score of the kinds kept, the pictures kept and not asked for again, a game with none, a refused key, no network, a
picture that does not download, the key sent only to the API, and the pictures fitted to Steam's sizes."""

from __future__ import annotations

import io
import json
import stat
import urllib.error

import pytest

from bc250_core import covers
from bc250_core.steam import ART

KEY = "0123456789abcdef"


def _item(number: int, score: int, mime: str = "image/png", **marks) -> dict:
    return {"id": number, "score": score, "style": "alternate", "mime": mime,
            "url": f"https://cdn2.steamgriddb.com/file/{number}{covers.SUFFIXES.get(mime, '.gif')}",
            "nsfw": False, "humor": False, "epilepsy": False, **marks}


SEARCH = {"success": True, "data": [
    {"id": 11, "name": "Ridge Racer Type 4", "types": ["steam"], "verified": True},
    {"id": 12, "name": "Arcade Archives RIDGE RACER", "types": [], "verified": True}]}
GRIDS = {"success": True, "data": [_item(1, 3), _item(2, 9, "image/jpeg"), _item(3, 20, nsfw=True),
                                   _item(4, 30, "image/gif"), _item(5, 5)]}
HEROES = {"success": True, "data": [_item(6, 1)]}
LOGOS = {"success": True, "data": [_item(7, 2, "image/webp"), _item(8, 4, humor=True)]}


class Server:
    """SteamGridDB as recorded: *answers* by the start of the path after the API; a picture is its URL's bytes."""

    def __init__(self, answers: dict[str, object] | None = None):
        self.answers = answers if answers is not None else {"search/": SEARCH, "grids/": GRIDS,
                                                            "heroes/": HEROES, "logos/": LOGOS}
        self.asked: list[tuple[str, dict[str, str]]] = []

    def __call__(self, url: str, headers: dict[str, str]) -> bytes:
        self.asked.append((url, headers))
        if not url.startswith(covers.API):
            return url.encode()
        path = url[len(covers.API) + 1:]
        for start, answer in self.answers.items():
            if path.startswith(start):
                if isinstance(answer, Exception):
                    raise answer
                return json.dumps(answer).encode()
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, io.BytesIO(b"{}"))   # type: ignore[arg-type]


def test_the_key_for_the_whole_suite(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert covers.key_file() == tmp_path / "bc250-bazzite-suite" / "steamgriddb-key"
    assert covers.read_key() == ""
    covers.write_key(f"  {KEY}\n")
    assert covers.read_key() == KEY
    assert stat.S_IMODE(covers.key_file().stat().st_mode) == 0o600
    covers.write_key("")
    assert not covers.key_file().exists() and covers.read_key() == ""


def test_the_key_dialog(tmp_path, qapp, monkeypatch):
    from PyQt6.QtWidgets import QInputDialog
    path = tmp_path / "key"
    monkeypatch.setattr(QInputDialog, "exec", lambda self: (self.setTextValue(KEY), 1)[1])
    assert covers.edit_key(path=path) and covers.read_key(path) == KEY
    assert not covers.edit_key(path=path)                                       # unchanged
    monkeypatch.setattr(QInputDialog, "exec", lambda self: 0)
    assert not covers.edit_key(path=path) and covers.read_key(path) == KEY     # canceled
    # The text names the app's button for Steam and wraps (owner, 24-10-2026: one line was as wide as the screen).
    from PyQt6.QtWidgets import QLabel
    seen = []                                           # (text, wraps) while the dialog is there
    monkeypatch.setattr(QInputDialog, "exec", lambda self: (seen.append((self.findChild(QLabel).text(),
                                                                         self.findChild(QLabel).wordWrap())), 0)[1])
    covers.edit_key(path=path, button="Update Steam")
    assert "Update Steam looks each game up" in seen[0][0] and seen[0][1]
    covers.edit_key(path=path)
    assert "Update Game Mode looks each game up" in seen[1][0]


def test_names_and_titles():
    assert covers.name("Ridge Racer", "CUSA01234") == "CUSA01234"
    assert covers.name("Ridge Racer", "SLUS-20001") == "SLUS-20001"
    assert covers.name("Ridge Racer", "../x") == "x"
    assert covers.name("Ridge Racer").startswith("title-") and covers.name("Ridge Racer") != covers.name("Other")
    assert covers.search_title("Gran Turismo 4 (USA) (v2.00) [!]") == "Gran Turismo 4"
    assert covers.search_title("Arcade Archives RIDGE RACER™") == "Arcade Archives RIDGE RACER"
    assert covers.search_title("(Prototype)") == "(Prototype)"                 # nothing left: as it is


def test_the_exact_name_else_the_first_found():
    server = Server()
    assert covers.find_game("Arcade Archives RIDGE RACER™", KEY, server) == 12
    assert "search/autocomplete/Arcade%20Archives%20RIDGE%20RACER" in server.asked[0][0]
    assert server.asked[0][1] == {"Authorization": f"Bearer {KEY}"}
    assert covers.find_game("Arcade Archives Ridge Racer (Japan)", KEY, server) == 12
    assert covers.find_game("Ridge", KEY, server) == 11
    assert covers.find_game("Nothing", KEY, Server({"search/": {"success": True, "data": []}})) is None


def test_the_picture_with_the_highest_score_of_the_kinds_kept():
    server = Server()
    assert covers.best(12, "p", KEY, server)["id"] == 2                       # not the nsfw one, not the gif
    assert "grids/game/12?dimensions=600x900&" in server.asked[-1][0] and "nsfw=false" in server.asked[-1][0]
    assert covers.best(12, "", KEY, server)["id"] == 2
    assert "dimensions=920x430%2C460x215" in server.asked[-1][0]
    assert covers.best(12, "_hero", KEY, server)["id"] == 6
    assert covers.best(12, "_logo", KEY, server)["id"] == 7                   # not the humor one
    assert "logos/game/12?types=static" in server.asked[-1][0]
    assert covers.best(12, "p", KEY, Server({"grids/": {"success": True, "data": []}})) is None


def test_pictures_are_kept_and_not_asked_for_again(tmp_path):
    server = Server()
    game = covers.name("Ridge Racer", "CUSA01234")
    notes = covers.fetch([(game, "Arcade Archives RIDGE RACER™")], covers.ALL, KEY, tmp_path, server)
    assert notes == ["Covers: SteamGridDB had pictures for 1 of 1 game(s)."]
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "CUSA01234.done", "CUSA01234.jpg", "CUSA01234_hero.png", "CUSA01234_logo.webp", "CUSA01234p.jpg"]
    assert covers.picture(tmp_path, game, "p").read_bytes() == b"https://cdn2.steamgriddb.com/file/2.jpg"
    pictures = [(url, headers) for url, headers in server.asked if not url.startswith(covers.API)]
    assert len(pictures) == 4 and all(headers == {} for _, headers in pictures)  # the key only to the API
    asked = len(server.asked)
    assert covers.fetch([(game, "x")], covers.ALL, KEY, tmp_path, server) == [] and len(server.asked) == asked


def test_only_the_kinds_asked_for(tmp_path):
    server = Server()
    covers.fetch([("CUSA01234", "Arcade Archives RIDGE RACER")], covers.PORTRAIT, KEY, tmp_path, server)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["CUSA01234.done", "CUSA01234p.jpg"]
    assert not any("heroes/" in url or "logos/" in url for url, _ in server.asked)


def test_a_game_with_no_pictures_is_not_asked_for_again(tmp_path):
    server = Server({"search/": {"success": True, "data": []}})
    game = covers.name("Unknown")
    notes = covers.fetch([(game, "Unknown")], covers.ALL, KEY, tmp_path, server)
    assert notes == ["Covers: SteamGridDB had pictures for 0 of 1 game(s); the others keep the drawn ones."]
    assert covers.known(tmp_path, game) and [p.suffix for p in tmp_path.iterdir()] == [".done"]
    assert covers.fetch([(game, "Unknown")], covers.ALL, KEY, tmp_path, server) == [] and len(server.asked) == 1


@pytest.mark.parametrize("error, says", [
    (urllib.error.HTTPError("u", 401, "Unauthorized", {}, io.BytesIO()), "refused the API key"),   # type: ignore
    (urllib.error.URLError("Name or service not known"), "could not be reached: Name or service not known"),
    (urllib.error.HTTPError("u", 500, "Error", {}, io.BytesIO()), "answered 500"),                 # type: ignore
])
def test_no_lookup_after_a_refused_key_or_no_network(tmp_path, error, says):
    server = Server({"search/": error})
    notes = covers.fetch([("A", "Game A"), ("B", "Game B")], covers.ALL, KEY, tmp_path, server)
    assert len(notes) == 1 and says in notes[0] and KEY not in notes[0]
    assert len(server.asked) == 1                                               # the second game not asked
    assert not covers.known(tmp_path, "A")                                      # asked again the next time


def test_a_picture_that_does_not_download_is_asked_for_again(tmp_path):
    server = Server()

    def get(url: str, headers: dict[str, str]) -> bytes:
        if url.endswith("6.png"):
            raise urllib.error.URLError("timed out")
        return server(url, headers)
    notes = covers.fetch([("A", "Arcade Archives RIDGE RACER")], covers.ALL, KEY, tmp_path, get)
    assert notes == ["Covers: SteamGridDB had pictures for 1 of 1 game(s).",
                     "Covers: a picture for Arcade Archives RIDGE RACER could not be downloaded: timed out."]
    assert not covers.known(tmp_path, "A") and covers.picture(tmp_path, "A", "_hero") is None
    asked = len(server.asked)
    covers.fetch([("A", "Arcade Archives RIDGE RACER")], covers.ALL, KEY, tmp_path, server)
    assert covers.known(tmp_path, "A") and covers.picture(tmp_path, "A", "_hero") is not None
    assert not any("grids/" in url for url, _ in server.asked[asked:])          # the pictures kept: not again


def test_the_pictures_fitted_to_steams_sizes(tmp_path, qapp):
    from PyQt6.QtGui import QColor, QImage
    for kind, size in (("p", (300, 500)), ("", (460, 215)), ("_hero", (1920, 620)), ("_logo", (400, 100))):
        image = QImage(*size, QImage.Format.Format_ARGB32)
        image.fill(QColor("#0000ff"))
        image.save(str(tmp_path / f"A{kind}.png"))
    (tmp_path / "Bp.png").write_bytes(b"not a picture")
    images = covers.art(tmp_path, "A", covers.ALL)
    for kind in ("p", "", "_hero"):
        image = QImage.fromData(images[kind], "PNG")
        assert (image.width(), image.height()) == ART[kind]
        assert image.pixelColor(image.width() - 1, image.height() - 1).name() == "#0000ff"
    logo = QImage.fromData(images["_logo"], "PNG")
    assert (logo.width(), logo.height()) == (400, 100)
    assert set(covers.art(tmp_path, "A", covers.PORTRAIT)) == {"p"}
    assert covers.art(tmp_path, "B", covers.ALL) == {}                          # broken or missing: left out
