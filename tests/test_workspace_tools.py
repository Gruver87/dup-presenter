"""Unit tests for scripts/workspace_tools.py (sandboxed inspect, find, mkdir, refuse-delete)."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import workspace_tools  # noqa: E402


class TestWorkspaceTools(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.base = Path(self._td.name).resolve()
        (self.base / "notes.txt").write_text("hello world", encoding="utf-8")
        (self.base / ".env").write_text("SECRET=1234567890", encoding="utf-8")
        self._env = mock.patch.dict(os.environ, {"DUP_WORKSPACE_ROOTS": str(self.base)}, clear=False)
        self._env.start()

    def tearDown(self) -> None:
        self._env.stop()
        self._td.cleanup()

    def test_list_dir_hides_env_and_lists_regular_files(self) -> None:
        res = workspace_tools.list_dir(self.base)
        self.assertTrue(res["ok"])
        names = [e["name"] for e in res["entries"]]
        self.assertIn("notes.txt", names)
        self.assertNotIn(".env", names)

    def test_create_dir_and_find_files(self) -> None:
        mk = workspace_tools.create_dir(self.base / "new_scene" / "clips")
        self.assertTrue(mk["ok"])
        self.assertTrue(mk["created"])
        self.assertTrue((self.base / "new_scene" / "clips").is_dir())

        found = workspace_tools.find_files("*.txt", self.base)
        self.assertEqual(found["count"], 1)
        self.assertEqual(found["matches"][0]["name"], "notes.txt")

    def test_refuses_escape_outside_allowed_roots(self) -> None:
        with self.assertRaises(workspace_tools.WorkspaceGuardError):
            workspace_tools.list_dir("C:\\Windows")
        with self.assertRaises(workspace_tools.WorkspaceGuardError):
            workspace_tools.create_dir(self.base / ".." / "escape_dir")

    def test_refuses_reading_secret_files(self) -> None:
        with self.assertRaises(workspace_tools.WorkspaceGuardError):
            workspace_tools.read_text_file(self.base / ".env")

    def test_delete_refused_without_explicit_confirmation(self) -> None:
        target = self.base / "notes.txt"
        with self.assertRaises(workspace_tools.WorkspaceGuardError):
            workspace_tools.delete_path(target)
        with self.assertRaises(workspace_tools.WorkspaceGuardError):
            workspace_tools.delete_path(target, confirmed_by_user=True, confirm_phrase="yes")
        self.assertTrue(target.is_file())


if __name__ == "__main__":
    unittest.main()
