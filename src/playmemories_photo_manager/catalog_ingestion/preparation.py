"""Owner-thread controller for a disposable preparation worker (not a renderer API).

The host must call tick at least every 50 ms in its multiplexed loop, including
while input is idle. This slice is deliberately not wired into the synchronous bridge.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import signal
import subprocess
import sys
import threading
import time
from contextlib import suppress
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from uuid import UUID, uuid4

from ..scanner import PhysicalIdentity
from .worker_wire import MAX_FRAME_BYTES, MAX_RESULT_BYTES, decode_result, unique_object

_TERMINAL = {"completed", "failed", "cancelled"}
_REASONS = {
    "resource_limit",
    "permission_denied",
    "root_changed",
    "incomplete_coverage",
    "worker_crash",
    "protocol_failure",
    "startup_timeout",
    "execution_timeout",
    "read_failed",
    "verification_timeout",
}
_PHASES = ("snapshot", "scanning", "verifying", "planning")


class PreparationError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class PreparationInput:
    """Private output of a future validated root grant; never construct from UI params."""

    catalog_path: str
    root_path: str
    root_id: str
    catalog_identity: tuple[int, int]
    root_identity: tuple[int, int]
    mount_id: int


@dataclass(frozen=True, slots=True)
class PreparationStatus:
    session_id: str
    operation_id: str
    revision: int = 1
    state: str = "queued"
    phase: str | None = None
    observed_count: int = 0
    verified_count: int = 0
    excluded_count: int = 0
    total: None = None
    terminal_reason: str | None = None
    proposal_id: str | None = None
    version: int = 1


def _uuid(value):
    try:
        if not isinstance(value, str) or str(UUID(value)) != value:
            raise ValueError
    except (ValueError, AttributeError):
        raise PreparationError("invalid_request") from None


def _validate_input(value):
    if not isinstance(value, PreparationInput):
        raise PreparationError("invalid_request")
    _uuid(value.root_id)
    for raw in (value.catalog_path, value.root_path):
        if not isinstance(raw, str) or not 1 <= len(raw) <= 4096 or "\0" in raw:
            raise PreparationError("invalid_request")
        path = Path(raw)
        if not path.is_absolute() or ".." in path.parts or str(path) != raw:
            raise PreparationError("invalid_request")
    if Path(value.catalog_path).is_relative_to(value.root_path):
        raise PreparationError("unsafe_location")
    for identity in (value.catalog_identity, value.root_identity):
        if (
            not isinstance(identity, tuple)
            or len(identity) != 2
            or any(type(n) is not int or n < 0 for n in identity)
        ):
            raise PreparationError("invalid_request")
    if type(value.mount_id) is not int or value.mount_id < 0:
        raise PreparationError("invalid_request")


def _read_rss(pid):
    with open(f"/proc/{pid}/statm", encoding="ascii") as source:
        resident = int(source.read(256).split()[1])
    return resident * os.sysconf("SC_PAGE_SIZE")


def _bind_monitor(child_pid):
    """Bind the unreaped child across a procfs/PID namespace boundary, or refuse."""
    parent = int(os.readlink("/proc/self"))
    candidates = []
    # Namespace-local PIDs need not equal the IDs exposed by a procfs mount.
    with os.scandir("/proc") as entries:
        for entry in entries:
            if not entry.name.isdecimal():
                continue
            if len(candidates) == 4096:
                raise ValueError("process inventory exceeds budget")
            candidates.append(int(entry.name))
    for pid in candidates:
        try:
            with open(f"/proc/{pid}/status", encoding="ascii") as source:
                fields = dict(
                    line.split(":", 1) for line in source.read(65536).splitlines() if ":" in line
                )
            if int(fields["PPid"]) != parent:
                continue
            namespace_pids = fields.get("NSpid", str(pid)).split()
            if int(namespace_pids[-1]) == child_pid:
                _read_rss(pid)
                return pid
        except (FileNotFoundError, ProcessLookupError):
            continue
    raise ValueError("cannot identify spawned child")


class PreparationController:
    """Single slot and bounded volatile history; serialized by its owning host thread."""

    def __init__(self, session_id: str, window_id: str):
        _uuid(session_id)
        _uuid(window_id)
        if sys.platform != "linux":
            raise PreparationError("unavailable")
        try:
            _read_rss(int(os.readlink("/proc/self")))
        except (OSError, ValueError, IndexError):
            raise PreparationError("unavailable") from None
        self.session_id, self.window_id = session_id, window_id
        self._owner = threading.get_ident()
        self._closed = False
        self._process = None
        self._current = None
        self._history = {}
        self._admissions = {}
        self._published = None
        self._cursors = {}
        self._tokens = {}
        self._page_size = None
        self.peak_worker_rss = 0
        self.max_monitor_gap = 0.0

    def _require(self):
        if threading.get_ident() != self._owner:
            raise PreparationError("invalid_request")
        if self._closed:
            raise PreparationError("stale_session")

    def _scope(self, session_id, window_id):
        self._require()
        if session_id != self.session_id or window_id != self.window_id:
            raise PreparationError("stale_session")

    def _update(self, **changes):
        self._current = replace(self._current, revision=self._current.revision + 1, **changes)
        self._history[self._current.operation_id] = self._current

    @property
    def busy(self):
        return self._process is not None

    _worker_module = "playmemories_photo_manager.catalog_ingestion.preparation_worker"

    def _validate_value(self, value):
        _validate_input(value)

    def _operation_identifier(self, _value):
        return str(uuid4())

    def _request_bytes(self, value):
        return json.dumps(asdict(value), ensure_ascii=True, separators=(",", ":")).encode() + b"\n"

    def _child_arguments(self):
        return ()

    def _inherited_fds(self):
        return ()

    def start(self, value: PreparationInput, client_request_id: str):
        self._require()
        _uuid(client_request_id)
        self._validate_value(value)
        if client_request_id in self._admissions:
            previous, operation_id = self._admissions[client_request_id]
            if previous != value:
                raise PreparationError("invalid_request")
            return asdict(self._history[operation_id])
        if self.busy:
            raise PreparationError("busy")
        if len(self._admissions) == 32:
            raise PreparationError("resource_limit")
        operation_id = self._operation_identifier(value)
        request = self._request_bytes(value)
        if len(request) > MAX_FRAME_BYTES:
            raise PreparationError("resource_limit")
        try:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    self._worker_module,
                    operation_id,
                    str(os.getpid()),
                    *self._child_arguments(),
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                pass_fds=self._inherited_fds(),
                shell=False,
                cwd=Path(__file__).resolve().parents[2],
                env={
                    "PATH": os.defpath,
                    "LANG": "C.UTF-8",
                    "PYTHONPATH": str(Path(__file__).resolve().parents[2]),
                },
            )
        except OSError:
            raise PreparationError("unavailable") from None
        self._process = process
        self._input = request
        self._buffer = bytearray()
        self._staging = bytearray()
        self._size = None
        self._sequence = 0
        self._ended = self._ready = self._eof = False
        self._target = self._cause = None
        self._signal_stage = 0
        self._started = self._last_monitor = time.monotonic()
        self._cleanup_started = None
        self._value = value
        self._published = None
        self._cursors.clear()
        self._tokens.clear()
        self._page_size = None
        self._current = PreparationStatus(self.session_id, operation_id)
        self._history[operation_id] = self._current
        self._admissions[client_request_id] = (value, operation_id)
        self._monitor_pid = None
        try:
            os.set_blocking(process.stdout.fileno(), False)
            os.set_blocking(process.stdin.fileno(), False)
        except OSError:
            self._input = b""
            self._eof = True
            process.stdin.close()
            process.stdout.close()
            self._abort("protocol_failure")
            self._signal(signal.SIGKILL)
            return asdict(self._current)
        try:
            self._monitor_pid = _bind_monitor(process.pid)
        except (OSError, ValueError, IndexError, StopIteration):
            if process.poll() is None:
                self._abort("protocol_failure")
                self._signal(signal.SIGKILL)
        return asdict(self._current)

    def _abort(self, reason=None):
        if self._current.state in _TERMINAL or self._cleanup_started is not None:
            return
        self._target = "failed" if reason else "cancelled"
        self._cause = reason
        self._cleanup_started = time.monotonic()
        self._published = None
        self._staging.clear()
        self._update(state="cancelling", phase="cleanup")
        if self._ready:
            self._signal(signal.SIGUSR1)

    def _signal(self, sig):
        with suppress(ProcessLookupError):
            self._process.send_signal(sig)

    def cancel(self, session_id, window_id, operation_id):
        self._scope(session_id, window_id)
        if self._current is None or operation_id != self._current.operation_id:
            raise PreparationError("stale_session")
        if self._current.state in _TERMINAL:
            effect = "too_late"
        elif self._cleanup_started is not None:
            effect = "already_cancelling"
        else:
            code = self._process.poll()
            self._abort("worker_crash" if code not in (None, 0) else None)
            effect = "accepted"
        return {"job": asdict(self._current), "cancel_effect": effect}

    def status(self, session_id, window_id, operation_id):
        self._scope(session_id, window_id)
        self.tick()
        if operation_id not in self._history:
            raise PreparationError("stale_session")
        return asdict(self._history[operation_id])

    def tick(self):
        """Nonblocking host-loop step, including external deadline/RSS checks."""
        if threading.get_ident() != self._owner:
            raise PreparationError("invalid_request")
        if not self.busy:
            return
        now = time.monotonic()
        code = self._process.poll()  # waitpid(WNOHANG), including reap when exited.
        self.max_monitor_gap = max(self.max_monitor_gap, now - self._last_monitor)
        if code is None and self._monitor_pid is not None and now - self._last_monitor >= 0.05:
            self._last_monitor = now
            try:
                rss = _read_rss(self._monitor_pid)
                self.peak_worker_rss = max(self.peak_worker_rss, rss)
                if rss > 256 * 1024 * 1024:
                    self._abort("resource_limit")
            except (OSError, ValueError, IndexError):
                if self._process.poll() is None:
                    self._abort("protocol_failure")
        if code is None and self._cleanup_started is None:
            if not self._ready and now - self._started >= 5:
                self._abort("startup_timeout")
            elif now - self._started >= 30:
                self._abort("execution_timeout")
        try:
            if self._input and code is None and self._cleanup_started is None:
                try:
                    written = os.write(self._process.stdin.fileno(), self._input)
                    self._input = self._input[written:]
                    if not self._input:
                        self._process.stdin.close()
                except BlockingIOError:
                    pass
            chunk = b""
            if not self._eof:
                try:
                    chunk = os.read(self._process.stdout.fileno(), MAX_FRAME_BYTES)
                    self._eof = not chunk
                except BlockingIOError:
                    pass
            self._buffer.extend(chunk)
            frames = 0
            while b"\n" in self._buffer:
                end = self._buffer.index(10) + 1
                frames += 1
                if end > MAX_FRAME_BYTES or frames > 16:
                    raise ValueError
                line = self._buffer[:end]
                del self._buffer[:end]
                self._frame(json.loads(line, object_pairs_hook=unique_object))
            if len(self._buffer) > MAX_FRAME_BYTES:
                raise ValueError
        except (OSError, ValueError, KeyError, TypeError, RecursionError):
            self._abort("protocol_failure")
            self._buffer.clear()
        if self._cleanup_started is not None and code is None:
            elapsed = now - self._cleanup_started
            if elapsed >= 1 and self._signal_stage < 2:
                self._signal(signal.SIGKILL)
                self._signal_stage = 2
            elif elapsed >= 0.5 and self._signal_stage < 1:
                self._signal(signal.SIGTERM)
                self._signal_stage = 1
        code = self._process.poll()
        if code is not None and self._eof:
            self._finish(code)

    def _frame(self, frame):
        if not isinstance(frame, dict) or frame.get("operation_id") != self._current.operation_id:
            raise ValueError
        kind = frame.get("kind")
        if self._cleanup_started is not None:
            if kind == "ready" and not self._ready:
                self._ready = True
                self._signal(signal.SIGUSR1)
            return  # Cancellation irrevocably discards even a completed result.
        keys = {"operation_id", "kind"}
        if kind == "ready" and not self._ready and set(frame) == keys:
            self._ready = True
            self._update(state="running", phase="snapshot")
        elif kind == "progress" and self._ready and self._size is None:
            if set(frame) != keys | {"phase", "observed_count", "verified_count", "excluded_count"}:
                raise ValueError
            phase = frame["phase"]
            if phase not in _PHASES or _PHASES.index(phase) < _PHASES.index(self._current.phase):
                raise ValueError
            counts = {
                key: frame[key] for key in ("observed_count", "verified_count", "excluded_count")
            }
            if any(
                type(n) is not int or not getattr(self._current, key) <= n <= 2000
                for key, n in counts.items()
            ):
                raise ValueError
            if (
                counts["verified_count"] > counts["observed_count"]
                or counts["excluded_count"] > counts["verified_count"]
            ):
                raise ValueError
            self._update(phase=phase, **counts)
        elif (
            kind == "result_begin"
            and self._ready
            and self._size is None
            and set(frame) == keys | {"size"}
        ):
            if type(frame["size"]) is not int or not 0 < frame["size"] <= MAX_RESULT_BYTES:
                raise ValueError
            self._size = frame["size"]
        elif (
            kind == "chunk"
            and self._size is not None
            and not self._ended
            and set(frame) == keys | {"sequence", "data"}
        ):
            if type(frame["sequence"]) is not int or frame["sequence"] != self._sequence:
                raise ValueError
            data = base64.b64decode(frame["data"], validate=True)
            if not data or len(data) > 32768 or len(self._staging) + len(data) > self._size:
                raise ValueError
            self._staging.extend(data)
            self._sequence += 1
        elif (
            kind == "result_end"
            and self._size is not None
            and not self._ended
            and set(frame) == keys | {"digest"}
        ):
            if (
                len(self._staging) != self._size
                or hashlib.sha256(self._staging).hexdigest() != frame["digest"]
            ):
                raise ValueError
            self._ended = True
        elif (
            kind == "failure"
            and self._ready
            and set(frame) == keys | {"reason"}
            and frame["reason"] in _REASONS
        ):
            self._abort(frame["reason"])
        else:
            raise ValueError

    def _finish(self, code):
        # Only reached after poll has reaped the process AND its output reached EOF.
        self._process.stdout.close()
        if not self._process.stdin.closed:
            self._process.stdin.close()
        self._process = None
        if self._target is not None:
            self._update(state=self._target, phase=None, terminal_reason=self._cause)
        elif code != 0 or not self._ended or self._buffer:
            self._update(
                state="failed",
                phase=None,
                terminal_reason="worker_crash" if code else "protocol_failure",
            )
        else:
            try:
                result = decode_result(self._staging)
                if result.original.plan.library_root_id != self._value.root_id:
                    raise ValueError
                if result.original.scan_result.root.physical_identity != PhysicalIdentity(
                    *self._value.root_identity
                ):
                    raise ValueError
                if result.original.scan_result.root.absolute_path != self._value.root_path:
                    raise ValueError
                if (
                    self._current.observed_count != len(result.original.scan_result.entries)
                    or self._current.verified_count != len(result.eligibilities)
                    or self._current.excluded_count != len(result.exclusions)
                ):
                    raise ValueError
                self._validate_public_pages(result)
                self._published = result
                self._update(state="completed", phase=None, proposal_id=str(uuid4()))
            except PreparationError as error:
                self._update(state="failed", phase=None, terminal_reason=error.code)
            except Exception:
                self._update(state="failed", phase=None, terminal_reason="protocol_failure")
        self._staging.clear()
        self._buffer.clear()

    @staticmethod
    def _public(item):
        return {
            "candidate_id": item.candidate_id,
            "relative_path": item.candidate.relative_path,
            "state": item.state,
            "reason": item.reason,
            "detected_format": item.detected_format,
            "profile": item.profile,
            "decoding": item.decoding,
        }

    def _validate_public_pages(self, result):
        eligible = set(result.eligible_candidates)
        sizes = [
            len(
                json.dumps(
                    self._public(item) | {"selectable": item.candidate in eligible},
                    ensure_ascii=True,
                ).encode()
            )
            + 1
            for item in result.eligibilities
        ]
        if any(sum(sizes[start : start + 50]) + 1024 > 256 * 1024 for start in range(len(sizes))):
            raise PreparationError("resource_limit")

    def application_source(self, session_id, window_id, proposal_id):
        """Private owner-thread handoff, never a renderer DTO or a mutable path request."""
        self._scope(session_id, window_id)
        _uuid(proposal_id)
        if (
            self.busy
            or self._published is None
            or self._current is None
            or (self._current.state != "completed" or self._current.proposal_id != proposal_id)
        ):
            raise PreparationError("stale_session")
        return self._published, self._value

    def page(self, session_id, window_id, proposal_id, cursor=None, page_size=50):
        self._scope(session_id, window_id)
        if self._published is None or proposal_id != self._current.proposal_id:
            raise PreparationError("stale_session")
        if type(page_size) is not int or not 1 <= page_size <= 50:
            raise PreparationError("invalid_request")
        if self._page_size is not None and self._page_size != page_size:
            raise PreparationError("invalid_request")
        self._page_size = page_size
        if cursor is not None and (not isinstance(cursor, str) or cursor not in self._cursors):
            raise PreparationError("invalid_request")
        position = self._cursors[cursor] if cursor is not None else 0
        items = self._published.eligibilities[position : position + page_size]
        eligible = set(self._published.eligible_candidates)
        next_position = position + len(items)
        token = None
        if next_position < len(self._published.eligibilities):
            if next_position not in self._tokens:
                token = secrets.token_hex(32)
                self._tokens[next_position] = token
                self._cursors[token] = next_position
            token = self._tokens[next_position]
        return {
            "proposal_id": proposal_id,
            "items": [
                self._public(item) | {"selectable": item.candidate in eligible} for item in items
            ],
            "next_cursor": token,
        }

    def shutdown(self, timeout=2.5):
        """Revoke immediately; bounded drain. False means cleanup still owns the slot."""
        self._require()
        if self.busy:
            self.cancel(self.session_id, self.window_id, self._current.operation_id)
        self._closed = True
        self._published = None
        deadline = time.monotonic() + timeout
        while self.busy and time.monotonic() < deadline:
            self.tick()
            time.sleep(0.01)
        return not self.busy
