from __future__ import annotations

import uuid
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta

import pytest

from playmemories_photo_manager.evidence import (
    CoverageClassification,
    DecisionImpediment,
    InferenceKind,
    PortabilityLimitation,
    ReasonCode,
    StructuralValidation,
    evaluate,
    evaluator,
)
from playmemories_photo_manager.scanner import (
    ConfinementKind,
    EntryObservation,
    EntryType,
    EvidenceKind,
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

NOW = datetime(2026, 10, 24, 12, tzinfo=UTC)
TIMESTAMPS = ObservedTimestamps(modified_ns=10, accessed_ns=None, changed_ns=20)
ROOT = RootObservation("/synthetic", "/synthetic", PhysicalIdentity(1, 100))
POSIX = ScanEnvironment(HostPlatform.POSIX, ConfinementKind.DESCRIPTOR_RELATIVE)


def _entry(
    path: str = "photo.jpg",
    *,
    entry_type: EntryType = EntryType.FILE,
    size: int | None = 10,
    identity: PhysicalIdentity | None = None,
    evidence_kind: EvidenceKind = EvidenceKind.DIRECT_OBSERVATION,
) -> EntryObservation:
    return EntryObservation(path, entry_type, size, TIMESTAMPS, identity, evidence_kind)


def _failure(
    path: str | None = "denied", *, operation: FailureOperation = FailureOperation.OBSERVE_ENTRY
) -> ObservationFailure:
    return ObservationFailure(path, operation, FailureKind.PERMISSION_DENIED, True, 13)


def _result(
    *,
    status: ScanStatus = ScanStatus.COMPLETE,
    recursive: bool = True,
    entries: tuple[EntryObservation, ...] = (),
    covered: tuple[str, ...] = (".",),
    failures: tuple[ObservationFailure, ...] = (),
    root: RootObservation | None = ROOT,
    environment: ScanEnvironment | None = POSIX,
) -> ScanResult:
    return ScanResult(
        run_id=str(uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")),
        root=root,
        scope=ScanScope(".", recursive, False),
        started_at=NOW,
        finished_at=NOW + timedelta(seconds=1),
        status=status,
        covered_directories=covered,
        entries=entries,
        failures=failures,
        environment=environment,
    )


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        (_result(), CoverageClassification.COMPLETE_RECURSIVE_SCOPE),
        (_result(recursive=False), CoverageClassification.COMPLETE_NON_RECURSIVE_SCOPE),
        (
            _result(status=ScanStatus.PARTIAL, failures=(_failure(),)),
            CoverageClassification.PARTIAL,
        ),
        (_result(status=ScanStatus.CANCELLED), CoverageClassification.CANCELLED),
        (
            _result(
                status=ScanStatus.ROOT_UNAVAILABLE,
                root=None,
                covered=(),
                failures=(_failure(None, operation=FailureOperation.OBSERVE_ROOT),),
            ),
            CoverageClassification.ROOT_UNAVAILABLE,
        ),
        (
            _result(
                status=ScanStatus.FAILED,
                covered=(),
                failures=(_failure(".", operation=FailureOperation.ENUMERATE_DIRECTORY),),
            ),
            CoverageClassification.FAILED,
        ),
    ],
)
def test_completeness_classifications(result: ScanResult, expected: CoverageClassification) -> None:
    assessment = evaluate(result)

    assert assessment.structural_validation is StructuralValidation.VALID
    assert assessment.coverage is expected
    assert assessment.original_status is result.status
    assert assessment.run_id == result.run_id


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ({"run_id": "invalid"}, ReasonCode.INVALID_RUN_ID),
        ({"finished_at": NOW - timedelta(seconds=1)}, ReasonCode.INVALID_TIME_RANGE),
        (
            {"entries": (_entry("../escape.jpg"),)},
            ReasonCode.INVALID_ENTRY_PATH,
        ),
        (
            {"entries": (_entry(), _entry())},
            ReasonCode.DUPLICATE_ENTRY_PATH,
        ),
        (
            {
                "entries": (_entry("album", entry_type=EntryType.DIRECTORY, size=None),),
                "covered_directories": (".",),
            },
            ReasonCode.DIRECTORY_NOT_COVERED,
        ),
        (
            {"failures": (_failure(),)},
            ReasonCode.COMPLETE_HAS_FAILURES,
        ),
        (
            {"covered_directories": ()},
            ReasonCode.COMPLETE_ROOT_NOT_COVERED,
        ),
        (
            {"entries": (_entry(size=None),)},
            ReasonCode.FILE_SIZE_MISSING,
        ),
        (
            {"entries": (_entry("link", entry_type=EntryType.SYMLINK, size=2),)},
            ReasonCode.NON_FILE_HAS_SIZE,
        ),
    ],
)
def test_structural_contradictions_are_rejected(
    mutation: dict[str, object], reason: ReasonCode
) -> None:
    result = replace(_result(), **mutation)

    assessment = evaluate(result)

    assert assessment.structural_validation is StructuralValidation.INVALID
    assert assessment.coverage is CoverageClassification.INVALID
    assert assessment.accepted_entries == ()
    assert DecisionImpediment.STRUCTURALLY_INVALID in assessment.decision_impediments
    assert reason in {item.code for item in assessment.reasons}


