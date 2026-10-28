"""Work around cursor-sdk sync ``Bridge.launch`` on Windows (WinError 10038).

``cursor_sdk._bridge._read_discovery`` uses ``selectors`` on the bridge
subprocess stderr pipe; on Windows ``select`` only accepts sockets. Replace
that function with a thread-based stderr reader before the first Agent call.

See: https://forum.cursor.com/t/python-sdk-client-launch-bridge-fails-on-windows-winerror-10038-and-a-failed-launch-leaves-node-exe-running/174900
"""

from __future__ import annotations

import queue
import subprocess
import sys
import threading
import time
from collections.abc import Mapping
from typing import Any

_PATCHED = False


def patch_cursor_sdk_bridge_on_windows() -> None:
    """Idempotent; no-op except on ``win32``."""
    global _PATCHED
    if _PATCHED or sys.platform != "win32":
        return
    import cursor_sdk._bridge as bridge_mod

    bridge_mod._read_discovery = _read_discovery_via_thread  # type: ignore[assignment]
    _PATCHED = True


def _read_discovery_via_thread(
    process: subprocess.Popen[str], timeout: float
) -> Mapping[str, Any]:
    from cursor_sdk._bridge import parse_discovery_line
    from cursor_sdk.errors import CursorSDKError

    if process.stderr is None:
        raise CursorSDKError("Bridge process stderr is unavailable")

    line_queue: queue.Queue[str | None] = queue.Queue()

    def reader() -> None:
        try:
            assert process.stderr is not None
            for line in process.stderr:
                line_queue.put(line)
        finally:
            line_queue.put(None)

    threading.Thread(target=reader, daemon=True).start()
    deadline = time.monotonic() + timeout
    stderr_lines: list[str] = []

    def check_queued_lines() -> Mapping[str, Any] | None:
        while True:
            try:
                line = line_queue.get_nowait()
            except queue.Empty:
                return None
            if line is None:
                return None
            stderr_lines.append(line)
            discovery = parse_discovery_line(line)
            if discovery is not None:
                return discovery
        return None

    while time.monotonic() < deadline:
        remaining = min(0.1, max(0.0, deadline - time.monotonic()))
        try:
            line = line_queue.get(timeout=remaining)
        except queue.Empty:
            discovery = check_queued_lines()
            if discovery is not None:
                return discovery
            exit_code = process.poll()
            if exit_code is not None:
                discovery = check_queued_lines()
                if discovery is not None:
                    return discovery
                raise CursorSDKError(
                    f"Bridge exited before discovery with status {exit_code}: "
                    + "".join(stderr_lines)
                )
            continue

        if line is None:
            exit_code = process.poll()
            if exit_code is not None:
                discovery = check_queued_lines()
                if discovery is not None:
                    return discovery
                raise CursorSDKError(
                    f"Bridge exited before discovery with status {exit_code}: "
                    + "".join(stderr_lines)
                )
            continue

        stderr_lines.append(line)
        discovery = parse_discovery_line(line)
        if discovery is not None:
            return discovery

    raise CursorSDKError("Timed out waiting for bridge discovery")
