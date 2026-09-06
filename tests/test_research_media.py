import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("research_media", ROOT / "scripts/research_media.py")
research = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(research)


class ResearchMediaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.input = self.root / "input"
        self.input.mkdir()
        self.output = self.root / "work/research"
        self.image = self.input / "capture.png"
        Image.new("RGB", (17, 29), "#557744").save(self.image)
        self.document = {"schema_version": 1, "sources": [{
            "source_id": "abc123", "url": "https://www.xiaohongshu.com/search_result/abc123?xsec_token=SECRET#tracking",
            "title": "蜡笔风景", "author": "作者", "media": [{
                "capture_method": "screenshot", "page": 2, "local_file": "capture.png",
                "failure_reason": "Download failed at /private/secret?xsec_token=SECRET"}]}]}

    def run_import(self):
        return research.import_media(self.document, self.input, self.output)

    def test_screenshot_keeps_original_file_bytes_and_records_dimensions(self):
        report = self.run_import()
        row = report["sources"][0]["media"][0]
        destination = self.output / row["local_file"]
        self.assertEqual(destination.read_bytes(), self.image.read_bytes())
        self.assertEqual(row["dimensions"], [17, 29])
        self.assertEqual(row["sha256"], hashlib.sha256(self.image.read_bytes()).hexdigest())
        self.assertEqual(row["capture_method"], "screenshot")
        self.assertEqual(row["page"], 2)
        self.assertEqual(report["summary"]["saved_by_capture_method"], {"screenshot": 1})

    def test_public_export_contains_neither_private_paths_nor_signed_urls(self):
        report = self.run_import()
        report["sources"][0]["media"][0]["media_url"] = "https://cdn.example/img?secret=123"
        public = research.public_inventory(report)
        serialized = json.dumps(public, ensure_ascii=False)
        self.assertEqual(public["sources"][0]["url"], "https://www.xiaohongshu.com/explore/abc123")
        for forbidden in ("SECRET", "xsec_token", "tracking", "capture.png", "failure_reason", "private/secret", "media_url", "local_file"):
            self.assertNotIn(forbidden, serialized)
        self.assertEqual(public["sources"][0]["title"], "蜡笔风景")
        self.assertEqual(public["sources"][0]["author"], "作者")

    def test_duplicate_content_counts_unique_files_without_losing_provenance(self):
        second = dict(self.document["sources"][0], source_id="second", title="第二篇")
        self.document["sources"].append(second)
        report = self.run_import()
        self.assertEqual(report["summary"]["saved_entries"], 2)
        self.assertEqual(report["summary"]["unique_files"], 1)
        self.assertEqual(report["summary"]["duplicate_entries"], 1)
        self.assertEqual(report["sources"][1]["media"][0]["duplicate_of"], "abc123:1")

    def test_repeat_reuses_files_but_changed_input_cannot_overwrite_archive(self):
        first = self.run_import()
        archived = self.output / first["sources"][0]["media"][0]["local_file"]
        old_bytes = archived.read_bytes()
        repeat = self.run_import()
        self.assertEqual(repeat["summary"]["reused_files"], 1)
        self.assertEqual(repeat["summary"]["copied_files"], 0)
        Image.new("RGB", (17, 29), "red").save(self.image)
        conflict = self.run_import()
        self.assertEqual(conflict["sources"][0]["media"][0]["error_code"], "destination_content_conflict")
        self.assertEqual(archived.read_bytes(), old_bytes)

    def test_missing_download_is_failed_while_screenshot_fallback_is_saved(self):
        self.document["sources"][0]["media"].insert(0, {
            "capture_method": "original_download", "page": 2, "failure_reason": "403"})
        report = self.run_import()
        self.assertEqual(report["summary"]["saved_entries"], 1)
        self.assertEqual(report["summary"]["failed_entries"], 1)
        self.assertEqual(report["sources"][0]["media"][0]["error_code"], "missing_local_file")

    def test_source_traversal_rejected_before_writing(self):
        for source_id in ("../escape", "/absolute", "bad/name", ".", "..", "a\\b"):
            with self.subTest(source_id=source_id):
                self.document["sources"][0]["source_id"] = source_id
                with self.assertRaises(ValueError):
                    self.run_import()
                self.assertFalse(self.output.exists())

    def test_relative_traversal_and_symlink_escape_recorded_as_failed(self):
        outside = self.root / "outside.png"
        Image.new("RGB", (3, 4)).save(outside)
        link = self.input / "escape.png"
        link.symlink_to(outside)
        for value in ("../outside.png", "escape.png"):
            with self.subTest(value=value):
                self.document["sources"][0]["media"][0]["local_file"] = value
                report = self.run_import()
                self.assertEqual(report["sources"][0]["media"][0]["error_code"], "unsafe_relative_path")
                self.assertEqual(report["summary"]["saved_entries"], 0)

    def test_explicit_absolute_saved_file_is_supported(self):
        self.document["sources"][0]["media"][0]["local_file"] = str(self.image)
        self.assertEqual(self.run_import()["summary"]["saved_entries"], 1)

    def test_destination_symlink_cannot_write_outside_archive(self):
        self.output.mkdir(parents=True)
        outside = self.root / "outside"
        outside.mkdir()
        (self.output / "abc123").symlink_to(outside, target_is_directory=True)
        report = self.run_import()
        self.assertEqual(report["sources"][0]["media"][0]["error_code"], "unsafe_destination")
        self.assertEqual(list(outside.iterdir()), [])

    def test_corrupt_image_is_failed_instead_of_saved(self):
        self.image.write_bytes(b"<html>download forbidden</html>")
        report = self.run_import()
        self.assertEqual(report["sources"][0]["media"][0]["error_code"], "image_decode_failed")
        self.assertEqual(report["summary"]["unique_files"], 0)

    def test_video_frame_has_seconds_but_remains_a_still_image(self):
        media = self.document["sources"][0]["media"][0]
        media.update(capture_method="video_frame", timestamp=12.5)
        row = self.run_import()["sources"][0]["media"][0]
        self.assertEqual(row["timestamp"], 12.5)
        self.assertEqual(row["verification"], "image_decoded")
        self.assertEqual(row["capture_method"], "video_frame")

    def test_video_does_not_claim_playback_or_unknown_dimensions(self):
        video = self.input / "video.mp4"
        video.write_bytes(b"\x00\x00\x00\x20ftypisom\x00\x00\x00\x00isom")
        media = self.document["sources"][0]["media"][0]
        media.update(capture_method="video_download", local_file="video.mp4")
        row = self.run_import()["sources"][0]["media"][0]
        self.assertEqual(row["status"], "saved")
        self.assertIsNone(row["dimensions"])
        self.assertIn("not_playback_verified", row["verification"])
        video.write_bytes(b"<html>login required</html>")
        row = self.run_import()["sources"][0]["media"][0]
        self.assertEqual(row["error_code"], "unrecognized_video_container")

    def test_invalid_page_timestamp_and_method_are_not_exported_as_observations(self):
        media = self.document["sources"][0]["media"][0]
        for field, value, error in (("page", -1, "invalid_page"), ("page", True, "invalid_page"),
                                    ("timestamp", float("nan"), "invalid_timestamp"),
                                    ("capture_method", "unknown", "invalid_capture_method")):
            with self.subTest(field=field, value=value):
                old = media.get(field)
                media[field] = value
                report = self.run_import()
                self.assertEqual(report["sources"][0]["media"][0]["error_code"], error)
                json.dumps(research.public_inventory(report), allow_nan=False)
                if old is None:
                    del media[field]
                else:
                    media[field] = old

    def test_duplicate_source_ids_and_non_http_urls_rejected(self):
        self.document["sources"].append(dict(self.document["sources"][0]))
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.run_import()
        for url in ("file:///tmp/private", "javascript:alert(1)", "https://user:secret@example.com/note", "https://example.com/white space"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                research.canonical_url(url)

    def test_report_writer_preserves_different_prior_report(self):
        path = self.root / "report.json"
        first = research.write_json_preserving(path, {"version": 1})
        same = research.write_json_preserving(path, {"version": 1})
        second = research.write_json_preserving(path, {"version": 2})
        self.assertEqual(first, same)
        self.assertEqual(second.name, "report_v2.json")
        self.assertEqual(json.loads(first.read_text()), {"version": 1})

    def test_cli_partial_failure_persists_audit_and_returns_nonzero(self):
        self.document["sources"][0]["media"].append({"capture_method": "original_download"})
        manifest = self.input / "input.json"
        manifest.write_text(json.dumps(self.document), encoding="utf-8")
        public = self.root / "public.json"
        result = subprocess.run([
            sys.executable, str(ROOT / "scripts/research_media.py"), "--manifest", str(manifest),
            "--output", str(self.output), "--public-export", str(public),
        ], text=True, capture_output=True)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(json.loads(result.stdout)["summary"]["failed_entries"], 1)
        self.assertTrue((self.output / "manifest.json").exists())
        self.assertNotIn("SECRET", public.read_text())


if __name__ == "__main__":
    unittest.main()
