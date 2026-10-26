# SPDX-License-Identifier: GPL-3.0-or-later
"""The suite's dependency catalog, the Python environment of each installed app, and the checks."""

from __future__ import annotations

import importlib.metadata
import json
import os
import re
import shutil
import subprocess
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

PYPI = "https://pypi.org/pypi/{name}/json"
OSV = "https://api.osv.dev/v1/query"            # the open vulnerability database (GitHub, PyPA, NVD)
SNYK_CVE = "https://security.snyk.io/vuln/?search={id}"
OSV_VULN = "https://osv.dev/vulnerability/{id}"
OSV_PAGES = 5
TIMEOUT = 15
NEEDS = ("required", "optional")
PROBES = ("", "flashrom-internal", "path", "console-link-ffmpeg")
# Where the apps look for tools besides PATH (bazzite-test's find_tool): a launch from the menu or the portal may
# not have them on PATH. sbin for tools that live there on other distributions.
SEARCH_DIRS = ("~/.local/bin", "/home/linuxbrew/.linuxbrew/bin", "/usr/local/sbin", "/usr/sbin")
_EXEC_PYTHON = re.compile(r"""exec\s+["']?([^"'\s]+/bin/python[0-9.]*)["']?""")
_RELEASE = re.compile(r"\d+(?:\.\d+)*")
_SPECIFIER = re.compile(r"\s*(~=|==|!=|<=|>=|<|>)\s*([0-9][0-9A-Za-z.*+!-]*)\s*")


class DependencyCatalogError(ValueError):
    pass


class DependencyCheckError(RuntimeError):
    pass


@dataclass(frozen=True)
class App:
    owner: str
    name: str
    launchers: tuple[str, ...] = ()


@dataclass(frozen=True)
class DependencySource:
    owner: str
    specifier: str


@dataclass(frozen=True)
class Dependency:
    name: str
    sources: tuple[DependencySource, ...]
    description: str = ""


@dataclass(frozen=True)
class ToolSource:
    owner: str
    usage: str
    anchor: str = ""
    need: str = "optional"


@dataclass(frozen=True)
class ExternalTool:
    name: str
    executables: tuple[str, ...]
    sources: tuple[ToolSource, ...]
    locations: tuple[str, ...] = ()
    probe: str = ""
    description: str = ""
    root: bool = False


@dataclass(frozen=True)
class Vulnerability:
    """A known vulnerability of one package version: its CVE ID when it has one, else the OSV ID (GHSA, PYSEC)."""
    id: str
    summary: str = ""
    fixed: str = ""                     # the first release with the fix, "" when none is known
    url: str = ""


@dataclass(frozen=True)
class EnvironmentVersion:
    """One Python environment of an installed app that uses the package: its venv, the apps that run in it and the
    package's version there ("" when it is missing)."""
    environment: str
    owners: tuple[str, ...]
    version: str
    unmet: tuple[str, ...] = ()         # owners whose specifier the version does not satisfy
    vulnerabilities: tuple[Vulnerability, ...] = ()
    outdated: tuple[str, ...] = ()      # of those, the owners that want a newer version than this one

    @property
    def fixes(self) -> tuple[Vulnerability, ...]:
        """The known vulnerabilities a newer release fixes."""
        return tuple(vuln for vuln in self.vulnerabilities if vuln.fixed and compare(vuln.fixed, self.version) > 0)

    @property
    def needs_update(self) -> bool:
        """It must be updated: an app wants a newer version, or a newer release fixes a known vulnerability."""
        return bool(self.version and (self.outdated or self.fixes))


