"""Runs the publish-gate smoke (real ffmpeg, synthetic MP4) as part of the suite."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import smoke_publish_gate  # noqa: E402


class PublishGateSmokeTests(unittest.TestCase):
    def test_smoke_chain_passes_end_to_end(self) -> None:
        self.assertEqual(smoke_publish_gate.run(), 0)


if __name__ == "__main__":
    unittest.main()
