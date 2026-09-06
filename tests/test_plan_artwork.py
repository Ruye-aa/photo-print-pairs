import argparse
import copy
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
SPEC = importlib.util.spec_from_file_location("plan_artwork", ROOT / "scripts/plan_artwork.py")
planner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(planner)


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.photo = self.root / "photo.png"
        Image.new("RGB", (60, 40), "green").save(self.photo)
        self.brief = {
            "subject_type": "botanical", "subject": "Two flowers in a vase",
            "protected": ["Both flower heads and the vase rim"],
            "simplify": ["Merge fine leaf veins"],
            "geometry": ["The small flower is left of the tall flower"],
            "palette": ["violet", "leaf green"],
            "composition": "Keep the vase low and both flowers inside the frame",
            "flow": "from the outer leaf tips toward nearby empty paper",
        }
        self.brief_path = self.write_json("brief.json", self.brief)
        self.args = argparse.Namespace(
            photo=str(self.photo), brief=str(self.brief_path), output=str(self.root / "plan.json"),
            style=None, strength=None, series=None, feedback=None, previous=None,
            references=None, review=None, result_sha256=None)

    def write_json(self, name, data):
        path = self.root / name
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def compile(self, **kwargs):
        args = copy.copy(self.args)
        for key, value in kwargs.items():
            setattr(args, key, str(value) if isinstance(value, Path) else value)
        return planner.compile_plan(args)

    def test_auto_is_conservative_and_subject_dependent(self):
        for subject_type in planner.SUBJECT_TYPES:
            with self.subTest(subject_type=subject_type):
                self.brief["subject_type"] = subject_type
                self.write_json("brief.json", self.brief)
                plan = self.compile(output=self.root / f"{subject_type}.json")
                self.assertIn(plan["style"]["id"], {"A", "B"})
                self.assertEqual(plan["style"]["id"], "B" if subject_type in {"water", "botanical"} else "A")

    def test_recipes_are_separate_and_content_contract_survives_abstraction(self):
        plans = {style: self.compile(style=style, strength="bold", output=self.root / f"{style}.json") for style in "ABCDE"}
        # Each prompt activates exactly its own material system, including at bold strength.
        for style_id, plan in plans.items():
            self.assertIn(plan["style"]["material"], plan["prompt"])
            self.assertTrue(plan["checks"]["review_required"])
            self.assertEqual(plan["checks"]["protected"], self.brief["protected"])
            for other_id, other in plans.items():
                if other_id != style_id:
                    self.assertNotIn(other["style"]["material"], plan["prompt"])
            for protected in self.brief["protected"] + self.brief["geometry"]:
                self.assertIn(protected, plan["prompt"])
        self.assertIn("grain", plans["C"]["style"]["avoid"])
        self.assertTrue(any("mesh grain" in rule for rule in plans["D"]["style"]["rules"]))
        self.assertNotIn(self.brief["flow"], plans["C"]["prompt"])
        self.assertIn(self.brief["flow"], plans["B"]["prompt"])

    def test_series_inheritance_and_explicit_overrides(self):
        series = self.write_json("series.json", {"style": "D", "strength": "gentle", "palette": ["navy", "ochre"], "paper_color": "#faf2e0"})
        inherited = self.compile(series=series)
        self.assertEqual((inherited["style"]["id"], inherited["strength"]), ("D", "gentle"))
        self.assertIn("navy; ochre", inherited["prompt"])
        self.assertIn("#FAF2E0", inherited["prompt"])
        self.assertEqual(inherited["style"]["paper_color"], "#FAF2E0")
        explicit = self.compile(series=series, style="C", strength="bold", output=self.root / "override.json")
        self.assertEqual((explicit["style"]["id"], explicit["strength"]), ("C", "bold"))
        self.assertEqual(explicit["series"]["style"], "C")
        auto = self.compile(series=series, style="auto", output=self.root / "auto.json")
        self.assertEqual(auto["style"]["id"], "B")

    def test_source_hash_uses_original_bytes_and_dimensions_use_exif_orientation(self):
        rotated = self.root / "rotated.jpg"
        im = Image.new("RGB", (72, 32), "red")
        exif = im.getexif()
        exif[274] = 6
        im.save(rotated, exif=exif)
        original = rotated.read_bytes()
        plan = self.compile(photo=rotated)
        self.assertEqual((plan["source"]["width"], plan["source"]["height"]), (32, 72))
        self.assertEqual(plan["source"]["sha256"], hashlib.sha256(original).hexdigest())
        self.assertIn("32:72", plan["prompt"])
        self.assertEqual(rotated.read_bytes(), original)
        self.assertEqual(plan["references"], [])

    def test_feedback_preserves_history_but_does_not_mix_old_style(self):
        previous = self.compile(style="D", strength="bold")
        before = Path(self.args.output).read_bytes()
        feedback = self.write_json("feedback.json", {"problem": "style_mismatch", "instruction": "Use clean planes", "keep": ["The vase size"]})
        revised = self.compile(previous=self.args.output, feedback=feedback, style="C", output=self.root / "revision.json")
        self.assertEqual(revised["revision"]["previous_prompt"], previous["prompt"])
        self.assertNotIn(previous["style"]["material"], revised["prompt"])
        self.assertIn("The vase size", revised["prompt"])
        self.assertEqual(revised["strength"], "bold")
        self.assertEqual(Path(self.args.output).read_bytes(), before)
        self.assertIsNone(revised["revision"]["selected_output_sha256"])

    def test_feedback_rejects_wrong_source_and_malformed_previous_plan(self):
        previous = self.compile()
        feedback = self.write_json("feedback.json", {"problem": "missing_subject", "instruction": "Restore the smaller flower", "keep": []})
        other = self.root / "other.png"
        Image.new("RGB", (60, 40), "blue").save(other)
        with self.assertRaisesRegex(ValueError, "another photo"):
            self.compile(photo=other, feedback=feedback, previous=self.args.output, output=self.root / "rev.json")
        for mutation in ({"prompt": "  "}, {"schema_version": True}, {"generated": True}, {"style": {"id": "C"}}):
            with self.subTest(mutation=mutation):
                invalid = dict(previous, **mutation)
                self.write_json("bad-plan.json", invalid)
                with self.assertRaises(ValueError):
                    self.compile(feedback=feedback, previous=self.root / "bad-plan.json", output=self.root / "rev.json")
        self.assertFalse((self.root / "rev.json").exists())

    def test_review_targets_one_exact_candidate_and_records_it(self):
        previous = self.compile()
        output_sha = "a" * 64
        item = {"output_sha256": output_sha, "photo_sha256": previous["source"]["sha256"], "decision": "revise",
                "generation_plan_sha256": hashlib.sha256(Path(self.args.output).read_bytes()).hexdigest(),
                "feedback": {"problem": "detail_overload", "instruction": "Simplify the tiny veins", "keep": ["Both flower shapes"]}}
        review = self.write_json("review.json", {"schema_version": 1, "items": [item]})
        revised = self.compile(previous=self.args.output, review=review, result_sha256=output_sha, output=self.root / "rev.json")
        self.assertEqual(revised["revision"]["selected_output_sha256"], output_sha)
        self.assertIn("Simplify the tiny veins", revised["prompt"])
        for bad_items in ([dict(item, decision="keep")], [dict(item, photo_sha256="b" * 64)],
                          [dict(item, generation_plan_sha256="c" * 64)],
                          [dict(item, generation_plan_sha256=None)], [item, item]):
            with self.subTest(items=bad_items):
                self.write_json("review.json", {"schema_version": 1, "items": bad_items})
                with self.assertRaises(ValueError):
                    self.compile(previous=self.args.output, review=review, result_sha256=output_sha, output=self.root / "bad-rev.json")

    def test_references_are_verified_and_omitted_reference_is_not_claimed(self):
        reference = self.root / "reference.png"
        Image.new("RGB", (18, 27), "ivory").save(reference)
        paths = self.write_json("references.json", [str(reference)])
        plan = self.compile(references=paths)
        self.assertEqual(plan["references"], [planner.inspect_image(reference)])
        self.assertIn("1 separately supplied style references", plan["prompt"])
        absent = self.compile(output=self.root / "no-reference.json")
        self.assertEqual(absent["references"], [])
        self.assertNotIn("separately supplied style references", absent["prompt"])
        self.write_json("references.json", [str(self.root / "missing.png")])
        with self.assertRaises(OSError):
            self.compile(references=paths, output=self.root / "bad-reference.json")

    def test_invalid_feedback_and_orphaned_revision_arguments_are_rejected(self):
        self.compile()
        for feedback in ({"problem": "random", "instruction": "fix", "keep": []},
                         {"problem": "layout", "instruction": "", "keep": []},
                         {"problem": "layout", "instruction": "fix", "keep": "shape"},
                         {"problem": "layout", "instruction": "fix", "keep": [], "extra": 1}):
            path = self.write_json("feedback.json", feedback)
            with self.subTest(feedback=feedback), self.assertRaises(ValueError):
                self.compile(previous=self.args.output, feedback=path, output=self.root / "invalid.json")
        for kwargs in ({"previous": self.args.output}, {"feedback": path},
                       {"review": path}, {"result_sha256": "a" * 64},
                       {"previous": self.args.output, "review": path, "feedback": path, "result_sha256": "a" * 64}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.compile(output=self.root / "invalid.json", **kwargs)

    def test_same_style_revision_inherits_references_and_explicit_empty_or_new_style_clears(self):
        reference = self.root / "reference.png"
        Image.new("RGB", (18, 27), "ivory").save(reference)
        paths = self.write_json("references.json", [str(reference)])
        previous = self.compile(style="A", references=paths)
        feedback = self.write_json("feedback.json", {"problem": "color", "instruction": "Use less green", "keep": ["Both flower heads"]})
        revised = self.compile(previous=self.args.output, feedback=feedback, output=self.root / "inherited.json")
        self.assertEqual(revised["references"], previous["references"])
        self.assertIn("1 separately supplied style references", revised["prompt"])
        empty = self.write_json("empty-references.json", [])
        # An explicitly cleared list and a different style must not even require the old reference to exist.
        reference.unlink()
        cleared = self.compile(previous=self.args.output, feedback=feedback, references=empty, output=self.root / "cleared.json")
        changed_style = self.compile(previous=self.args.output, feedback=feedback, style="C", output=self.root / "changed-style.json")
        for plan in (cleared, changed_style):
            self.assertEqual(plan["references"], [])
            self.assertNotIn("separately supplied style references", plan["prompt"])
        replacement = self.root / "replacement.png"
        Image.new("RGB", (12, 20), "blue").save(replacement)
        self.write_json("references.json", [str(replacement)])
        replaced = self.compile(previous=self.args.output, feedback=feedback, references=paths, output=self.root / "replaced.json")
        self.assertEqual(replaced["references"], [planner.inspect_image(replacement)])

    def test_inherited_references_reject_changed_bytes_wrong_dimensions_and_missing_files(self):
        reference = self.root / "reference.png"
        Image.new("RGB", (18, 27), "ivory").save(reference)
        paths = self.write_json("references.json", [str(reference)])
        previous = self.compile(style="B", references=paths)
        feedback = self.write_json("feedback.json", {"problem": "color", "instruction": "Use less green", "keep": []})
        original = reference.read_bytes()
        Image.new("RGB", (18, 27), "blue").save(reference)
        with self.assertRaisesRegex(ValueError, "Inherited reference changed"):
            self.compile(previous=self.args.output, feedback=feedback, output=self.root / "invalid.json")
        reference.write_bytes(original)
        altered_record = copy.deepcopy(previous)
        altered_record["references"][0]["width"] += 1
        altered_path = self.write_json("altered-plan.json", altered_record)
        with self.assertRaisesRegex(ValueError, "oriented dimensions mismatch"):
            self.compile(previous=altered_path, feedback=feedback, output=self.root / "invalid.json")
        reference.unlink()
        with self.assertRaisesRegex(ValueError, "Inherited reference cannot be decoded"):
            self.compile(previous=self.args.output, feedback=feedback, output=self.root / "invalid.json")
        self.assertFalse((self.root / "invalid.json").exists())

    def test_empty_simplification_survives_json_roundtrip_and_revision(self):
        self.brief["simplify"] = []
        self.write_json("brief.json", self.brief)
        original = self.compile(style="C", strength="gentle")
        original_bytes = Path(self.args.output).read_bytes()
        stored = planner.validate_plan(planner.load_json(self.args.output))
        self.assertEqual(stored, original)
        self.assertEqual(stored["brief"]["simplify"], [])
        self.assertEqual(stored["checks"]["allowed_simplification"], [])
        self.assertIn("No content removal", stored["prompt"])
        feedback = self.write_json("feedback.json", {"problem": "color", "instruction": "Use less green", "keep": []})
        revised = self.compile(previous=self.args.output, feedback=feedback, output=self.root / "revision.json")
        self.assertEqual(revised["checks"]["allowed_simplification"], [])
        self.assertEqual(revised["checks"]["protected"], stored["checks"]["protected"])
        self.assertIn("No content removal", revised["prompt"])
        self.assertEqual(revised["revision"]["previous_prompt"], stored["prompt"])
        self.assertEqual(Path(self.args.output).read_bytes(), original_bytes)

    def test_invalid_inputs_fail_without_output(self):
        variants = []
        for key in self.brief:
            if key == "simplify":
                variants.append(dict(self.brief, simplify="remove background"))
                continue
            bad = dict(self.brief)
            bad[key] = [] if isinstance(bad[key], list) else ""
            variants.append(bad)
        variants += [dict(self.brief, subject_type="portrait"), dict(self.brief, unknown=True), dict(self.brief, protected="flowers")]
        missing = dict(self.brief)
        del missing["geometry"]
        variants.append(missing)
        for index, value in enumerate(variants):
            with self.subTest(case=index):
                self.write_json("brief.json", value)
                with self.assertRaises(ValueError):
                    self.compile()
                self.assertFalse(Path(self.args.output).exists())
        self.write_json("brief.json", self.brief)
        for series in ({}, {"style": "F"}, {"paper_color": "ivory"}, {"strength": 3}, {"palette": []}, {"seed": 12}):
            with self.subTest(series=series):
                path = self.write_json("bad-series.json", series)
                with self.assertRaises(ValueError):
                    self.compile(series=path)
        broken_image = self.root / "broken.png"
        broken_image.write_text("not an image")
        with self.assertRaises(OSError):
            self.compile(photo=broken_image)

    def test_rejects_overwrite_and_duplicate_json_keys(self):
        self.compile()
        before = Path(self.args.output).read_bytes()
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.compile(style="C")
        self.assertEqual(Path(self.args.output).read_bytes(), before)
        self.brief_path.write_text('{"subject":"first", "subject":"second"}')
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.compile(output=self.root / "new.json")

    def test_cli_reports_plan_and_does_not_claim_image_generation(self):
        result = subprocess.run([sys.executable, str(ROOT / "scripts/plan_artwork.py"),
                                 "--photo", str(self.photo), "--brief", str(self.brief_path),
                                 "--output", self.args.output, "--style", "E"], check=True, capture_output=True, text=True)
        response = json.loads(result.stdout)
        self.assertEqual(response["style"], "E")
        self.assertTrue(response["review_required"])
        self.assertNotIn("generated", response)
        plan = json.loads(Path(response["plan"]).read_text())
        self.assertEqual(plan["style"]["id"], "E")


if __name__ == "__main__":
    unittest.main()
