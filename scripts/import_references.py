#!/usr/bin/env python3
"""Import the named reference images from a local folder, verifying hashes."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def import_references(source, manifest_path, target):
    source, target = Path(source).expanduser().resolve(), Path(target).expanduser().resolve()
    rows = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    if not source.is_dir():
        raise ValueError("Source must be an existing local directory")
    prepared = []
    for row in rows:
        name = Path(row["file"]).name
        expected = row["sha256"]
        matches = [p for p in source.rglob(name) if p.is_file()
                   and hashlib.sha256(p.read_bytes()).hexdigest() == expected]
        if not matches:
            raise ValueError(f"Missing or changed reference: {name}")
        dest = target / name
        if dest.exists() and hashlib.sha256(dest.read_bytes()).hexdigest() != expected:
            raise ValueError(f"A different reference already exists: {dest}")
        prepared.append((matches[0], dest, expected))
    target.mkdir(parents=True, exist_ok=True)
    for src, dest, expected in prepared:
        if not dest.exists():
            with src.open("rb") as source_file, dest.open("xb") as target_file:
                shutil.copyfileobj(source_file, target_file)
        if hashlib.sha256(dest.read_bytes()).hexdigest() != expected:
            raise RuntimeError(f"Copy verification failed: {dest.name}")
    return {"references": len(prepared), "target": str(target), "hashes_verified": True}


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="Local folder containing the original references")
    parser.add_argument("--target", type=Path, default=root / "assets/reference-originals")
    args = parser.parse_args()
    try:
        result = import_references(args.source, root / "references/reference-manifest.json", args.target)
    except (ValueError, OSError, RuntimeError) as exc:
        parser.exit(1, f"ERROR: {exc}\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