@dataclass(frozen=True)
class DependencyStatus:
    dependency: Dependency
    environments: tuple[EnvironmentVersion, ...] = ()
    latest: str = ""
    error: str = ""
    cve_error: str = ""                 # the vulnerability check failed: unknown, not "none known"

    @property
    def cve_checked(self) -> bool:
        return not self.cve_error and any(env.version for env in self.environments)

    @property
    def vulnerabilities(self) -> tuple[tuple[str, Vulnerability], ...]:
        """(version, vulnerability) for every installed version, each version once."""
        seen, found = set(), []
        for env in self.environments:
            if env.version and env.version not in seen:
                seen.add(env.version)
                found.extend((env.version, vuln) for vuln in env.vulnerabilities)
        return tuple(found)

    @property
    def needed(self) -> bool:
        return bool(self.environments)

    @property
    def missing(self) -> tuple[EnvironmentVersion, ...]:
        return tuple(env for env in self.environments if not env.version)

    @property
    def unmet(self) -> tuple[EnvironmentVersion, ...]:
        return tuple(env for env in self.environments if env.version and env.unmet)

    @property
    def needs_update(self) -> tuple[EnvironmentVersion, ...]:
        """The environments where it must be updated (EnvironmentVersion.needs_update)."""
        return tuple(env for env in self.environments if env.needs_update)

    @property
    def update_available(self) -> bool:
        return any(env.version and compare(self.latest, env.version) > 0 for env in self.environments)


@dataclass(frozen=True)
class ToolStatus:
    tool: ExternalTool
    path: str = ""
    note: str = ""
    version: str = ""


@dataclass(frozen=True)
class CheckResult:
    packages: list[DependencyStatus]
    tools: list[ToolStatus]
    installed: frozenset[str] = field(default_factory=frozenset)


def _read_catalog(path: Path) -> dict:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise DependencyCatalogError(f"could not read {path}: {exc}") from exc


def _string_list(name: str, field_name: str, value: object, *, allow_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list) or (not allow_empty and not value) or \
            not all(isinstance(item, str) and item.strip() for item in value):
        raise DependencyCatalogError(f"{name} {field_name} must be a list of non-empty strings")
    return tuple(item.strip() for item in value)


