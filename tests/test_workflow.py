import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from PIL import Image, ImageChops, ImageOps

ROOT = Path(__file__).resolve().parents[1]


def module(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / file)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


pair = module("compose_pair", "compose_pair.py")
installer = module("install_skill", "install_skill.py")
reference_importer = module("import_references", "import_references.py")


class CompositionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.photo = self.root / "photo.png"
        self.art = self.root / "art.png"
        im = Image.new("RGB", (64, 40))
        im.putdata([(x * 3, y * 5, (x + y) * 2) for y in range(40) for x in range(64)])
        im.save(self.photo)
        Image.new("RGB", (21, 37), "#778844").save(self.art)
        self.args = argparse.Namespace(
            photo=str(self.photo), artwork=str(self.art), output=str(self.root / "pair.png"),
            size=None, art_crop=None, paper_color="#EEE8DA", paper_sample=None, record=None)

    def test_native_keeps_every_source_pixel_and_input_files(self):
        before = (pair.digest(self.photo), pair.digest(self.art))
        result = pair.compose(self.args)
        with Image.open(result["output"]) as im, Image.open(self.photo) as photo:
            self.assertEqual(im.size, (64, 80))
            self.assertIsNone(ImageChops.difference(im.crop((0, 0, 64, 40)), photo).getbbox())
        self.assertEqual(before, (pair.digest(self.photo), pair.digest(self.art)))
        record = json.loads(Path(result["record"]).read_text())
        self.assertEqual(record["output_sha256"], pair.digest(result["output"]))
        self.assertTrue(record["top_matches_oriented_source_rgb_pixels"])

    def test_fixed_odd_size_uses_two_complete_panels(self):
        self.args.size = (77, 63)
        result = pair.compose(self.args)
        record = json.loads(Path(result["record"]).read_text())
        self.assertEqual(result["dimensions"], [77, 63])
        self.assertEqual((record["top_height"], record["bottom_height"]), (31, 32))
        self.assertTrue(record["photo_fitted_pixels_verified"])
        self.assertFalse(result["top_source_rgb_pixels_equal"])
        l, t, r, b = record["photo_paste_box"]
        self.assertLessEqual(r, 77)
        self.assertLessEqual(b, 31)
        self.assertAlmostEqual((r - l) / (b - t), 64 / 40, delta=0.04)

    def test_exif_orientation_precedes_size_selection(self):
        photo = Image.new("RGB", (40, 24), "red")
        exif = photo.getexif()
        exif[274] = 6
        path = self.root / "rotated.jpg"
        photo.save(path, exif=exif)
        self.args.photo = str(path)
        result = pair.compose(self.args)
        self.assertEqual(result["dimensions"], [24, 80])
        self.assertTrue(result["top_source_rgb_pixels_equal"])

    def test_repeat_reuses_png_without_adding_a_version(self):
        first = pair.compose(self.args)
        second = pair.compose(self.args)
        self.assertEqual(first["output"], second["output"])
        self.assertTrue(second["reused"])
        self.assertNotEqual(first["record"], second["record"])
        self.assertFalse((self.root / "pair_v2.png").exists())

    def test_conflicting_output_is_preserved(self):
        old = Image.new("RGB", (5, 5), "black")
        old.save(self.args.output)
        old_hash = pair.digest(self.args.output)
        result = pair.compose(self.args)
        self.assertEqual(Path(result["output"]).name, "pair_v2.png")
        self.assertEqual(pair.digest(self.args.output), old_hash)

    def test_invalid_crop_produces_no_output(self):
        self.args.art_crop = (0, 0, 1000, 40)
        with self.assertRaises(ValueError):
            pair.compose(self.args)
        self.assertFalse(Path(self.args.output).exists())

    def test_cannot_overwrite_either_input(self):
        for source in (self.photo, self.art):
            with self.subTest(source=source.name):
                self.args.output = str(source)
                before = pair.digest(source)
                with self.assertRaises(ValueError):
                    pair.compose(self.args)
                self.assertEqual(pair.digest(source), before)

    def test_cli_outputs_machine_readable_success(self):
        result = subprocess.run([
            sys.executable, str(ROOT / "scripts/compose_pair.py"),
            "--photo", str(self.photo), "--artwork", str(self.art),
            "--output", self.args.output,
        ], check=True, capture_output=True, text=True)
        self.assertEqual(json.loads(result.stdout)["dimensions"], [64, 80])


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.target = Path(self.temp.name) / "skills" / "photo-print-pairs"

    def test_install_contains_only_payload_and_repeat_is_unchanged(self):
        first = installer.install(ROOT, self.target)
        second = installer.install(ROOT, self.target)
        self.assertEqual(first["status"], "installed")
        self.assertEqual(second["status"], "unchanged")
        self.assertTrue((self.target / "SKILL.md").exists())
        self.assertTrue((self.target / "scripts/compose_pair.py").exists())
        self.assertFalse((self.target / "tests").exists())
        self.assertFalse((self.target / ".git").exists())
        self.assertFalse((self.target / "README.md").exists())

    def test_changed_install_requires_replace_and_preserves_backup(self):
        installer.install(ROOT, self.target)
        custom = self.target / "local-note.txt"
        custom.write_text("local customization")
        with self.assertRaises(ValueError):
            installer.install(ROOT, self.target)
        self.assertTrue(custom.exists())
        result = installer.install(ROOT, self.target, replace=True)
        backup = Path(result["backup"])
        self.assertEqual((backup / "local-note.txt").read_text(), "local customization")
        self.assertFalse(custom.exists())
        self.assertEqual(installer.install(ROOT, self.target)["status"], "unchanged")

    def test_install_rejects_source_and_ancestor_targets(self):
        for path in (ROOT, ROOT.parent):
            with self.subTest(target=str(path)), self.assertRaises(ValueError):
                installer.install(ROOT, path)


class ReferenceImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.target = self.root / "target"
        self.manifest = self.root / "manifest.json"
        self.rows = []
        for name, color in [("one.png", "red"), ("two.png", "blue")]:
            path = self.source / name
            Image.new("RGB", (8, 6), color).save(path)
            self.rows.append({"file": "assets/" + name, "sha256": pair.digest(path)})
        self.manifest.write_text(json.dumps(self.rows))

    def test_import_and_repeat_keep_exact_files(self):
        for _ in range(2):
            result = reference_importer.import_references(self.source, self.manifest, self.target)
            self.assertEqual(result["references"], 2)
        for row in self.rows:
            self.assertEqual(pair.digest(self.target / Path(row["file"]).name), row["sha256"])

    def test_missing_reference_writes_nothing(self):
        (self.source / "two.png").unlink()
        with self.assertRaises(ValueError):
            reference_importer.import_references(self.source, self.manifest, self.target)
        self.assertFalse(self.target.exists())

    def test_changed_target_is_not_overwritten(self):
        self.target.mkdir()
        conflict = self.target / "two.png"
        conflict.write_bytes(b"keep this file")
        with self.assertRaises(ValueError):
            reference_importer.import_references(self.source, self.manifest, self.target)
        self.assertEqual(conflict.read_bytes(), b"keep this file")
        self.assertFalse((self.target / "one.png").exists())


class ReferenceIntegrityTests(unittest.TestCase):
    def test_all_reference_images_match_manifest_and_decode(self):
        rows = json.loads((ROOT / "references/reference-manifest.json").read_text())
        self.assertEqual(len(rows), 13)
        self.assertEqual(len({r["file"] for r in rows}), 13)
        for row in rows:
            with self.subTest(reference=row["id"]):
                path = ROOT / row["file"]
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), row["sha256"])
                with Image.open(path) as im:
                    self.assertEqual(list(im.size), row["dimensions"])
                    im.load()


if __name__ == "__main__":
    unittest.main()
