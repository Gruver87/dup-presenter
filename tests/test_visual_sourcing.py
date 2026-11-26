"""Offline fail-closed tests for the Stage 3 visual sourcing layer (no network, no keys)."""

from __future__ import annotations

import copy
import shutil
import sys
import unittest
import uuid
from pathlib import Path
from unittest import mock

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import archive_sources as arc  # noqa: E402
import visual_sourcing as vs  # noqa: E402
from build_deck import validate_deck  # noqa: E402

PNG_1080P = (1920, 1080)


def _make_png(path: Path, size: tuple[int, int]) -> None:
    """Write a real PNG. Noise, not a flat fill, so the file size is realistic (flat fills compress to ~6 KB)."""
    from PIL import Image

    Image.effect_noise(size, 64).convert("RGB").save(path, format="PNG")


def _cand(**over) -> dict:
    base = {
        "source": "wikimedia",
        "source_id": "1",
        "kind": "image",
        "title": "Orion Nebula Hubble mosaic",
        "description": "",
        "keywords": [],
        "creator": "Hubble",
        "license": "cc0",
        "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
        "attribution_required": False,
        "page_url": "https://commons.wikimedia.org/wiki/File:x.jpg",
        "asset_url": "https://upload.wikimedia.org/x/y/orion.jpg",
        "width": 4000,
        "height": 2250,
        "duration_sec": None,
    }
    base.update(over)
    return base


# --------------------------------------------------------------------------- licences


class LicenceTests(unittest.TestCase):
    def test_allowed_urls(self) -> None:
        self.assertEqual(arc.normalize_license(url="https://creativecommons.org/publicdomain/zero/1.0/"), "cc0")
        self.assertEqual(arc.normalize_license(url="http://creativecommons.org/publicdomain/mark/1.0/"), "pdm")
        self.assertEqual(arc.normalize_license(url="https://creativecommons.org/licenses/by/4.0"), "by")
        self.assertEqual(arc.normalize_license(url="https://creativecommons.org/licenses/by-sa/2.0/"), "by-sa")

    def test_nc_nd_and_unknown_urls_are_rejected(self) -> None:
        for url in (
            "https://creativecommons.org/licenses/by-nc/4.0/",
            "https://creativecommons.org/licenses/by-nc-sa/4.0/",
            "https://creativecommons.org/licenses/by-nd/4.0/",
            "https://creativecommons.org/licenses/by-nc-nd/4.0/",
            "https://example.com/my-own-licence",
        ):
            self.assertIsNone(arc.normalize_license(url=url), url)

    def test_url_is_authoritative_over_name(self) -> None:
        self.assertIsNone(arc.normalize_license(url="https://creativecommons.org/licenses/by-nc/4.0/", name="CC BY 4.0"))

    def test_names_and_missing_licence(self) -> None:
        self.assertEqual(arc.normalize_license(name="CC BY-SA 4.0"), "by-sa")
        self.assertEqual(arc.normalize_license(name="CC BY 2.0"), "by")
        self.assertEqual(arc.normalize_license(name="Public domain"), "pdm")
        self.assertEqual(arc.normalize_license(name="CC0"), "cc0")
        self.assertIsNone(arc.normalize_license(name="CC BY-NC 4.0"))
        self.assertIsNone(arc.normalize_license(name=""))
        self.assertIsNone(arc.normalize_license(url="", name=""))


# --------------------------------------------------------------------------- hosts / transport


