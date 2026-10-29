"""Only synthetic catalogs and read models; no physical duplicate analysis."""

from __future__ import annotations

import io
import json
import subprocess
import sys

import pytest

from playmemories_photo_manager.desktop.bridge import _dispatch, serve
from playmemories_photo_manager.desktop.demo import open_demo_catalog
from playmemories_photo_manager.desktop.duplicates import (
    DuplicatePresentation,
    _decode,
    _encode,
    synthetic_groups,
)
from playmemories_photo_manager.duplicates.models import DuplicateCoverage
from playmemories_photo_manager.gallery import GalleryQueries, GalleryQuery


@pytest.fixture
def fixture():
    connection = open_demo_catalog()
    yield connection
    connection.close()


def model(connection):
    return DuplicatePresentation(*synthetic_groups(connection), snapshot_id="fixture-session")


def test_fixture_preserves_catalog_and_ids_and_has_no_physical_claims(fixture):
    before = fixture.serialize()
    groups, issues = synthetic_groups(fixture)
    assert (groups, issues) == synthetic_groups(fixture)
    catalog = {
        r[0]: tuple(r)[1:]
        for r in fixture.execute(
            "SELECT id, asset_id, library_root_id, normalized_relative_path FROM file_location"
        )
    }
    assets = {r[0] for r in fixture.execute("SELECT id FROM asset")}
    roots = {r[0] for r in fixture.execute("SELECT id FROM library_root")}
    seen = set()
    for group in groups:
        assert group["occurrence_count"] == len(group["members"])
        assert group["plan_state"] in (None, "stale")
        assert group["evidence_fingerprint"] is None
        for member in group["members"]:
            assert member["location_id"] not in seen
            seen.add(member["location_id"])
            assert member["asset_id"] in assets
            assert member["library_root_id"] in roots
            assert member["protected"] in (True, None)
            assert not member["relative_path"].startswith("/")
            assert "device" not in member and "file_id" not in member
            if member["location_source"] == "catalog_fixture":
                assert catalog[member["location_id"]] == (
                    member["asset_id"],
                    member["library_root_id"],
                    member["relative_path"],
                )
            else:
                assert member["location_id"] not in catalog
    assert set(catalog) <= seen
    hardlinks = [m for m in groups[1]["members"] if m["hardlinked"]]
    assert len(hardlinks) == 2 and len({m["asset_id"] for m in hardlinks}) == 1
    assert groups[1]["physical_copy_count"] == 2 < groups[1]["occurrence_count"]
    assert all(m["identity_conflict"] for m in groups[2]["members"])
    assert groups[2]["review"]["status"] == "stale"
    assert groups[3]["byte_size"] == "9007199254740993"
    assert groups[3]["occurrence_count"] == 105
    assert len(assets) == 73 and fixture.serialize() == before
    # The original gallery's identities/order remain byte-for-byte reproducible.
    other = open_demo_catalog()
    try:
        assert GalleryQueries(fixture).list_assets(GalleryQuery(page_size=50)) == GalleryQueries(
            other
        ).list_assets(GalleryQuery(page_size=50))
    finally:
        other.close()


def collect(p, method, params, field):
    result = []
    while True:
        response = p.request(method, params)
        assert response["status"] == "ready"
        page = response["page"]
        result.extend(page[field])
        if page["next_cursor"] is None:
            assert len(result) == page["total_count"]
            return result
        params = {**params, "after": page["next_cursor"]}


def test_pagination_all_groups_and_105_members_without_loss(fixture):
    p = model(fixture)
    groups = collect(p, "duplicates.list", {"page_size": 1}, "groups")
    assert len(groups) == 4
    for group in groups:
        members = collect(
            p,
            "duplicates.group",
            {"snapshot_id": p.snapshot_id, "group_key": group["group_key"], "page_size": 7},
            "members",
        )
        assert len(members) == group["occurrence_count"]
        assert len({m["location_id"] for m in members}) == len(members)
        assert members == next(
            g["members"] for g in p.groups if g["group_key"] == group["group_key"]
        )


@pytest.mark.parametrize(
    "params",
    [
        [],
        None,
        {"demo": True},
        {"catalog": "/private"},
        {"page_size": True},
        {"page_size": 0},
        {"page_size": 51},
        {"page_size": 1.5},
        {"after": 3},
        {"after": ""},
        {"after": "%%%%"},
        {"after": "x" * 2049},
    ],
)
def test_invalid_requests_are_sanitized(fixture, params):
    assert model(fixture).request("duplicates.list", params) == {"status": "invalid_request"}


def test_crossed_noncanonical_and_stale_cursors(fixture):
    p = model(fixture)
    cursor = p.request("duplicates.list", {"page_size": 1})["page"]["next_cursor"]
    assert p.request("duplicates.list", {"after": cursor + "="})["status"] == "invalid_request"
    params = {"snapshot_id": p.snapshot_id, "group_key": p.groups[1]["group_key"], "after": cursor}
    assert p.request("duplicates.group", params)["status"] == "invalid_request"
    decoded = _decode(cursor)
    for update in (
        {"offset": True},
        {"offset": -1},
        {"offset": 999},
        {"v": True},
        {"order": "other"},
        {"extra": 1},
    ):
        assert (
            p.request("duplicates.list", {"after": _encode({**decoded, **update})})["status"]
            == "invalid_request"
        )
    other = DuplicatePresentation(*synthetic_groups(fixture))
    assert other.request("duplicates.list", {"after": cursor})["status"] == "stale_snapshot"
    assert (
        other.request("duplicates.group", {**params, "after": None})["status"] == "stale_snapshot"
    )
    assert (
        p.request("duplicates.group", {"snapshot_id": p.snapshot_id, "group_key": "unknown"})[
            "status"
        ]
        == "not_found"
    )


