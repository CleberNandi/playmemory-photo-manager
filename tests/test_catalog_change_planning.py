from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime

import pytest

from playmemories_photo_manager.catalog import (
    Asset,
    AssetKind,
    FileLocation,
    HashState,
    LibraryRoot,
    LocationAvailability,
    RootAvailability,
)
from playmemories_photo_manager.catalog import EntryType as CatalogEntryType
from playmemories_photo_manager.change_planning import (
    CatalogChangePlan,
    CatalogSnapshot,
    ChangeClassification,
    DiagnosticCode,
    LocationPhysicalEvidence,
    PlanningContext,
    PlanStatus,
    plan_changes,
)
from playmemories_photo_manager.evidence import evaluate
from playmemories_photo_manager.scanner import (
    ConfinementKind,
    EntryObservation,
    EntryType,
    FailureKind,
    FailureOperation,
    HostPlatform,
    ObservationFailure,
    ObservedTimestamps,
    PhysicalIdentity,
    RootObservation,
    ScanEnvironment,
    ScanResult,
    ScanScope,
    ScanStatus,
)

ROOT_ID = "11111111-1111-4111-8111-111111111111"
ASSET_ID = "22222222-2222-4222-8222-222222222222"
OTHER_ASSET_ID = "33333333-3333-4333-8333-333333333333"
LOCATION_ID = "44444444-4444-4444-8444-444444444444"
OTHER_LOCATION_ID = "55555555-5555-4555-8555-555555555555"
RUN_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
ROOT_PATH = "/synthetic/library"
ROOT_PHYSICAL = PhysicalIdentity(1, 10)
FILE_PHYSICAL = PhysicalIdentity(1, 20)
DEFAULT_SCOPE = ScanScope(".", True, False)
OBSERVED_ROOT = RootObservation(ROOT_PATH, ROOT_PATH, ROOT_PHYSICAL)
TIMESTAMPS = ObservedTimestamps(20, None, 30)


def _asset(identifier: str = ASSET_ID, sha256: str | None = None) -> Asset:
    return Asset(
        identifier,
        AssetKind.PHOTO,
        sha256,
        HashState.VERIFIED if sha256 else HashState.ABSENT,
        10,
        "image/jpeg",
        "active",
        "2026-10-24T00:00:00Z",
    )


def _location(
    path: str = "photo.jpg",
    *,
    identifier: str = LOCATION_ID,
    asset_id: str = ASSET_ID,
    availability: LocationAvailability = LocationAvailability.PRESENT,
) -> FileLocation:
    return FileLocation(
        identifier,
        asset_id,
        ROOT_ID,
        path,
        CatalogEntryType.FILE,
        None,
        "opaque-legacy-id",
        10,
        20,
        availability,
        "2026-10-24T00:00:00Z",
    )


def _entry(
    path: str = "photo.jpg",
    *,
    identity: PhysicalIdentity | None = FILE_PHYSICAL,
    entry_type: EntryType = EntryType.FILE,
) -> EntryObservation:
    return EntryObservation(
        path,
        entry_type,
        10 if entry_type is EntryType.FILE else None,
        TIMESTAMPS,
        identity,
    )


def _assessment(
    entries: tuple[EntryObservation, ...] = (_entry(),),
    *,
    status: ScanStatus = ScanStatus.COMPLETE,
    scope: ScanScope = DEFAULT_SCOPE,
    root: RootObservation | None = OBSERVED_ROOT,
):
    failures: tuple[ObservationFailure, ...] = ()
    covered = (scope.relative_path,)
    if status is ScanStatus.PARTIAL:
        failures = (
            ObservationFailure(
                "denied", FailureOperation.OBSERVE_ENTRY, FailureKind.PERMISSION_DENIED, True, 13
            ),
        )
    elif status is ScanStatus.ROOT_UNAVAILABLE:
        root = None
        entries = ()
        covered = ()
        failures = (
            ObservationFailure(None, FailureOperation.OBSERVE_ROOT, FailureKind.IO_ERROR, True, 5),
        )
    elif status is ScanStatus.FAILED:
        entries = ()
        covered = ()
        failures = (
            ObservationFailure(
                scope.relative_path,
                FailureOperation.ENUMERATE_DIRECTORY,
                FailureKind.IO_ERROR,
                True,
                5,
            ),
        )
    return evaluate(
        ScanResult(
            RUN_ID,
            root,
            scope,
            datetime(2026, 10, 24, tzinfo=UTC),
            datetime(2026, 10, 24, 0, 0, 1, tzinfo=UTC),
            status,
            covered,
            entries,
            failures,
            ScanEnvironment(HostPlatform.POSIX, ConfinementKind.DESCRIPTOR_RELATIVE),
        )
    )


