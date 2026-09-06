#!/usr/bin/env python3
"""Compile a photo brief into a reproducible generation plan; no images are generated."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
SUBJECT_TYPES = {"landscape", "architecture", "botanical", "water", "object", "food", "animals", "street"}
STRENGTHS = {"gentle", "balanced", "bold"}
PROBLEMS = {"missing_subject", "detail_overload", "style_mismatch", "layout", "text", "color"}
BRIEF_REQUIRED = {"subject_type", "subject", "protected", "simplify", "geometry", "palette", "composition"}
PLAN_KEYS = {"schema_version", "source", "style", "strength", "brief", "series", "revision", "references", "prompt", "checks"}
HEX_COLOR = re.compile(r"#[0-9a-fA-F]{6}\Z")
HASH = re.compile(r"[0-9a-f]{64}\Z")


def object_fields(value, required, optional=(), label="object"):
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    missing = set(required) - set(value)
    unknown = set(value) - set(required) - set(optional)
    if missing:
        raise ValueError(f"{label} is missing: {', '.join(sorted(missing))}")
    if unknown:
        raise ValueError(f"{label} has unknown fields: {', '.join(sorted(unknown))}")


def string(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


def strings(value, label, allow_empty=False):
    if not isinstance(value, list) or (not value and not allow_empty):
        raise ValueError(f"{label} must be a {'possibly empty ' if allow_empty else 'non-empty '}string array")
    return [string(item, f"{label}[{index}]") for index, item in enumerate(value)]


def choice(value, allowed, label):
    if not isinstance(value, str) or value not in allowed:
        raise ValueError(f"{label} must be one of {', '.join(sorted(allowed))}")
    return value


def sha(value, label):
    if not isinstance(value, str) or not HASH.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return value


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON field: {key}")
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError(f"Invalid JSON number: {value}")


def load_json(path):
    return json.loads(Path(path).expanduser().read_text(encoding="utf-8"),
                      object_pairs_hook=unique_keys, parse_constant=reject_constant)


def validate_brief(value):
    object_fields(value, BRIEF_REQUIRED, {"flow"}, "brief")
    result = {key: strings(value[key], f"brief.{key}", allow_empty=(key == "simplify"))
              for key in ("protected", "simplify", "geometry", "palette")}
    result.update({key: string(value[key], f"brief.{key}") for key in ("subject", "composition")})
    result["subject_type"] = choice(value["subject_type"], SUBJECT_TYPES, "brief.subject_type")
    if "flow" in value:
        result["flow"] = string(value["flow"], "brief.flow")
    return result


def validate_series(value):
    object_fields(value, (), {"style", "strength", "palette", "paper_color"}, "series")
    if not value:
        raise ValueError("series must contain at least one preference")
    result = dict(value)
    if "style" in result:
        choice(result["style"], set("ABCDE") | {"auto"}, "series.style")
    if "strength" in result:
        choice(result["strength"], STRENGTHS, "series.strength")
    if "palette" in result:
        result["palette"] = strings(result["palette"], "series.palette")
    if "paper_color" in result:
        if not isinstance(result["paper_color"], str) or not HEX_COLOR.fullmatch(result["paper_color"]):
            raise ValueError("series.paper_color must use #RRGGBB")
        result["paper_color"] = result["paper_color"].upper()
    return result


def validate_feedback(value):
    object_fields(value, {"problem", "instruction", "keep"}, label="feedback")
    return {"problem": choice(value["problem"], PROBLEMS, "feedback.problem"),
            "instruction": string(value["instruction"], "feedback.instruction"),
            "keep": strings(value["keep"], "feedback.keep", allow_empty=True)}


def inspect_image(path):
    path = Path(path).expanduser().resolve()
    payload = path.read_bytes()
    with Image.open(io.BytesIO(payload)) as raw:
        oriented = ImageOps.exif_transpose(raw)
        oriented.load()
        width, height = oriented.size
    return {"path": str(path), "sha256": hashlib.sha256(payload).hexdigest(),
            "width": width, "height": height}


def validate_image_record(value, label):
    object_fields(value, {"path", "sha256", "width", "height"}, label=label)
    string(value["path"], f"{label}.path")
    sha(value["sha256"], f"{label}.sha256")
    for key in ("width", "height"):
        if type(value[key]) is not int or value[key] <= 0:
            raise ValueError(f"{label}.{key} must be a positive integer")


def load_recipes():
    catalog = load_json(ROOT / "references/style-recipes.json")
    object_fields(catalog, {"schema_version", "styles"}, label="style catalog")
    if type(catalog["schema_version"]) is not int or catalog["schema_version"] != 1:
        raise ValueError("Unsupported style catalog schema_version")
    object_fields(catalog["styles"], set("ABCDE"), label="styles")
    for key, value in catalog["styles"].items():
        validate_style(dict(value, id=key))
    return catalog["styles"]


def validate_style(value):
    object_fields(value, {"id", "name", "material", "rules", "avoid"}, {"paper_color"}, label="style")
    choice(value["id"], set("ABCDE"), "style.id")
    for key in ("name", "material"):
        string(value[key], f"style.{key}")
    for key in ("rules", "avoid"):
        strings(value[key], f"style.{key}")
    if "paper_color" in value:
        if not isinstance(value["paper_color"], str) or not HEX_COLOR.fullmatch(value["paper_color"]):
            raise ValueError("style.paper_color must use #RRGGBB")


def validate_revision(value):
    if value is None:
        return
    object_fields(value, {"previous_plan", "previous_prompt", "problem", "instruction", "keep", "selected_output_sha256"}, label="revision")
    object_fields(value["previous_plan"], {"path", "sha256"}, label="revision.previous_plan")
    string(value["previous_plan"]["path"], "revision.previous_plan.path")
    sha(value["previous_plan"]["sha256"], "revision.previous_plan.sha256")
    string(value["previous_prompt"], "revision.previous_prompt")
    validate_feedback({key: value[key] for key in ("problem", "instruction", "keep")})
    if value["selected_output_sha256"] is not None:
        sha(value["selected_output_sha256"], "revision.selected_output_sha256")


def validate_plan(value):
    object_fields(value, PLAN_KEYS, label="previous plan")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise ValueError("Unsupported plan schema_version")
    validate_image_record(value["source"], "source")
    validate_style(value["style"])
    choice(value["strength"], STRENGTHS, "strength")
    validate_brief(value["brief"])
    if value["series"] is not None:
        validate_series(value["series"])
    validate_revision(value["revision"])
    if not isinstance(value["references"], list):
        raise ValueError("references must be an array")
    for record in value["references"]:
        validate_image_record(record, "reference")
    string(value["prompt"], "previous plan.prompt")
    object_fields(value["checks"], {"protected", "geometry", "allowed_simplification", "style_rules", "forbidden", "review_required"}, label="checks")
    for key in ("protected", "geometry", "allowed_simplification", "style_rules", "forbidden"):
        strings(value["checks"][key], f"checks.{key}", allow_empty=(key == "allowed_simplification"))
    if value["checks"]["review_required"] is not True:
        raise ValueError("A generation plan must retain review_required=true")
    return value


def feedback_from_review(path, result_sha, source_sha, previous_sha):
    review = load_json(path)
    object_fields(review, {"schema_version", "items"}, label="review")
    if type(review["schema_version"]) is not int or review["schema_version"] != 1:
        raise ValueError("Unsupported review schema_version")
    if not isinstance(review["items"], list):
        raise ValueError("review.items must be an array")
    sha(result_sha, "result-sha256")
    matches = []
    for item in review["items"]:
        object_fields(item, {"output_sha256", "photo_sha256", "decision", "feedback"}, {"generation_plan_sha256"}, label="review item")
        sha(item["output_sha256"], "review.output_sha256")
        sha(item["photo_sha256"], "review.photo_sha256")
        choice(item["decision"], {"pending", "keep", "revise", "discard"}, "review.decision")
        if item.get("generation_plan_sha256") is not None:
            sha(item["generation_plan_sha256"], "review.generation_plan_sha256")
        if item["output_sha256"] == result_sha:
            matches.append(item)
    if len(matches) != 1:
        raise ValueError("result-sha256 must identify exactly one review item")
    item = matches[0]
    if item["decision"] != "revise":
        raise ValueError("Selected review item must have decision=revise")
    if item["photo_sha256"] != source_sha:
        raise ValueError("Selected review item belongs to another photo")
    if not item.get("generation_plan_sha256"):
        raise ValueError("Selected review item has no generation plan hash; inspect its history and use --feedback with the correct --previous plan")
    if item["generation_plan_sha256"] != previous_sha:
        raise ValueError("Selected review item was generated from a different previous plan (SHA-256 mismatch)")
    return validate_feedback(item["feedback"])


def make_prompt(source, brief, style, strength, palette, paper_color, references, feedback):
    lines = [
        "Create one standalone artwork from the supplied content photograph.",
        "Do not generate a photograph panel, comparison layout, caption area, or surrounding card.",
        f"Artwork aspect ratio: {source['width']}:{source['height']} after applying the photograph's EXIF orientation. Do not stretch the subject.",
        f"Subject: {brief['subject']}",
        "Preserve every listed visible subject, its count when specified, position, direction, and occlusion. Do not invent hidden detail.",
        "Protected content:\n" + "\n".join("- " + item for item in brief["protected"]),
        "Spatial relationships:\n" + "\n".join("- " + item for item in brief["geometry"]),
        "Permitted simplification only:\n" + ("\n".join("- " + item for item in brief["simplify"]) or "No content removal or shape merging is permitted; change the rendering medium only."),
        "Composition: " + brief["composition"],
        f"Use one rendering system throughout: {style['material']}.",
        "Style rules:\n" + "\n".join("- " + item for item in style["rules"]),
        "Palette: " + "; ".join(palette) + ".",
        f"Base paper color: {paper_color}. Keep this surface consistent in the empty areas.",
    ]
    strengths = {
        "gentle": "Keep more of the source's secondary shape distinctions while fully redrawing the image in the chosen style.",
        "balanced": "Merge the permitted minor detail into larger shapes while keeping the protected structure clear.",
        "bold": "Use the strongest shape reduction allowed by the brief and generous open space. Never trade away protected objects or geometry for abstraction.",
    }
    lines.append("Abstraction strength: " + strengths[strength])
    if style["id"] == "B":
        lines.append("Rubbing flow: " + brief.get("flow", "Follow secondary forms outward into neighboring empty paper; keep the principal silhouette legible.") )
    if references:
        lines.append(f"There are {len(references)} separately supplied style references. Use only their artwork areas to understand this selected style; exclude photo panels, reference subjects, lettering, and framing. The content photograph alone defines the depicted scene.")
    lines.append("Exclude: " + "; ".join(style["avoid"]) + ".")
    lines.append("No lettering, numbers, pseudo-text, signatures, logos, watermarks, extra objects, or decorative symbols. Leave paper empty where such marks might appear.")
    if feedback:
        corrections = {
            "missing_subject": "Restore the missing or altered protected content and check every listed object again, including small visible instances.",
            "detail_overload": "Reduce the identified secondary detail into larger forms without deleting a protected subject.",
            "style_mismatch": "Rebuild the rendering according to the selected style rules consistently throughout the artwork.",
            "layout": "Repair the identified placement, proportions, or empty-space balance while preserving the specified geometry and aspect ratio.",
            "text": "Remove all text-like marks, including small marks near edges, and recheck the entire composition for unintended changes.",
            "color": "Correct the specified ink or wash colors while retaining the intended contrast and protected forms.",
        }
        lines += ["Revision focus: " + corrections[feedback["problem"]],
                  "Requested correction: " + feedback["instruction"]]
        if feedback["keep"]:
            lines.append("Keep these satisfactory features from the previous candidate:\n" + "\n".join("- " + item for item in feedback["keep"]))
        lines.append("After the targeted correction, recheck all content and style constraints across the whole image.")
    return "\n\n".join(lines)


def compile_plan(args):
    output = Path(args.output).expanduser().resolve()
    if output.suffix.lower() != ".json":
        raise ValueError("Output must be a new .json file")
    if output.exists():
        raise ValueError("Output already exists; choose a new plan path")
    feedback_path = getattr(args, "feedback", None)
    review_path = getattr(args, "review", None)
    result_sha = getattr(args, "result_sha256", None)
    previous_path = getattr(args, "previous", None)
    if feedback_path and review_path:
        raise ValueError("Use either feedback or review, not both")
    if bool(review_path) != bool(result_sha):
        raise ValueError("review and result-sha256 must be used together")
    if bool(previous_path) != bool(feedback_path or review_path):
        raise ValueError("Revisions require previous and either feedback or review together")
    source = inspect_image(args.photo)
    brief = validate_brief(load_json(args.brief))
    recipes = load_recipes()
    previous = None
    previous_sha = None
    if previous_path:
        previous = validate_plan(load_json(previous_path))
        previous_sha = hashlib.sha256(Path(previous_path).expanduser().read_bytes()).hexdigest()
        if previous["source"]["sha256"] != source["sha256"]:
            raise ValueError("Previous plan belongs to another photo (SHA-256 mismatch)")
        if any(previous["source"][key] != source[key] for key in ("width", "height")):
            raise ValueError("Previous plan dimensions do not match the oriented photo")
    feedback = (validate_feedback(load_json(feedback_path)) if feedback_path else
                feedback_from_review(review_path, result_sha, source["sha256"], previous_sha) if review_path else None)
    series = dict(previous["series"] or {}) if previous else {}
    if getattr(args, "series", None):
        series.update(validate_series(load_json(args.series)))
    requested_style = getattr(args, "style", None)
    if requested_style is None:
        requested_style = series.get("style", previous["style"]["id"] if previous else "auto")
    choice(requested_style, set("ABCDE") | {"auto"}, "style")
    style_id = ("B" if brief["subject_type"] in {"botanical", "water"} else "A") if requested_style == "auto" else requested_style
    strength = getattr(args, "strength", None) or series.get("strength", previous["strength"] if previous else "balanced")
    choice(strength, STRENGTHS, "strength")
    palette = series.get("palette", brief["palette"])
    paper_color = series.get("paper_color", "#F4F0E8" if style_id == "C" else "#EEE8DA")
    if series:
        series.update(style=style_id, strength=strength)
    references = []
    if getattr(args, "references", None):
        paths = strings(load_json(args.references), "references", allow_empty=True)
        references = [inspect_image(path) for path in paths]
    elif previous and previous["style"]["id"] == style_id:
        for record in previous["references"]:
            try:
                current = inspect_image(record["path"])
            except (OSError, ValueError) as exc:
                raise ValueError(f"Inherited reference cannot be decoded: {record['path']}. Supply --references explicitly to replace or clear it.") from exc
            if any(current[key] != record[key] for key in ("sha256", "width", "height")):
                raise ValueError(f"Inherited reference changed: {record['path']} (SHA-256 or oriented dimensions mismatch). Supply --references explicitly to replace or clear it.")
            references.append(current)
    style = dict(recipes[style_id], id=style_id, paper_color=paper_color)
    revision = None
    if previous:
        previous_file = Path(previous_path).expanduser().resolve()
        revision = dict(feedback, previous_plan={"path": str(previous_file), "sha256": previous_sha},
                        previous_prompt=previous["prompt"], selected_output_sha256=result_sha)
    plan = {
        "schema_version": 1, "source": source, "style": style, "strength": strength,
        "brief": brief, "series": series or None, "revision": revision, "references": references,
        "prompt": make_prompt(source, brief, style, strength, palette, paper_color, references, feedback),
        "checks": {"protected": brief["protected"], "geometry": brief["geometry"],
                   "allowed_simplification": brief["simplify"], "style_rules": style["rules"],
                   "forbidden": style["avoid"] + ["text or watermark", "invented objects"],
                   "review_required": True},
    }
    validate_plan(plan)
    if hashlib.sha256(Path(source["path"]).read_bytes()).hexdigest() != source["sha256"]:
        raise ValueError("Photo changed while compiling the plan")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(plan, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--photo", required=True)
    parser.add_argument("--brief", required=True, help="JSON scene brief, based on inspecting the actual photograph")
    parser.add_argument("--output", required=True, help="New JSON plan path; existing files are rejected")
    parser.add_argument("--style", choices=["auto", "A", "B", "C", "D", "E"], help="Overrides series preference; auto chooses only A/B")
    parser.add_argument("--strength", choices=sorted(STRENGTHS), help="Overrides series preference")
    parser.add_argument("--series", help="JSON style/strength/palette/paper_color preferences")
    parser.add_argument("--references", help="JSON array of local reference image paths; same-style revisions inherit verified references unless explicitly replaced or cleared with []")
    feedback_group = parser.add_mutually_exclusive_group()
    feedback_group.add_argument("--feedback", help="JSON problem/instruction/keep revision request")
    feedback_group.add_argument("--review", help="Review JSON exported by the batch gallery")
    parser.add_argument("--result-sha256", help="Exact output SHA-256 selected from --review")
    parser.add_argument("--previous", help="Existing plan for this exact source photograph")
    args = parser.parse_args()
    try:
        plan = compile_plan(args)
        print(json.dumps({"plan": str(Path(args.output).expanduser().resolve()),
                          "style": plan["style"]["id"], "strength": plan["strength"],
                          "photo_sha256": plan["source"]["sha256"], "review_required": True}, ensure_ascii=False))
    except (ValueError, OSError, RuntimeError, Image.DecompressionBombError) as exc:
        parser.exit(1, f"ERROR: {exc}\n")


if __name__ == "__main__":
    main()
