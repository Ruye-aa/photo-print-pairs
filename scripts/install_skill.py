#!/usr/bin/env python3
"""Install this skill without copying repository maintenance files."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

PAYLOAD = ("SKILL.md", "agents", "assets", "references", "scripts/compose_pair.py",
           "scripts/plan_artwork.py", "scripts/review_gallery.py",
           "scripts/prepare_extended.py", "scripts/research_media.py", "requirements.txt")


def file_map(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def install(source, target, replace=False):
    source = Path(source).resolve()
    target = Path(target).expanduser().absolute()
    if target.is_symlink():
        raise ValueError("Target is a symlink; choose a real skill directory")
    if target == source or target in source.parents or source in target.parents:
        raise ValueError("Install target must be separate from the source repository")
    if target.exists() and not target.is_dir():
        raise ValueError("Install target exists and is not a directory")
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".photo-print-pairs-", dir=target.parent))
    backup = None
    try:
        for relative in PAYLOAD:
            src, dst = source / relative, stage / relative
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"))
            else:
                shutil.copy2(src, dst)
        expected = file_map(stage)
        if target.exists():
            if file_map(target) == expected:
                return {"target": str(target), "status": "unchanged", "files": len(expected)}
            if not replace:
                raise ValueError("A different skill already exists; --replace preserves it as a backup")
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            backup_root = (target.parent.parent / "skill-backups" if target.parent.name == "skills"
                           else target.parent / ".skill-backups")
            backup_root.mkdir(parents=True, exist_ok=True)
            backup = backup_root / (target.name + "-" + stamp)
            target.rename(backup)
        try:
            stage.rename(target)
        except Exception:
            if backup is not None and not target.exists():
                backup.rename(target)
            raise
        if file_map(target) != expected:
            raise RuntimeError("Installed file verification failed")
        return {"target": str(target), "status": "installed", "files": len(expected),
                "backup": str(backup) if backup else None}
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def main():
    codex_root = Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex"))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, default=codex_root / "skills" / "photo-print-pairs")
    parser.add_argument("--replace", action="store_true", help="Keep the old directory as a backup before updating")
    args = parser.parse_args()
    try:
        result = install(Path(__file__).resolve().parents[1], args.target, args.replace)
    except (ValueError, OSError, RuntimeError) as exc:
        parser.exit(1, f"ERROR: {exc}\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
