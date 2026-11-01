# SPDX-License-Identifier: GPL-3.0-or-later
"""The GTT limit on the kernel command line: ttm.pages_limit in the next boot's kernel arguments, read and changed
with rpm-ostree.

rpm-ostree keeps the kernel arguments per deployment. `rpm-ostree kargs --deploy-index=0` prints those of the
first deployment, the one the next boot starts, and needs no root. A change (`--append-if-missing`, `--replace`
or `--delete`) makes a new deployment with the argument and takes effect at the next boot. The delete names the
whole argument, key and value: `--delete-if-present=ttm.pages_limit` with the key alone matched nothing on the
owner's board (01-11-2026), rpm-ostree reported no change in a second, and the app took that for done. So a change
is checked afterwards: the next boot's arguments are read again and must hold what was asked. rpm-ostree's
daemon asks polkit for it (org.projectatomic.rpmostree1.bootconfig), so the desktop's password dialog appears by
itself, without pkexec. The limit is in 4 KiB pages: amdgpu sizes the GTT from it and caps it at the RAM, and
without the argument the kernel takes half the RAM.

Nothing here needs the standard library's subprocess: the window runs the commands through privileged.run_command,
which keeps the window responsive, and the tests run a fake."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

KEY = "ttm.pages_limit"
PAGES_PER_MIB = 256                     # 4 KiB pages
UNCHANGED = 77                          # rpm-ostree kargs --unchanged-exit-77: nothing to change
NOT_INSTALLED = -2                      # privileged.run_command: the command is not on this system

# The limits the app offers: (label, pages); None is the kernel's default, the argument removed.
PRESETS: tuple[tuple[str, int | None], ...] = (
    ("Kernel default: half the RAM", None),
    ("11.5 GiB, the suite's value (Bazzite Test, test 37)", 3014656),
    ("16 GiB: all the RAM, whatever the split", 4194304),
)

Run = Callable[[list[str]], tuple[int, str, str]]   # (exit code, stdout, stderr)


def pages_in(arguments: str | None) -> int | None:
    """The ttm.pages_limit of a kernel argument line (/proc/cmdline, rpm-ostree kargs); the last one counts, as
    for the kernel. None when it is absent or not a number."""
    found = None
    for word in (arguments or "").split():
        if word.startswith(KEY + "="):
            try:
                found = int(word[len(KEY) + 1:])
            except ValueError:
                found = None
    return found


def mib(pages: int | None) -> int | None:
    return pages // PAGES_PER_MIB if pages is not None else None


@dataclass(frozen=True)
class NextBoot:
    pages: int | None = None            # ttm.pages_limit in the next boot's kernel arguments; None: not set
    error: str = ""                     # why they could not be read: no rpm-ostree, its daemon failed


def _failure(code: int, out: str, err: str) -> str:
    if code == NOT_INSTALLED:
        return "This system has no rpm-ostree: it is not Bazzite, or not an image-based one."
    text = (err.strip() or out.strip()).splitlines()
    last = text[-1] if text else f"exit code {code}"
    if "not authorized" in last.lower() or "notauthorized" in last.lower():
        return "Not authorized: the password dialog was canceled or refused."
    return f"rpm-ostree kargs failed: {last[-300:]}"


def read_next_boot(run: Run) -> NextBoot:
    code, out, err = run(["rpm-ostree", "kargs", "--deploy-index=0"])
    if code != 0:
        return NextBoot(error=_failure(code, out, err))
    return NextBoot(pages_in(out))


def command(pages: int | None, present: int | None) -> list[str]:
    """The rpm-ostree call that puts *pages* in the next boot's arguments (removes the argument for None);
    *present* is the value the next boot has now, None when it has none (--replace and --delete name it,
    --append-if-missing needs it absent)."""
    if pages is None:
        change = f"--delete={KEY}={present}"
    elif present is not None:
        change = f"--replace={KEY}={pages}"
    else:
        change = f"--append-if-missing={KEY}={pages}"
    return ["rpm-ostree", "kargs", change, "--unchanged-exit-77"]


def apply(run: Run, pages: int | None, present: int | None) -> str:
    """Changes the next boot's arguments to *pages* and checks that they hold it; "" when done (or nothing to
    change), else why not."""
    if pages == present:
        return ""
    code, out, err = run(command(pages, present))
    if code not in (0, UNCHANGED):
        return _failure(code, out, err)
    after = read_next_boot(run)
    if after.error:
        return after.error
    if after.pages != pages:
        now = f"{KEY}={after.pages}" if after.pages is not None else f"no {KEY}"
        return (f"rpm-ostree reported {'no change' if code == UNCHANGED else 'success'}, but the next boot's kernel "
                f"arguments still have {now}. Nothing is changed; try again, or in a terminal: "
                f"{' '.join(command(pages, after.pages))}")
    return ""
