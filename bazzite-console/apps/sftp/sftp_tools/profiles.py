# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class ConnectionProfile:
    name: str
    host: str
    port: int
    username: str
    key_filename: str


class ConnectionProfileStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def list_profiles(self) -> list[ConnectionProfile]:
        if not self.path.exists():
            return []

        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            profiles = data["profiles"]
            if not isinstance(profiles, list):
                raise ValueError("The profiles entry must be a list.")
            return [self._parse_profile(item) for item in profiles]
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            raise ValueError(f"Could not read connection profiles: {error}") from error

    def save(self, profile: ConnectionProfile) -> None:
        profiles = {
            item.name: item
            for item in self.list_profiles()
            if item.name != profile.name
        }
        profiles[profile.name] = profile
        self._write(list(profiles.values()))

    def delete(self, name: str) -> None:
        profiles = [
            item for item in self.list_profiles() if item.name != name
        ]
        self._write(profiles)

    def _write(self, profiles: list[ConnectionProfile]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.",
            dir=self.path.parent,
            text=True,
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                json.dump(
                    {"profiles": [asdict(profile) for profile in profiles]},
                    output,
                    indent=2,
                )
                output.write("\n")
            os.replace(temporary_name, self.path)
            if os.name != "nt":
                self.path.chmod(0o600)
        except Exception:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            raise

    @staticmethod
    def _parse_profile(value: object) -> ConnectionProfile:
        if not isinstance(value, dict):
            raise ValueError("Each profile must be an object.")
        try:
            name = value["name"]
            host = value["host"]
            port = value["port"]
            username = value["username"]
            key_filename = value["key_filename"]
        except KeyError as error:
            raise ValueError(f"Profile is missing {error.args[0]}.") from error
        if (
            not isinstance(name, str)
            or not isinstance(host, str)
            or not isinstance(port, int)
            or isinstance(port, bool)
            or not isinstance(username, str)
            or not isinstance(key_filename, str)
        ):
            raise ValueError("Profile fields have invalid types.")
        return ConnectionProfile(name, host, port, username, key_filename)
