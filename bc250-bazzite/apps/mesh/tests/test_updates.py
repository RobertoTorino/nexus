# SPDX-License-Identifier: GPL-3.0-or-later
"""The lookup of the newest DirectMesh release, against recorded GitHub answers."""

from __future__ import annotations

import urllib.error

from mesh_shaders.updates import API_URL, Release, is_newer, latest_release, version_tuple


def answer(data):
    def fetch(url: str):
        assert url == API_URL
        if isinstance(data, Exception):
            raise data
        return data
    return fetch


def release(tag: str, **extra) -> dict:
    return {"tag_name": tag, "html_url": f"https://github.com/r/releases/tag/{tag}",
            "published_at": "2026-10-08T21:00:00Z", **extra}


def test_versions_with_two_or_three_numbers():
    assert version_tuple("v1.3") == (1, 3, 0) and version_tuple("v1.3.1") == (1, 3, 1)
    assert version_tuple("1.10") == (1, 10, 0)
    assert version_tuple("v1.3-rc1") is None and version_tuple("latest") is None


def test_the_newest_release_wins_whatever_the_order():
    found = latest_release(answer([release("directmesh-v1.3"), release("directmesh-v1.10"),
                                   release("directmesh-v1.3.1"), release("directmesh-v1.9.9")]))
    assert found == Release("v1.10", "https://github.com/r/releases/tag/directmesh-v1.10", "2026-10-08")


def test_drafts_pre_releases_and_other_tags_are_skipped():
    found = latest_release(answer([release("directmesh-v2.0", prerelease=True), release("directmesh-v1.9", draft=True),
                                   release("helixsr-v9.0"), release("directmesh-v1.4-test"),
                                   release("directmesh-v1.3.1")]))
    assert found.version == "v1.3.1" and not found.error


def test_errors_never_raise():
    assert latest_release(answer([])).error == "no DirectMesh release found"
    assert latest_release(answer({"message": "x"})).error == "no connection (not a release list)"
    assert latest_release(answer(urllib.error.HTTPError(API_URL, 403, "rate limit", {}, None))).error == \
        "GitHub answered 403"
    assert latest_release(answer(OSError("timed out"))).error == "no connection (timed out)"


def test_is_newer_than_the_pinned_release():
    assert is_newer(Release("v1.4"), "v1.3.1, Mesa 26.2.1")
    assert is_newer(Release("v1.3.2"), "v1.3.1")
    assert not is_newer(Release("v1.3.1"), "v1.3.1, Mesa 26.2.1")
    assert not is_newer(Release("v1.3"), "v1.3.1")
    assert not is_newer(Release(error="x"), "v1.3.1") and not is_newer(Release("v1.4"), "")
