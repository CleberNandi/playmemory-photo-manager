from dataclasses import replace
from uuid import uuid4

import pytest
from jpeg_fixtures import jpeg

from playmemories_photo_manager.catalog import AssetKind, Catalog, connect, initialize_database
from playmemories_photo_manager.catalog_ingestion import (
    IngestionAuthorizationError,
    SnapshotLimits,
    authorize_ingestion,
    authorize_scoped_ingestion,
    capture_catalog_snapshot,
    classify_media,
    prepare_from_snapshot,
    scope_catalogable_proposal,
    validate_scoped_authorization,
)
from playmemories_photo_manager.change_planning import PlanningContext
from playmemories_photo_manager.scanner import ScanLimits, ScanOptions, scan


@pytest.fixture
def prepared(tmp_path):
    root = tmp_path / "media"
    root.mkdir()
    (root / "nested").mkdir()
    (root / "nested" / "a.jpg").write_bytes(jpeg(3))
    (root / "b.jpeg").write_bytes(jpeg(1))
    (root / "notes.txt").write_text("synthetic exclusion")
    path = tmp_path / "catalog.sqlite3"
    connection = initialize_database(path)
    registered = Catalog(connection).register_root("Synthetic", str(root))
    connection.close()
    snapshot = capture_catalog_snapshot(path, registered.id, limits=SnapshotLimits())
    observed = scan(root, ScanOptions(limits=ScanLimits()))
    context = PlanningContext(registered.id, str(root), str(root), observed.scope)
    original = prepare_from_snapshot(snapshot, observed, context)
    scoped = scope_catalogable_proposal(original, classify_media(observed, registered.id))
    return scoped, root, path


def ids(scoped):
    return tuple(item.candidate_id for item in scoped.eligibilities if item.state == "eligible")


def test_exact_subset_is_backend_typed_and_never_writes(prepared):
    scoped, root, path = prepared
    before = {p: p.read_bytes() for p in (path, *root.rglob("*")) if p.is_file()}
    auth = authorize_scoped_ingestion(scoped, ids(scoped)[:1])
    assert len(auth.selections) == 1
    assert auth.selections[0].asset_kind is AssetKind.PHOTO
    assert auth.selections[0].media_type == "image/jpeg"
    assert auth.scope_fingerprint == scoped.scope_fingerprint
    assert auth.run_id == scoped.original.scan_result.run_id
    validate_scoped_authorization(scoped, auth)
    assert {p: p.read_bytes() for p in before} == before
    # Directories do not make the legacy all-or-nothing API permissive.
    with pytest.raises(IngestionAuthorizationError):
        authorize_ingestion(scoped.original.plan, ())


def test_selection_is_canonical_and_empty_is_explicit(prepared):
    scoped, _, _ = prepared
    selected = ids(scoped)
    assert authorize_scoped_ingestion(scoped, selected) == authorize_scoped_ingestion(
        scoped, tuple(reversed(selected))
    )
    empty = authorize_scoped_ingestion(scoped, ())
    assert empty.candidate_ids == empty.selections == ()
    validate_scoped_authorization(scoped, empty)
    assert (
        empty.decision_fingerprint
        != authorize_scoped_ingestion(scoped, selected).decision_fingerprint
    )


@pytest.mark.parametrize(
    "case", ["foreign", "excluded", "directory", "duplicate", "list", "nonstring", "oversized"]
)
def test_rejects_noneligible_or_unbounded_selection(prepared, case):
    scoped, _, _ = prepared
    selected = ids(scoped)
    choices = {
        "foreign": (str(uuid4()),),
        "excluded": (
            next(
                item.candidate_id
                for item in scoped.eligibilities
                if item.reason == "unsupported_extension"
            ),
        ),
        "directory": (
            next(
                item.candidate_id
                for item in scoped.eligibilities
                if item.reason == "not_regular_file"
            ),
        ),
        "duplicate": (selected[0], selected[0]),
        "list": list(selected),
        "nonstring": ({"path": "b.jpeg", "media_type": "image/jpeg"},),
        "oversized": tuple(str(uuid4()) for _ in range(101)),
    }
    with pytest.raises(IngestionAuthorizationError):
        authorize_scoped_ingestion(scoped, choices[case])


