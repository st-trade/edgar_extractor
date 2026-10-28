"""Tests for Windows cursor-sdk bridge discovery workaround."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from unittest import mock

from scorecard_cursor_bridge_win32 import (
    _read_discovery_via_thread,
    patch_cursor_sdk_bridge_on_windows,
)


def _minimal_discovery_payload() -> dict:
    return {
        "schemaVersion": 1,
        "transport": "tcp",
        "protocol": "connect",
        "url": "http://127.0.0.1:59999",
        "authToken": "test-token",
    }


class TestBridgeDiscoveryThreadReader(unittest.TestCase):
    def test_reads_discovery_line_from_stderr_pipe(self) -> None:
        payload = json.dumps(_minimal_discovery_payload())
        script = (
            "import sys; "
            f"sys.stderr.write('cursor-sdk-bridge ready {payload}\\n'); "
            "sys.stderr.flush()"
        )
        proc = subprocess.Popen(
            [sys.executable, "-c", script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            discovery = _read_discovery_via_thread(proc, timeout=5.0)
            self.assertEqual(discovery.get("schemaVersion"), 1)
            self.assertEqual(discovery.get("authToken"), "test-token")
        finally:
            proc.wait(timeout=5)

    def test_patch_replaces_read_discovery_on_win32(self) -> None:
        import cursor_sdk._bridge as bridge_mod

        original = bridge_mod._read_discovery
        try:
            with mock.patch.object(sys, "platform", "win32"):
                # Reset module patch flag for test isolation
                import scorecard_cursor_bridge_win32 as mod

                mod._PATCHED = False
                patch_cursor_sdk_bridge_on_windows()
                self.assertIs(bridge_mod._read_discovery, _read_discovery_via_thread)
        finally:
            bridge_mod._read_discovery = original
            import scorecard_cursor_bridge_win32 as mod

            mod._PATCHED = False


if __name__ == "__main__":
    unittest.main()