def test_direct_observations_preserve_optional_unknown_values() -> None:
    entry = _entry(identity=None)

    assessment = evaluate(_result(entries=(entry,)))

    assert assessment.accepted_entries == (entry,)
    assert assessment.inconclusive_entries == ()
    assert assessment.accepted_entries[0].timestamps.accessed_ns is None
    assert ReasonCode.FILESYSTEM_TIMESTAMPS_NOT_CAPTURE_TIME in {
        reason.code for reason in assessment.reasons
    }


def test_same_physical_identity_produces_only_potential_hardlink_inference() -> None:
    identity = PhysicalIdentity(7, 42)
    first = _entry("first.jpg", identity=identity)
    second = _entry("second.jpg", identity=identity)

    assessment = evaluate(_result(entries=(first, second)))

    assert len(assessment.inferences) == 1
    assert assessment.inferences[0].kind is InferenceKind.POTENTIAL_HARDLINK
    assert assessment.inferences[0].relative_paths == ("first.jpg", "second.jpg")
    assert DecisionImpediment.LOGICAL_IDENTITY_UNCONFIRMED in assessment.decision_impediments


def test_same_size_without_physical_identity_produces_no_identity_inference() -> None:
    assessment = evaluate(_result(entries=(_entry("a.jpg"), _entry("b.jpg"))))

    assert assessment.inferences == ()
    assert DecisionImpediment.CONTENT_NOT_VERIFIED in assessment.decision_impediments


def test_different_sizes_without_physical_identity_are_independent_observations() -> None:
    assessment = evaluate(_result(entries=(_entry("a.jpg", size=10), _entry("b.jpg", size=20))))

    assert assessment.structural_validation is StructuralValidation.VALID
    assert assessment.inferences == ()


def test_symlink_is_direct_evidence_without_target_or_traversal_claim() -> None:
    link = _entry("shortcut", entry_type=EntryType.SYMLINK, size=None)

    assessment = evaluate(_result(entries=(link,)))

    assert assessment.accepted_entries == (link,)
    assert assessment.inferences == ()


def test_unconfirmed_input_is_kept_inconclusive() -> None:
    entry = _entry(evidence_kind=EvidenceKind.UNCONFIRMED_INFERENCE)

    assessment = evaluate(_result(status=ScanStatus.CANCELLED, entries=(entry,), covered=()))

    assert assessment.accepted_entries == ()
    assert assessment.inconclusive_entries == (entry,)
    assert ReasonCode.UNCONFIRMED_INFERENCE in {reason.code for reason in assessment.reasons}


def test_complete_result_cannot_depend_on_non_direct_evidence() -> None:
    entry = _entry(evidence_kind=EvidenceKind.UNCONFIRMED_INFERENCE)

    assessment = evaluate(_result(entries=(entry,)))

    assert assessment.structural_validation is StructuralValidation.INVALID
    assert assessment.accepted_entries == ()
    assert ReasonCode.COMPLETE_HAS_NON_DIRECT_EVIDENCE in {
        reason.code for reason in assessment.reasons
    }


def test_permission_and_disappearance_are_failures_not_negative_observations() -> None:
    failures = (
        _failure("private"),
        ObservationFailure(
            "gone.jpg", FailureOperation.OBSERVE_ENTRY, FailureKind.DISAPPEARED, True, 2
        ),
    )

    assessment = evaluate(_result(status=ScanStatus.PARTIAL, failures=failures))

    assert assessment.failures == failures
    assert assessment.accepted_entries == ()
    assert not hasattr(assessment, "missing_entries")


def test_root_unavailable_never_supports_absence() -> None:
    result = _result(
        status=ScanStatus.ROOT_UNAVAILABLE,
        root=None,
        covered=(),
        failures=(_failure(None, operation=FailureOperation.OBSERVE_ROOT),),
    )

    assessment = evaluate(result)

    assert DecisionImpediment.ROOT_UNAVAILABLE in assessment.decision_impediments
    assert ReasonCode.ROOT_UNAVAILABLE_PROVES_NO_ABSENCE in {
        reason.code for reason in assessment.reasons
    }