def _normalized(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _entry_name(raw: object, what: str) -> str:
    if not isinstance(raw, dict) or not isinstance(raw.get("name"), str) or not raw["name"].strip():
        raise DependencyCatalogError(f"each {what} needs a non-empty name")
    return raw["name"].strip()


def _description(name: str, raw: dict) -> str:
    description = raw.get("description", "")
    if not isinstance(description, str) or not description.strip():
        raise DependencyCatalogError(f"{name} needs a description")
    return description.strip()


def _sources(name: str, raw: dict, apps: dict[str, App] | None) -> list[dict]:
    sources = raw.get("source")
    if not isinstance(sources, list) or not sources or not all(isinstance(source, dict) for source in sources):
        raise DependencyCatalogError(f"{name} needs at least one source")
    owners: set[str] = set()
    for source in sources:
        owner = source.get("owner")
        if not isinstance(owner, str) or not owner.strip():
            raise DependencyCatalogError(f"{name} sources need an owner")
        if owner in owners:
            raise DependencyCatalogError(f"{name} has duplicate source owner {owner}")
        if apps is not None and owner not in apps:
            raise DependencyCatalogError(f"{name} names {owner}, which has no [app.{owner}]")
        owners.add(owner)
    return sources


def load_apps(path: Path) -> dict[str, App]:
    raw_apps = _read_catalog(path).get("app")
    if not isinstance(raw_apps, dict) or not raw_apps:
        raise DependencyCatalogError("dependencies.toml has no [app.<name>] entries")
    apps = {}
    for owner, raw in raw_apps.items():
        name = _entry_name(raw, "app")
        apps[owner] = App(owner, name, _string_list(name, "launchers", raw.get("launchers", []), allow_empty=True))
    return apps


def load_catalog(path: Path) -> list[Dependency]:
    data = _read_catalog(path)
    apps = load_apps(path) if "app" in data else None
    raw_dependencies = data.get("dependency")
    if not isinstance(raw_dependencies, list) or not raw_dependencies:
        raise DependencyCatalogError("dependencies.toml has no [[dependency]] entries")
    dependencies = []
    seen: set[str] = set()
    for raw in raw_dependencies:
        name = _entry_name(raw, "dependency")
        if _normalized(name) in seen:
            raise DependencyCatalogError(f"duplicate dependency: {name}")
        seen.add(_normalized(name))
        sources = []
        for source in _sources(name, raw, apps):
            specifier = source.get("specifier")
            if not isinstance(specifier, str) or not specifier.strip():
                raise DependencyCatalogError(f"{name} sources need an owner and version specifier")
            sources.append(DependencySource(source["owner"], specifier))
        dependencies.append(Dependency(name, tuple(sources), _description(name, raw)))
    return dependencies


def load_tools(path: Path) -> list[ExternalTool]:
    data = _read_catalog(path)
    apps = load_apps(path) if "app" in data else None
    raw_tools = data.get("tool")
    if not isinstance(raw_tools, list) or not raw_tools:
        raise DependencyCatalogError("dependencies.toml has no [[tool]] entries")
    tools = []
    seen: set[str] = set()
    for raw in raw_tools:
        name = _entry_name(raw, "tool")
        if _normalized(name) in seen:
            raise DependencyCatalogError(f"duplicate external tool: {name}")
        seen.add(_normalized(name))
        executables = _string_list(name, "executables", raw.get("executables", []), allow_empty=True)
        locations = _string_list(name, "locations", raw.get("locations", []), allow_empty=True)
        if not executables and not locations:
            raise DependencyCatalogError(f"{name} needs executables or locations")
        probe = raw.get("probe", "")
        if probe not in PROBES:
            raise DependencyCatalogError(f"{name} has an unknown probe {probe!r}")
        root = raw.get("root", False)
        if not isinstance(root, bool):
            raise DependencyCatalogError(f"{name} root must be true or false")
        parsed_sources = []
        for source in _sources(name, raw, apps):
            usage, anchor, need = source.get("usage"), source.get("anchor", ""), source.get("need", "optional")
            if not isinstance(usage, str) or not usage.strip() or not isinstance(anchor, str):
                raise DependencyCatalogError(f"{name} sources need an owner, usage, and optional anchor")
            if need not in NEEDS:
                raise DependencyCatalogError(f"{name} need must be one of {', '.join(NEEDS)}")
            parsed_sources.append(ToolSource(source["owner"], usage.strip(), anchor, need))
        tools.append(ExternalTool(name, executables, tuple(parsed_sources), locations, probe,
                                  _description(name, raw), root))
    return tools


# --- Installed apps and their Python environments -----------------------------------------------------------------

def launcher_python(launcher: Path) -> Path | None:
    """The python on the exec line of an app launcher written by its installer; None when there is none."""
    try:
        text = launcher.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    match = _EXEC_PYTHON.search(text)
    return Path(match.group(1)) if match else None


def installed_environments(apps: dict[str, App]) -> dict[str, tuple[Path, ...]]:
    """owner -> the venvs its launchers run, for every installed app (an app whose launcher exists). An installed
    app whose launcher names no python has no venvs."""
    environments = {}
    for owner, app in apps.items():
        launchers = [Path(launcher).expanduser() for launcher in app.launchers]
        existing = [launcher for launcher in launchers if launcher.is_file()]
        if not existing:
            continue
        venvs = []
        for launcher in existing:
            python = launcher_python(launcher)
            if python is not None and python.parent.parent not in venvs:
                venvs.append(python.parent.parent)
        environments[owner] = tuple(venvs)
    return environments


def environment_versions(venv: Path) -> dict[str, str]:
    """normalized distribution name -> version in a venv, read from its site-packages without running it."""
    site = [str(path) for path in sorted(venv.glob("lib/python*/site-packages"))]
    if not site:
        return {}
    versions = {}
    for dist in importlib.metadata.distributions(path=site):
        name = dist.metadata["Name"] if dist.metadata else None
        if name:
            versions.setdefault(_normalized(name), dist.version)
    return versions


def release(version: str) -> tuple[int, ...]:
    """The release numbers of a version: "6.11.0" -> (6, 11, 0), "1.8" -> (1, 8), "2.0rc1" -> (2, 0)."""
    match = _RELEASE.match((version or "").strip().lstrip("vV"))
    return tuple(int(part) for part in match.group(0).split(".")) if match else ()


def compare(a: str, b: str) -> int:
    """-1, 0 or 1 as release a is older, equal or newer than b ("7" == "7.0.0"); 0 when either is unreadable."""
    x, y = release(a), release(b)
    if not x or not y:
        return 0
    width = max(len(x), len(y))
    x, y = x + (0,) * (width - len(x)), y + (0,) * (width - len(y))
    return (x > y) - (x < y)


def satisfies(version: str, specifier: str) -> bool:
    """Whether a release version meets a simple PEP 440 specifier such as ">=6.11,<7". Parts it cannot read count
    as met, so the checker never calls a version wrong on a guess."""
    have = release(version)
    if not have:
        return True
    for part in specifier.split(","):
        match = _SPECIFIER.fullmatch(part)
        if not match or "*" in match.group(2) or not release(match.group(2)):
            continue
        op, want = match.group(1), match.group(2)
        order = compare(version, want)
        if op == "~=":
            prefix = release(want)[:-1] or release(want)
            ok = order >= 0 and have[:len(prefix)] == prefix
        else:
            ok = {"==": order == 0, "!=": order != 0, "<=": order <= 0, ">=": order >= 0, "<": order < 0,
                  ">": order > 0}[op]
        if not ok:
            return False
    return True


def too_old(version: str, specifier: str) -> bool:
    """Whether a version misses a specifier because it is older than a lower bound (>=, >, ==, ~=), so a newer one
    would do; not when it is too new."""
    if not release(version):
        return False
    for part in specifier.split(","):
        match = _SPECIFIER.fullmatch(part)
        if not match or "*" in match.group(2) or not release(match.group(2)):
            continue
        op, want = match.group(1), match.group(2)
        order = compare(version, want)
        if (op in (">=", "~=", ">", "==") and order < 0) or (op == ">" and order == 0):
            return True
    return False


def package_environments(
    dependency: Dependency,
    environments: dict[str, tuple[Path, ...]],
    get_versions: Callable[[Path], dict[str, str]] = environment_versions,
    get_vulnerabilities: Callable[[str], tuple[Vulnerability, ...]] = lambda _version: (),
) -> tuple[EnvironmentVersion, ...]:
    """The package's version in each environment of the installed apps that use it."""
    by_venv: dict[Path, list[str]] = {}
    for source in dependency.sources:
        for venv in environments.get(source.owner, ()):
            by_venv.setdefault(venv, []).append(source.owner)
    specifiers = {source.owner: source.specifier for source in dependency.sources}
    result = []
    for venv, owners in by_venv.items():
        version = get_versions(venv).get(_normalized(dependency.name), "")
        unmet = tuple(owner for owner in owners if version and not satisfies(version, specifiers[owner]))
        outdated = tuple(owner for owner in unmet if too_old(version, specifiers[owner]))
        vulnerabilities = get_vulnerabilities(version) if version else ()
        result.append(EnvironmentVersion(str(venv), tuple(owners), version, unmet, vulnerabilities, outdated))
    return tuple(result)


# --- PyPI ---------------------------------------------------------------------------------------------------------

def latest_pypi_version(name: str, user_agent: str) -> str:
    url = PYPI.format(name=urllib.parse.quote(name, safe=""))
    request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": user_agent})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        data = json.load(response)
    if not isinstance(data, dict) or not isinstance(data.get("info"), dict):
        raise DependencyCheckError("PyPI returned an unexpected response")
    version = data["info"].get("version")
    if not isinstance(version, str) or not version.strip():
        raise DependencyCheckError("PyPI did not return a latest version")
    return version


def _fixed_version(vuln: dict) -> str:
    fixed = [event["fixed"] for affected in vuln.get("affected", []) if isinstance(affected, dict)
             for rng in affected.get("ranges", []) if isinstance(rng, dict) and rng.get("type") == "ECOSYSTEM"
             for event in rng.get("events", []) if isinstance(event, dict) and isinstance(event.get("fixed"), str)]
    fixed.sort(key=release)
    return fixed[-1] if fixed else ""


def known_vulnerabilities(name: str, version: str, user_agent: str) -> tuple[Vulnerability, ...]:
    """The vulnerabilities OSV.dev knows for this PyPI release. One CVE often has a GHSA and a PYSEC entry; they
    are shown once, under the CVE ID."""
    payload: dict = {"package": {"name": name, "ecosystem": "PyPI"}, "version": version}
    found: dict[str, Vulnerability] = {}
    for _page in range(OSV_PAGES):
        request = urllib.request.Request(OSV, data=json.dumps(payload).encode(), method="POST", headers={
            "Content-Type": "application/json", "Accept": "application/json", "User-Agent": user_agent})
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            data = json.load(response)
        if not isinstance(data, dict) or not isinstance(data.get("vulns", []), list):
            raise DependencyCheckError("OSV.dev returned an unexpected response")
        for vuln in data.get("vulns", []):
            if not isinstance(vuln, dict) or not isinstance(vuln.get("id"), str):
                continue
            ids = [vuln["id"], *(alias for alias in vuln.get("aliases", []) if isinstance(alias, str))]
            cves = sorted(i for i in ids if i.startswith("CVE-"))
            key = cves[0] if cves else min(ids)
            url = (SNYK_CVE if key.startswith("CVE-") else OSV_VULN).format(id=urllib.parse.quote(key))
            summary = str(vuln.get("summary") or "").strip()
            known = found.get(key)
            if known is None or (summary and not known.summary):
                found[key] = Vulnerability(key, summary, _fixed_version(vuln) or (known.fixed if known else ""), url)
        token = data.get("next_page_token")
        if not token:
            break
        payload["page_token"] = token
    return tuple(sorted(found.values(), key=lambda vuln: vuln.id))


def check_dependencies(
    dependencies: list[Dependency],
    user_agent: str,
    environments: dict[str, tuple[Path, ...]],
    get_versions: Callable[[Path], dict[str, str]] = environment_versions,
    get_latest: Callable[[str, str], str] = latest_pypi_version,
    get_vulnerabilities: Callable[[str, str, str], tuple[Vulnerability, ...]] = known_vulnerabilities,
) -> list[DependencyStatus]:
    """Check each dependency independently so one network error does not hide the other results."""
    cache: dict[Path, dict[str, str]] = {}

    def versions(venv: Path) -> dict[str, str]:
        if venv not in cache:
            cache[venv] = get_versions(venv)
        return cache[venv]

    known: dict[tuple[str, str], tuple[tuple[Vulnerability, ...], str]] = {}     # (name, version) -> found, error
    statuses = []
    for dependency in dependencies:
        cve_error = ""

        def vulnerabilities(version: str, name: str = dependency.name) -> tuple[Vulnerability, ...]:
            nonlocal cve_error
            if (name, version) not in known:
                try:
                    known[name, version] = (get_vulnerabilities(name, version, user_agent), "")
                except (DependencyCheckError, urllib.error.URLError, OSError, ValueError) as exc:
                    known[name, version] = ((), _reason(exc))
            found, error = known[name, version]
            cve_error = cve_error or error
            return found

        found = package_environments(dependency, environments, versions, vulnerabilities)
        try:
            latest = get_latest(dependency.name, user_agent)
        except (DependencyCheckError, urllib.error.URLError, OSError, ValueError) as exc:
            statuses.append(DependencyStatus(dependency, found, error=_reason(exc), cve_error=cve_error))
        else:
            statuses.append(DependencyStatus(dependency, found, latest=latest, cve_error=cve_error))
    return statuses


def _reason(exc: Exception) -> str:
    return (str(getattr(exc, "reason", exc)).strip() or exc.__class__.__name__)[:160]


# --- External tools -----------------------------------------------------------------------------------------------

def find_executable(name: str) -> str:
    """The executable on PATH, else in the folders the apps also look in."""
    found = shutil.which(name)
    if found:
        return found
    extra = os.pathsep.join(str(Path(folder).expanduser()) for folder in SEARCH_DIRS)
    return shutil.which(name, path=extra) or ""


def tool_need(tool: ExternalTool, installed: Iterable[str]) -> str:
    """"required" when an installed app needs the tool, "optional" when installed apps only use it if it is
    there, "" when no installed app uses it."""
    installed = set(installed)
    needs = {source.need for source in tool.sources if source.owner in installed}
    return "required" if "required" in needs else "optional" if needs else ""


def check_tools(tools: list[ExternalTool]) -> list[ToolStatus]:
    """Check availability without installing or changing tools; probe only flashrom's read-only help output."""
    statuses = []
    for tool in tools:
        candidates = []
        for location in tool.locations:
            candidate = Path(location).expanduser()
            if candidate.is_file() and (tool.probe == "path" or os.access(candidate, os.X_OK)):
                candidates.append(candidate)
        for executable in tool.executables:
            found = find_executable(executable)
            if found and Path(found) not in candidates:
                candidates.append(Path(found))

        if tool.probe == "flashrom-internal":
            supported = None
            for candidate in candidates:
                env = dict(os.environ)
                unpacked_libdir = Path.home() / "flashrom" / "usr" / "lib64"
                if candidate == Path.home() / "flashrom" / "usr" / "bin" / "flashrom":
                    env["LD_LIBRARY_PATH"] = str(unpacked_libdir)
                try:
                    result = subprocess.run([str(candidate), "--help"], capture_output=True, text=True,
                                            timeout=10, check=False, env=env)
                except (OSError, subprocess.SubprocessError):
                    continue
                if "internal" in result.stdout + result.stderr:
                    supported = candidate
                    break
            if supported is not None:
                statuses.append(ToolStatus(tool, str(supported)))
            elif candidates:
                statuses.append(ToolStatus(tool, str(candidates[0]), "No internal programmer found."))
            else:
                statuses.append(ToolStatus(tool))
        elif tool.probe == "console-link-ffmpeg":
            statuses.append(console_link_ffmpeg(tool, candidates))
        else:
            statuses.append(ToolStatus(tool, str(candidates[0]) if candidates else ""))
    return statuses


# Run with the app's python, in isolated mode: the native core's file and the FFmpeg it was built with ("" when built
# without the video decoder). Importing it loads the system's libva too, so a missing libva shows here as well.
_CORE_PROBE = ("import os, bc250_console_link_core as core; print(os.path.dirname(core.__file__)); "
               "print(getattr(core, 'FFMPEG_VERSION', '') if getattr(core, 'DECODER', False) else '')")


def console_link_ffmpeg(tool: ExternalTool, pythons: list[Path]) -> ToolStatus:
    """FFmpeg inside Console Link's native core: the core is asked, through the app's own python (the tool's
    location), which FFmpeg it carries. Not found when the app or its core is not installed."""
    for python in pythons:
        try:
            result = subprocess.run([str(python), "-I", "-c", _CORE_PROBE], capture_output=True, text=True,
                                    timeout=20, check=False, cwd=Path.home())
        except (OSError, subprocess.SubprocessError):
            continue
        lines = result.stdout.splitlines()
        if result.returncode != 0 or not lines:
            reason = (result.stderr.strip().splitlines() or ["it does not load"])[-1]
            if "No module named" in reason:
                continue
            return ToolStatus(tool, str(python), f"The native core does not load: {reason[:160]}")
        version = lines[1].strip() if len(lines) > 1 else ""
        if not version:
            return ToolStatus(tool, lines[0], "The native core was built without the video decoder.")
        return ToolStatus(tool, lines[0], version=version)
    return ToolStatus(tool)


def check_all(dependencies: list[Dependency], tools: list[ExternalTool], apps: dict[str, App],
              user_agent: str) -> CheckResult:
    environments = installed_environments(apps)
    return CheckResult(check_dependencies(dependencies, user_agent, environments), check_tools(tools),
                       frozenset(environments))
