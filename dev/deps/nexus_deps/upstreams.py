# SPDX-License-Identifier: GPL-3.0-or-later
"""The programs and firmware the suites' apps use, and their updates (owner, 09-11-2026: "we also check for app
dependencies we use, like emulator updates, and for PlayStation firmware updates"). catalogs/upstreams.json lists
them, kept in sync with the apps (owner, 09-11-2026: a separate JSON file, kept in sync): the pins, repos, names and
launchers are read from each app's code and its portal's apps.toml by sync() (`dev/deps/run.sh
--sync-upstreams`), without importing the apps; tests/test_upstreams.py fails while the file is stale or misses an app.

* github: an emulator, which each app pins at a build tested on a board. Two kinds of update: the
  installed one is not the pin (the app's Install puts the pin in place), or upstream has a newer release than the
  pin (it comes with a release of the app, after a test on a board: release work). Neither is installed from here.
* sony: firmware Sony publishes a version list for (the DualSense controllers, the PS4), compared with what was seen
  before, so a new version is news once; and firmware with no list a program can read (the PS5, the PlayStation
  Portal), whose card says how to check on the device.

Every card is "by hand": its about (the card's "i") says what the update does and how to handle it."""

from __future__ import annotations

import argparse
import ast
import copy
import json
import os
import re
import sys
import tomllib
import urllib.request
from collections.abc import Callable
from html import escape
from pathlib import Path

from . import CATALOGS, CHECKOUT, __version__
from .system import Source, Update

CATALOG = CATALOGS / "upstreams.json"
TIMEOUT = 15
USER_AGENT = f"nexus-deps/{__version__}"
SUITE_NAMES = {"bc250-bazzite": "BC250 Bazzite Suite"}
SYNCED = ("repo", "pin", "version", "home", "name", "launcher")

Fetch = Callable[[str], object]          # a GitHub API URL -> its decoded JSON
Get = Callable[[str], bytes]             # a URL -> its body


class UpstreamError(Exception):
    pass


# --- The catalog and its sync with the apps -------------------------------------------------------------------