def _snapshot(
    *,
    assets: tuple[Asset, ...] = (_asset(),),
    locations: tuple[FileLocation, ...] = (_location(),),
    evidence: tuple[LocationPhysicalEvidence, ...] = (),
    scope: ScanScope = DEFAULT_SCOPE,
) -> CatalogSnapshot:
    root = LibraryRoot(
        ROOT_ID,
        "Synthetic",
        ROOT_PATH,
        RootAvailability.AVAILABLE,
        "2026-10-24T00:00:00Z",
        None,
    )
    return CatalogSnapshot(root, assets, locations, evidence, scope, "read-42")


def _context(scope: ScanScope = DEFAULT_SCOPE) -> PlanningContext:
    return PlanningContext(ROOT_ID, ROOT_PATH, ROOT_PATH, scope, ROOT_PHYSICAL)


def _codes(plan) -> set[DiagnosticCode]:
    return {item.code for item in plan.diagnostics}


def test_known_location_is_observed_without_content_or_last_seen_claim() -> None:
    location = _location()
    plan = plan_changes(_assessment(), _snapshot(locations=(location,)), _context())

    assert plan.status is PlanStatus.READY
    assert plan.changes[0].classification is ChangeClassification.KNOWN_LOCATION_OBSERVED
    assert plan.changes[0].asset_id == ASSET_ID
    assert plan.changes[0].location_id == LOCATION_ID
    assert DiagnosticCode.CONTENT_NOT_VERIFIED in _codes(plan)
    assert location.last_seen_at == "2026-10-24T00:00:00Z"


def test_new_observed_file_is_only_a_candidate_without_generated_id() -> None:
    plan = plan_changes(_assessment(), _snapshot(assets=(), locations=()), _context())

    change = plan.changes[0]
    assert change.classification is ChangeClassification.NEW_FILE_CANDIDATE
    assert change.asset_id is None
    assert change.location_id is None


def test_empty_catalog_and_empty_complete_observation_produce_no_changes() -> None:
    plan = plan_changes(_assessment(entries=()), _snapshot(assets=(), locations=()), _context())

    assert plan.changes == ()
    assert plan.permits_absence_conclusions is False
    assert DiagnosticCode.ABSENCE_NOT_AUTHORIZED in _codes(plan)


def test_unobserved_known_path_never_becomes_missing() -> None:
    location = _location("not-observed.jpg")
    plan = plan_changes(_assessment(entries=()), _snapshot(locations=(location,)), _context())

    assert plan.changes == ()
    assert location.availability is LocationAvailability.PRESENT
    assert plan.authorizes_catalog_mutation is False


def test_multiple_locations_for_one_asset_are_compared_by_exact_path() -> None:
    locations = (
        _location("a.jpg"),
        _location("b.jpg", identifier=OTHER_LOCATION_ID),
    )
    plan = plan_changes(_assessment((_entry("b.jpg"),)), _snapshot(locations=locations), _context())

    assert plan.changes[0].location_id == OTHER_LOCATION_ID
    assert plan.changes[0].asset_id == ASSET_ID


def test_same_hash_on_different_assets_does_not_merge_or_match() -> None:
    digest = "a" * 64
    assets = (_asset(ASSET_ID, digest), _asset(OTHER_ASSET_ID, digest))
    locations = (_location("known.jpg"),)
    plan = plan_changes(
        _assessment((_entry("new.jpg"),)), _snapshot(assets=assets, locations=locations), _context()
    )

    assert plan.changes[0].classification is ChangeClassification.NEW_FILE_CANDIDATE
    assert plan.changes[0].asset_id is None


