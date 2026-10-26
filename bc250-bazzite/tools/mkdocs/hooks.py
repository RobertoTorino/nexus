# SPDX-License-Identifier: GPL-3.0-or-later
"""MkDocs hook: serve the pictures the manual shows from where they live, without copies in docs/.

* assets/apps/<key>.webp   the small app icons the portal shows on its cards (portal/images/apps/)
* assets/<app>/<file>      an app's own images (apps/<app>/images/): its icon and its screenshots
* assets/portal/<file>     the portal's own images (portal/images/): its icon
* assets/categories/<category>.webp   each category's icon (icons/<category>/, the 256 px one)

The icons are WebP in the repository already and are served as they are. For a PNG or JPG a page names (a
screenshot), the wiki gets a WebP copy made while it is built, and its pages point at that copy; the chapters
themselves keep naming the PNG, which Bazzite Test also shows from its own images/ folder. Without Pillow the wiki
simply shows the PNGs.

The controller beside the board on the home page changes with every portal release: the pictures and their order
are in docs/images/home/controllers/controllers.toml, and the number of "Release" entries in portal/CHANGELOG picks
one, from the first again after the last. The home page names any of them; the build puts the chosen one there.

The wiki's own icon is a real file in docs/: images/wiki-icon.webp in the header and footer, images/wiki-icon.png as
the favicon (a PNG favicon works everywhere)."""

from __future__ import annotations

import io
import re
import tomllib
from functools import lru_cache
from pathlib import Path

from mkdocs.structure.files import File

SUITE = Path(__file__).resolve().parents[2]
PICTURES = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}
CONVERTED = {".png", ".jpg", ".jpeg"}
WEBP_QUALITY = 85
_ASSET = re.compile(r"assets/[a-z0-9-]+/[A-Za-z0-9_.-]+\.(?:png|jpe?g)\b")
_webp: set[str] = set()                 # the asset paths that have a WebP copy in this build
CONTROLLERS = SUITE / "docs" / "images" / "home" / "controllers"
_CONTROLLER = re.compile(r"!\[[^\]]*\]\(images/home/controllers/[^)\s]+\)")
_RELEASE = re.compile(r"^Release \d+\.\d+\.\d+", re.M)


def controllers(folder: Path = CONTROLLERS) -> list[tuple[str, str]]:
    """(file, alt text) of each controller, in the order they take turns."""
    table = tomllib.loads((folder / "controllers.toml").read_text(encoding="utf-8"))
    return [(c["file"], c["alt"]) for c in table["controller"]]


def portal_releases(changelog: Path = SUITE / "portal" / "CHANGELOG") -> int:
    return len(_RELEASE.findall(changelog.read_text(encoding="utf-8")))


def controller(folder: Path = CONTROLLERS, changelog: Path = SUITE / "portal" / "CHANGELOG") -> tuple[str, str]:
    """The controller of this portal release: the next one at each release."""
    found = controllers(folder)
    return found[portal_releases(changelog) % len(found)]


def pictures() -> dict[str, Path]:
    """Site path -> source file."""
    found = {f"assets/apps/{p.name}": p for p in (SUITE / "portal" / "images" / "apps").iterdir()}
    portal = SUITE / "portal" / "images"
    found.update({f"assets/portal/{p.name}": p for p in sorted(portal.glob("*")) if p.is_file()})
    for category in sorted(p for p in (SUITE / "icons").iterdir() if p.is_dir()):
        found[f"assets/categories/{category.name}.webp"] = category / f"{category.name}-256.webp"
    for app in sorted((SUITE / "apps").iterdir()):
        for p in sorted((app / "images").glob("*")) if (app / "images").is_dir() else []:
            found[f"assets/{app.name}/{p.name}"] = p
    return {uri: p for uri, p in found.items() if p.suffix.lower() in PICTURES}


def webp_uri(uri: str) -> str:
    return uri.rsplit(".", 1)[0] + ".webp"


@lru_cache(maxsize=None)
def to_webp(path: Path, mtime: float) -> bytes | None:
    """The picture as WebP (transparency kept), or None without Pillow. mtime keys the cache for mkdocs serve."""
    try:
        from PIL import Image
    except ImportError:
        return None
    with Image.open(path) as image:
        out = io.BytesIO()
        image.save(out, "WEBP", quality=WEBP_QUALITY, alpha_quality=100)
        return out.getvalue()


def shown(docs_dir: str) -> set[str]:
    """The asset paths the pages name: only those get a WebP copy (the Steam artwork and the like do not)."""
    return {m.group(0) for md in Path(docs_dir).rglob("*.md") for m in _ASSET.finditer(md.read_text(encoding="utf-8"))}


def on_files(files, config):
    _webp.clear()
    files.remove(files.get_file_from_path("images/home/controllers/controllers.toml"))       # the build's, not a page's
    wanted = shown(config["docs_dir"])
    for uri, path in pictures().items():
        files.append(File.generated(config, uri, abs_src_path=str(path)))
        if uri in wanted and path.suffix.lower() in CONVERTED and not path.with_suffix(".webp").exists():
            data = to_webp(path, path.stat().st_mtime)
            if data is not None:
                files.append(File.generated(config, webp_uri(uri), content=data))
                _webp.add(uri)
    return files


def on_page_markdown(markdown, page, config, files):
    """Point the page at the WebP copies; the chapter's own text keeps the PNG names. The home page gets the
    controller of this portal release."""
    if _CONTROLLER.search(markdown):
        file, alt = controller()
        markdown = _CONTROLLER.sub(lambda m: f"![{alt}](images/home/controllers/{file})", markdown)
    return _ASSET.sub(lambda m: webp_uri(m.group(0)) if m.group(0) in _webp else m.group(0), markdown)
