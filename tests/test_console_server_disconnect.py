"""Client disconnects (browser seek / tab close) must not print tracebacks in the console server."""

from __future__ import annotations

import contextlib
import io
import sys
import unittest
from pathlib import Path
from http.server import BaseHTTPRequestHandler

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import console_server  # noqa: E402


class _NoopHandler(BaseHTTPRequestHandler):
    def handle(self) -> None:  # pragma: no cover - never served in this test
        return


class TestClientDisconnect(unittest.TestCase):
    def setUp(self) -> None:
        self.server = console_server._DupConsoleServer(("127.0.0.1", 0), _NoopHandler)

    def tearDown(self) -> None:
        self.server.server_close()

    def _run_handle_error(self, exc: BaseException) -> str:
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            try:
                raise exc
            except BaseException:
                self.server.handle_error(None, ("127.0.0.1", 59696))
        return buf.getvalue()

    def test_connection_reset_is_silent(self) -> None:
        out = self._run_handle_error(ConnectionResetError(10054, "Удаленный хост разорвал подключение"))
        self.assertEqual(out, "")

    def test_broken_pipe_is_silent(self) -> None:
        self.assertEqual(self._run_handle_error(BrokenPipeError()), "")

    def test_real_server_errors_are_still_reported(self) -> None:
        out = self._run_handle_error(ValueError("real bug"))
        self.assertIn("Traceback", out)
        self.assertIn("real bug", out)


if __name__ == "__main__":
    unittest.main()