def test_potential_hardlinks_do_not_attach_or_merge_assets() -> None:
    identity = PhysicalIdentity(8, 80)
    entries = (_entry("one.jpg", identity=identity), _entry("two.jpg", identity=identity))
    plan = plan_changes(_assessment(entries), _snapshot(assets=(), locations=()), _context())

    assert [item.classification for item in plan.changes] == [
        ChangeClassification.NEW_FILE_CANDIDATE,
        ChangeClassification.NEW_FILE_CANDIDATE,
    ]
    assert all(item.asset_id is None for item in plan.changes)


def test_previously_missing_path_is_a_new_candidate_not_known_location() -> None:
    missing = _location(availability=LocationAvailability.MISSING)
    plan = plan_changes(_assessment(), _snapshot(locations=(missing,)), _context())

    assert plan.changes[0].classification is ChangeClassification.NEW_FILE_CANDIDATE
    assert plan.changes[0].diagnostics[0].code is DiagnosticCode.PREVIOUSLY_MISSING_PATH


@pytest.mark.parametrize("recursive", [True, False])
def test_matching_recursive_and_non_recursive_scope_is_accepted(recursive: bool) -> None:
    scope = ScanScope("album", recursive, False)
    assessment = _assessment((_entry("album/photo.jpg"),), scope=scope)
    snapshot = _snapshot(locations=(_location("album/photo.jpg"),), scope=scope)

    plan = plan_changes(assessment, snapshot, _context(scope))

    assert plan.changes[0].classification is ChangeClassification.KNOWN_LOCATION_OBSERVED


def test_scope_mismatch_blocks_comparison() -> None:
    plan = plan_changes(
        _assessment(),
        _snapshot(scope=ScanScope(".", False, False)),
        _context(),
    )

    assert plan.status is PlanStatus.BLOCKED
    assert DiagnosticCode.SCOPE_MISMATCH in _codes(plan)


def test_root_path_or_id_mismatch_blocks_comparison() -> None:
    wrong_path = replace(_context(), observed_root_path="/synthetic/Library")
    path_plan = plan_changes(_assessment(), _snapshot(), wrong_path)
    wrong_id = replace(_context(), library_root_id="99999999-9999-4999-8999-999999999999")
    id_plan = plan_changes(_assessment(), _snapshot(), wrong_id)

    assert DiagnosticCode.ROOT_PATH_MISMATCH in _codes(path_plan)
    assert DiagnosticCode.ROOT_ID_MISMATCH in _codes(id_plan)
    assert path_plan.status is id_plan.status is PlanStatus.BLOCKED


@pytest.mark.parametrize("status", [ScanStatus.PARTIAL, ScanStatus.CANCELLED])
def test_valid_positive_observations_survive_incomplete_runs(status: ScanStatus) -> None:
    plan = plan_changes(_assessment(status=status), _snapshot(), _context())

    assert plan.status is PlanStatus.INCONCLUSIVE
    assert plan.changes[0].classification is ChangeClassification.KNOWN_LOCATION_OBSERVED
    assert DiagnosticCode.INCOMPLETE_COVERAGE in _codes(plan)
    assert plan.permits_absence_conclusions is False


@pytest.mark.parametrize("status", [ScanStatus.ROOT_UNAVAILABLE, ScanStatus.FAILED])
def test_unavailable_or_failed_run_never_proposes_absence(status: ScanStatus) -> None:
    plan = plan_changes(_assessment(status=status), _snapshot(), _context())

    assert plan.changes == ()
    assert plan.permits_absence_conclusions is False
    assert plan.status is PlanStatus.INCONCLUSIVE


def test_invalid_assessment_blocks_all_observations() -> None:
    assessment = replace(_assessment(), run_id="invalid")
    plan = plan_changes(assessment, _snapshot(), _context())

    assert plan.status is PlanStatus.BLOCKED
    assert plan.changes[0].classification is ChangeClassification.BLOCKED