class HostAndTransportTests(unittest.TestCase):
    def test_asset_hosts(self) -> None:
        self.assertTrue(arc.asset_host_allowed("nasa", "https://images-assets.nasa.gov/video/x/x~large.mp4"))
        self.assertFalse(arc.asset_host_allowed("nasa", "https://evil.example.com/x.mp4"))
        self.assertTrue(arc.asset_host_allowed("wikimedia", "https://upload.wikimedia.org/a/b.jpg"))
        self.assertFalse(arc.asset_host_allowed("wikimedia", "https://upload.wikimedia.org.evil.com/a.jpg"))
        self.assertTrue(arc.asset_host_allowed("archive_org", "https://ia800.us.archive.org/1/items/x/x.mp4"))
        self.assertFalse(arc.asset_host_allowed("archive_org", "https://archive.org.evil.com/x.mp4"))
        self.assertFalse(arc.asset_host_allowed("wikimedia", "http://upload.wikimedia.org/a.jpg"))
        self.assertTrue(arc.asset_host_allowed("openverse", "https://live.staticflickr.com/x.jpg"))

    def test_http_json_refuses_plain_http(self) -> None:
        with self.assertRaisesRegex(arc.ArchiveSourceError, "non-https"):
            arc.http_json("http://images-api.nasa.gov/search")

    def test_http_error_is_raised_not_swallowed(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(403, text="robot policy")

        real = httpx.Client
        with mock.patch.object(httpx, "Client", lambda *a, **k: real(*a, transport=httpx.MockTransport(handler), **k)):
            with self.assertRaisesRegex(arc.ArchiveSourceError, "HTTP 403"):
                arc.http_json("https://commons.wikimedia.org/w/api.php", {"q": "x"})


# --------------------------------------------------------------------------- provider parsing


class ProviderParsingTests(unittest.TestCase):
    def test_nasa_search_and_asset_preference(self) -> None:
        payload = {
            "collection": {
                "items": [
                    {"data": [{"nasa_id": "PIA00001", "title": "Crab Nebula", "keywords": ["nebula"], "center": "JPL"}]}
                ]
            }
        }
        with mock.patch.object(arc, "http_json", return_value=payload):
            cands = arc.search_nasa("crab nebula", "image", 5)
        self.assertEqual(cands[0]["license"], "nasa-media")
        self.assertIsNone(cands[0]["asset_url"])
        manifest = {
            "collection": {
                "items": [
                    {"href": "https://images-assets.nasa.gov/image/PIA00001/PIA00001~orig.jpg"},
                    {"href": "https://images-assets.nasa.gov/image/PIA00001/PIA00001~large.jpg"},
                    {"href": "https://images-assets.nasa.gov/image/PIA00001/PIA00001~thumb.jpg"},
                ]
            }
        }
        with mock.patch.object(arc, "http_json", return_value=manifest):
            resolved = arc.resolve_asset(cands[0])
        self.assertTrue(resolved["asset_url"].endswith("~large.jpg"))

    def test_wikimedia_licence_and_nc_rejection(self) -> None:
        payload = {
            "query": {
                "pages": [
                    {
                        "pageid": 10,
                        "title": "File:Nebula ok.jpg",
                        "imageinfo": [
                            {
                                "url": "https://upload.wikimedia.org/a/ok.jpg",
                                "descriptionurl": "https://commons.wikimedia.org/wiki/File:Nebula_ok.jpg",
                                "mime": "image/jpeg",
                                "width": 3000,
                                "height": 2000,
                                "extmetadata": {
                                    "LicenseShortName": {"value": "CC BY-SA 4.0"},
                                    "LicenseUrl": {"value": "https://creativecommons.org/licenses/by-sa/4.0"},
                                    "Artist": {"value": "<a href='x'>Jane Doe</a>"},
                                    "ImageDescription": {"value": "A nebula"},
                                },
                            }
                        ],
                    },
                    {
                        "pageid": 11,
                        "title": "File:Nebula nc.jpg",
                        "imageinfo": [
                            {
                                "url": "https://upload.wikimedia.org/a/nc.jpg",
                                "descriptionurl": "https://commons.wikimedia.org/wiki/File:Nebula_nc.jpg",
                                "mime": "image/jpeg",
                                "width": 3000,
                                "height": 2000,
                                "extmetadata": {
                                    "LicenseUrl": {"value": "https://creativecommons.org/licenses/by-nc/4.0"},
                                    "Artist": {"value": "Someone"},
                                },
                            }
                        ],
                    },
                ]
            }
        }
        with mock.patch.object(arc, "http_json", return_value=payload):
            cands = arc.search_wikimedia("nebula", "image", 5)
        by_id = {c["source_id"]: c for c in cands}
        self.assertEqual(by_id["10"]["license"], "by-sa")
        self.assertEqual(by_id["10"]["creator"], "Jane Doe")
        self.assertTrue(by_id["10"]["attribution_required"])
        self.assertIsNone(by_id["11"]["license"])
        ok, reason, _ = vs.filter_candidate("nebula", by_id["11"], "image")
        self.assertFalse(ok)
        self.assertEqual(reason, "licence_not_allowed")

    def test_archive_search_excludes_nc_nd_server_side(self) -> None:
        captured: dict = {}

        def fake(url, params=None):
            captured.update(params or {})
            return {"response": {"docs": []}}

        with mock.patch.object(arc, "http_json", side_effect=fake):
            arc.search_archive_org("nebula", "video", 5)
        self.assertIn("NOT licenseurl:(*-nc*)", captured["q"])
        self.assertIn("NOT licenseurl:(*-nd*)", captured["q"])
        self.assertIn("mediatype:movies", captured["q"])

    def test_archive_resolve_rechecks_licence_from_metadata(self) -> None:
        meta = {
            "metadata": {"licenseurl": "https://creativecommons.org/licenses/by-nc/3.0/"},
            "files": [{"name": "a.mp4", "format": "h.264", "width": 1920, "height": 1080}],
        }
        cand = _cand(source="archive_org", source_id="abc", kind="video", asset_url=None, license="by")
        with mock.patch.object(arc, "http_json", return_value=meta):
            with self.assertRaisesRegex(arc.ArchiveSourceError, "licence not allowed"):
                arc.resolve_asset(cand)

    def test_archive_resolve_picks_largest_h264_mp4(self) -> None:
        meta = {
            "metadata": {"licenseurl": "https://creativecommons.org/publicdomain/zero/1.0/"},
            "files": [
                {"name": "small.mp4", "format": "h.264", "width": 640, "height": 360},
                {"name": "big.mp4", "format": "h.264", "width": 1920, "height": 1080},
                {"name": "x.ogv", "format": "Ogg Video", "width": 4000, "height": 3000},
            ],
        }
        cand = _cand(source="archive_org", source_id="abc", kind="video", asset_url=None, license="cc0")
        with mock.patch.object(arc, "http_json", return_value=meta):
            resolved = arc.resolve_asset(cand)
        self.assertTrue(resolved["asset_url"].endswith("/big.mp4"))
        self.assertEqual((resolved["width"], resolved["height"]), (1920, 1080))

    def test_openverse_has_no_video_index(self) -> None:
        self.assertEqual(arc.search_openverse("nebula", "video", 5), [])


# --------------------------------------------------------------------------- relevance and filters


class RelevanceAndFilterTests(unittest.TestCase):
    def test_strong_match_beats_description_only_match(self) -> None:
        strong = _cand(title="Crab Nebula close view")
        weak = _cand(title="Unrelated photo", description="a long text that mentions nebula once")
        _, strong_ok = vs.relevance("crab nebula", strong)
        _, weak_ok = vs.relevance("nebula", weak)
        self.assertTrue(strong_ok)
        self.assertFalse(vs.relevance("crab nebula", weak)[1])
        self.assertTrue(strong_ok)
        self.assertFalse(weak_ok)

    def test_plural_folding(self) -> None:
        self.assertTrue(vs.relevance("galaxies", _cand(title="Spiral galaxy M51"))[1])

    def test_two_of_three_tokens_needed_for_long_queries(self) -> None:
        self.assertTrue(vs.relevance("big bang expansion", _cand(title="Big Bang expansion model"))[1])
        self.assertTrue(vs.relevance("big bang expansion", _cand(title="Big Bang poster"))[1])  # 2 of 3 = bar
        self.assertFalse(vs.relevance("big bang expansion", _cand(title="Expansion poster"))[1])  # 1 of 3

    def test_filter_reasons(self) -> None:
        q = "orion nebula"
        self.assertEqual(vs.filter_candidate(q, _cand(license=None), "any")[1], "licence_not_allowed")
        self.assertEqual(vs.filter_candidate(q, _cand(), "video")[1], "kind_mismatch")
        self.assertEqual(vs.filter_candidate(q, _cand(title="Orion Nebula logo"), "any")[1], "negative_keyword")
        self.assertEqual(vs.filter_candidate(q, _cand(width=800, height=600), "any")[1], "too_small")
        self.assertEqual(vs.filter_candidate(q, _cand(width=900, height=2400), "any")[1], "aspect")
        self.assertEqual(
            vs.filter_candidate(q, _cand(asset_url="https://upload.wikimedia.org/a/x.tif"), "any")[1],
            "unsupported_format",
        )
        self.assertEqual(
            vs.filter_candidate(q, _cand(asset_url="https://evil.example.com/x.jpg"), "any")[1],
            "asset_host_not_allowed",
        )
        ok, reason, score = vs.filter_candidate(q, _cand(), "any")
        self.assertTrue(ok)
        self.assertEqual(reason, "accepted")
        self.assertGreater(score, 0.9)

    def test_oversized_image_is_rejected(self) -> None:
        self.assertEqual(vs.filter_candidate("orion nebula", _cand(width=10485, height=6044), "any")[1], "too_large")
        self.assertEqual(vs.filter_candidate("orion nebula", _cand(width=8000, height=4500), "any")[1], "accepted")

    def test_video_gets_preference_in_mixed_scene(self) -> None:
        v = _cand(kind="video", source="nasa", width=1920, height=1080, asset_url=None, title="Orion Nebula flythrough")
        i = _cand(kind="image", source="wikimedia", width=1920, height=1080, title="Orion Nebula photo")
        _, _, sv = vs.filter_candidate("orion nebula", v, "any")
        _, _, si = vs.filter_candidate("orion nebula", i, "any")
        self.assertGreater(sv, si)
        _, _, sv_only = vs.filter_candidate("orion nebula", v, "video")
        _, _, si_only = vs.filter_candidate("orion nebula", i, "image")
        self.assertEqual(sv_only, si_only)  # preference applies only to mixed scenes

    def test_unknown_dimensions_pass_metadata_gate(self) -> None:
        ok, _, _ = vs.filter_candidate("orion nebula", _cand(width=None, height=None, asset_url=None), "any")
        self.assertTrue(ok)


# --------------------------------------------------------------------------- plan


class SelectionTests(unittest.TestCase):
    def test_mixed_scene_keeps_video_slots_even_when_images_score_higher(self) -> None:
        images = [_cand(source="openverse", source_id=f"i{n}", title=f"Nebula photo {n}", score=1.1) for n in range(6)]
        video = _cand(source="nasa", source_id="v1", kind="video", title="Nebula flythrough", score=0.9)
        chosen = vs.select_top(images + [video], "any", 4)
        self.assertIn("v1", [c["source_id"] for c in chosen])
        self.assertEqual(len(chosen), 4)

    def test_cross_source_duplicate_title_is_dropped(self) -> None:
        a = _cand(source="openverse", source_id="o1", title="CEERS mosaic of galaxies", score=1.1)
        b = _cand(source="wikimedia", source_id="w1", title="CEERS mosaic of galaxies", score=1.1)
        chosen = vs.select_top([a, b], "image", 5)
        self.assertEqual(len(chosen), 1)

    def test_image_only_scene_has_no_video_reservation(self) -> None:
        images = [_cand(source="openverse", source_id=f"i{n}", title=f"Nebula photo {n}", score=1.1) for n in range(6)]
        video = _cand(source="nasa", source_id="v1", kind="video", title="Nebula flythrough", score=0.5)
        chosen = vs.select_top(images + [video], "image", 5)
        self.assertEqual(len(chosen), 5)
        self.assertNotIn("v1", [c["source_id"] for c in chosen])


class PlanTests(unittest.TestCase):
    def _script(self) -> dict:
        return {
            "slug": "unit-plan-1min",
            "title": "Unit plan",
            "lang": "en",
            "scenes": [
                {"id": "a1s01", "act": 1, "visual_type": "cinema_clip", "stock_queries_en": ["orion nebula"]},
                {"id": "a1s02", "act": 1, "visual_type": "broll_cinematic", "stock_queries_en": []},
                {"id": "a1s03", "act": 1, "visual_type": "kpi", "stock_queries_en": []},
                {"id": "a1s04", "act": 1, "visual_type": "broll_cinematic", "stock_queries_en": ["orion nebula"]},
            ],
        }

    def test_plan_statuses_errors_and_dedupe(self) -> None:
        good = _cand(source="wikimedia", source_id="1")
        dup = _cand(source="wikimedia", source_id="1")  # same id -> must be deduped
        calls: list[tuple[str, str]] = []

        def wiki(q, kind, limit):
            calls.append(("wikimedia", kind))
            return [good, dup]

        def nasa(q, kind, limit):
            calls.append(("nasa", kind))
            raise arc.ArchiveSourceError("nasa.gov answered HTTP 500")

        with mock.patch.dict(arc.SEARCHERS, {"wikimedia": wiki, "nasa": nasa}, clear=False):
            plan = vs.build_plan(self._script(), sources=["wikimedia", "nasa"], per_scene=5)
        by_id = {s["id"]: s for s in plan["scenes"]}
        self.assertEqual(by_id["a1s03"]["status"], "skipped")
        self.assertEqual(by_id["a1s02"]["status"], "no_queries")
        self.assertEqual(by_id["a1s01"]["status"], "candidates")
        self.assertEqual(len(by_id["a1s01"]["candidates"]), 1)
        self.assertEqual(by_id["a1s01"]["source_errors"][0]["source"], "nasa")
        self.assertIn(("wikimedia", "video"), calls)
        self.assertIn(("wikimedia", "image"), calls)
        self.assertEqual(by_id["a1s04"]["visual_type"], "broll_cinematic")
        self.assertTrue(all(c["kind"] == "image" for c in by_id["a1s04"]["candidates"]) or by_id["a1s04"]["candidates"] == [])

    def test_broll_never_searches_video(self) -> None:
        kinds: list[str] = []

        def wiki(q, kind, limit):
            kinds.append(kind)
            return []

        script = {"slug": "unit-b-1min", "title": "t", "lang": "en", "scenes": [
            {"id": "a1s01", "act": 1, "visual_type": "broll_cinematic", "stock_queries_en": ["orion nebula"]}
        ]}
        with mock.patch.dict(arc.SEARCHERS, {"wikimedia": wiki}, clear=False):
            vs.build_plan(script, sources=["wikimedia"], per_scene=3)
        self.assertEqual(set(kinds), {"image"})

    def test_unknown_source_and_bad_slug_fail_closed(self) -> None:
        with self.assertRaisesRegex(vs.VisualSourcingError, "unknown"):
            vs.build_plan(self._script(), sources=["getty"], per_scene=3)
        bad = self._script()
        bad["slug"] = "Bad Slug!"
        with self.assertRaisesRegex(vs.VisualSourcingError, "not a valid slug"):
            vs.build_plan(bad, sources=["wikimedia"], per_scene=3)


# --------------------------------------------------------------------------- download and probe


class DownloadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = ROOT / "work" / f"_vs_test_{uuid.uuid4().hex[:8]}"
        self.tmp.mkdir(parents=True)
        self.png_path = self.tmp / "src.png"
        _make_png(self.png_path, PNG_1080P)
        self.png_bytes = self.png_path.read_bytes()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _client_with(self, handler):
        real = httpx.Client
        return mock.patch.object(httpx, "Client", lambda *a, **k: real(*a, transport=httpx.MockTransport(handler), **k))

    def test_good_png_downloads_with_sha(self) -> None:
        def handler(request):
            return httpx.Response(200, content=self.png_bytes, headers={"content-type": "image/png"})

        tmp = self.tmp / "dl.part"
        with self._client_with(handler):
            sha, n, fmt = vs._download("wikimedia", "https://upload.wikimedia.org/a.png", "image", tmp)
        self.assertEqual(fmt, "png")
        self.assertEqual(n, len(self.png_bytes))
        self.assertEqual(len(sha), 64)
        self.assertFalse(tmp.exists() and tmp.stat().st_size == 0)

    def test_html_error_page_is_rejected(self) -> None:
        def handler(request):
            return httpx.Response(200, content=b"<html>" + b"x" * 40_000 + b"</html>", headers={"content-type": "text/html"})

        with self._client_with(handler):
            with self.assertRaisesRegex(vs.VisualSourcingError, "not media"):
                vs._download("wikimedia", "https://upload.wikimedia.org/a.png", "image", self.tmp / "x.part")

    def test_magic_mismatch_is_rejected(self) -> None:
        def handler(request):
            return httpx.Response(200, content=b"NOTIMAGE" * 5000, headers={"content-type": "image/png"})

        tmp = self.tmp / "y.part"
        with self._client_with(handler):
            with self.assertRaisesRegex(vs.VisualSourcingError, "magic bytes"):
                vs._download("wikimedia", "https://upload.wikimedia.org/a.png", "image", tmp)
        self.assertFalse(tmp.exists())

    def test_redirect_to_foreign_host_is_rejected(self) -> None:
        def handler(request):
            if request.url.host == "upload.wikimedia.org":
                return httpx.Response(302, headers={"location": "https://evil.example.com/a.png"})
            return httpx.Response(200, content=self.png_bytes, headers={"content-type": "image/png"})

        with self._client_with(handler):
            with self.assertRaisesRegex(vs.VisualSourcingError, "outside the allow-list"):
                vs._download("wikimedia", "https://upload.wikimedia.org/a.png", "image", self.tmp / "z.part")

    def test_declared_size_over_cap_is_rejected_before_download(self) -> None:
        def handler(request):
            return httpx.Response(200, content=self.png_bytes, headers={"content-type": "image/png", "content-length": str(vs.MAX_IMAGE_BYTES + 1)})

        with self._client_with(handler):
            with self.assertRaisesRegex(vs.VisualSourcingError, "declared size"):
                vs._download("wikimedia", "https://upload.wikimedia.org/a.png", "image", self.tmp / "c.part")

    def test_too_small_asset_is_rejected(self) -> None:
        def handler(request):
            return httpx.Response(200, content=b"\x89PNG\r\n\x1a\n" + b"0" * 100, headers={"content-type": "image/png"})

        with self._client_with(handler):
            with self.assertRaisesRegex(vs.VisualSourcingError, "too small"):
                vs._download("wikimedia", "https://upload.wikimedia.org/a.png", "image", self.tmp / "s.part")

    def test_small_png_fails_post_download_probe(self) -> None:
        small = self.tmp / "small.png"
        _make_png(small, (640, 360))
        probe = vs._probe_image(small)
        self.assertEqual((probe["width"], probe["height"]), (640, 360))
        with self.assertRaisesRegex(vs.VisualSourcingError, "too_small"):
            vs._validate_probe("image", probe)

    def test_corrupt_image_fails_probe(self) -> None:
        bad = self.tmp / "bad.jpg"
        bad.write_bytes(b"\xff\xd8\xff" + b"garbage" * 4000)
        with self.assertRaisesRegex(vs.VisualSourcingError, "decode failed"):
            vs._probe_image(bad)

    def test_real_video_probe_if_sample_present(self) -> None:
        sample = ROOT / "public" / "cinema" / "bb_01_explosion.mp4"
        if not sample.is_file():
            self.skipTest("public/cinema/bb_01_explosion.mp4 not present")
        probe = vs._probe_video(sample)
        self.assertGreater(probe["width"], 0)
        self.assertGreater(probe["duration_sec"], 0)
        vs._validate_probe("video", probe)


# --------------------------------------------------------------------------- fetch orchestration


class FetchOrchestrationTests(unittest.TestCase):
    def test_falls_back_to_next_candidate_and_records_errors(self) -> None:
        first = _cand(source_id="bad")
        second = _cand(source_id="good")
        plan = {
            "slug": "unit-fetch-1min",
            "scenes": [
                {"id": "a1s01", "visual_type": "cinema_clip", "status": "candidates", "candidates": [first, second], "asset": None}
            ],
            "summary": {},
        }
        ok_record = {"file": "visual/unit-fetch-1min/a1s01_abc.jpg", "kind": "image", "license": "cc0"}

        def fake(scene_id, slug, cand):
            if cand["source_id"] == "bad":
                raise vs.VisualSourcingError("wikimedia: asset HTTP 404")
            return dict(ok_record)

        with mock.patch.object(vs, "fetch_candidate", side_effect=fake):
            vs.fetch_plan(plan)
        scene = plan["scenes"][0]
        self.assertEqual(scene["status"], "fetched")
        self.assertEqual(scene["asset"]["file"], ok_record["file"])
        self.assertEqual(plan["summary"], {"fetched": 1})

    def test_same_archive_item_is_not_used_in_two_scenes(self) -> None:
        shared = _cand(source_id="same", source="wikimedia")
        other = _cand(source_id="other", source="openverse")
        plan = {
            "slug": "unit-dup-1min",
            "scenes": [
                {"id": "a1s01", "visual_type": "cinema_clip", "status": "candidates", "candidates": [shared], "asset": None},
                {"id": "a1s02", "visual_type": "broll_cinematic", "status": "candidates", "candidates": [shared, other], "asset": None},
            ],
            "summary": {},
        }

        def fake(scene_id, slug, cand):
            return {"file": f"visual/x/{scene_id}.jpg", "kind": "image", "license": "cc0", "source": cand["source"], "source_id": cand["source_id"]}

        with mock.patch.object(vs, "fetch_candidate", side_effect=fake):
            vs.fetch_plan(plan)
        self.assertEqual(plan["scenes"][0]["asset"]["source_id"], "same")
        self.assertEqual(plan["scenes"][1]["asset"]["source_id"], "other")
        self.assertEqual(plan["scenes"][1]["status"], "fetched")

    def test_all_candidates_fail_marks_scene_failed_not_green(self) -> None:
        plan = {
            "slug": "unit-fetch2-1min",
            "scenes": [{"id": "a1s01", "visual_type": "cinema_clip", "status": "candidates", "candidates": [_cand(source_id="x")], "asset": None}],
            "summary": {},
        }
        with mock.patch.object(vs, "fetch_candidate", side_effect=vs.VisualSourcingError("nope")):
            vs.fetch_plan(plan)
        self.assertEqual(plan["scenes"][0]["status"], "failed")
        self.assertIsNone(plan["scenes"][0]["asset"])
        self.assertEqual(len(plan["scenes"][0]["fetch_errors"]), 1)


# --------------------------------------------------------------------------- apply to deck


class ApplyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.slug = f"unit-apply-{uuid.uuid4().hex[:6]}-1min"
        self.dir = vs.PUBLIC_VISUAL_DIR / self.slug
        self.dir.mkdir(parents=True)
        _make_png(self.dir / "a1s01_abc.png", PNG_1080P)
        _make_png(self.dir / "a1s02_def.png", PNG_1080P)
        self.deck = {
            "slug": self.slug,
            "lang": "en",
            "theme": "quantum_ledger",
            "aspect": "16:9",
            "brand": "DUP LABS",
            "burn_captions": True,
            "caption_style": "bold",
            "background": {"enabled": False},
            "music": {"enabled": False},
            "voice": {"engine": "kokoro_v1", "lang": "en", "speaker": "am_michael", "rate": "100%"},
            "slides": [
                {
                    "id": "a1s01",
                    "tag": "01",
                    "type": "cinema_clip",
                    "title": "t",
                    "voice_text": "Energy erupted from a single point and space began to stretch.",
                    "background_query": "orion nebula",
                    "cinema": {"badge": "ACT 1", "crossfade_frames": 12, "grade": "cinema_warm"},
                },
                {
                    "id": "a1s02",
                    "tag": "02",
                    "type": "broll_cinematic",
                    "title": "t2",
                    "voice_text": "Galaxies drift apart as the cosmos keeps expanding over time.",
                    "broll": {"badge": "ACT 1"},
                },
            ],
        }
        self.plan = {
            "slug": self.slug,
            "title": "t",
            "scenes": [
                {"id": "a1s01", "visual_type": "cinema_clip", "status": "fetched", "asset": {
                    "file": f"visual/{self.slug}/a1s01_abc.png", "kind": "image", "license": "cc0",
                    "creator": "Hubble", "title": "Orion", "license_url": "", "page_url": "https://x", "source": "wikimedia",
                    "source_id": "1", "width": 1920, "height": 1080, "duration_sec": None, "sha256": "0", "bytes": 1,
                    "asset_url": "https://upload.wikimedia.org/a.png"}},
                {"id": "a1s02", "visual_type": "broll_cinematic", "status": "fetched", "asset": {
                    "file": f"visual/{self.slug}/a1s02_def.png", "kind": "image", "license": "by",
                    "creator": "Jane", "title": "Galaxy", "license_url": "https://creativecommons.org/licenses/by/4.0",
                    "page_url": "https://x", "source": "openverse", "source_id": "2", "width": 1920, "height": 1080,
                    "duration_sec": None, "sha256": "1", "bytes": 1, "asset_url": "https://live.staticflickr.com/b.png"}},
            ],
        }

    def tearDown(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_wires_cinema_src_and_broll_image_and_validates(self) -> None:
        result = vs.apply_to_deck(self.deck, self.plan)
        out = result["deck"]
        s1, s2 = out["slides"]
        self.assertEqual(s1["cinema"]["src"], f"visual/{self.slug}/a1s01_abc.png")
        self.assertNotIn("background_query", s1)
        self.assertEqual(s2["broll"]["image"], f"visual/{self.slug}/a1s02_def.png")
        self.assertEqual(result["wired"], ["a1s01", "a1s02"])
        validate_deck(out, check_assets=True)

    def test_input_deck_is_not_mutated(self) -> None:
        before = copy.deepcopy(self.deck)
        vs.apply_to_deck(self.deck, self.plan)
        self.assertEqual(self.deck, before)

    def test_missing_asset_fails_closed_by_default(self) -> None:
        self.plan["scenes"][0]["asset"] = None
        self.plan["scenes"][0]["status"] = "failed"
        with self.assertRaisesRegex(vs.VisualSourcingError, "a1s01"):
            vs.apply_to_deck(self.deck, self.plan)

    def test_missing_broll_asset_allowed_only_explicitly(self) -> None:
        self.plan["scenes"][1]["asset"] = None
        self.plan["scenes"][1]["status"] = "no_candidates"
        with self.assertRaisesRegex(vs.VisualSourcingError, "a1s02"):
            vs.apply_to_deck(self.deck, self.plan)
        result = vs.apply_to_deck(self.deck, self.plan, allow_missing=True)
        self.assertEqual(result["missing"], ["a1s02 (no_candidates)"])
        self.assertNotIn("image", result["deck"]["slides"][1]["broll"])

    def test_missing_cinema_asset_is_never_allowed(self) -> None:
        """A cinema_clip with no media would render empty (background is disabled); --allow-missing must not hide it."""
        self.plan["scenes"][0]["asset"] = None
        self.plan["scenes"][0]["status"] = "failed"
        with self.assertRaisesRegex(vs.VisualSourcingError, "cannot be left empty"):
            vs.apply_to_deck(self.deck, self.plan, allow_missing=True)

    def test_existing_shots_are_not_overridden(self) -> None:
        self.deck["slides"][0]["cinema"]["shots"] = [{"src": "cinema/x.mp4"}]
        with self.assertRaisesRegex(vs.VisualSourcingError, "shots already set"):
            vs.apply_to_deck(self.deck, self.plan)

    def test_attribution_contains_licence_and_creator(self) -> None:
        lines = vs.attribution_lines(self.plan)
        text = "\n".join(lines)
        self.assertIn("Hubble", text)
        self.assertIn("CC0 1.0", text)
        self.assertIn("CC BY (attribution required)", text)
        self.assertIn("Jane", text)


if __name__ == "__main__":
    unittest.main()
