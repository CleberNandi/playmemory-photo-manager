"""Pure catalogable projection; the original scan and plan are never rewritten."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import PurePosixPath
from uuid import UUID

from ..change_planning import ChangeClassification, DiagnosticCode, DiagnosticSeverity, PlanStatus
from ..evidence import CoverageClassification, DecisionImpediment
from ..scanner import ConfinementKind, EntryObservation, EntryType, HostPlatform, ScanStatus
from .images import EXTENSIONS, FORMATS
from .images import PROFILE as IMAGE_PROFILE
from .jpeg import PROFILE
from .media import EXCLUDED_REASONS, MediaEligibility, PhysicalFingerprint
from .models import CandidateReference, IngestionAuthorizationError, IngestionProposal
from .service import _proposal_evidence_error

MAX_PROPOSAL_BYTES = 8 * 1024 * 1024


class ProposalResourceLimitError(RuntimeError):
    def __init__(self):
        super().__init__("resource_limit")


@dataclass(frozen=True, slots=True)
class ScopedIngestionProposal:
    original: IngestionProposal
    eligibilities: tuple[MediaEligibility, ...]
    exclusions: tuple[MediaEligibility, ...]
    eligible_candidates: tuple[CandidateReference, ...]
    scope_fingerprint: str
    additions_only: bool = False


def _require(condition):
    if not condition:
        raise IngestionAuthorizationError("proposal is not eligible for catalogable scoping")


def _valid_identifier(value):
    try:
        return isinstance(value, str) and str(UUID(value)) == value
    except ValueError:
        return False


def _default(value):
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError("unsupported canonical value")


def _fingerprint(original, eligibilities, exclusions, eligible, additions_only):
    encoder = json.JSONEncoder(
        ensure_ascii=True, sort_keys=True, separators=(",", ":"), default=_default
    )
    digest = hashlib.sha256(b"additions_only\n" if additions_only else b"")
    size = 512  # Conservative envelope/digest/list overhead for the complete projection.
    # Include the entire private original and every eligibility, not just selected paths.
    for value in (original, *eligibilities, *exclusions, *eligible):
        for chunk in encoder.iterencode(asdict(value)):
            data = chunk.encode("utf-8")
            size += len(data)
            if size > MAX_PROPOSAL_BYTES:
                raise ProposalResourceLimitError
            digest.update(data)
        digest.update(b"\n")
        size += 1
        if size > MAX_PROPOSAL_BYTES:
            raise ProposalResourceLimitError
    return digest.hexdigest()


def _validate_eligibility(item, original, decode_paths):
    _require(isinstance(item, MediaEligibility))
    _require(_valid_identifier(item.candidate_id))
    _require(item.profile in (PROFILE, IMAGE_PROFILE))
    _require(isinstance(item.candidate, CandidateReference))
    _require(isinstance(item.observation, EntryObservation))
    decoded = item.observation.relative_path in decode_paths and item.state == "eligible"
    _require(item.decoding == ("verified" if decoded else "not_checked"))
    _require(item.candidate.run_id == original.scan_result.run_id)
    _require(item.candidate.library_root_id == original.plan.library_root_id)
    _require(item.candidate.relative_path == item.observation.relative_path)
    _require(item.detected_format is None or item.detected_format in FORMATS)
    _require(
        item.state == "eligible"
        and (
            (
                item.reason == "eligible_jpeg"
                and item.detected_format == "jpeg"
                and item.profile == PROFILE
            )
            or (
                item.reason == "eligible_image"
                and item.detected_format in FORMATS
                and item.profile == IMAGE_PROFILE
            )
        )
        or item.state == "excluded"
        and item.reason in EXCLUDED_REASONS
    )
    if item.observation.entry_type is not EntryType.FILE:
        _require(item.state == "excluded" and item.reason == "not_regular_file")
        _require(item.fingerprint is None and item.detected_format is None)
    elif item.reason == "unsupported_extension":
        _require(item.fingerprint is None and item.detected_format is None)
        _require(PurePosixPath(item.observation.relative_path).suffix.lower() not in EXTENSIONS)
    else:
        _require(item.reason != "not_regular_file")
        _require(PurePosixPath(item.observation.relative_path).suffix.lower() in EXTENSIONS)
        _require(isinstance(item.fingerprint, PhysicalFingerprint))
        fp = item.fingerprint
        observed = item.observation
        _require(observed.physical_identity is not None)
        expected = (
            observed.physical_identity.device,
            observed.physical_identity.file_id,
            observed.byte_size,
            observed.timestamps.modified_ns,
            observed.timestamps.changed_ns,
        )
        _require(fp.root == original.scan_result.root.physical_identity)
        _require(fp.before == fp.after == expected)


def scope_catalogable_proposal(
    original: IngestionProposal,
    eligibilities: tuple[MediaEligibility, ...],
    *,
    additions_only=False,
) -> ScopedIngestionProposal:
    """Validate trusted backend evidence; this is not an authorization or renderer API."""
    _require(type(additions_only) is bool)
    _require(_proposal_evidence_error(original, additions_only=additions_only) is None)
    assessment, plan, scan = original.assessment, original.plan, original.scan_result
    _require(
        scan.status is ScanStatus.COMPLETE
        and assessment.coverage is CoverageClassification.COMPLETE_RECURSIVE_SCOPE
        and scan.scope.relative_path == "."
        and scan.scope.recursive
        and not scan.scope.follows_links
        and scan.root is not None
        and scan.root.physical_identity is not None
        and scan.environment is not None
        and scan.environment.platform is HostPlatform.POSIX
        and scan.environment.confinement is ConfinementKind.DESCRIPTOR_RELATIVE
        and len(scan.entries) <= 2000
        and all(len(PurePosixPath(item.relative_path).parts) <= 32 for item in scan.entries)
    )
    _require(
        set(assessment.decision_impediments)
        <= {
            DecisionImpediment.ENUMERATION_NOT_ATOMIC,
            DecisionImpediment.CONTENT_NOT_VERIFIED,
            DecisionImpediment.LOGICAL_IDENTITY_UNCONFIRMED,
        }
    )
    _require(plan.status in (PlanStatus.READY, PlanStatus.INCONCLUSIVE))
    for diagnostic in plan.diagnostics:
        _require(diagnostic.severity is not DiagnosticSeverity.ERROR)
        if diagnostic.severity is DiagnosticSeverity.WARNING:
            _require(diagnostic.code is DiagnosticCode.ROOT_IDENTITY_UNAVAILABLE)
    _require(isinstance(eligibilities, tuple) and len(eligibilities) == len(scan.entries))
    by_path = {}
    identifiers = set()
    observations = {item.relative_path: item for item in scan.entries}
    decode_paths = {
        change.relative_path
        for change in plan.changes
        if additions_only and change.classification is ChangeClassification.NEW_FILE_CANDIDATE
    }
    for item in eligibilities:
        _validate_eligibility(item, original, decode_paths)
        path = item.candidate.relative_path
        _require(path not in by_path and item.candidate_id not in identifiers)
        _require(observations.get(path) == item.observation)
        by_path[path] = item
        identifiers.add(item.candidate_id)
    eligible = []
    for change in plan.changes:
        _require(change.classification is not ChangeClassification.BLOCKED)
        item = by_path[change.relative_path]
        if change.classification is ChangeClassification.INCONCLUSIVE:
            _require(len(change.diagnostics) == 1)
            diagnostic = change.diagnostics[0]
            _require(diagnostic.code is DiagnosticCode.NON_FILE_OBSERVATION)
            _require(diagnostic.severity is DiagnosticSeverity.WARNING)
            _require(item.reason == "not_regular_file" and item.state == "excluded")
            if change.observation.entry_type is EntryType.DIRECTORY:
                _require(change.relative_path in scan.covered_directories)
        else:
            _require(all(d.severity is DiagnosticSeverity.INFORMATION for d in change.diagnostics))
        if (
            change.classification is ChangeClassification.NEW_FILE_CANDIDATE
            and item.state == "eligible"
        ):
            eligible.append(item.candidate)
    ordered = tuple(sorted(eligibilities, key=lambda item: item.candidate.relative_path))
    exclusions = tuple(item for item in ordered if item.state == "excluded")
    eligible = tuple(sorted(eligible, key=lambda item: item.relative_path))
    return ScopedIngestionProposal(
        original,
        ordered,
        exclusions,
        eligible,
        _fingerprint(original, ordered, exclusions, eligible, additions_only),
        additions_only,
    )
