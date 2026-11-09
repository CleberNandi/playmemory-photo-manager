import json
import threading
from dataclasses import replace
from uuid import uuid4

import pytest
from jpeg_fixtures import jpeg

from playmemories_photo_manager.catalog import Catalog
from playmemories_photo_manager.catalog_ingestion.models import (
    IngestionBatchStatus,
    IngestionItemDisposition,
    IngestionItemResult,
    IngestionReport,
)
from playmemories_photo_manager.catalog_ingestion.preparation import PreparationError
from playmemories_photo_manager.catalog_ingestion.root_grants import RootGrantService
from playmemories_photo_manager.catalog_ingestion.scoped_application import apply_scoped_ingestion
from playmemories_photo_manager.library import LibraryError, LibrarySession


@pytest.fixture
def ready(tmp_path):
    import time

    session = LibrarySession.create(tmp_path / "catalog.sqlite3")
    root = tmp_path / "media"
    root.mkdir()
    (root / "a.jpg").write_bytes(jpeg(1))
    (root / "b.jpg").write_bytes(jpeg(3))
    service = RootGrantService(session, str(uuid4()), protected_paths=())
    grant = service.select(
        dict(
            session_id=service.session_id,
            window_id=service.window_id,
            path=str(root),
            recursive=True,
            identity_reviewed=True,
        )
    )
    job = service.prepare(
        dict(
            session_id=service.session_id,
            window_id=service.window_id,
            root_grant_id=grant["root_grant_id"],
            recursive=True,
            client_request_id=str(uuid4()),
        )
    )
    deadline = time.monotonic() + 8
    while service.preparation.busy and time.monotonic() < deadline:
        service.tick()
        time.sleep(0.01)
    status = service.preparation.status(service.session_id, service.window_id, job["operation_id"])
    assert status["state"] == "completed"
    page = service.preparation.page(service.session_id, service.window_id, status["proposal_id"])
    params = dict(
        session_id=service.session_id,
        window_id=service.window_id,
        proposal_id=status["proposal_id"],
        candidate_ids=[item["candidate_id"] for item in page["items"]],
        client_request_id=str(uuid4()),
    )
    yield session, service, root, params
    assert service.close()
    session.close()


def claim(service, command):
    return service.commands.claim(service.session_id, service.window_id, command["command_id"])


def report(payload, status=IngestionBatchStatus.CONFLICT, diagnostic="catalog_changed"):
    chosen = {item.candidate for item in payload.authorization.selections}
    items = tuple(
        IngestionItemResult(
            candidate,
            IngestionItemDisposition.CREATED
            if status is IngestionBatchStatus.APPLIED
            else IngestionItemDisposition.TRANSACTION_FAILED
            if status is IngestionBatchStatus.TRANSACTION_FAILED
            else IngestionItemDisposition.CONFLICT,
            str(uuid4()) if status is IngestionBatchStatus.APPLIED else None,
            str(uuid4()) if status is IngestionBatchStatus.APPLIED else None,
        )
        if candidate in chosen
        else IngestionItemResult(candidate, IngestionItemDisposition.IGNORED_NOT_AUTHORIZED)
        for candidate in payload.scoped.eligible_candidates
    )
    return IngestionReport(
        payload.scoped.original.plan.run_id,
        payload.source.root_id,
        payload.scoped.scope_fingerprint,
        status,
        items,
        diagnostic,
    )


def finish(service, command, result):
    return service.commands.finish(
        service.session_id, service.window_id, command["command_id"], result, reaped=True
    )


def test_actual_application_and_replay_return_same_result_without_reexecution(ready):
    session, service, _, params = ready
    command = service.commands.admit(params)
    assert service.commands.admit(params) == command
    payload = claim(service, command)
    with session.command_connection() as connection:
        result = apply_scoped_ingestion(
            Catalog(connection),
            payload.scoped,
            payload.authorization,
            expected_root_mount=payload.source.mount_id,
        )
    completed = finish(service, command, result)
    assert completed["result"]["status"] == "applied"
    reversed_choice = params | {"candidate_ids": list(reversed(params["candidate_ids"]))}
    assert service.commands.admit(reversed_choice) == completed
    assert service.commands._identifiers[command["command_id"]].payload is None
    assert len(Catalog(session.query_connection).list_assets()) == 2
    assert "relative_path" not in json.dumps(completed) and "catalog_path" not in json.dumps(
        completed
    )
    completed["result"]["items"].clear()
    assert len(service.commands.admit(params)["result"]["items"]) == 2


def test_same_request_with_different_choice_is_rejected_and_queued_close_revokes(ready):
    _, service, _, params = ready
    command = service.commands.admit(params)
    with pytest.raises(PreparationError, match="invalid_request"):
        service.commands.admit(params | {"candidate_ids": []})
    assert service.close()
    with pytest.raises(PreparationError, match="stale_session"):
        claim(service, command)


def test_only_one_command_runs_and_cannot_be_claimed_twice(ready):
    _, service, _, params = ready
    command = service.commands.admit(params)
    payload = claim(service, command)
    with pytest.raises(PreparationError, match="busy"):
        service.commands.admit(params | {"client_request_id": str(uuid4())})
    with pytest.raises(PreparationError, match="invalid_request"):
        claim(service, command)
    finish(service, command, report(payload))