def load(path: Path = CATALOG) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _value(node: ast.AST, names: dict[str, object]) -> object:
    """A module constant's value: a literal, a name defined above it, an f-string of those, or str() of one."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name) and node.id in names:
        return names[node.id]
    if isinstance(node, ast.JoinedStr):
        parts = []
        for part in node.values:
            if isinstance(part, ast.FormattedValue):
                if part.format_spec is not None:
                    raise ValueError("a format spec")
                parts.append(str(_value(part.value, names)))
            else:
                parts.append(str(_value(part, names)))
        return "".join(parts)
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "str"
            and len(node.args) == 1 and not node.keywords):
        return str(_value(node.args[0], names))
    raise ValueError(f"not a constant: {ast.dump(node)[:60]}")


def constants(path: Path) -> dict[str, object]:
    """The module-level constants of a Python file, read without running it."""
    names: dict[str, object] = {}
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            target, value = node.targets[0].id, node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            target, value = node.target.id, node.value
        else:
            continue
        try:
            names[target] = _value(value, names)
        except ValueError:
            pass
    return names


def _portal_app(checkout: Path, suite: str, app: str) -> dict:
    path = checkout / suite / "portal" / "apps.toml"
    entry = tomllib.loads(path.read_text(encoding="utf-8")).get("apps", {}).get(app)
    if entry is None:
        raise UpstreamError(f"{suite}: {app} is not in {path.relative_to(checkout)}")
    return entry


def sync(data: dict, checkout: Path = CHECKOUT) -> dict:
    """The catalog with its synced fields read from the apps again (SYNCED); the hand-written ones as they are."""
    data = copy.deepcopy(data)
    for entry in [*data.get("github", []), *data.get("sony", [])]:
        for app in entry.get("apps", []):
            portal = _portal_app(checkout, app["suite"], app["app"])
            app["name"] = portal["name"]
            app["launcher"] = (portal.get("detect") or [""])[0]
            if "module" not in app:
                continue
            folder = checkout / app["suite"] / "apps" / app["app"]
            module = folder / app["module"]
            if not module.is_file():
                raise UpstreamError(f"{module.relative_to(checkout)} is missing")
            values = constants(module)
            for field, constant in app["constants"].items():
                if constant not in values:
                    raise UpstreamError(f"{module.relative_to(checkout)} has no constant {constant}")
                app[field] = str(values[constant])
            app_id = constants(module.parent / "__init__.py").get("APP_ID")
            app["home"] = f"~/.local/share/{app_id}/emulator"             # its emulator_home(): current -> <version>
            # The synced fields after the hand-written ones, in one order
            for field in SYNCED:
                if field in app:
                    app[field] = app.pop(field)
    return data


def apps_with_upstreams(checkout: Path = CHECKOUT) -> set[tuple[str, str]]:
    """Every (suite, app) of the Linux suites with a pinned upstream: an emulator.py."""
    found = set()
    for suite in SUITE_NAMES:
        for module in (checkout / suite / "apps").glob("*/*/emulator.py"):
            if "REPO" in constants(module) and "VERSION" in constants(module):
                found.add((suite, module.parents[1].name))
    return found


def write(path: Path = CATALOG, checkout: Path = CHECKOUT) -> bool:
    """Write the synced catalog; True when it changed."""
    old = path.read_text(encoding="utf-8")
    new = dump(sync(load(path), checkout))
    if new != old:
        path.write_text(new, encoding="utf-8")
    return new != old


def dump(data: dict) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


# --- Asking ---------------------------------------------------------------------------------------------------

def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return response.read(4 * 1024 * 1024)


def _fetch(url: str) -> object:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                                   "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return json.loads(response.read(4 * 1024 * 1024))


def numbers(version: str) -> tuple[int, ...]:
    """"v.0.21.0" -> (0, 21, 0), "0.0.43-20395" -> (0, 0, 43, 20395); trailing zeros dropped for comparing."""
    values = [int(found) for found in re.findall(r"\d+", version)]
    while values and values[-1] == 0:
        values.pop()
    return tuple(values)


def newer(compare: str, latest: dict, pin: str) -> bool:
    """Whether GitHub's latest release (tag_name, published_at) is newer than the app's pin."""
    tag = str(latest.get("tag_name", "")).strip()
    if compare == "build":
        return tag.isdigit() and pin.isdigit() and int(tag) > int(pin)
    if compare == "published":
        return str(latest.get("published_at", "")) > pin                # ISO 8601 in UTC: compared as text
    return bool(numbers(tag)) and numbers(tag) > numbers(pin)


def installed_version(app: dict, home: Path) -> str | None:
    """The version of the app's upstream on this machine: the folder current links to.
    None when the app is not installed (its launcher is missing); "" when the app is but the upstream is not."""
    if not (home / app["launcher"].removeprefix("~/")).exists():
        return None
    current = home / app["home"].removeprefix("~/") / "current"
    return os.path.basename(os.readlink(current)) if current.is_symlink() else ""


def _app_label(app: dict) -> str:
    return f"{app['name']} ({SUITE_NAMES.get(app['suite'], app['suite'])})"


def check_github(entry: dict, fetch: Fetch = _fetch, home: Path = Path.home()) -> Source:
    name, key = entry["name"], f"upstream-{entry['id']}"
    apps = entry["apps"]
    try:
        latest = fetch(f"https://api.github.com/repos/{apps[0]['repo']}/releases/latest")
        if not isinstance(latest, dict):
            raise ValueError("not a release")
    except (OSError, ValueError) as exc:
        return Source(key, name, error=f"GitHub could not be asked: {exc}", group="apps",
                      about=_github_about(entry, {}))
    tag = str(latest.get("tag_name", ""))
    updates, notes, without = [], [], []
    for app in apps:
        installed = installed_version(app, home)
        if installed is None or installed == app["version"]:
            continue
        if not installed:
            without.append(app["name"])             # the app is there, the program not (yet): a choice, no update
            continue
        updates.append(Update(f"{_app_label(app)}: installed", installed, app["version"]))
        notes.append(f"Open {app['name']} and use its Install: it puts its tested {name} in place.")
    late = [app for app in apps if newer(entry["compare"], latest, app["pin"])]
    if late:
        pins = sorted({app["version"] for app in late})
        updates.append(Update(f"{name} on GitHub", ", ".join(pins), tag))
        notes.append(f"{name} {tag} is newer than the tested one of {', '.join(_app_label(app) for app in late)}: "
                     "it comes with a release of the app, after a test on a board.")
    detail = f"Latest on GitHub: {tag} ({str(latest.get('published_at', ''))[:10]})."
    if without:
        detail += f" Installed without {name} so far: {', '.join(dict.fromkeys(without))}."
    return Source(key, name, tuple(updates), note=" ".join(dict.fromkeys(notes)), group="apps", detail=detail,
                  about=_github_about(entry, latest))


def _github_about(entry: dict, latest: dict) -> str:
    name = escape(entry["name"])
    pins = "".join(f"<li>{escape(_app_label(app))}: {escape(app['version'])}</li>" for app in entry["apps"])
    page = escape(str(latest.get("html_url") or f"https://github.com/{entry['apps'][0]['repo']}/releases"),
                  quote=True)
    text = (f"<p>{name}, {escape(entry['what'])}. Each app installs the build of {name} it was tested with on a "
            f"board (its pin):</p><ul>{pins}</ul>"
            f"<p><b>Installed is not the pin</b>: open the app and use its Install; it downloads the pin, checks it "
            "and swaps it in. Close the program first.</p>"
            f"<p><b>Newer on GitHub</b>: it is not installed from here. A newer {name} comes with a release of the "
            "app, once it has been tried on a board (release work); until then the app keeps the tested one. "
            f"See <a href='{page}'>the release</a> for what changed.</p>")
    return text


def parse_controllers(text: bytes, targets: dict[str, str]) -> dict[str, str]:
    """Sony's info.json: {"FwUpdate0044LatestVersion": "0x0217", ...} -> {"DualSense Edge (0x0044)": "0x0217"}."""
    data = json.loads(text)
    found = {}
    for target, label in targets.items():
        version = data.get(f"FwUpdate{int(target, 16):04X}LatestVersion")
        if version:
            found[f"{label} ({target})"] = str(version)
    return found