def test_platform_provenance_and_windows_path_confinement_are_explicit() -> None:
    unknown = evaluate(_result(environment=None))
    windows = evaluate(
        _result(environment=ScanEnvironment(HostPlatform.WINDOWS, ConfinementKind.PATH_BASED))
    )

    assert (
        PortabilityLimitation.PLATFORM_OR_CONFINEMENT_UNRECORDED in unknown.portability_limitations
    )
    assert (
        PortabilityLimitation.PATH_BASED_CONFINEMENT_NOT_RACE_SAFE
        in windows.portability_limitations
    )
    assert DecisionImpediment.CONFINEMENT_NOT_DEMONSTRATED in windows.decision_impediments


def test_assessment_and_received_objects_are_immutable_and_unchanged() -> None:
    entry = _entry()
    result = _result(entries=(entry,))

    assessment = evaluate(result)

    assert result.entries == (entry,)
    with pytest.raises(FrozenInstanceError):
        assessment.coverage = CoverageClassification.PARTIAL  # type: ignore[misc]
    with pytest.raises(TypeError, match="ScanResult"):
        evaluate(object())  # type: ignore[arg-type]


def test_evaluator_has_no_filesystem_sqlite_or_catalog_dependencies() -> None:
    assert "os" not in evaluator.__dict__
    assert "sqlite3" not in evaluator.__dict__
    assert "Catalog" not in evaluator.__dict__
    assert "Asset" not in evaluator.__dict__


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ({"started_at": "2026-10-24"}, ReasonCode.INVALID_CONTRACT_TYPE),
        (
            {"entries": (replace(_entry(), timestamps=ObservedTimestamps("bad", None, None)),)},
            ReasonCode.INVALID_TIMESTAMP,
        ),
        (
            {
                "environment": ScanEnvironment(
                    HostPlatform.WINDOWS, ConfinementKind.DESCRIPTOR_RELATIVE
                )
            },
            ReasonCode.INVALID_ENVIRONMENT,
        ),
    ],
)
def test_manually_constructed_invalid_types_are_diagnostic_not_accepted(
    mutation: dict[str, object], reason: ReasonCode
) -> None:
    assessment = evaluate(replace(_result(entries=(_entry(),)), **mutation))

    assert assessment.structural_validation is StructuralValidation.INVALID
    assert assessment.accepted_entries == ()
    assert assessment.inferences == ()
    assert reason in {item.code for item in assessment.reasons}


def test_complete_result_rejects_entries_outside_declared_scope() -> None:
    result = replace(
        _result(entries=(_entry("outside.jpg"),), covered=("album",)),
        scope=ScanScope("album", True, False),
    )

    assessment = evaluate(result)

    assert assessment.coverage is CoverageClassification.INVALID
    assert assessment.accepted_entries == ()
    assert ReasonCode.PATH_OUTSIDE_SCOPE in {item.code for item in assessment.reasons}


def test_non_recursive_result_rejects_descendant_observation() -> None:
    directory = _entry("album", entry_type=EntryType.DIRECTORY, size=None)
    result = _result(recursive=False, entries=(directory, _entry("album/photo.jpg")))

    assessment = evaluate(result)

    assert assessment.coverage is CoverageClassification.INVALID
    assert ReasonCode.PATH_OUTSIDE_SCOPE in {item.code for item in assessment.reasons}


def test_nested_entry_requires_observed_parent_directory() -> None:
    assessment = evaluate(_result(entries=(_entry("album/photo.jpg"),)))

    assert assessment.coverage is CoverageClassification.INVALID
    assert ReasonCode.ENTRY_PARENT_NOT_OBSERVED in {item.code for item in assessment.reasons}


def test_conflicting_physical_identity_does_not_produce_inference() -> None:
    identity = PhysicalIdentity(7, 42)
    result = _result(
        entries=(
            _entry("first.jpg", size=10, identity=identity),
            _entry("second.jpg", size=11, identity=identity),
        )
    )

    assessment = evaluate(result)

    assert assessment.structural_validation is StructuralValidation.INVALID
    assert assessment.accepted_entries == ()
    assert assessment.inferences == ()
    assert ReasonCode.PHYSICAL_IDENTITY_CONTRADICTION in {item.code for item in assessment.reasons}


def test_evaluation_is_deterministic() -> None:
    result = _result(entries=(_entry(identity=PhysicalIdentity(1, 2)),))

    assert evaluate(result) == evaluate(result)