@pytest.mark.parametrize(
    "assessment",
    [
        replace(_assessment(), coverage="complete_recursive_scope"),
        replace(_assessment(), accepted_entries=(_entry("../escape.jpg"),)),
        replace(_assessment(), accepted_entries=(_entry(), _entry())),
        replace(_assessment(), root=RootObservation(ROOT_PATH, ROOT_PATH, PhysicalIdentity(-1, 1))),
    ],
)
def test_forged_assessment_contracts_block_all_observations(assessment) -> None:
    plan = plan_changes(assessment, _snapshot(), _context())

    assert plan.status is PlanStatus.BLOCKED
    assert DiagnosticCode.INVALID_ASSESSMENT in _codes(plan)
    assert all(item.classification is ChangeClassification.BLOCKED for item in plan.changes)


def test_duplicate_active_paths_block_snapshot() -> None:
    locations = (
        _location(),
        _location(identifier=OTHER_LOCATION_ID, asset_id=OTHER_ASSET_ID),
    )
    plan = plan_changes(
        _assessment(),
        _snapshot(assets=(_asset(), _asset(OTHER_ASSET_ID)), locations=locations),
        _context(),
    )

    assert plan.status is PlanStatus.BLOCKED
    assert DiagnosticCode.ACTIVE_LOCATION_CONFLICT in _codes(plan)


@pytest.mark.parametrize(
    "snapshot",
    [
        _snapshot(assets=(replace(_asset(), id="bad"),)),
        _snapshot(locations=(_location("../escape.jpg"),)),
        _snapshot(locations=(replace(_location(), library_root_id=OTHER_ASSET_ID),)),
        _snapshot(locations=(replace(_location(), asset_id=OTHER_ASSET_ID),)),
        replace(_snapshot(), library_root="invalid"),  # type: ignore[arg-type]
    ],
)
def test_malformed_snapshot_blocks(snapshot: CatalogSnapshot) -> None:
    plan = plan_changes(_assessment(), snapshot, _context())

    assert plan.status is PlanStatus.BLOCKED
    assert DiagnosticCode.INVALID_SNAPSHOT in _codes(plan)


@pytest.mark.parametrize(
    "snapshot",
    [
        _snapshot(assets=(replace(_asset(), sha256="bad", hash_state=HashState.VERIFIED),)),
        _snapshot(assets=(replace(_asset(), byte_size=-1),)),
        _snapshot(locations=(replace(_location(), observed_mtime_ns=-1),)),
        _snapshot(
            locations=(
                replace(
                    _location(),
                    entry_type=CatalogEntryType.SYMLINK,
                    symlink_target=None,
                ),
            )
        ),
        _snapshot(locations=(replace(_location(), availability=LocationAvailability.OFFLINE),)),
        replace(_snapshot(), read_version=42),
    ],
)
def test_snapshot_fields_incompatible_with_sqlite_contract_block(snapshot) -> None:
    plan = plan_changes(_assessment(), snapshot, _context())

    assert plan.status is PlanStatus.BLOCKED
    assert DiagnosticCode.INVALID_SNAPSHOT in _codes(plan)


def test_offline_library_rejects_active_present_location() -> None:
    snapshot = _snapshot()
    offline_root = replace(snapshot.library_root, availability=RootAvailability.OFFLINE)

    plan = plan_changes(_assessment(), replace(snapshot, library_root=offline_root), _context())

    assert plan.status is PlanStatus.BLOCKED
    assert DiagnosticCode.INVALID_SNAPSHOT in _codes(plan)


def test_missing_or_blank_read_version_is_explicitly_inconclusive() -> None:
    for version in (None, ""):
        plan = plan_changes(_assessment(), replace(_snapshot(), read_version=version), _context())

        assert plan.status is PlanStatus.INCONCLUSIVE
        assert DiagnosticCode.READ_VERSION_UNAVAILABLE in _codes(plan)


def test_contradictory_physical_identity_blocks_only_observed_path() -> None:
    evidence = (LocationPhysicalEvidence(LOCATION_ID, PhysicalIdentity(9, 90)),)
    plan = plan_changes(_assessment(), _snapshot(evidence=evidence), _context())

    assert plan.status is PlanStatus.BLOCKED
    assert plan.changes[0].classification is ChangeClassification.BLOCKED
    assert plan.changes[0].diagnostics[0].code is DiagnosticCode.PHYSICAL_IDENTITY_CONTRADICTION


