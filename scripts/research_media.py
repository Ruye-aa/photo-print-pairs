#!/usr/bin/env python3
"""Import already-saved research media and export a source-only public inventory.

This tool does not browse, download, take screenshots, or infer reuse rights.
Input JSON: {"schema_version": 1, "sources": [{"source_id": "note-id",
"url": "https://...", "title": "...", "author": "...", "media": [
{"capture_method": "screenshot", "page": 1, "local_file": "capture.png",
"failure_reason": "Original download unavailable"}]}]}.

Relative local_file paths resolve inside the manifest directory. Explicit
absolute local_file paths are also accepted. timestamp, when present, is a
nonnegative video position in seconds; it is not a publication date.
"""

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
from urllib.parse import urlsplit, urlunsplit

from PIL import Image, ImageOps, UnidentifiedImageError


METHODS = {"original_download", "screenshot", "video_frame", "video_download"}
SOURCE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}\Z")
IMAGE_EXTENSIONS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp",
                    "GIF": ".gif", "TIFF": ".tiff", "BMP": ".bmp",
                    "AVIF": ".avif"}


class MediaError(ValueError):
    """A stable error code safe to include in a public inventory."""


def canonical_url(value):
    """Remove query/fragment, including XHS signatures and tracking tokens."""
    if not isinstance(value, str) or any(ch.isspace() for ch in value):
        raise ValueError("Source URL must be an HTTP(S) URL without whitespace")
    parsed = urlsplit(value)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname:
        raise ValueError("Source URL must be an HTTP(S) URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Source URL must not contain credentials")
    host = parsed.hostname.lower()
    port = parsed.port
    netloc = f"[{host}]" if ":" in host else host
    if port is not None and (parsed.scheme, port) not in {("https", 443), ("http", 80)}:
        netloc += f":{port}"
    path = parsed.path or "/"
    if host in {"xiaohongshu.com", "www.xiaohongshu.com"}:
        match = re.fullmatch(r"/(?:search_result|explore|discovery/item)/([A-Za-z0-9_-]+)/?", path)
        if match:
            path = f"/explore/{match.group(1)}"
            netloc = "www.xiaohongshu.com"
    return urlunsplit((parsed.scheme, netloc, path, "", ""))


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def local_path(value, base):
    if not isinstance(value, str) or not value:
        raise MediaError("missing_local_file")
    path = Path(value).expanduser()
    if not path.is_absolute():
        if ".." in path.parts:
            raise MediaError("unsafe_relative_path")
        path = (base / path).resolve()
        if not path.is_relative_to(base):
            raise MediaError("unsafe_relative_path")
    else:
        path = path.resolve()
    if not path.is_file():
        raise MediaError("local_file_not_found")
    return path


def inspect_media(path, method):
    size = path.stat().st_size
    if not size:
        raise MediaError("empty_file")
    if method == "video_download":
        with path.open("rb") as stream:
            header = stream.read(32)
        if header[4:8] == b"ftyp":
            extension = ".mp4"
        elif header.startswith(b"\x1a\x45\xdf\xa3"):
            extension = ".webm"
        else:
            raise MediaError("unrecognized_video_container")
        dimensions = None
        verification = "container_signature_only_not_playback_verified"
    else:
        try:
            with Image.open(path) as image:
                extension = IMAGE_EXTENSIONS.get(image.format)
                image.verify()
            with Image.open(path) as image:
                image.load()
                dimensions = list(ImageOps.exif_transpose(image).size)
            if extension is None:
                raise MediaError("unsupported_image_format")
        except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
            if isinstance(exc, MediaError):
                raise
            raise MediaError("image_decode_failed") from exc
        verification = "image_decoded"
    return {"bytes": size, "sha256": digest(path), "dimensions": dimensions,
            "verification": verification}, extension


def validate_sources(document):
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise ValueError("Expected schema_version: 1")
    sources = document.get("sources")
    if not isinstance(sources, list):
        raise ValueError("sources must be an array")
    seen = set()
    prepared = []
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError("Every source must be an object")
        source_id = source.get("source_id")
        if not isinstance(source_id, str) or not SOURCE_ID.fullmatch(source_id):
            raise ValueError("source_id must contain only ASCII letters, digits, '_' or '-'")
        if source_id in seen:
            raise ValueError(f"Duplicate source_id: {source_id}")
        seen.add(source_id)
        for field in ("title", "author"):
            if not isinstance(source.get(field), str):
                raise ValueError(f"{source_id}: {field} must be a string")
        media = source.get("media", [])
        if not isinstance(media, list) or any(not isinstance(row, dict) for row in media):
            raise ValueError(f"{source_id}: media must be an array of objects")
        prepared.append({"source_id": source_id, "url": canonical_url(source.get("url")),
                         "title": source["title"], "author": source["author"], "media": media})
    return prepared


def safe_destination(root, source_id, name):
    directory = root / source_id
    # Reject links even if they currently point inside root: the archive layout
    # must remain an ordinary directory owned by this import.
    if directory.is_symlink():
        raise MediaError("unsafe_destination")
    directory.mkdir(exist_ok=True)
    destination = directory / name
    if destination.is_symlink() or not destination.resolve().is_relative_to(root):
        raise MediaError("unsafe_destination")
    return destination