@pytest.mark.parametrize("field", ["scope_fingerprint", "exclusions", "eligible_candidates"])
def test_recomputes_projection_instead_of_trusting_mutated_fields(prepared, field):
    scoped, _, _ = prepared
    changed = replace(scoped, **{field: "forged" if field == "scope_fingerprint" else ()})
    with pytest.raises(IngestionAuthorizationError):
        authorize_scoped_ingestion(changed, ids(scoped))


@pytest.mark.parametrize(
    "field",
    [
        "scope_fingerprint",
        "run_id",
        "library_root_id",
        "candidate_ids",
        "selections",
        "decision_fingerprint",
    ],
)
def test_rejects_altered_authorization(prepared, field):
    scoped, _, _ = prepared
    auth = authorize_scoped_ingestion(scoped, ids(scoped))
    changed = replace(auth, **{field: () if field in ("candidate_ids", "selections") else "forged"})
    with pytest.raises(IngestionAuthorizationError):
        validate_scoped_authorization(scoped, changed)


def test_changed_eligibility_ids_invalidate_prior_consent(prepared):
    scoped, _, _ = prepared
    auth = authorize_scoped_ingestion(scoped, ids(scoped))
    updated = scope_catalogable_proposal(
        scoped.original,
        tuple(replace(item, candidate_id=str(uuid4())) for item in scoped.eligibilities),
    )
    with pytest.raises(IngestionAuthorizationError):
        validate_scoped_authorization(updated, auth)


def rebuild(prepared):
    scoped, root, path = prepared
    root_id = scoped.original.plan.library_root_id
    observed = scan(root, ScanOptions(limits=ScanLimits()))
    original = prepare_from_snapshot(
        capture_catalog_snapshot(path, root_id, limits=SnapshotLimits()),
        observed,
        PlanningContext(root_id, str(root), str(root), observed.scope),
    )
    return scope_catalogable_proposal(original, classify_media(observed, root_id))


def test_known_location_is_not_authorized_as_a_new_asset(prepared):
    scoped, root, path = prepared
    observed = (root / "b.jpeg").stat()
    with connect(path) as connection:
        catalog = Catalog(connection)
        asset = catalog.create_asset(AssetKind.PHOTO, media_type="image/jpeg")
        catalog.register_location(
            asset.id,
            scoped.original.plan.library_root_id,
            "b.jpeg",
            last_seen_at="2026-01-01T00:00:00Z",
            observed_byte_size=observed.st_size,
            observed_mtime_ns=observed.st_mtime_ns,
        )
    updated = rebuild(prepared)
    known = next(item for item in updated.eligibilities if item.candidate.relative_path == "b.jpeg")
    assert known.state == "eligible"  # A valid JPEG is not necessarily a new candidate.
    with pytest.raises(IngestionAuthorizationError):
        authorize_scoped_ingestion(updated, (known.candidate_id,))


def test_admits_exactly_one_hundred_creations(prepared):
    _, root, _ = prepared
    for index in range(98):
        (root / f"extra-{index}.jpg").write_bytes(jpeg(3))
    updated = rebuild(prepared)
    assert len(authorize_scoped_ingestion(updated, ids(updated)).selections) == 100


def test_backend_media_type_cannot_be_changed_in_the_decision(prepared):
    scoped, _, _ = prepared
    auth = authorize_scoped_ingestion(scoped, ids(scoped)[:1])
    for selection in (
        replace(auth.selections[0], media_type="image/png"),
        replace(auth.selections[0], asset_kind=AssetKind.VIDEO),
    ):
        with pytest.raises(IngestionAuthorizationError):
            validate_scoped_authorization(scoped, replace(auth, selections=(selection,)))