PS4_LABEL = re.compile(rb'<system_pup\b[^>]*?\blabel="(\d{1,2}\.\d{2})"')


def parse_ps4(text: bytes) -> dict[str, str]:
    """Sony's PS4 update list: the system_pup's label ("14.02"). Sony serves it over plain HTTP (its HTTPS has a
    chain of its own): no XML parser reads it, only this one attribute in its one shape, and it is only shown."""
    found = PS4_LABEL.search(text)
    if found is None:
        raise ValueError("no system software version in the list")
    return {"PS4": found.group(1).decode()}


def check_sony(entry: dict, seen: dict[str, str] | None, get: Get = _get) -> Source:
    """Sony's latest versions, compared with *seen* (what was known at the last look): a version that changed is an
    update, once. No *seen* yet: this look is the first, nothing is new."""
    name, key = entry["name"], f"upstream-{entry['id']}"
    users = ", ".join(dict.fromkeys(app.get("name", app["app"]) for app in entry.get("apps", []))) or "the device"
    about = f"<p>{escape(entry['what'][0].upper() + entry['what'][1:])}.</p><p>{escape(entry['how'].format(apps=users))}</p>"
    if entry["kind"] == "on-device":
        return Source(key, name, group="apps", checked=False, about=about,
                      detail="Checked on the device itself: the i says where.")
    try:
        body = get(entry["url"])
        found = (parse_controllers(body, entry["targets"]) if entry["kind"] == "controllers" else parse_ps4(body))
    except (OSError, ValueError) as exc:
        return Source(key, name, error=f"Sony's list could not be read: {exc}", group="apps", about=about)
    seen = seen or {}
    updates = tuple(Update(label, seen[label], version) for label, version in found.items()
                    if label in seen and seen[label] != version)
    note = (f"New from Sony: {', '.join(f'{update.name} {update.latest}' for update in updates)}. "
            + entry["how"].format(apps=users)) if updates else ""
    detail = "Latest: " + ", ".join(f"{label} {version}" for label, version in found.items()) + "."
    return Source(key, name, updates, note=note, group="apps", detail=detail, about=about,
                  known=tuple(found.items()))


# --- Every upstream, and what was seen ------------------------------------------------------------------------

def state_path() -> Path:
    base = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state")
    return base / "nexus-deps" / "upstreams.json"


def read_state(path: Path | None = None) -> dict:
    try:
        data = json.loads((path or state_path()).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_state(data: dict, path: Path | None = None) -> None:
    path = path or state_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except OSError:
        pass                            # nothing remembered: the next look says it again


def read(section: str = "seen", catalog: dict | None = None, fetch: Fetch = _fetch, get: Get = _get,
         home: Path = Path.home(), state: Path | None = None) -> tuple[Source, ...]:
    """Every upstream's card. Sony's versions are compared with *section* of the state ("seen": the window,
    "notified": the reminder), which then holds the versions just read."""
    catalog = catalog or load()
    remembered = read_state(state)
    known = remembered.setdefault(section, {})
    sources = [check_github(entry, fetch, home) for entry in catalog.get("github", [])]
    for entry in catalog.get("sony", []):
        source = check_sony(entry, known.get(entry["id"]), get)
        sources.append(source)
        if source.known:
            known[entry["id"]] = dict(source.known)
    write_state(remembered, state)
    return tuple(sources)


def unnotified(sources: tuple[Source, ...], state: Path | None = None) -> tuple[Source, ...]:
    """The reminder's view: the GitHub cards without the updates it named before (a newer upstream stays until a
    release; the notification says it once). Remembers what it names now."""
    remembered = read_state(state)
    named = remembered.setdefault("named", {})
    result = []
    for source in sources:
        if not source.key.startswith("upstream-") or source.error:
            result.append(source)
            continue
        before = set(named.get(source.key, []))
        fresh = tuple(update for update in source.updates if f"{update.name}={update.latest}" not in before)
        named[source.key] = sorted(before | {f"{update.name}={update.latest}" for update in source.updates})
        result.append(Source(source.key, source.name, fresh, note=source.note if fresh else "", group=source.group,
                             about=source.about))
    write_state(remembered, state)
    return tuple(result)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nexus_deps.upstreams", description="catalogs/upstreams.json, in sync with "
                                     "the apps' pins and their portals' apps.toml")
    parser.add_argument("--write", action="store_true", help="write the synced catalog")
    args = parser.parse_args(argv)
    if args.write:
        print("upstreams.json " + ("updated" if write() else "was in sync"))
        return 0
    stale = dump(sync(load())) != CATALOG.read_text(encoding="utf-8")
    print("upstreams.json is stale: run dev/deps/run.sh --sync-upstreams" if stale else "upstreams.json in sync")
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main())