def test_running_command_blocks_session_close_until_reaped(ready):
    session, service, _, params = ready
    command = service.commands.admit(params)
    payload = claim(service, command)
    with pytest.raises(LibraryError, match="busy"):
        session.close()
    with pytest.raises(PreparationError, match="busy"):
        service.commands.finish(
            service.session_id,
            service.window_id,
            command["command_id"],
            report(payload),
            reaped=False,
        )
    finish(service, command, report(payload))
    with pytest.raises(PreparationError, match="stale_session"):
        service.commands.admit(params | {"client_request_id": str(uuid4())})
    session.close()


def test_unknown_failure_suspends_new_commands_but_replays_original_result(ready):
    _, service, _, params = ready
    command = service.commands.admit(params)
    claim(service, command)
    with pytest.raises(PreparationError, match="busy"):
        service.commands.worker_failed(
            service.session_id, service.window_id, command["command_id"], reaped=False
        )
    unknown = service.commands.worker_failed(
        service.session_id, service.window_id, command["command_id"], reaped=True
    )
    assert service.commands.admit(params) == unknown
    with pytest.raises(PreparationError, match="outcome_unknown"):
        service.commands.admit(params | {"client_request_id": str(uuid4())})
    assert not service.commands.busy and service.commands.suspended


@pytest.mark.parametrize(
    "mutation", ["root", "fingerprint", "partial", "duplicate_ids", "diagnostic", "unexpected_item"]
)
def test_invalid_worker_report_is_unknown_not_false_success(ready, mutation):
    _, service, _, params = ready
    command = service.commands.admit(params)
    payload = claim(service, command)
    result = report(payload, IngestionBatchStatus.APPLIED, None)
    if mutation == "root":
        result = replace(result, library_root_id=str(uuid4()))
    if mutation == "fingerprint":
        result = replace(result, plan_fingerprint="forged")
    if mutation == "partial":
        result = replace(result, items=result.items[:1])
    if mutation == "duplicate_ids":
        result = replace(
            result,
            items=(result.items[0], replace(result.items[1], asset_id=result.items[0].asset_id)),
        )
    if mutation == "diagnostic":
        result = replace(result, diagnostic="private-path")
    if mutation == "unexpected_item":
        result = replace(result, items=("forged",))
    settled = finish(service, command, result)
    assert settled["state"] == "outcome_unknown" and service.commands.suspended
    assert settled["result"]["items"] == []


def test_rechecks_physical_binding_at_claim_and_caches_rejection(ready):
    _, service, root, params = ready
    command = service.commands.admit(params)
    root.rename(root.with_name("old-media"))
    root.mkdir()
    with pytest.raises(PreparationError, match="root_changed"):
        claim(service, command)
    assert service.commands.admit(params)["result"]["status"] == "rejected"
    assert not service.commands.busy


def test_limits_volatile_history_to_32_commands(ready):
    _, service, _, params = ready
    for _ in range(32):
        command = service.commands.admit(params | {"client_request_id": str(uuid4())})
        service.commands.cancel_queued(service.session_id, service.window_id, command["command_id"])
    with pytest.raises(PreparationError, match="resource_limit"):
        service.commands.admit(params | {"client_request_id": str(uuid4())})
    assert all(command.payload is None for command in service.commands._commands.values())


def test_rejects_extra_fields_cross_session_and_other_owner_thread(ready):
    _, service, _, params = ready
    with pytest.raises(PreparationError, match="invalid_request"):
        service.commands.admit(params | {"path": "/untrusted"})
    with pytest.raises(PreparationError, match="stale_session"):
        service.commands.admit(params | {"session_id": str(uuid4())})
    with pytest.raises(PreparationError, match="stale_session"):
        service.commands.admit(params | {"window_id": str(uuid4())})
    errors = []

    def other():
        try:
            service.commands.admit(params)
        except PreparationError as error:
            errors.append(error.code)

    thread = threading.Thread(target=other)
    thread.start()
    thread.join()
    assert errors == ["invalid_request"]


def test_queued_commands_block_new_preparation_and_native_selection(ready):
    _, service, root, params = ready
    command = service.commands.admit(params)
    with pytest.raises(PreparationError, match="busy"):
        service.select(
            dict(
                session_id=service.session_id,
                window_id=service.window_id,
                path=str(root),
                recursive=True,
                identity_reviewed=True,
            )
        )
    with pytest.raises(PreparationError, match="busy"):
        service.prepare(
            dict(
                session_id=service.session_id,
                window_id=service.window_id,
                root_grant_id=str(uuid4()),
                recursive=True,
                client_request_id=str(uuid4()),
            )
        )
    service.commands.cancel_queued(service.session_id, service.window_id, command["command_id"])


def test_uncertain_core_report_is_cached_and_suspends_the_session_commands(ready):
    _, service, root, params = ready
    command = service.commands.admit(params)
    payload = claim(service, command)
    core = report(payload, IngestionBatchStatus.TRANSACTION_FAILED, "outcome_unknown")
    result = finish(service, command, core)
    assert result["state"] == "outcome_unknown" and service.commands.admit(params) == result
    with pytest.raises(PreparationError, match="outcome_unknown"):
        service.select(
            dict(
                session_id=service.session_id,
                window_id=service.window_id,
                path=str(root),
                recursive=True,
                identity_reviewed=True,
            )
        )


def test_proposal_from_previous_preparation_cannot_be_claimed(ready):
    _, service, _, params = ready
    command = service.commands.admit(params)
    service.preparation._published = None  # Simulates invalidation before the executor claims.
    with pytest.raises(PreparationError, match="stale_session"):
        claim(service, command)
    assert service.commands.admit(params)["result"]["status"] == "rejected"
