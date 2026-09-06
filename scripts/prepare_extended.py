#!/usr/bin/env python3
"""Prepare a source-bound prompt for a researched style; no images are generated."""
import argparse
import hashlib
import io
import json
from pathlib import Path

from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "references" / "extended-styles.json"
STYLE_REQUIRED = {"name", "category", "material", "rules", "avoid", "source_refs",
                  "validation_status", "generation_trials"}
CATEGORIES = {"illustration", "material", "composition", "layout", "color_grade"}


def nonempty(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


def strings(value, label, allow_empty=False):
    if not isinstance(value, list) or (not value and not allow_empty):
        raise ValueError(f"{label} must be a string array")
    return [nonempty(item, f"{label}[{index}]") for index, item in enumerate(value)]


def validate_style(style_id, value):
    nonempty(style_id, "style id")
    if not isinstance(value, dict):
        raise ValueError(f"Style {style_id} must be an object")
    missing = STYLE_REQUIRED - value.keys()
    if missing:
        raise ValueError(f"Style {style_id} is missing: {', '.join(sorted(missing))}")
    for field in ("name", "material", "validation_status"):
        nonempty(value[field], f"{style_id}.{field}")
    if not isinstance(value["category"], str) or value["category"] not in CATEGORIES:
        raise ValueError(f"Style {style_id} has an unsupported category")
    strings(value["rules"], f"{style_id}.rules")
    strings(value["avoid"], f"{style_id}.avoid")
    if not isinstance(value["generation_trials"], list):
        raise ValueError(f"{style_id}.generation_trials must be an array")
    for field in ("requires_composition_change", "requires_plain_background_reset", "requires_abstract_effect"):
        if field in value and type(value[field]) is not bool:
            raise ValueError(f"{style_id}.{field} must be a boolean")
    if "composition_mode" in value and (not isinstance(value["composition_mode"], str)
                                        or value["composition_mode"] not in {"photographic_cutout", "pixel_stretch"}):
        raise ValueError(f"{style_id}.composition_mode is unsupported")
    if "composition_mode" in value and value["category"] != "composition":
        raise ValueError(f"{style_id}: composition modes require category=composition")
    if value.get("requires_plain_background_reset") and value.get("composition_mode") != "photographic_cutout":
        raise ValueError(f"{style_id}: plain background reset requires a photographic cutout route")
    if value.get("requires_abstract_effect") and value.get("composition_mode") != "pixel_stretch":
        raise ValueError(f"{style_id}: abstract effects require a supported composition mode")
    refs = value["source_refs"]
    if not isinstance(refs, list) or not refs:
        raise ValueError(f"{style_id}.source_refs must be a non-empty array")
    for ref in refs:
        if not isinstance(ref, dict):
            raise ValueError(f"{style_id}.source_refs must contain objects")
        nonempty(ref.get("source_id"), "source_ref.source_id")
        url = nonempty(ref.get("url"), "source_ref.url")
        if not url.startswith("https://"):
            raise ValueError("source_ref.url must be an HTTPS source URL")
        pages = ref.get("pages")
        if not isinstance(pages, list) or any(type(p) is not int or p < 1 for p in pages):
            raise ValueError("source_ref.pages must contain positive one-based page numbers")
    return value


def load_catalog(path=None):
    path = Path(path) if path is not None else CATALOG_PATH
    payload = path.read_bytes()
    catalog = json.loads(payload)
    if not isinstance(catalog, dict) or type(catalog.get("schema_version")) is not int or catalog["schema_version"] != 1:
        raise ValueError("Unsupported extended style catalog schema_version")
    if not isinstance(catalog.get("styles"), dict) or not catalog["styles"]:
        raise ValueError("Extended style catalog must contain styles")
    for style_id, style in catalog["styles"].items():
        validate_style(style_id, style)
    return catalog, hashlib.sha256(payload).hexdigest()


def inspect_photo(path):
    path = Path(path).expanduser().resolve()
    payload = path.read_bytes()
    with Image.open(io.BytesIO(payload)) as raw:
        stored_size = list(raw.size)
        exif_orientation = raw.getexif().get(274, 1)
        oriented = ImageOps.exif_transpose(raw)
        oriented.load()
        width, height = oriented.size
    return {"path": str(path), "sha256": hashlib.sha256(payload).hexdigest(),
            "width": width, "height": height, "stored_dimensions": stored_size,
            "exif_orientation": exif_orientation,
            "orientation": "landscape" if width > height else "portrait" if height > width else "square",
            "dimension_space": "EXIF-oriented decoded image"}


def prepare(photo, style_id, subject, preserve=None, simplify=None,
            allow_recompose=False, catalog_path=None):
    subject = nonempty(subject, "subject")
    if type(allow_recompose) is not bool:
        raise ValueError("allow_recompose must be a boolean")
    preserve = strings(preserve if preserve is not None else [], "preserve", allow_empty=True)
    simplify = strings(simplify if simplify is not None else [], "simplify", allow_empty=True)
    catalog, catalog_sha = load_catalog(catalog_path)
    if not isinstance(style_id, str) or style_id not in catalog["styles"]:
        raise ValueError(f"Unknown extended style: {style_id}")
    style = catalog["styles"][style_id]
    requires_change = any(style.get(key, False) for key in
                          ("requires_composition_change", "requires_plain_background_reset", "requires_abstract_effect"))
    if requires_change and not allow_recompose:
        raise ValueError(f"Style {style_id} requires composition changes; pass --allow-recompose only when authorized")
    source = inspect_photo(photo)
    category = style["category"]
    category_task = {
        "layout": "Apply a layout treatment to the source photograph. Retain photographic rendering inside the layout.",
        "color_grade": "Apply a photographic color grade. Preserve geometry and existing source text; do not redraw the scene.",
        "illustration": "Redraw the source photo as an illustration using the selected visual rules.",
        "material": "Translate the existing source subjects into the selected physical material.",
        "composition": "Apply the selected composition treatment while retaining the existing source subjects.",
    }[category]
    mode = style.get("composition_mode")
    if mode == "photographic_cutout":
        category_task = "Make a photographic cutout collage using only subjects already present in the source photo."
    elif mode == "pixel_stretch":
        category_task = "Keep the source photographic and add exactly one abstract pixel-stretch ribbon sampled from its colors. Preserve the source scene geometry."
    composition_allowed = allow_recompose and requires_change
    plain_background_allowed = allow_recompose and style.get("requires_plain_background_reset", False)
    abstract_effect_allowed = allow_recompose and style.get("requires_abstract_effect", False)
    reposition_allowed = composition_allowed and mode == "photographic_cutout"
    constraints = {
        "add_objects": False, "add_text": False, "add_decorations": abstract_effect_allowed,
        "recomposition_authorized": allow_recompose,
        "allow_composition_change": composition_allowed,
        "allow_subject_reposition": reposition_allowed,
        "allow_background_replacement": plain_background_allowed,
        "background_replacement_scope": "plain_paper_color_only" if plain_background_allowed else "none",
        "allow_new_scene": False,
        "allow_abstract_effect": abstract_effect_allowed,
        "abstract_effect_limit": {"type": "pixel_stretch_ribbon", "count": 1} if abstract_effect_allowed else None,
        "preserve_subject_identity_and_count": True,
        "preserve_original_panel": True,
        "generate_effect_panel_only": True,
        "preserve": preserve,
        "simplify": simplify,
    }
    geometry = ("Composition changes are authorized for the effect panel only. Reposition only existing source elements, retaining their identity and count."
                if reposition_allowed else
                "Preserve the main subjects' count, relative placement, orientation, viewpoint, and identifying silhouette.")
    background_rule = ("A simple flat paper-colored background may replace the source background in this effect panel only. Do not introduce a new landscape, room, or other replacement scene."
                       if plain_background_allowed else
                       "Do not replace the source setting with a different scene. Only the style's stated material treatment and planned simplification are permitted.")
    decoration_rule = ("The only permitted added abstract element is exactly one pixel-stretch ribbon whose colors come from the source. No other decorations or physical props are allowed."
                       if abstract_effect_allowed else
                       "Do not add decorative symbols, accent lines, or other graphic ornaments.")
    prompt = [
        f"Create one standalone effect panel at {source['width']} x {source['height']} pixels, matching the EXIF-oriented source aspect ratio.",
        "Use the attached source photo as the content reference. Output the effect panel only; do not create a before/after pair, duplicate photo, comparison labels, or a surrounding page.",
        f"Selected route: {style_id} ({style['name']}); category: {category}.",
        category_task,
        f"Source content description: {subject}",
        "Keep these main subjects recognizable; do not omit, substitute, or add subjects.",
        geometry,
        "Do not introduce new physical objects, people, animals, lettering, captions, signatures, dates, logos, or a replacement scene from the style reference.",
        background_rule,
        decoration_rule,
        f"Material and rendering: {style['material']}",
        "Apply these route rules:",
        *[f"- {rule}" for rule in style["rules"]],
        "Required source details to preserve:",
        *([f"- {item}" for item in preserve] or ["- The main subjects and their identifying shapes and colors."]),
        "Permitted simplification in this plan:",
        *([f"- {item}" for item in simplify] or ["- Only the detail reduction inherent in the selected route; keep main subjects and their identifying details."]),
        "Avoid:",
        *[f"- {item}" for item in style["avoid"]],
        "The final deliverable will be composed locally: the unmodified, EXIF-oriented source photo above this effect panel, at source width by twice source height. Do not render that composition yourself.",
    ]
    width, height = source["width"], source["height"]
    return {
        "schema_version": 1,
        "plan_type": "extended_style_generation",
        "catalog": {"file": "references/extended-styles.json", "sha256": catalog_sha},
        "source": source,
        "style": {**style, "id": style_id},
        "brief": {"subject": subject, "preserve": preserve, "simplify": simplify},
        "constraints": constraints,
        "prompt": "\n".join(prompt),
        "source_refs": style["source_refs"],
        "review": {
            "reference_status": style["validation_status"],
            "generation_trials": style["generation_trials"],
            "this_plan_status": "not_generated",
            "review_required": True,
            "checks": ["Subject identity and count", "Requested preservation and simplification",
                       "Selected route material or layout/color-grade behavior",
                       "No unrequested objects, text, decorations, or scene replacement",
                       "Original upper panel RGB pixels and final dimensions"],
            "evidence_limits": style.get("evidence_limits", "Reference review does not establish generated output quality."),
        },
        "generation": {"tool": "image_gen", "performed": False,
                       "reference_image": source["path"], "effect_panel_dimensions": [width, height],
                       "note": "Pass this source photo and the complete prompt to image_gen. Dimensions are a request, not a verified result; inspect the returned image and its actual dimensions before composition."},
        "composition_plan": {
            "order": "original_top_effect_bottom", "output_dimensions": [width, 2 * height],
            "upper_panel_dimensions": [width, height], "lower_panel_dimensions": [width, height],
            "original_pixel_space": "EXIF-oriented decoded RGB",
            "script": "scripts/compose_pair.py",
            "arguments": ["--photo", source["path"], "--artwork", "<GENERATED_ARTWORK_PATH>",
                          "--output", "<PAIR_OUTPUT_PNG>"],
            "plan_binding": "Keep this plan alongside the output. compose_pair.py --plan currently accepts only the separate A-E plan format; omit --plan for this extended plan.",
        },
    }


def save_plan(plan, output):
    output = Path(output).expanduser().resolve()
    if output.suffix.lower() != ".json":
        raise ValueError("Output must be a .json file")
    if output == Path(plan["source"]["path"]):
        raise ValueError("Output must differ from the source photo")
    payload = (json.dumps(plan, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open("xb") as stream:
            stream.write(payload)
        reused = False
    except FileExistsError:
        if output.read_bytes() != payload:
            raise ValueError("Output already contains different content; choose a new path")
        reused = True
    return {"output": str(output), "reused": reused, "plan_type": plan["plan_type"],
            "style": plan["style"]["id"], "generation_performed": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="List available routes, categories, and review status")
    parser.add_argument("--photo", help="Source image path")
    parser.add_argument("--style", help="Style id from --list")
    parser.add_argument("--subject", help="Required description of the main subjects")
    parser.add_argument("--preserve", action="append", default=[], help="Source detail to keep; repeat as needed")
    parser.add_argument("--simplify", action="append", default=[], help="Detail permitted to simplify in this plan; repeat as needed")
    parser.add_argument("--output", help="New JSON plan path; identical content can be reused")
    parser.add_argument("--allow-recompose", action="store_true", help="Explicit authorization for composition changes within the effect panel")
    args = parser.parse_args()
    try:
        if args.list:
            if any((args.photo, args.style, args.subject, args.output, args.preserve, args.simplify, args.allow_recompose)):
                raise ValueError("Use --list alone, without generation-plan options")
            catalog, _ = load_catalog()
            result = {"styles": [{"id": key, "name": style["name"], "category": style["category"],
                                   "validation_status": style["validation_status"],
                                   "requires_composition_change": style.get("requires_composition_change", False)}
                                  for key, style in catalog["styles"].items()],
                      "deferred": catalog.get("deferred", [])}
        else:
            for key in ("photo", "style", "subject", "output"):
                if not getattr(args, key):
                    raise ValueError(f"--{key} is required when preparing a plan")
            plan = prepare(args.photo, args.style, args.subject, args.preserve,
                           args.simplify, args.allow_recompose)
            result = save_plan(plan, args.output)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError, TypeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
