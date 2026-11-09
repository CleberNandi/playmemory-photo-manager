"""Owner-thread admission/result registry; no worker, IPC, or SQLite execution here."""

from __future__ import annotations

import copy
import threading
from dataclasses import dataclass
from uuid import uuid4

from .models import (
    IngestionAuthorizationError,
    IngestionBatchStatus,
    IngestionItemResult,
    IngestionReport,
)
from .models import (
    IngestionItemDisposition as Disposition,
)
from .preparation import PreparationError, PreparationInput, _uuid, _validate_input
from .scoped_authorization import ScopedIngestionAuthorization, authorize_scoped_ingestion
from .scoping import ScopedIngestionProposal


@dataclass(frozen=True, slots=True)
class ApplicationInput:
    command_id: str
    session_id: str
    window_id: str
    proposal_id: str
    source: PreparationInput
    scoped: ScopedIngestionProposal
    authorization: ScopedIngestionAuthorization


@dataclass(slots=True)
class _Command:
    identifier: str
    signature: tuple
    payload: ApplicationInput | None
    state: str = "queued"
    result: dict | None = None


class ApplicationCommands:
    """One queued/running slot, 32 volatile results, strict owner/session/window binding.

    Providers are private backend callbacks, never request parameters. An executor
    must claim once, supervise a worker, then finish or report a reaped failure.
    """

    def __init__(self, session_id, window_id, *, active_guard, resolve_proposal, validate_source):
        _uuid(session_id)
        _uuid(window_id)
        self.session_id, self.window_id = session_id, window_id
        self._guard, self._resolve, self._validate = active_guard, resolve_proposal, validate_source
        self._owner = threading.get_ident()
        self._closed = self._suspended = self._closing = False
        self._commands = {}
        self._identifiers = {}
        self._active = None

    def _require(self):
        if threading.get_ident() != self._owner:
            raise PreparationError("invalid_request")
        if self._closed:
            raise PreparationError("stale_session")
        self._guard()

    def _scope(self, session_id, window_id):
        self._require()
        _uuid(session_id)
        _uuid(window_id)
        if (session_id, window_id) != (self.session_id, self.window_id):
            raise PreparationError("stale_session")

    @property
    def busy(self):
        return self._active is not None

    @property
    def closing(self):
        return self._closing

    @property
    def suspended(self):
        return self._suspended

    def _view(self, command):
        return copy.deepcopy(
            {"command_id": command.identifier, "state": command.state, "result": command.result}
        )

    def admit(self, params):
        self._require()
        fields = {"session_id", "window_id", "proposal_id", "candidate_ids", "client_request_id"}
        if not isinstance(params, dict) or set(params) != fields:
            raise PreparationError("invalid_request")
        self._scope(params["session_id"], params["window_id"])
        _uuid(params["proposal_id"])
        _uuid(params["client_request_id"])
        ids = params["candidate_ids"]
        if not isinstance(ids, list) or len(ids) > 100:
            raise PreparationError("invalid_request")
        for identifier in ids:
            _uuid(identifier)
        if len(set(ids)) != len(ids):
            raise PreparationError("invalid_request")
        signature = (params["proposal_id"], tuple(sorted(ids)))
        previous = self._commands.get(params["client_request_id"])
        if previous is not None:
            if previous.signature != signature:
                raise PreparationError("invalid_request")
            return self._view(previous)
        if self._closing:
            raise PreparationError("stale_session")
        if self._suspended:
            raise PreparationError("outcome_unknown")
        if self.busy:
            raise PreparationError("busy")
        if len(self._commands) == 32:
            raise PreparationError("resource_limit")
        scoped, source = self._resolve(params["proposal_id"])
        if not isinstance(scoped, ScopedIngestionProposal) or not isinstance(
            source, PreparationInput
        ):
            raise PreparationError("invalid_request")
        _validate_input(source)
        if (
            source.root_id != scoped.original.plan.library_root_id
            or source.root_path != scoped.original.scan_result.root.absolute_path
            or source.root_identity
            != (
                scoped.original.scan_result.root.physical_identity.device,
                scoped.original.scan_result.root.physical_identity.file_id,
            )
        ):
            raise PreparationError("stale_session")
        self._validate(source)
        try:
            authorization = authorize_scoped_ingestion(scoped, tuple(ids))
        except IngestionAuthorizationError:
            raise PreparationError("invalid_request") from None
        identifier = str(uuid4())
        payload = ApplicationInput(
            identifier,
            self.session_id,
            self.window_id,
            params["proposal_id"],
            source,
            scoped,
            authorization,
        )
        command = _Command(identifier, signature, payload)
        self._commands[params["client_request_id"]] = command
        self._identifiers[identifier] = command
        self._active = identifier
        return self._view(command)

    def _command(self, session_id, window_id, identifier):
        self._scope(session_id, window_id)
        _uuid(identifier)
        command = self._identifiers.get(identifier)
        if command is None:
            raise PreparationError("stale_session")
        return command

    def status(self, session_id, window_id, identifier):
        return self._view(self._command(session_id, window_id, identifier))

    def claim(self, session_id, window_id, identifier):
        command = self._command(session_id, window_id, identifier)
        if command.state != "queued" or self._suspended:
            raise PreparationError("invalid_request")
        payload = command.payload
        try:
            scoped, source = self._resolve(payload.proposal_id)
            if scoped != payload.scoped or source != payload.source:
                raise PreparationError("stale_session")
            self._validate(source)
        except PreparationError as error:
            self._settle(
                command, "completed", {"status": "rejected", "diagnostic": error.code, "items": []}
            )
            raise
        command.state = "running"
        return payload

    def _settle(self, command, state, result):
        command.state, command.result, command.payload = state, result, None
        self._active = None

    def cancel_queued(self, session_id, window_id, identifier):
        command = self._command(session_id, window_id, identifier)
        if command.state != "queued":
            raise PreparationError("busy")
        self._settle(command, "completed", {"status": "cancelled", "diagnostic": None, "items": []})
        return self._view(command)

    def worker_failed(self, session_id, window_id, identifier, *, reaped):
        command = self._command(session_id, window_id, identifier)
        if command.state != "running" or reaped is not True:
            raise PreparationError("busy")
        self._suspended = True
        self._settle(
            command,
            "outcome_unknown",
            {"status": "transaction_failed", "diagnostic": "outcome_unknown", "items": []},
        )
        return self._view(command)

    def finish(self, session_id, window_id, identifier, report, *, reaped):
        command = self._command(session_id, window_id, identifier)
        if command.state != "running" or reaped is not True:
            raise PreparationError("busy")
        try:
            result = self._project(command.payload, report)
        except (ValueError, TypeError, AttributeError, PreparationError):
            # A worker's invalid result cannot establish that no commit occurred.
            return self.worker_failed(session_id, window_id, identifier, reaped=True)
        uncertain = result["diagnostic"] == "outcome_unknown"
        self._suspended |= uncertain
        self._settle(command, "outcome_unknown" if uncertain else "completed", result)
        return self._view(command)

    @staticmethod
    def _project(payload, report):
        if not isinstance(report, IngestionReport) or (
            report.run_id,
            report.library_root_id,
            report.plan_fingerprint,
        ) != (
            payload.scoped.original.plan.run_id,
            payload.source.root_id,
            payload.scoped.scope_fingerprint,
        ):
            raise ValueError("invalid worker binding")
        if not isinstance(report.status, IngestionBatchStatus) or report.diagnostic not in {
            None,
            "no_authorization",
            "invalid_authorization",
            "active_transaction",
            "invalid_observation",
            "catalog_changed",
            "source_changed",
            "verification_timeout",
            "resource_limit",
            "transaction_failed",
            "outcome_unknown",
            "unsupported_platform",
            "invalid_mount_binding",
        }:
            raise ValueError("invalid worker result")
        if not isinstance(report.items, tuple) or not all(
            isinstance(item, IngestionItemResult) for item in report.items
        ):
            raise ValueError("invalid result items")
        count = len(payload.authorization.selections)
        if (
            report.status is IngestionBatchStatus.NO_AUTHORIZATION
            or (report.status is IngestionBatchStatus.EMPTY_SELECTION and count)
            or (report.status is IngestionBatchStatus.APPLIED and not count)
        ):
            raise ValueError("invalid batch outcome")
        expected = set(payload.scoped.eligible_candidates)
        if (
            len(report.items) != len(expected)
            or {item.candidate for item in report.items} != expected
        ):
            raise ValueError("incomplete worker result")
        chosen = {
            item.candidate: identifier
            for identifier, item in zip(
                payload.authorization.candidate_ids, payload.authorization.selections, strict=True
            )
        }
        items = []
        for item in report.items:
            identifier = chosen.get(item.candidate)
            if identifier is None:
                if (
                    item.disposition is not Disposition.IGNORED_NOT_AUTHORIZED
                    or item.asset_id is not None
                    or item.location_id is not None
                ):
                    raise ValueError("unauthorized worker write")
                continue
            if report.status is IngestionBatchStatus.APPLIED:
                if report.diagnostic is not None or item.disposition is not Disposition.CREATED:
                    raise ValueError("incomplete successful batch")
                _uuid(item.asset_id)
                _uuid(item.location_id)
            elif (
                item.disposition
                is not {
                    IngestionBatchStatus.REJECTED: Disposition.BLOCKED,
                    IngestionBatchStatus.CONFLICT: Disposition.CONFLICT,
                    IngestionBatchStatus.TRANSACTION_FAILED: Disposition.TRANSACTION_FAILED,
                }.get(report.status)
                or item.asset_id is not None
                or item.location_id is not None
                or item.disposition
                not in {
                    Disposition.BLOCKED,
                    Disposition.CONFLICT,
                    Disposition.TRANSACTION_FAILED,
                }
            ):
                raise ValueError("uncommitted worker identifiers")
            items.append(
                {
                    "candidate_id": identifier,
                    "disposition": item.disposition.value,
                    "asset_id": item.asset_id,
                    "location_id": item.location_id,
                }
            )
        if report.status is IngestionBatchStatus.APPLIED and (
            len({item["asset_id"] for item in items}) != len(items)
            or len({item["location_id"] for item in items}) != len(items)
        ):
            raise ValueError("merged worker identities")
        return {"status": report.status.value, "diagnostic": report.diagnostic, "items": items}

    def close(self):
        self._require()
        self._closing = True
        if self._active is not None and self._identifiers[self._active].state == "running":
            raise PreparationError("busy")
        self._closed = True
        self._active = None
        self._commands.clear()
        self._identifiers.clear()
