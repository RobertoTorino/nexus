# SPDX-License-Identifier: GPL-3.0-or-later
"""Kernel-line matching and the watch's event/unavailable bookkeeping (journalctl itself is not run)."""

from __future__ import annotations

import pytest

from gpu_governor.kernelwatch import KernelWatch, matches


@pytest.mark.parametrize("line", [
    "amdgpu 0000:03:00.0: amdgpu: ring gfx_0.0.0 timeout, signaled seq=12, emitted seq=14",
    "amdgpu 0000:03:00.0: amdgpu: GPU reset begin!",
    "[drm:amdgpu_job_timedout [amdgpu]] *ERROR* ring gfx timeout",
    "amdgpu: SMU: I'm not done with your previous command: SMN_C2PMSG_66:0x0000001E",
    "amdgpu 0000:03:00.0: amdgpu: soft recovery failed",
    "amdgpu 0000:03:00.0: amdgpu: failed to set power state",
    "amdgpu 0000:03:00.0: amdgpu: MODE2 reset",
    "amdgpu: SMU firmware timed out",
])
def test_hang_lines_match(line):
    assert matches(line)


@pytest.mark.parametrize("line", [
    "amdgpu 0000:03:00.0: amdgpu: Using BACO for runtime pm",
    "[drm] Initialized amdgpu 3.57.0 20150101 for 0000:03:00.0 on minor 0",
    "cyan-skillfish-governor-smu[1234]: set 1800 MHz @ 850 mV",
    "amdgpu: smu driver if version = 0x00000005, smu fw if version = 0x00000007, smu fw version = 0x003e3400",
    "",
])
def test_normal_lines_do_not_match(line):
    assert not matches(line)


def test_feed_collects_and_emits(qapp):
    watch = KernelWatch()
    seen = []
    watch.trouble.connect(seen.append)
    watch.feed("… kernel: [drm] something fine")
    watch.feed("… kernel: amdgpu: GPU reset begin!")
    watch.feed("… kernel: amdgpu: Using BACO for runtime pm")
    watch.feed("… kernel: amdgpu: GPU reset end")
    assert seen == ["… kernel: amdgpu: GPU reset begin!", "… kernel: amdgpu: GPU reset end"]
    assert watch.events == seen and not watch.running and watch.reason == ""


def test_unavailable_hint(qapp):
    watch = KernelWatch()
    why = []
    watch.unavailable.connect(why.append)
    watch._fail("the kernel log is not readable by this user")
    assert why == [watch.reason] and "not readable" in watch.reason
