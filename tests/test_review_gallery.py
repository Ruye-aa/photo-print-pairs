import hashlib
from html.parser import HTMLParser
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("review_gallery", ROOT / "scripts/review_gallery.py")
gallery = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gallery)


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.scripts = []
        self.remote = []
        self.payload = ""
        self.in_payload = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script":
            self.scripts.append(attrs)
            self.in_payload = attrs.get("id") == "gallery-data"
        for key in ("src", "href"):
            if attrs.get(key, "").startswith(("http:", "https:", "//")):
                self.remote.append(attrs[key])

    def handle_endtag(self, tag):
        if tag == "script":
            self.in_payload = False

    def handle_data(self, text):
        if self.in_payload:
            self.payload += text


class ReviewGalleryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.records = self.root / "records"
        self.records.mkdir()
        self.output = self.root / "review.html"

    def record(self, name="pair.png", color="red", record_name="one.json"):
        image = self.root / name
        Image.new("RGB", (80, 120), color).save(image)
        value = {"output": str(image), "output_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
                 "photo_sha256": "a" * 64, "output_size": [80, 120],
                 "top_matches_oriented_source_rgb_pixels": True}
        self.write_record(value, record_name)
        return value

    def write_record(self, value, name="one.json"):
        (self.records / name).write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def parse(self):
        parser = PageParser()
        parser.feed(self.output.read_text(encoding="utf-8"))
        return parser, json.loads(parser.payload)

    def review_entry(self, record, decision="keep"):
        return {"output_sha256": record["output_sha256"], "photo_sha256": record["photo_sha256"],
                "generation_plan_sha256": record.get("generation_plan_sha256"), "decision": decision,
                "feedback": {"problem": "", "instruction": "", "keep": []}}

    def write_review(self, entries):
        path = self.root / "previous-review.json"
        path.write_text(json.dumps({"schema_version": 1, "items": entries}, ensure_ascii=False), encoding="utf-8")
        return path

    def test_builds_offline_verified_gallery_without_absolute_paths(self):
        self.record()
        result = gallery.build_gallery(self.records, self.output)
        self.assertEqual(result["items"], 1)
        parser, data = self.parse()
        self.assertEqual(parser.remote, [])
        self.assertEqual(len(parser.scripts), 2)
        self.assertNotIn(str(self.root), self.output.read_text())
        item = data["items"][0]
        self.assertTrue(item["thumbnail"].startswith("data:image/png;base64,"))
        self.assertTrue(item["image"].startswith("data:image/png;base64,"))
        self.assertEqual(item["output_size"], [80, 120])
        self.assertIn("没有自动美学评分", self.output.read_text())
        self.assertNotIn("innerHTML", self.output.read_text())

    def test_hash_mismatch_leaves_no_output(self):
        record = self.record()
        record["output_sha256"] = "b" * 64
        self.write_record(record)
        with self.assertRaisesRegex(ValueError, "output_sha256 mismatch"):
            gallery.build_gallery(self.records, self.output)
        self.assertFalse(self.output.exists())

    def test_size_mismatch_leaves_no_output(self):
        record = self.record()
        record["output_size"] = [81, 120]
        self.write_record(record)
        with self.assertRaisesRegex(ValueError, "output_size mismatch"):
            gallery.build_gallery(self.records, self.output)
        self.assertFalse(self.output.exists())

    def test_invalid_record_among_valid_records_leaves_no_output(self):
        self.record()
        self.write_record({"output": "arbitrary.png"}, "two.json")
        with self.assertRaisesRegex(ValueError, "two.json"):
            gallery.build_gallery(self.records, self.output)
        self.assertFalse(self.output.exists())

    def test_missing_records_and_nested_records_are_rejected(self):
        nested = self.records / "nested"
        nested.mkdir()
        (nested / "ignored.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "No composition records"):
            gallery.build_gallery(self.records, self.output)
        self.assertFalse(self.output.exists())

    def test_duplicate_outputs_merge_but_distinct_versions_remain(self):
        first = self.record()
        self.write_record(first, "repeat.json")
        self.record(name="pair_v2.png", color="blue", record_name="version.json")
        result = gallery.build_gallery(self.records, self.output)
        self.assertEqual((result["items"], result["duplicates_skipped"]), (2, 1))
        _, data = self.parse()
        self.assertEqual(len({item["photo_sha256"] for item in data["items"]}), 1)

    def test_conflicting_duplicate_photo_hash_is_rejected(self):
        record = self.record()
        record["photo_sha256"] = "b" * 64
        self.write_record(record, "repeat.json")
        with self.assertRaisesRegex(ValueError, "conflicting photo_sha256"):
            gallery.build_gallery(self.records, self.output)
        self.assertFalse(self.output.exists())

    def test_plan_hash_is_preserved_and_old_records_remain_reviewable(self):
        record = self.record()
        gallery.build_gallery(self.records, self.output)
        _, data = self.parse()
        self.assertIsNone(data["items"][0]["generation_plan_sha256"])
        self.output.unlink()
        record["generation_plan_sha256"] = "c" * 64
        self.write_record(record, "with-plan.json")
        gallery.build_gallery(self.records, self.output)
        _, data = self.parse()
        self.assertEqual(data["items"][0]["generation_plan_sha256"], "c" * 64)

    def test_invalid_or_conflicting_plan_hash_is_rejected(self):
        record = self.record()
        record["generation_plan_sha256"] = "invalid"
        self.write_record(record)
        with self.assertRaisesRegex(ValueError, "invalid generation_plan_sha256"):
            gallery.build_gallery(self.records, self.output)
        record["generation_plan_sha256"] = "c" * 64
        self.write_record(record)
        record["generation_plan_sha256"] = "d" * 64
        self.write_record(record, "other-plan.json")
        with self.assertRaisesRegex(ValueError, "conflicting generation_plan_sha256"):
            gallery.build_gallery(self.records, self.output)
        self.assertFalse(self.output.exists())

    def test_title_and_record_fields_cannot_inject_script(self):
        name = '<img src=x onerror=alert(1)>.png'
        record = self.record(name=name)
        hostile = '</script><script>alert("injected")</script>&\u2028__DATA__'
        record["generation_plan"] = {"style": {"id": "C", "name": hostile}, "prompt": hostile}
        self.write_record(record)
        gallery.build_gallery(self.records, self.output, title=hostile)
        parser, data = self.parse()
        self.assertEqual(len(parser.scripts), 2)
        self.assertEqual(data["items"][0]["style_name"], hostile)
        self.assertEqual(data["items"][0]["name"], name)
        self.assertNotIn('<script>alert("injected")</script>', self.output.read_text())

    def test_existing_output_is_preserved(self):
        self.record()
        self.output.write_text("keep me")
        with self.assertRaisesRegex(ValueError, "already exists"):
            gallery.build_gallery(self.records, self.output)
        self.assertEqual(self.output.read_text(), "keep me")

    def test_relative_output_resolves_against_record_directory(self):
        record = self.record()
        record["output"] = "../pair.png"
        self.write_record(record)
        self.assertEqual(gallery.build_gallery(self.records, self.output)["items"], 1)

    def test_false_source_pixel_flag_remains_explicit(self):
        record = self.record()
        record["top_matches_oriented_source_rgb_pixels"] = False
        self.write_record(record)
        gallery.build_gallery(self.records, self.output)
        _, data = self.parse()
        self.assertFalse(data["items"][0]["source_pixels_equal_recorded"])

    def test_cli_failure_is_clear_and_does_not_write(self):
        result = subprocess.run([sys.executable, str(ROOT / "scripts/review_gallery.py"),
                                 "--records", str(self.records), "--output", str(self.output)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("ERROR: No composition records", result.stderr)
        self.assertFalse(self.output.exists())

    def test_import_keeps_old_vote_and_new_version_of_same_photo_starts_pending(self):
        first = self.record()
        review = self.write_review([self.review_entry(first)])
        second = self.record(name="pair_v2.png", color="blue", record_name="version.json")
        result = gallery.build_gallery(self.records, self.output, review=review)
        _, data = self.parse()
        items = {item["output_sha256"]: item for item in data["items"]}
        self.assertEqual(items[first["output_sha256"]]["initial_review"]["decision"], "keep")
        self.assertNotIn("initial_review", items[second["output_sha256"]])
        self.assertEqual(result["review_imported"], 1)
        self.assertEqual(result["review_skipped"], 0)

    def test_import_can_skip_outputs_outside_current_subset(self):
        first = self.record()
        other = self.review_entry(first, "discard")
        other["output_sha256"] = "e" * 64
        review = self.write_review([self.review_entry(first), other])
        result = gallery.build_gallery(self.records, self.output, review=review)
        self.assertEqual((result["review_imported"], result["review_skipped"]), (1, 1))

    def test_import_rejects_same_output_with_wrong_source_or_plan(self):
        record = self.record()
        record["generation_plan_sha256"] = "c" * 64
        self.write_record(record)
        for field, value in [("photo_sha256", "b" * 64), ("generation_plan_sha256", "d" * 64),
                             ("generation_plan_sha256", None)]:
            with self.subTest(field=field, value=value):
                entry = self.review_entry(record)
                entry[field] = value
                review = self.write_review([entry])
                with self.assertRaisesRegex(ValueError, f"review {field} does not match"):
                    gallery.build_gallery(self.records, self.output, review=review)
                self.assertFalse(self.output.exists())

    def test_import_rejects_duplicate_items_even_with_identical_decisions(self):
        record = self.record()
        entry = self.review_entry(record)
        review = self.write_review([entry, entry])
        with self.assertRaisesRegex(ValueError, "duplicate output_sha256"):
            gallery.build_gallery(self.records, self.output, review=review)
        self.assertFalse(self.output.exists())

    def test_import_requires_valid_review_fields(self):
        record = self.record()
        cases = [("output_sha256", "no"), ("photo_sha256", None), ("generation_plan_sha256", 7),
                 ("decision", []), ("decision", "accepted"), ("feedback", "keep")]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                entry = self.review_entry(record)
                entry[field] = value
                with self.assertRaises(ValueError):
                    gallery.build_gallery(self.records, self.output, review=self.write_review([entry]))
                self.assertFalse(self.output.exists())
        for field, value in [("problem", "unknown"), ("instruction", None), ("keep", "text"),
                             ("keep", ["correct", 1])]:
            with self.subTest(feedback_field=field, value=value):
                entry = self.review_entry(record)
                entry["feedback"][field] = value
                with self.assertRaises(ValueError):
                    gallery.build_gallery(self.records, self.output, review=self.write_review([entry]))
                self.assertFalse(self.output.exists())
        for field in ("photo_sha256", "generation_plan_sha256", "decision", "feedback"):
            with self.subTest(missing=field):
                entry = self.review_entry(record)
                del entry[field]
                with self.assertRaises(ValueError):
                    gallery.build_gallery(self.records, self.output, review=self.write_review([entry]))

    def test_import_revise_requires_problem_and_instruction(self):
        record = self.record()
        for problem, instruction in [("", "修复主体"), ("missing_subject", "  ")]:
            with self.subTest(problem=problem):
                entry = self.review_entry(record, "revise")
                entry["feedback"].update(problem=problem, instruction=instruction)
                with self.assertRaisesRegex(ValueError, "revise requires"):
                    gallery.build_gallery(self.records, self.output, review=self.write_review([entry]))
                self.assertFalse(self.output.exists())

    def test_import_preserves_valid_feedback_and_neutral_decisions(self):
        record = self.record()
        for decision in ("pending", "keep", "discard", "revise"):
            with self.subTest(decision=decision):
                entry = self.review_entry(record, decision)
                if decision == "revise":
                    entry["feedback"] = {"problem": "style_mismatch", "instruction": "减少颗粒", "keep": ["主体轮廓", "纸底颜色"]}
                gallery.build_gallery(self.records, self.output, review=self.write_review([entry]))
                _, data = self.parse()
                self.assertEqual(data["items"][0]["initial_review"], {"decision": decision, "feedback": entry["feedback"]})
                self.output.unlink()

    def test_import_changes_storage_namespace_when_imported_votes_change(self):
        record = self.record()
        review = self.write_review([self.review_entry(record, "keep")])
        gallery.build_gallery(self.records, self.output, review=review)
        _, first = self.parse()
        self.output.unlink()
        self.write_review([self.review_entry(record, "discard")])
        gallery.build_gallery(self.records, self.output, review=review)
        _, second = self.parse()
        self.assertNotEqual(first["batch_id"], second["batch_id"])

    def test_imported_feedback_remains_inert_html_data(self):
        record = self.record()
        entry = self.review_entry(record, "revise")
        hostile = '</script><script>alert("review")</script>'
        entry["feedback"] = {"problem": "text", "instruction": hostile, "keep": [hostile]}
        gallery.build_gallery(self.records, self.output, review=self.write_review([entry]))
        parser, data = self.parse()
        self.assertEqual(len(parser.scripts), 2)
        self.assertEqual(data["items"][0]["initial_review"]["feedback"]["instruction"], hostile)

    def test_import_validates_schema_and_duplicate_json_keys(self):
        self.record()
        review = self.root / "previous-review.json"
        for value in [{"schema_version": True, "items": []}, {"schema_version": 2, "items": []},
                      {"schema_version": 1, "items": {}}, {"items": []}]:
            with self.subTest(value=value):
                review.write_text(json.dumps(value))
                with self.assertRaises(ValueError):
                    gallery.build_gallery(self.records, self.output, review=review)
                self.assertFalse(self.output.exists())
        review.write_text('{"schema_version":1,"schema_version":1,"items":[]}')
        with self.assertRaisesRegex(ValueError, "Duplicate JSON key"):
            gallery.build_gallery(self.records, self.output, review=review)

    def test_cli_accepts_review_file(self):
        record = self.record()
        review = self.write_review([self.review_entry(record)])
        result = subprocess.run([sys.executable, str(ROOT / "scripts/review_gallery.py"),
                                 "--records", str(self.records), "--output", str(self.output),
                                 "--review", str(review)], capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout)["review_imported"], 1)
        _, data = self.parse()
        self.assertEqual(data["items"][0]["initial_review"]["decision"], "keep")


if __name__ == "__main__":
    unittest.main()
