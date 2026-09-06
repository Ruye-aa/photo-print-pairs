#!/usr/bin/env python3
"""Compose a source photo above generated artwork; never generate artwork here."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageChops, ImageColor, ImageOps


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_rgb(path):
    with Image.open(path) as raw:
        mode = raw.mode
        oriented = ImageOps.exif_transpose(raw)
        return oriented.convert("RGB"), mode


def rect(value):
    try:
        result = tuple(int(v) for v in value.split(","))
        if len(result) != 4:
            raise ValueError
        return result
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Use LEFT,TOP,RIGHT,BOTTOM integers") from exc


def valid_rect(box, size, name):
    l, t, r, b = box
    if not (0 <= l < r <= size[0] and 0 <= t < b <= size[1]):
        raise ValueError(f"{name} {box} is outside image size {size}")


def size_arg(value):
    try:
        w, h = (int(v) for v in value.lower().split("x"))
        if w < 1 or h < 2:
            raise ValueError
        return w, h
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Use positive WIDTHxHEIGHT; height >= 2") from exc


def contain_panel(im, size, background):
    fitted = ImageOps.contain(im, size, method=Image.Resampling.LANCZOS)
    x = (size[0] - fitted.width) // 2
    y = (size[1] - fitted.height) // 2
    panel = background.copy()
    panel.paste(fitted, (x, y))
    return panel, fitted, (x, y, x + fitted.width, y + fitted.height)


def same_pixels(a, b):
    return a.size == b.size and ImageChops.difference(a.convert("RGB"), b.convert("RGB")).getbbox() is None


def save_without_overwrite(im, requested):
    requested.parent.mkdir(parents=True, exist_ok=True)
    version = 1
    while True:
        out = requested if version == 1 else requested.with_name(f"{requested.stem}_v{version}.png")
        if out.exists():
            try:
                with Image.open(out) as old:
                    if old.format == "PNG" and same_pixels(old, im):
                        return out, True
            except (OSError, ValueError):
                pass
            version += 1
            continue
        try:
            with out.open("xb") as stream:
                im.save(stream, format="PNG", optimize=True)
            return out, False
        except FileExistsError:
            continue


def compose(args):
    photo_path = Path(args.photo).expanduser().resolve()
    art_path = Path(args.artwork).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    if output.suffix.lower() != ".png":
        raise ValueError("Output must be a lossless .png file")
    if output in (photo_path, art_path):
        raise ValueError("Output must differ from both input paths")
    if args.record and Path(args.record).expanduser().exists():
        raise ValueError("Explicit record already exists; choose a new path")
    photo_sha = digest(photo_path)
    art_sha = digest(art_path)
    photo, source_mode = load_rgb(photo_path)
    art, _ = load_rgb(art_path)
    plan_path = Path(args.plan).expanduser().resolve() if getattr(args, "plan", None) else None
    plan = None
    plan_sha = None
    if plan_path:
        plan_bytes = plan_path.read_bytes()
        plan_sha = hashlib.sha256(plan_bytes).hexdigest()
        plan = json.loads(plan_bytes)
        if not isinstance(plan, dict) or plan.get("schema_version") != 1:
            raise ValueError("Unsupported generation plan")
        source = plan.get("source")
        if not isinstance(source, dict) or source.get("sha256") != photo_sha:
            raise ValueError("Generation plan belongs to a different source photo")
        if (source.get("width"), source.get("height")) != photo.size:
            raise ValueError("Generation plan source dimensions differ")
        if not isinstance(plan.get("prompt"), str) or not plan["prompt"].strip():
            raise ValueError("Generation plan must contain its complete prompt")
        style = plan.get("style")
        if not isinstance(style, dict) or style.get("id") not in {"A", "B", "C", "D", "E"}:
            raise ValueError("Generation plan style is invalid")
    crop = args.art_crop or (0, 0, art.width, art.height)
    valid_rect(crop, art.size, "art-crop")
    series = plan.get("series") if plan else None
    series_color = series.get("paper_color") if isinstance(series, dict) else None
    style_color = plan["style"].get("paper_color") if plan else None
    paper_color = args.paper_color or series_color or style_color or "#EEE8DA"
    color = ImageColor.getrgb(paper_color)
    if len(color) != 3:
        raise ValueError("Paper color must be opaque RGB")
    canvas_size = args.size or (photo.width, photo.height * 2)
    w, total_h = canvas_size
    top_h = total_h // 2
    bottom_h = total_h - top_h
    if args.size:
        top, photo_fitted, top_box = contain_panel(photo, (w, top_h), Image.new("RGB", (w, top_h), color))
    else:
        top = photo.copy()
        photo_fitted = photo
        top_box = (0, 0, w, top_h)
    paper = Image.new("RGB", (w, bottom_h), color)
    if args.paper_sample:
        valid_rect(args.paper_sample, art.size, "paper-sample")
        paper = art.crop(args.paper_sample).resize((w, bottom_h), Image.Resampling.LANCZOS)
    bottom, _, art_box = contain_panel(art.crop(crop), (w, bottom_h), paper)
    combined = Image.new("RGB", canvas_size)
    combined.paste(top, (0, 0))
    combined.paste(bottom, (0, top_h))
    saved, reused = save_without_overwrite(combined, output)
    with Image.open(saved) as check:
        if check.size != canvas_size:
            raise RuntimeError("Saved dimensions differ")
        if not same_pixels(check.crop((0, 0, w, top_h)), top):
            raise RuntimeError("Top panel was altered while saving")
        if not same_pixels(check.crop(top_box), photo_fitted):
            raise RuntimeError("Photo pixels differ from intended fitted photo")
        source_pixels_equal = same_pixels(check.crop((0, 0, w, top_h)), photo)
    if digest(photo_path) != photo_sha or digest(art_path) != art_sha:
        raise RuntimeError("An input file changed during composition")
    if plan_path and digest(plan_path) != plan_sha:
        raise RuntimeError("Generation plan changed during composition")
    artwork_output = None
    artwork_reused = None
    if getattr(args, "export_artwork", False):
        artwork_output, artwork_reused = save_without_overwrite(
            bottom, saved.with_name(saved.stem + "_artwork.png"))
        with Image.open(artwork_output) as exported:
            if not same_pixels(exported, bottom):
                raise RuntimeError("Exported artwork differs from the lower panel")
    now = datetime.now(timezone.utc)
    record = {
        "created_at": now.isoformat(),
        "photo": str(photo_path),
        "artwork": str(art_path),
        "output": str(saved),
        "output_reused": reused,
        "photo_sha256": photo_sha,
        "artwork_sha256": art_sha,
        "output_sha256": digest(saved),
        "source_file_mode": source_mode,
        "pixel_comparison_space": "EXIF-oriented decoded RGB; not a color-profile accuracy test",
        "photo_size": list(photo.size),
        "generated_artwork_size": list(art.size),
        "output_size": list(canvas_size),
        "top_height": top_h,
        "bottom_height": bottom_h,
        "size_mode": "fixed_contain" if args.size else "native_photo",
        "photo_paste_box": list(top_box),
        "artwork_crop": list(crop),
        "artwork_paste_box_within_bottom": list(art_box),
        "paper_color": paper_color,
        "paper_sample": list(args.paper_sample) if args.paper_sample else None,
        "top_panel_verified": True,
        "photo_fitted_pixels_verified": True,
        "top_matches_oriented_source_rgb_pixels": source_pixels_equal,
        "input_files_unchanged": True,
        "generation_plan": plan,
        "generation_plan_sha256": plan_sha,
        "artwork_output": str(artwork_output) if artwork_output else None,
        "artwork_output_sha256": digest(artwork_output) if artwork_output else None,
        "artwork_output_reused": artwork_reused,
        "artwork_output_size": list(bottom.size) if artwork_output else None,
    }
    record_path = (Path(args.record).expanduser().resolve() if args.record
                   else saved.parent / ".records" / f"{saved.stem}_{now.strftime('%Y%m%dT%H%M%S%fZ')}.json")
    record_path.parent.mkdir(parents=True, exist_ok=True)
    with record_path.open("x", encoding="utf-8") as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2)
    return {"output": str(saved), "dimensions": list(canvas_size),
            "top_source_rgb_pixels_equal": source_pixels_equal,
                "reused": reused, "record": str(record_path),
                "artwork_output": str(artwork_output) if artwork_output else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--photo", required=True)
    parser.add_argument("--artwork", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--size", type=size_arg, help="Total composite WIDTHxHEIGHT; default source W by 2H")
    parser.add_argument("--art-crop", type=rect, help="Manually inspected blank-margin crop in oriented artwork pixels")
    parser.add_argument("--paper-color", help="Opaque paper color; defaults to plan series color or #EEE8DA")
    parser.add_argument("--paper-sample", type=rect, help="Manually inspected blank-paper rectangle from oriented artwork")
    parser.add_argument("--record", help="Optional new record path; default output/.records/")
    parser.add_argument("--plan", help="Generation plan from plan_artwork.py; source hash must match")
    parser.add_argument("--export-artwork", action="store_true", help="Also save the fitted lower panel as a separate PNG")
    args = parser.parse_args()
    try:
        print(json.dumps(compose(args), ensure_ascii=False))
    except (ValueError, OSError, RuntimeError) as exc:
        parser.exit(1, f"ERROR: {exc}\n")


if __name__ == "__main__":
    main()