@pytest.mark.parametrize("coverage", list(DuplicateCoverage))
@pytest.mark.parametrize("populated", [True, False])
def test_explicit_coverage_global_counts_and_no_hashing(fixture, coverage, populated):
    groups, issues = synthetic_groups(fixture) if populated else ([], [])
    p = DuplicatePresentation(groups, issues, coverage=coverage)
    page = p.request("duplicates.list", {"page_size": 1})["page"]
    assert page["coverage"] == coverage
    assert page["source"] == "synthetic_fixture" and page["freshness"] == "synthetic"
    assert page["observed_at"] is None and page["hashed_location_count"] == 0
    assert page["eligible_location_count"] == sum(g["occurrence_count"] for g in groups)
    assert page["issues"] == issues


def test_numeric_precision_and_payload_fail_explicitly(fixture):
    p = model(fixture)
    assert p.request("duplicates.list", {})["page"]["groups"][3]["byte_size"] == str(2**53 + 1)
    p.groups[0]["occurrence_count"] = 2**53
    assert p.request("duplicates.list", {}) == {"status": "internal_error"}
    p = model(fixture)
    p.groups[0]["members"][0]["relative_path"] = "界" * 50000
    result = p.request(
        "duplicates.group", {"snapshot_id": p.snapshot_id, "group_key": p.groups[0]["group_key"]}
    )
    assert result == {"status": "response_too_large"}


def test_bridge_is_read_only_and_never_calls_physical_operations(fixture, monkeypatch):
    import builtins

    import playmemories_photo_manager.duplicates.detector as detector
    import playmemories_photo_manager.duplicates.review as review

    def forbidden(*args, **kwargs):
        pytest.fail("physical operation called")

    monkeypatch.setattr(detector, "find_exact_duplicates", forbidden)
    monkeypatch.setattr(review, "find_exact_duplicates", forbidden)
    monkeypatch.setattr(review, "generate_exact_duplicate_plan", forbidden)
    monkeypatch.setattr(builtins, "open", forbidden)
    before = fixture.serialize()
    statements = []
    fixture.set_trace_callback(statements.append)
    requests = [
        {"id": str(i), "token": "a" * 32, "method": "duplicates.list", "params": {"page_size": 1}}
        for i in range(2)
    ]
    sink = io.StringIO()
    serve(fixture, "a" * 32, io.StringIO("\n".join(map(json.dumps, requests))), sink, demo=True)
    messages = list(map(json.loads, sink.getvalue().splitlines()))
    assert (
        messages[1]["result"]["page"]["snapshot_id"] == messages[2]["result"]["page"]["snapshot_id"]
    )
    assert all(s.lstrip().startswith("SELECT") for s in statements)
    assert fixture.serialize() == before
    statements.clear()
    assert _dispatch(fixture, "duplicates.list", {}, demo=False) == {
        "status": "analysis_not_available"
    }
    assert not statements
    assert _dispatch(fixture, "duplicates.list", {"demo": True}, demo=False) == {
        "status": "invalid_request"
    }


def test_enum_import_does_not_load_detector_or_review():
    code = (
        "import sys; import playmemories_photo_manager.desktop.duplicates; "
        "assert 'playmemories_photo_manager.duplicates.detector' not in sys.modules; "
        "assert 'playmemories_photo_manager.duplicates.review' not in sys.modules"
    )
    subprocess.run([sys.executable, "-c", code], check=True, capture_output=True)


def test_bridge_message_limits_and_envelope_sanitize_large_response(fixture):
    from playmemories_photo_manager.desktop.bridge import MAX_MESSAGE_BYTES, _write

    sink = io.StringIO()
    serve(fixture, "a" * 32, io.StringIO("x" * (MAX_MESSAGE_BYTES + 1)), sink)
    assert json.loads(sink.getvalue().splitlines()[1])["error"]["code"] == "message_too_large"
    sink = io.StringIO()
    _write(sink, {"id": "request", "ok": True, "result": {"data": "界" * 100000}})
    response = json.loads(sink.getvalue())
    assert response == {"id": "request", "ok": False, "error": {"code": "response_too_large"}}
    assert len(sink.getvalue().encode()) < 256 * 1024


def test_member_cursor_cannot_cross_groups_and_default_page_is_24(fixture):
    p = model(fixture)
    params = {"snapshot_id": p.snapshot_id, "group_key": p.groups[-1]["group_key"]}
    page = p.request("duplicates.group", params)["page"]
    assert len(page["members"]) == 24
    assert p.request("duplicates.group", {**params, "page_size": 50})["page"]["total_count"] == 105
    assert p.request(
        "duplicates.group",
        {**params, "group_key": p.groups[0]["group_key"], "after": page["next_cursor"]},
    ) == {"status": "invalid_request"}
    assert p.request("duplicates.list", {"after": page["next_cursor"]}) == {
        "status": "invalid_request"
    }
