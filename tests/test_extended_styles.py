import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "prepare_extended.py"
SPEC = importlib.util.spec_from_file_location("prepare_extended", SCRIPT)
planner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(planner)


class ExtendedStyleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.photo = self.root / "source.png"
        Image.new("RGB", (51, 29), "#537288").save(self.photo)

    def plan(self, style="crayon-vignette", **kwargs):
        return planner.prepare(self.photo, style, "湖边的两个人与一辆红色自行车", **kwargs)

    def cli(self, *arguments, script=SCRIPT, **kwargs):
        return subprocess.run([sys.executable, str(script), *arguments],
                              capture_output=True, text=True, **kwargs)

    def test_catalog_validates_required_fields_without_fixed_style_count(self):
        catalog, digest = planner.load_catalog()
        self.assertEqual(len(digest), 64)
        for style_id, style in catalog["styles"].items():
            with self.subTest(style=style_id):
                self.assertTrue(planner.STYLE_REQUIRED <= style.keys())
                planner.validate_style(style_id, style)
        candidate = dict(catalog["styles"]["crayon-vignette"])
        del candidate["source_refs"]
        with self.assertRaisesRegex(ValueError, "source_refs"):
            planner.validate_style("incomplete-future-style", candidate)

    def test_prompt_contains_complete_subject_and_repeated_requirements(self):
        plan = self.plan(preserve=["红色车架", "两个人的位置"], simplify=["远处草地", "细小石块"])
        for text in ["湖边的两个人与一辆红色自行车", "红色车架", "两个人的位置", "远处草地", "细小石块"]:
            self.assertIn(text, plan["prompt"])
        self.assertFalse(plan["constraints"]["add_objects"])
        self.assertFalse(plan["constraints"]["add_text"])
        self.assertFalse(plan["generation"]["performed"])
        self.assertEqual(plan["review"]["this_plan_status"], "not_generated")
        self.assertTrue(plan["review"]["review_required"])
        self.assertEqual(plan["composition_plan"]["output_dimensions"], [51, 58])
        self.assertEqual(plan["source"]["sha256"], hashlib.sha256(self.photo.read_bytes()).hexdigest())
        self.assertEqual(plan["source_refs"], plan["style"]["source_refs"])
        self.assertNotIn("--plan", plan["composition_plan"]["arguments"])

    def test_exif_orientation_sets_effect_and_pair_dimensions(self):
        self.photo = self.root / "rotated.jpg"
        raw = Image.new("RGB", (60, 20), "red")
        exif = raw.getexif()
        exif[274] = 6
        raw.save(self.photo, exif=exif)
        plan = self.plan()
        self.assertEqual(plan["source"]["stored_dimensions"], [60, 20])
        self.assertEqual((plan["source"]["width"], plan["source"]["height"]), (20, 60))
        self.assertEqual(plan["source"]["orientation"], "portrait")
        self.assertEqual(plan["generation"]["effect_panel_dimensions"], [20, 60])
        self.assertEqual(plan["composition_plan"]["output_dimensions"], [20, 120])
        self.assertIn("20 x 60", plan["prompt"])

    def test_recomposition_needs_explicit_authorization(self):
        with self.assertRaisesRegex(ValueError, "--allow-recompose"):
            self.plan("surreal-photo-collage")
        allowed = self.plan("surreal-photo-collage", allow_recompose=True)
        self.assertTrue(allowed["constraints"]["allow_composition_change"])
        self.assertFalse(allowed["constraints"]["add_objects"])
        self.assertIn("Composition changes are authorized", allowed["prompt"])

    def test_surreal_authorization_allows_plain_paper_but_no_new_scene(self):
        plan = self.plan("surreal-photo-collage", allow_recompose=True)
        constraints = plan["constraints"]
        self.assertTrue(constraints["allow_background_replacement"])
        self.assertEqual(constraints["background_replacement_scope"], "plain_paper_color_only")
        self.assertTrue(constraints["allow_subject_reposition"])
        self.assertFalse(constraints["allow_new_scene"])
        self.assertFalse(constraints["add_decorations"])
        self.assertIn("simple flat paper-colored background", plan["prompt"])

    def test_pixel_stretch_allows_one_abstract_ribbon_and_preserves_photo_geometry(self):
        with self.assertRaisesRegex(ValueError, "--allow-recompose"):
            self.plan("pixel-stretch")
        plan = self.plan("pixel-stretch", allow_recompose=True)
        constraints = plan["constraints"]
        self.assertTrue(constraints["allow_abstract_effect"])
        self.assertTrue(constraints["add_decorations"])
        self.assertEqual(constraints["abstract_effect_limit"], {"type": "pixel_stretch_ribbon", "count": 1})
        self.assertFalse(constraints["add_objects"])
        self.assertFalse(constraints["allow_subject_reposition"])
        self.assertFalse(constraints["allow_background_replacement"])
        self.assertIn("Preserve the source scene geometry", plan["prompt"])
        self.assertNotIn("Make a photographic cutout collage", plan["prompt"])
        self.assertNotIn("Do not add decorative symbols", plan["prompt"])

    def test_recomposition_flag_does_not_expand_unrelated_route_permissions(self):
        for style in ("crayon-vignette", "airy-film", "postage-stamp-layout"):
            with self.subTest(style=style):
                plan = self.plan(style, allow_recompose=True)
                constraints = plan["constraints"]
                self.assertFalse(constraints["allow_composition_change"])
                self.assertFalse(constraints["allow_abstract_effect"])
                self.assertFalse(constraints["allow_subject_reposition"])
                self.assertFalse(constraints["allow_background_replacement"])

    def test_layout_and_color_grade_are_not_mislabeled_as_illustration(self):
        for style, category, required in [
            ("postage-stamp-layout", "layout", "Retain photographic rendering"),
            ("airy-film", "color_grade", "do not redraw the scene"),
        ]:
            with self.subTest(style=style):
                plan = self.plan(style)
                self.assertEqual(plan["style"]["category"], category)
                self.assertIn(required, plan["prompt"])

    def test_unknown_deferred_or_empty_subject_is_rejected(self):
        for style in ["unknown", "distant-mountain-background"]:
            with self.subTest(style=style), self.assertRaisesRegex(ValueError, "Unknown extended style"):
                self.plan(style)
        with self.assertRaisesRegex(ValueError, "subject"):
            planner.prepare(self.photo, "crayon-vignette", "  ")

    def test_existing_different_plan_is_not_overwritten(self):
        output = self.root / "plan.json"
        first = planner.save_plan(self.plan(), output)
        original = output.read_bytes()
        self.assertFalse(first["reused"])
        self.assertTrue(planner.save_plan(self.plan(), output)["reused"])
        with self.assertRaisesRegex(ValueError, "different content"):
            planner.save_plan(self.plan(preserve=["different requirement"]), output)
        self.assertEqual(output.read_bytes(), original)

    def test_cli_missing_arguments_unknown_style_and_blank_subject_write_nothing(self):
        output = self.root / "plan.json"
        cases = [[], ["--photo", str(self.photo)],
                 ["--photo", str(self.photo), "--style", "unknown", "--subject", "cat", "--output", str(output)],
                 ["--photo", str(self.photo), "--style", "crayon-vignette", "--subject", " ", "--output", str(output)]]
        for arguments in cases:
            with self.subTest(arguments=arguments):
                result = self.cli(*arguments)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(output.exists())

    def test_cli_plan_repeated_options_and_list(self):
        listed = self.cli("--list", check=True)
        styles = {item["id"]: item for item in json.loads(listed.stdout)["styles"]}
        self.assertEqual(styles["airy-film"]["category"], "color_grade")
        output = self.root / "plan.json"
        self.cli("--photo", str(self.photo), "--style", "crayon-vignette", "--subject", "a red bicycle",
                 "--preserve", "red frame", "--preserve", "two wheels", "--simplify", "grass texture",
                 "--simplify", "cloud detail", "--output", str(output), check=True)
        plan = json.loads(output.read_text())
        self.assertEqual(plan["brief"]["preserve"], ["red frame", "two wheels"])
        self.assertEqual(plan["brief"]["simplify"], ["grass texture", "cloud detail"])
        self.assertIn("a red bicycle", plan["prompt"])

    def test_copied_skill_resolves_its_own_catalog_from_unrelated_cwd(self):
        installed = self.root / "installed" / "photo-print-pairs"
        (installed / "scripts").mkdir(parents=True)
        (installed / "references").mkdir()
        shutil.copy2(SCRIPT, installed / "scripts" / SCRIPT.name)
        catalog, _ = planner.load_catalog()
        # Adding a new valid route checks that routing does not hard-code current IDs.
        catalog["styles"]["installed-only-style"] = dict(catalog["styles"]["crayon-vignette"], name="Installed local route")
        (installed / "references" / "extended-styles.json").write_text(json.dumps(catalog), encoding="utf-8")
        copied = installed / "scripts" / SCRIPT.name
        listed = self.cli("--list", script=copied, cwd=self.root, check=True)
        self.assertIn("installed-only-style", {item["id"] for item in json.loads(listed.stdout)["styles"]})
        output = self.root / "installed-plan.json"
        self.cli("--photo", str(self.photo), "--style", "installed-only-style", "--subject", "a lake",
                 "--output", str(output), script=copied, cwd=self.root, check=True)
        self.assertEqual(json.loads(output.read_text())["style"]["name"], "Installed local route")


if __name__ == "__main__":
    unittest.main()
