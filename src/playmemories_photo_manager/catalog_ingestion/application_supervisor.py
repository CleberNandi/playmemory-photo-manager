"""Application specialization of the existing bounded, nonblocking worker supervisor."""

from __future__ import annotations

import fcntl
import json
import os
import time
from dataclasses import asdict

from .application_commands import ApplicationInput
from .preparation import PreparationController, PreparationError, _validate_input
from .worker_wire import decode_application_report, encode_result


class ApplicationSupervisor(PreparationController):
    _worker_module = "playmemories_photo_manager.catalog_ingestion.application_worker"

    def __init__(self, commands):
        super().__init__(commands.session_id, commands.window_id)
        self.commands = commands
        self._payload_fd = None

    def _validate_value(self, value):
        if not isinstance(value, ApplicationInput) or (value.session_id, value.window_id) != (
            self.session_id,
            self.window_id,
        ):
            raise PreparationError("invalid_request")
        _validate_input(value.source)

    def _operation_identifier(self, value):
        return value.command_id

    def _request_bytes(self, value):
        # Sealed anonymous memory avoids temp files and streaming an 8MiB proposal
        # over the small command pipe while the owner must monitor the worker.
        fd = os.memfd_create("pm-application", os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
        self._payload_fd = fd
        data = encode_result(value.scoped)
        view = memoryview(data)
        while view:
            count = os.write(fd, view)
            if count <= 0:
                raise OSError("short anonymous payload write")
            view = view[count:]
        os.lseek(fd, 0, os.SEEK_SET)
        # Linux UAPI (linux/fcntl.h): some Python builds omit these constants.
        fcntl.fcntl(fd, getattr(fcntl, "F_ADD_SEALS", 1033), 0x000F)
        return (
            json.dumps(
                {
                    "source": asdict(value.source),
                    "candidate_ids": value.authorization.candidate_ids,
                    "decision_fingerprint": value.authorization.decision_fingerprint,
                },
                separators=(",", ":"),
                ensure_ascii=True,
            ).encode()
            + b"\n"
        )

    def _child_arguments(self):
        return (str(self._payload_fd),)

    def _inherited_fds(self):
        return (self._payload_fd,)

    def start(self, value, client_request_id):
        try:
            return super().start(value, client_request_id)
        finally:
            if self._payload_fd is not None:
                os.close(self._payload_fd)
                self._payload_fd = None

    def _finish(self, code):
        # The shared tick reached waitpid + EOF. Never release before actual reap.
        self._process.stdout.close()
        if not self._process.stdin.closed:
            self._process.stdin.close()
        self._process = None
        command = self._current.operation_id
        try:
            if code != 0 or self._target is not None or not self._ended or self._buffer:
                self.commands.worker_failed(self.session_id, self.window_id, command, reaped=True)
            else:
                try:
                    report = decode_application_report(self._staging)
                except Exception:
                    self.commands.worker_failed(
                        self.session_id, self.window_id, command, reaped=True
                    )
                else:
                    self.commands.finish(
                        self.session_id, self.window_id, command, report, reaped=True
                    )
        finally:
            self._staging.clear()
            self._buffer.clear()
            self._admissions.clear()
            self._history.clear()
            self._value = None
            self._input = b""

    def shutdown(self, timeout=2.5):
        if not self._closed:
            return super().shutdown(timeout)
        deadline = time.monotonic() + timeout
        while self.busy and time.monotonic() < deadline:
            self.tick()
            time.sleep(0.01)
        return not self.busy