def public_inventory(report):
    """Allowlist fields; never copy raw paths, signed media URLs, or error text."""
    sources = []
    keys = ("index", "capture_method", "page", "timestamp", "status", "error_code",
            "bytes", "sha256", "dimensions", "verification", "duplicate_of")
    for source in report["sources"]:
        sources.append({"source_id": source["source_id"], "url": canonical_url(source["url"]),
                        "title": source["title"], "author": source["author"],
                        "media": [{key: row[key] for key in keys if key in row}
                                  for row in source["media"]]})
    return {"schema_version": 1, "scope": "source_metadata_only",
            "rights": "Media retention does not establish permission to redistribute.",
            "summary": report["summary"], "sources": sources}


def import_media(document, manifest_directory, output):
    sources = validate_sources(document)
    base = Path(manifest_directory).expanduser().resolve()
    requested = Path(output).expanduser().absolute()
    if requested.is_symlink():
        raise ValueError("Output directory must not be a symlink")
    root = requested.resolve()
    root.mkdir(parents=True, exist_ok=True)
    report = {"schema_version": 1, "sources": [], "summary": {}}
    seen_hashes, counts, methods = {}, Counter(), Counter()
    for source in sources:
        result = {key: source[key] for key in ("source_id", "url", "title", "author")}
        result["media"] = []
        for index, item in enumerate(source["media"], 1):
            row = {"index": index}
            counts["media_entries"] += 1
            try:
                method = item.get("capture_method")
                if not isinstance(method, str) or method not in METHODS:
                    raise MediaError("invalid_capture_method")
                row["capture_method"] = method
                page = item.get("page")
                if page is not None:
                    if type(page) is not int or page < 1:
                        raise MediaError("invalid_page")
                    row["page"] = page
                timestamp = item.get("timestamp")
                if timestamp is not None:
                    if type(timestamp) not in (int, float) or not math.isfinite(timestamp) or timestamp < 0:
                        raise MediaError("invalid_timestamp")
                    row["timestamp"] = timestamp
                if isinstance(item.get("failure_reason"), str):
                    row["failure_reason"] = item["failure_reason"]
                path = local_path(item.get("local_file"), base)
                details, extension = inspect_media(path, method)
                destination = safe_destination(root, source["source_id"], f"{index:03d}_{method}{extension}")
                if destination.exists():
                    if not destination.is_file() or digest(destination) != details["sha256"]:
                        raise MediaError("destination_content_conflict")
                    counts["reused_files"] += 1
                else:
                    with path.open("rb") as source_stream, destination.open("xb") as target_stream:
                        shutil.copyfileobj(source_stream, target_stream)
                    if digest(destination) != details["sha256"]:
                        raise MediaError("copy_verification_failed")
                    counts["copied_files"] += 1
                row.update(details)
                row.update({"status": "saved", "local_file": str(destination.relative_to(root))})
                identity = f"{source['source_id']}:{index}"
                if details["sha256"] in seen_hashes:
                    row["duplicate_of"] = seen_hashes[details["sha256"]]
                    counts["duplicate_entries"] += 1
                else:
                    seen_hashes[details["sha256"]] = identity
                counts["saved_entries"] += 1
                methods[method] += 1
            except (MediaError, OSError) as exc:
                row.update({"status": "failed", "error_code": str(exc) if isinstance(exc, MediaError) else "file_io_error"})
                counts["failed_entries"] += 1
            result["media"].append(row)
        report["sources"].append(result)
    report["summary"] = {"sources": len(sources), **{key: counts[key] for key in (
        "media_entries", "saved_entries", "failed_entries", "copied_files", "reused_files", "duplicate_entries")},
        "unique_files": len(seen_hashes), "saved_by_capture_method": dict(sorted(methods.items()))}
    return report


def write_json_preserving(path, document):
    """Reuse identical reports; save a new numbered version on a conflict."""
    path = Path(path).expanduser().absolute()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    version = 1
    while True:
        candidate = path if version == 1 else path.with_name(f"{path.stem}_v{version}{path.suffix}")
        if candidate.is_symlink():
            raise ValueError("Report destination must not be a symlink")
        try:
            with candidate.open("xb") as stream:
                stream.write(data)
            return candidate
        except FileExistsError:
            if candidate.is_file() and candidate.read_bytes() == data:
                return candidate
            version += 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "work/research-media")
    parser.add_argument("--public-export", type=Path, help="Optional source-only JSON; never copies raw media")
    args = parser.parse_args()
    try:
        manifest = args.manifest.expanduser().resolve()
        document = json.loads(manifest.read_text(encoding="utf-8"))
        report = import_media(document, manifest.parent, args.output)
        report_path = write_json_preserving(args.output / "manifest.json", report)
        result = {"summary": report["summary"], "local_manifest": str(report_path)}
        if args.public_export:
            result["public_export"] = str(write_json_preserving(args.public_export, public_inventory(report)))
    except (ValueError, OSError) as exc:
        parser.exit(2, f"ERROR: {exc}\n")
    print(json.dumps(result, ensure_ascii=False))
    # Partial success is persisted, but must not look like complete collection.
    return 1 if report["summary"]["failed_entries"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
