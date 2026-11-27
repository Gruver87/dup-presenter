"""Item 7: release publish refuses silent overwrites, writes a manifest, and verifies the release afterwards."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import github_release_uploader as gru  # noqa: E402


class FakeGh:
    """Scripted `gh` replacement. `remote` is the release asset list; mutated by create/upload."""

    def __init__(self, exists: bool, remote: list[dict] | None = None) -> None:
        self.exists = exists
        self.remote = list(remote or [])
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str]):
        self.calls.append(list(args))
        res = mock.Mock(returncode=0, stdout="", stderr="")
        if args[:2] == ["auth", "status"]:
            return res
        if args[:2] == ["release", "view"]:
            if not self.exists:
                res.returncode = 1
                return res
            res.stdout = json.dumps({"assets": self.remote})
            return res
        if args[:2] == ["release", "create"]:
            self.exists = True
            self.remote = self._from_args(args)
            return res
        if args[:2] == ["release", "upload"]:
            self.remote = [a for a in self.remote if a["name"] not in {x["name"] for x in self._from_args(args)}] + self._from_args(args)
            return res
        res.returncode = 2
        return res

    @staticmethod
    def _from_args(args: list[str]) -> list[dict]:
        out = []
        for a in args:
            p = Path(a)
            if p.suffix in {".mp4", ".png", ".json", ".srt", ".vtt", ".txt"} and p.is_file():
                out.append({"name": p.name, "size": p.stat().st_size})
        return out


class ReleasePublishTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="rel_"))
        self.mp4 = self.tmp / "clip.mp4"
        self.mp4.write_bytes(b"x" * 4096)
        self.thumb = self.tmp / "clip_thumb.png"
        self.thumb.write_bytes(b"p" * 128)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, fake: FakeGh, **kw):
        with mock.patch.object(gru, "_run_gh", side_effect=fake):
            return gru.upload_to_release(self.mp4, "Gruver87/dup-presenter", "media-clip", **kw)

    def test_create_path_writes_manifest_and_verifies(self) -> None:
        fake = FakeGh(exists=False)
        res = self._run(fake)
        self.assertTrue(res["ok"], res)
        self.assertTrue(res["verified"])
        self.assertEqual(res["action"], "created")
        manifest = json.loads((self.tmp / "clip_release_manifest.json").read_text(encoding="utf-8"))
        names = {a["name"] for a in manifest["assets"]}
        self.assertIn("clip.mp4", names)
        mp4_entry = next(a for a in manifest["assets"] if a["name"] == "clip.mp4")
        self.assertEqual(mp4_entry["bytes"], 4096)
        self.assertEqual(len(mp4_entry["sha256"]), 64)
        self.assertIn("--latest=false", next(c for c in fake.calls if c[:2] == ["release", "create"]))

    def test_same_named_asset_is_refused_without_replace(self) -> None:
        fake = FakeGh(exists=True, remote=[{"name": "clip.mp4", "size": 4096}])
        res = self._run(fake)
        self.assertFalse(res["ok"])
        self.assertIn("clip.mp4", res["conflicts"])
        self.assertFalse(any(c[:2] == ["release", "upload"] for c in fake.calls), "no upload may happen")

    def test_replace_flag_uses_clobber_and_verifies(self) -> None:
        fake = FakeGh(exists=True, remote=[{"name": "clip.mp4", "size": 1}])
        res = self._run(fake, replace=True)
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["action"], "replaced")
        upload = next(c for c in fake.calls if c[:2] == ["release", "upload"])
        self.assertIn("--clobber", upload)

    def test_verification_catches_size_mismatch(self) -> None:
        class Corrupting(FakeGh):
            def __call__(self, args):
                res = super().__call__(args)
                if args[:2] == ["release", "create"]:
                    self.remote = [{**a, "size": a["size"] + 1} for a in self.remote]
                return res

        res = self._run(Corrupting(exists=False))
        self.assertFalse(res["ok"])
        self.assertIn("verification", res["error"])
        self.assertEqual(res["verification"]["size_mismatch"][0]["name"], "clip.mp4")

    def test_plan_conflicts_and_verify_are_pure(self) -> None:
        self.assertEqual(gru.plan_asset_conflicts([{"name": "clip.mp4"}], [self.mp4], replace=False), ["clip.mp4"])
        self.assertEqual(gru.plan_asset_conflicts([{"name": "clip.mp4"}], [self.mp4], replace=True), [])
        ok = gru.verify_release_assets([{"name": "clip.mp4", "size": 4096}], [self.mp4])
        self.assertTrue(ok["ok"])
        missing = gru.verify_release_assets([], [self.mp4])
        self.assertEqual(missing["missing"], ["clip.mp4"])


if __name__ == "__main__":
    unittest.main()
