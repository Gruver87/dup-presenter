"""Windows Credential Manager store: name validation, real round-trip (test-only name), loader priority."""

from __future__ import annotations

import os
import secrets
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import credstore  # noqa: E402
import stock_media  # noqa: E402


class NameValidationTests(unittest.TestCase):
    def test_rejects_bad_names_before_any_system_call(self) -> None:
        for bad in ("", "x", "lower_case", "1ABC", "A B", "A/B", "A" * 65):
            with self.assertRaises(credstore.CredStoreError):
                credstore.get_secret(bad)

    def test_refuses_empty_and_oversized_values(self) -> None:
        with self.assertRaises(credstore.CredStoreError):
            credstore.set_secret("DUP_TEST_NAME", "")
        with self.assertRaises(credstore.CredStoreError):
            credstore.set_secret("DUP_TEST_NAME", "x" * (credstore.MAX_BLOB_BYTES + 1))


@unittest.skipUnless(credstore.available(), "Windows Credential Manager only")
class RealStoreRoundTripTests(unittest.TestCase):
    def setUp(self) -> None:
        self.name = f"DUP_SELFTEST_{secrets.token_hex(6).upper()}"

    def tearDown(self) -> None:
        credstore.delete_secret(self.name)

    def test_set_get_list_delete(self) -> None:
        value = "тест-" + secrets.token_hex(16)
        self.assertIsNone(credstore.get_secret(self.name))
        credstore.set_secret(self.name, value)
        self.assertEqual(credstore.get_secret(self.name), value)
        self.assertIn(self.name, credstore.list_names())
        self.assertTrue(credstore.delete_secret(self.name))
        self.assertIsNone(credstore.get_secret(self.name))
        self.assertFalse(credstore.delete_secret(self.name))


class MediaKeyPriorityTests(unittest.TestCase):
    def test_store_beats_file_and_env_beats_store(self) -> None:
        stored = {"PEXELS_API_KEY": "from_store_pexels", "PIXABAY_API_KEY": "from_store_pixabay"}
        with mock.patch.object(stock_media, "credstore_available", return_value=True), \
                mock.patch.object(stock_media, "get_secret", side_effect=stored.get), \
                mock.patch.object(stock_media, "SECRETS_ENV", ROOT / "does-not-exist.env"), \
                mock.patch.dict(os.environ, {"PIXABAY_API_KEY": "from_env_pixabay"}, clear=False):
            os.environ.pop("PEXELS_API_KEY", None)
            keys = stock_media.load_media_keys()
        self.assertEqual(keys["PEXELS_API_KEY"], "from_store_pexels")
        self.assertEqual(keys["PIXABAY_API_KEY"], "from_env_pixabay")


if __name__ == "__main__":
    unittest.main()