def test_same_physical_identity_across_assets_blocks_snapshot_but_same_asset_does_not() -> None:
    identity = PhysicalIdentity(9, 90)
    locations = (
        _location("one.jpg"),
        _location("two.jpg", identifier=OTHER_LOCATION_ID, asset_id=OTHER_ASSET_ID),
    )
    evidence = (
        LocationPhysicalEvidence(LOCATION_ID, identity),
        LocationPhysicalEvidence(OTHER_LOCATION_ID, identity),
    )
    plan = plan_changes(
        _assessment((_entry("one.jpg", identity=identity),)),
        _snapshot(
            assets=(_asset(), _asset(OTHER_ASSET_ID)), locations=locations, evidence=evidence
        ),
        _context(),
    )

    assert plan.status is PlanStatus.BLOCKED
    assert DiagnosticCode.PHYSICAL_IDENTITY_CONTRADICTION in _codes(plan)

    same_asset = replace(locations[1], asset_id=ASSET_ID)
    safe_plan = plan_changes(
        _assessment((_entry("one.jpg", identity=identity),)),
        _snapshot(locations=(locations[0], same_asset), evidence=evidence),
        _context(),
    )
    assert DiagnosticCode.PHYSICAL_IDENTITY_CONTRADICTION not in _codes(safe_plan)


def test_unavailable_root_identity_is_explicitly_inconclusive() -> None:
    assessment = _assessment(root=RootObservation(ROOT_PATH, ROOT_PATH, None))
    plan = plan_changes(assessment, _snapshot(), replace(_context(), catalog_root_identity=None))

    assert plan.status is PlanStatus.INCONCLUSIVE
    assert DiagnosticCode.ROOT_IDENTITY_UNAVAILABLE in _codes(plan)


def test_missing_optional_physical_identity_remains_known_but_inconclusive() -> None:
    evidence = (LocationPhysicalEvidence(LOCATION_ID, PhysicalIdentity(1, 20)),)
    plan = plan_changes(
        _assessment((_entry(identity=None),)), _snapshot(evidence=evidence), _context()
    )

    assert plan.changes[0].classification is ChangeClassification.KNOWN_LOCATION_OBSERVED
    assert plan.changes[0].diagnostics[0].code is DiagnosticCode.PHYSICAL_IDENTITY_UNAVAILABLE
    assert plan.status is PlanStatus.INCONCLUSIVE


def test_case_and_unicode_are_not_normalized_for_matching() -> None:
    entries = (_entry("PHOTO.jpg"), _entry("cafe\N{COMBINING ACUTE ACCENT}.jpg"))
    locations = (
        _location("photo.jpg"),
        _location("caf\N{LATIN SMALL LETTER E WITH ACUTE}.jpg", identifier=OTHER_LOCATION_ID),
    )
    plan = plan_changes(_assessment(entries), _snapshot(locations=locations), _context())

    assert all(
        item.classification is ChangeClassification.NEW_FILE_CANDIDATE for item in plan.changes
    )


def test_non_file_and_unconfirmed_information_are_not_new_file_candidates() -> None:
    plan = plan_changes(
        _assessment((_entry("shortcut", entry_type=EntryType.SYMLINK),)),
        _snapshot(assets=(), locations=()),
        _context(),
    )

    assert plan.changes[0].classification is ChangeClassification.INCONCLUSIVE


def test_planning_is_deterministic_immutable_and_has_no_side_effect_api() -> None:
    assessment = _assessment()
    snapshot = _snapshot()
    context = _context()

    first = plan_changes(assessment, snapshot, context)
    second = plan_changes(assessment, snapshot, context)

    assert first == second
    with pytest.raises(FrozenInstanceError):
        first.status = PlanStatus.BLOCKED  # type: ignore[misc]
    assert first.authorizes_catalog_mutation is False
    assert first.permits_absence_conclusions is False
    with pytest.raises(TypeError):
        CatalogChangePlan(
            first.run_id,
            first.library_root_id,
            first.scope,
            first.snapshot_read_version,
            first.status,
            first.changes,
            first.diagnostics,
            authorizes_catalog_mutation=True,
        )
