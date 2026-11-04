"""Linux pipe pump: bounded frames, one owner/writer, no blocking stdio in the host loop."""

import os
import selectors
import time
from collections import deque
from contextlib import suppress

MAX_INPUT = 64 * 1024
MAX_OUTPUT = 256 * 1024


class TransportFailure(RuntimeError):
    pass


class PipePump:
    def __init__(self, source, sink):
        self.source, self.sink = source.fileno(), sink.fileno()
        self.selector = selectors.DefaultSelector()
        self._blocking = (os.get_blocking(self.source), os.get_blocking(self.sink))
        try:
            os.set_blocking(self.source, False)
            os.set_blocking(self.sink, False)
            self.selector.register(self.source, selectors.EVENT_READ)
        except BaseException:
            self.close()
            raise
        self.buffer = bytearray()
        self.output = deque()
        self.frames = deque()
        self.dropping = False
        self.eof = False

    def write(self, line):
        payload = line.encode("utf-8")
        if len(payload) > MAX_OUTPUT or len(self.output) == 16:
            raise TransportFailure("protocol_failure")
        self.output.append(memoryview(payload))

    def flush(self):
        if not self.output:
            return
        try:
            written = os.write(self.sink, self.output[0][:65536])
        except BlockingIOError:
            return
        except OSError:
            raise TransportFailure("disconnected") from None
        pending = self.output.popleft()[written:]
        if pending:
            self.output.appendleft(pending)

    def lines(self, tick):
        while True:
            tick()
            self.flush()
            if self.frames:
                yield self.frames.popleft()
                continue
            if self.eof:
                return
            if not self.selector.select(0.01):
                continue
            try:
                chunk = os.read(self.source, MAX_INPUT)
            except BlockingIOError:
                continue
            if not chunk:
                self.eof = True
                if self.dropping:
                    self._frame(None)
                elif self.buffer:
                    self._frame(bytes(self.buffer))
                    self.buffer.clear()
                continue
            for part in chunk.splitlines(keepends=True):
                # Only LF terminates JSON-lines; other whitespace stays in the bounded buffer.
                self.buffer.extend(part)
                if len(self.buffer) > MAX_INPUT:
                    self.buffer.clear()
                    self.dropping = True
                if part.endswith(b"\n"):
                    if self.dropping:
                        self._frame(None)
                    else:
                        self._frame(bytes(self.buffer))
                    self.buffer.clear()
                    self.dropping = False

    def _frame(self, payload):
        if len(self.frames) == 16:
            raise TransportFailure("protocol_failure")
        if payload is None:
            self.frames.append("x" * (MAX_INPUT + 1) + "\n")
        else:
            try:
                self.frames.append(payload.decode("utf-8", errors="strict"))
            except UnicodeError:
                self.frames.append("!invalid_utf8\n")

    def drain(self, timeout=0.5):
        deadline = time.monotonic() + timeout
        while self.output and time.monotonic() < deadline:
            self.flush()
            time.sleep(0.001)
        return not self.output

    def close(self):
        self.selector.close()
        for fd, blocking in zip((self.source, self.sink), self._blocking, strict=True):
            with suppress(OSError):
                os.set_blocking(fd, blocking)
