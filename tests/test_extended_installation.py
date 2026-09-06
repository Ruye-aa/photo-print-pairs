import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ExtendedInstallationTests(unittest.TestCase):
    def test_installed_extended_entrypoints_and_catalog_work_outside_repo(self):
        with tempfile.TemporaryDirectory() as directory:
            scratch = Path(directory)
            target = scratch / "skills" / "photo-print-pairs"
            subprocess.run([
                sys.executable, str(ROOT / "scripts/install_skill.py"),
                "--target", str(target),
            ], check=True, capture_output=True, text=True, cwd=scratch)
            for relative in ("scripts/prepare_extended.py", "scripts/research_media.py",
                             "references/extended-styles.json"):
                self.assertEqual((target / relative).read_bytes(), (ROOT / relative).read_bytes())
            listed = subprocess.run([
                sys.executable, str(target / "scripts/prepare_extended.py"), "--list",
            ], check=True, capture_output=True, text=True, cwd=scratch)
            actual = {row["id"] for row in json.loads(listed.stdout)["styles"]}
            expected = set(json.loads((target / "references/extended-styles.json").read_text())["styles"])
            self.assertEqual(actual, expected)
            help_result = subprocess.run([
                sys.executable, str(target / "scripts/research_media.py"), "--help",
            ], check=True, capture_output=True, text=True, cwd=scratch)
            self.assertIn("usage:", help_result.stdout)
            for excluded in ("work", "examples", "tests", ".git"):
                self.assertFalse((target / excluded).exists())


if __name__ == "__main__":
    unittest.main()
