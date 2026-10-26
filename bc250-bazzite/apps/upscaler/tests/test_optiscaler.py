# SPDX-License-Identifier: GPL-3.0-or-later
"""OptiScaler next to a game's .exe, pointed at a stand-alone HelixSR folder, and taken out again."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from upscaler import backend

INI = ("[Upscalers]\r\n; which upscaler\r\nDx12Upscaler=auto\r\n\r\n[Libraries]\r\n; paths\r\n"
       "FfxDx12Path=auto\r\nFfxDx12SRPath=auto\r\n")


def add_optiscaler(folder: Path) -> Path:
    """The optiscaler folder of a HelixSR 1.7+ release, with marker bytes."""
    opti = folder / backend.OPTISCALER_DIR
    opti.mkdir(parents=True, exist_ok=True)
    (opti / "OptiScaler.dll").write_bytes(b"MZ-OptiScaler-0.9.4")
    (opti / "OptiScaler.ini").write_bytes(INI.encode())
    (opti / "fakenvapi.dll").write_bytes(b"MZ-fakenvapi")
    (opti / "fakenvapi.ini").write_text("[fakenvapi]\n")
    (opti / "LICENSE-GPL-3.0.txt").write_text("GPL")
    return opti


def make_game(tmp_path: Path) -> tuple[Path, Path]:
    """An Unreal-like game: the real .exe deep in Binaries/Win64 (with the game's own dxgi.dll next to it), a bigger
    launcher and a crash handler at the top."""
    game = tmp_path / "steamapps" / "common" / "GodOfWar"
    exe_dir = game / "Game" / "Binaries" / "Win64"
    exe_dir.mkdir(parents=True)
    (exe_dir / "Game-Win64-Shipping.exe").write_bytes(b"MZ" * 10)
    (exe_dir / "dxgi.dll").write_bytes(b"MZ-the-games-dxgi")
    (game / "Launcher.exe").write_bytes(b"MZ" * 1000)
    (game / "UnityCrashHandler64.exe").write_bytes(b"MZ" * 5000)
    return game, exe_dir


def test_import_takes_the_optiscaler_folder(release, tmp_path):
    add_optiscaler(release)
    payload = tmp_path / "p1"
    result = backend.import_payload(release, payload)
    assert "optiscaler/OptiScaler.dll" in result.copied and backend.payload_status(payload).optiscaler
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for path in release.rglob("*"):
            if path.is_file():
                zf.write(path, f"HelixSR-1.8.1/{path.relative_to(release)}")
    (tmp_path / "r.zip").write_bytes(buf.getvalue())
    backend.import_payload(tmp_path / "r.zip", tmp_path / "p2")
    assert (tmp_path / "p2" / "optiscaler" / "OptiScaler.ini").read_bytes() == INI.encode()
    assert not backend.payload_status(tmp_path / "p3").optiscaler


def test_find_exe_folder(tmp_path):
    game, exe_dir = make_game(tmp_path)
    assert backend.find_exe_folder(game) == exe_dir                 # the Unreal shipping .exe, not the launcher
    other = game / "Other"
    other.mkdir()
    (other / "OptiScaler.ini").write_text("")
    assert backend.find_exe_folder(game) == other                   # a folder that already has OptiScaler wins
    assert backend.find_exe_folder(tmp_path / "empty") is None


def test_install_and_remove_put_everything_back(payload, tmp_path):
    add_optiscaler(payload)
    game, exe_dir = make_game(tmp_path)
    folder = game / "HelixSR"
    backend.deploy_folder(folder, payload)
    backend.install_optiscaler(exe_dir, folder, payload)
    assert (exe_dir / "dxgi.dll").read_bytes() == b"MZ-OptiScaler-0.9.4"
    assert (folder / "backup" / "dxgi.dll").read_bytes() == b"MZ-the-games-dxgi"
    assert (exe_dir / "fakenvapi.dll").is_file() and (exe_dir / "fakenvapi.ini").is_file()
    ini = (exe_dir / "OptiScaler.ini").read_bytes().decode()
    win = backend.to_windows_path(folder)
    assert "Dx12Upscaler=fsr31\r\n" in ini and f"FfxDx12Path={win}\\amd_fidelityfx_dx12.dll\r\n" in ini
    assert f"FfxDx12SRPath={win}\\amd_fidelityfx_upscaler_dx12.dll\r\n" in ini and "; paths" in ini
    backend.install_optiscaler(exe_dir, folder, payload)            # again: an update, the backup stays the game's
    assert (folder / "backup" / "dxgi.dll").read_bytes() == b"MZ-the-games-dxgi"
    with pytest.raises(backend.HelixError):                         # one folder serves one game
        backend.install_optiscaler(tmp_path, folder, payload)
    backend.remove_folder(folder, payload)
    assert (exe_dir / "dxgi.dll").read_bytes() == b"MZ-the-games-dxgi" and not folder.exists()
    assert sorted(p.name for p in exe_dir.iterdir()) == ["Game-Win64-Shipping.exe", "dxgi.dll"]


def test_an_existing_optiscaler_keeps_its_name_and_its_ini(payload, tmp_path):
    add_optiscaler(payload)
    exe_dir = tmp_path / "game"
    exe_dir.mkdir()
    (exe_dir / "winmm.dll").write_bytes(b"MZ-OptiScaler-0.7")
    own = "[Upscalers]\r\nDx12Upscaler=xess\r\n[Libraries]\r\nFfxDx12Path=auto\r\n"
    (exe_dir / "OptiScaler.ini").write_bytes(own.encode())
    (exe_dir / "fakenvapi.dll").write_bytes(b"theirs")
    folder = exe_dir / "HelixSR"
    backend.deploy_folder(folder, payload)
    backend.install_optiscaler(exe_dir, folder, payload)
    assert (exe_dir / "winmm.dll").read_bytes() == b"MZ-OptiScaler-0.9.4" and not (exe_dir / "dxgi.dll").exists()
    ini = (exe_dir / "OptiScaler.ini").read_bytes().decode()
    assert "Dx12Upscaler=fsr31\r\n" in ini and "FfxDx12SRPath=" in ini        # a missing key goes into its section
    assert (exe_dir / "fakenvapi.dll").read_bytes() == b"theirs"               # theirs, not replaced
    backend.remove_folder(folder, payload)
    assert (exe_dir / "winmm.dll").read_bytes() == b"MZ-OptiScaler-0.7"
    assert (exe_dir / "OptiScaler.ini").read_bytes() == own.encode() and (exe_dir / "fakenvapi.dll").exists()


def test_install_refusals(payload, tmp_path):
    exe_dir = tmp_path / "game"
    exe_dir.mkdir()
    with pytest.raises(backend.HelixError, match="no OptiScaler"):
        backend.install_optiscaler(exe_dir, exe_dir / "HelixSR", payload)
    add_optiscaler(payload)
    with pytest.raises(backend.HelixError, match="must not be"):
        backend.install_optiscaler(exe_dir, exe_dir, payload)


# ------------------------------------------------------------------------------------- Steam launch options
LOCALCONFIG = ('"UserLocalConfigStore"\n{\n\t"Broadcast"\n\t{\n\t\t"Permissions"\t\t"1"\n\t}\n'
               '\t"1593500"\t\t"3200000004"\n'                                   # the same AppID elsewhere: not a game
               '\t"Software"\n\t{\n\t\t"Valve"\n\t\t{\n\t\t\t"Steam"\n\t\t\t{\n\t\t\t\t"apps"\n\t\t\t\t{\n'
               '\t\t\t\t\t"1593500"\n\t\t\t\t\t{\n\t\t\t\t\t\t"LastPlayed"\t\t"1791287757"\n'
               '\t\t\t\t\t\t"cloud"\n\t\t\t\t\t\t{\n\t\t\t\t\t\t\t"last_sync_state"\t\t"synchronized"\n'
               '\t\t\t\t\t\t}\n\t\t\t\t\t}\n'
               '\t\t\t\t\t"297860"\n\t\t\t\t\t{\n\t\t\t\t\t\t"LaunchOptions"\t\t"gamemoderun %command%"\n'
               '\t\t\t\t\t}\n\t\t\t\t}\n\t\t\t}\n\t\t}\n\t}\n}\n')


def write_config(tmp_path: Path, text: str = LOCALCONFIG) -> Path:
    config = tmp_path / "Steam" / "userdata" / "1234" / "config" / "localconfig.vdf"
    config.parent.mkdir(parents=True)
    config.write_bytes(text.encode())
    return config


def test_launch_options_are_read_and_set_in_place(tmp_path):
    config = write_config(tmp_path)
    assert backend.launch_configs(tmp_path / "Steam") == [config]
    assert backend.launch_options(config, "297860") == "gamemoderun %command%"
    assert backend.launch_options(config, "1593500") == ""
    line = 'WINEDLLOVERRIDES="dxgi=n,b" %command%'
    backend.set_launch_options(config, "1593500", line)            # added to the game's block
    text = config.read_text()
    assert ('\t\t\t\t\t\t}\n\t\t\t\t\t\t"LaunchOptions"\t\t"WINEDLLOVERRIDES=\\"dxgi=n,b\\" %command%"\n\t\t\t\t\t}\n'
            in text)
    assert backend.launch_options(config, "1593500") == line
    backend.set_launch_options(config, "1593500", "")              # replaced; the rest byte for byte
    assert config.read_text() == text.replace('WINEDLLOVERRIDES=\\"dxgi=n,b\\" %command%', "")
    backend.set_launch_options(config, "42", "-dx12")              # a game without a block gets one
    assert backend.launch_options(config, "42") == "-dx12" and backend.launch_options(config, "297860") == \
        "gamemoderun %command%"


def test_launch_options_refusals(tmp_path):
    config = write_config(tmp_path, '"UserLocalConfigStore"\n{\n\t"system"\n\t{\n\t}\n}\n')
    with pytest.raises(backend.HelixError, match="no list of games"):
        backend.set_launch_options(config, "42", "x")
    config.write_text('"UserLocalConfigStore"\n{\n')
    with pytest.raises(backend.HelixError, match="not complete"):
        backend.launch_options(config, "42")


@pytest.mark.parametrize("before, after", [
    ("", 'WINEDLLOVERRIDES="dxgi=n,b" %command%'),
    ("gamemoderun %command% -dx12", 'WINEDLLOVERRIDES="dxgi=n,b" gamemoderun %command% -dx12'),
    ("-dx12", 'WINEDLLOVERRIDES="dxgi=n,b" %command% -dx12'),
    ('WINEDLLOVERRIDES="winmm=n,b" %command%', 'WINEDLLOVERRIDES="dxgi=n,b;winmm=n,b" %command%'),
    ("WINEDLLOVERRIDES=d3d11,dxgi=n %command%", "WINEDLLOVERRIDES=d3d11,dxgi=n %command%"),     # the user's own
    ('WINEDLLOVERRIDES="dxgi=n,b" %command%', 'WINEDLLOVERRIDES="dxgi=n,b" %command%'),
])
def test_with_override(before, after):
    assert backend.with_override(before, "dxgi.dll") == after


def test_the_record_keeps_the_first_launch_options(payload, tmp_path):
    add_optiscaler(payload)
    game, exe_dir = make_game(tmp_path)
    folder = game / "HelixSR"
    backend.deploy_folder(folder, payload)
    backend.install_optiscaler(exe_dir, folder, payload)
    config = write_config(tmp_path)
    backend.record_launch_options(folder, "297860", [(config, "gamemoderun %command%", "A")])
    backend.record_launch_options(folder, "297860", [(config, "A", "B")])    # deployed again: the first before stays
    (entry,) = backend.optiscaler_record(folder)["launch"]
    assert (entry["before"], entry["after"]) == ("gamemoderun %command%", "B")
    assert backend.launch_restores([entry]) == []                    # the file says something else: the user's
    backend.set_launch_options(config, "297860", "B")
    assert backend.launch_restores([entry]) == [(config, "297860", "gamemoderun %command%")]
    assert backend.launch_restores([{**entry, "config": str(tmp_path / "gone.vdf")}]) == []
