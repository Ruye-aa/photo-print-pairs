#!/usr/bin/env python3
"""Build a self-contained, offline review page from verified composition records."""
import argparse
import base64
import hashlib
import html
import io
import json
from pathlib import Path
import re

from PIL import Image


SHA256 = re.compile(r"^[0-9a-f]{64}$")
DECISIONS = {"pending", "keep", "revise", "discard"}
PROBLEMS = {"", "missing_subject", "detail_overload", "style_mismatch", "layout", "text", "color"}


def image_url(data):
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii")


def read_item(record_path):
    """Verify stored output bytes; source-pixel equality remains a recorded claim."""
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"{record_path.name}: cannot read JSON: {exc}") from exc
    if not isinstance(record, dict):
        raise ValueError(f"{record_path.name}: expected a composition record object")
    for key in ("output_sha256", "photo_sha256"):
        if not isinstance(record.get(key), str) or not SHA256.fullmatch(record[key]):
            raise ValueError(f"{record_path.name}: missing or invalid {key}")
    plan_sha = record.get("generation_plan_sha256")
    if plan_sha is not None and (not isinstance(plan_sha, str) or not SHA256.fullmatch(plan_sha)):
        raise ValueError(f"{record_path.name}: invalid generation_plan_sha256")
    size = record.get("output_size")
    if not (isinstance(size, list) and len(size) == 2
            and all(type(value) is int and value > 0 for value in size)):
        raise ValueError(f"{record_path.name}: invalid output_size")
    if size[1] < 2:
        raise ValueError(f"{record_path.name}: output_size cannot contain two panels")
    if type(record.get("top_matches_oriented_source_rgb_pixels")) is not bool:
        raise ValueError(f"{record_path.name}: missing boolean source-pixel comparison")
    output_name = record.get("output")
    if not isinstance(output_name, str) or not output_name.strip():
        raise ValueError(f"{record_path.name}: missing output path")
    output = Path(output_name).expanduser()
    if not output.is_absolute():
        output = record_path.parent / output
    if output.suffix.lower() != ".png":
        raise ValueError(f"{record_path.name}: output must be a PNG file")
    try:
        data = output.read_bytes()
        if hashlib.sha256(data).hexdigest() != record["output_sha256"]:
            raise ValueError("output_sha256 mismatch")
        with Image.open(io.BytesIO(data)) as source:
            if source.format != "PNG":
                raise ValueError("output is not a PNG image")
            if list(source.size) != size:
                raise ValueError("output_size mismatch")
            if getattr(source, "n_frames", 1) != 1:
                raise ValueError("animated PNG is not a composition output")
            source.load()
            thumbnail = source.convert("RGB")
            thumbnail.thumbnail((640, 800), Image.Resampling.LANCZOS)
            buffer = io.BytesIO()
            thumbnail.save(buffer, format="PNG", optimize=True)
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise ValueError(f"{record_path.name}: {exc}") from exc
    plan = record.get("generation_plan")
    style_name = "未附风格记录"
    if plan is not None:
        if not isinstance(plan, dict):
            raise ValueError(f"{record_path.name}: generation_plan must be an object")
        style = plan.get("style")
        if style is not None:
            if not isinstance(style, dict):
                raise ValueError(f"{record_path.name}: generation_plan.style must be an object")
            for key in ("id", "name"):
                if key in style and not isinstance(style[key], str):
                    raise ValueError(f"{record_path.name}: style.{key} must be text")
            style_name = style.get("name") or style.get("id") or style_name
    return {
        "name": output.name,
        "output_sha256": record["output_sha256"],
        "photo_sha256": record["photo_sha256"],
        "generation_plan_sha256": plan_sha,
        "output_size": size,
        "source_pixels_equal_recorded": record["top_matches_oriented_source_rgb_pixels"],
        "style_name": style_name,
        "thumbnail": image_url(buffer.getvalue()),
        "image": image_url(data),
    }


def read_items(records):
    records = Path(records).expanduser().resolve()
    if not records.is_dir():
        raise ValueError("--records must be an existing directory")
    paths = sorted(records.glob("*.json"))
    if not paths:
        raise ValueError("No composition records (*.json) found; subdirectories are not scanned")
    items = []
    by_hash = {}
    duplicates = 0
    for path in paths:
        item = read_item(path)
        previous = by_hash.get(item["output_sha256"])
        if previous:
            for key in ("photo_sha256", "source_pixels_equal_recorded"):
                if previous[key] != item[key]:
                    raise ValueError(f"{path.name}: duplicate output has a conflicting {key}")
            old_plan = previous["generation_plan_sha256"]
            new_plan = item["generation_plan_sha256"]
            if old_plan and new_plan and old_plan != new_plan:
                raise ValueError(f"{path.name}: duplicate output has a conflicting generation_plan_sha256")
            if not old_plan and new_plan:
                previous.update(item)
            duplicates += 1
            continue
        by_hash[item["output_sha256"]] = item
        items.append(item)
    return items, duplicates


def unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def import_review(path, items):
    """Seed exact output/source/plan identities; never inherit votes across versions."""
    path = Path(path).expanduser().resolve()
    try:
        raw = path.read_bytes()
        review = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_json_object)
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError(f"{path.name}: cannot read review JSON: {exc}") from exc
    if not isinstance(review, dict) or type(review.get("schema_version")) is not int or review["schema_version"] != 1:
        raise ValueError(f"{path.name}: review schema_version must be 1")
    if not isinstance(review.get("items"), list):
        raise ValueError(f"{path.name}: review items must be an array")
    previous = {}
    for index, entry in enumerate(review["items"]):
        location = f"{path.name}: items[{index}]"
        if not isinstance(entry, dict):
            raise ValueError(f"{location} must be an object")
        for key in ("output_sha256", "photo_sha256"):
            if not isinstance(entry.get(key), str) or not SHA256.fullmatch(entry[key]):
                raise ValueError(f"{location}: missing or invalid {key}")
        if "generation_plan_sha256" not in entry:
            raise ValueError(f"{location}: missing generation_plan_sha256 (use null for an unlinked record)")
        plan_sha = entry["generation_plan_sha256"]
        if plan_sha is not None and (not isinstance(plan_sha, str) or not SHA256.fullmatch(plan_sha)):
            raise ValueError(f"{location}: invalid generation_plan_sha256")
        decision = entry.get("decision")
        if not isinstance(decision, str) or decision not in DECISIONS:
            raise ValueError(f"{location}: invalid decision")
        feedback = entry.get("feedback")
        if not isinstance(feedback, dict):
            raise ValueError(f"{location}: feedback must be an object")
        problem, instruction, keep = (feedback.get(key) for key in ("problem", "instruction", "keep"))
        if not isinstance(problem, str) or problem not in PROBLEMS:
            raise ValueError(f"{location}: invalid feedback.problem")
        if not isinstance(instruction, str):
            raise ValueError(f"{location}: feedback.instruction must be text")
        if not isinstance(keep, list) or not all(isinstance(value, str) for value in keep):
            raise ValueError(f"{location}: feedback.keep must be an array of strings")
        if len(instruction) > 2000 or len("\n".join(keep)) > 2000:
            raise ValueError(f"{location}: feedback text exceeds the page's 2000-character field limit")
        if decision == "revise" and (not problem or not instruction.strip()):
            raise ValueError(f"{location}: revise requires a problem and instruction")
        if entry["output_sha256"] in previous:
            raise ValueError(f"{location}: duplicate output_sha256 in review")
        previous[entry["output_sha256"]] = {
            "photo_sha256": entry["photo_sha256"], "generation_plan_sha256": plan_sha,
            "decision": decision,
            "feedback": {"problem": problem, "instruction": instruction, "keep": keep},
        }
    imported = 0
    for item in items:
        old = previous.get(item["output_sha256"])
        if old is None:
            continue
        for key in ("photo_sha256", "generation_plan_sha256"):
            if old[key] != item[key]:
                raise ValueError(f"{path.name}: {item['name']}: review {key} does not match composition record")
        item["initial_review"] = {"decision": old["decision"], "feedback": old["feedback"]}
        imported += 1
    return hashlib.sha256(raw).hexdigest(), imported, len(previous) - imported


def safe_json(value):
    """Keep JSON data inert even when a filename contains an HTML closing tag."""
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            .replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
            .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


HTML = r'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer">
<title>__TITLE__</title>
<style>
:root{color-scheme:light;--paper:#f4f0e7;--ink:#263931;--line:#d5d9cf;--accent:#305b45}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.65 system-ui,sans-serif}
header,main{max-width:1440px;margin:auto;padding:26px 28px}header{padding-bottom:0}h1{font-size:clamp(1.65rem,4vw,2.4rem);margin:0 0 12px;font-weight:650;letter-spacing:-.03em}p{margin:8px 0}.muted{color:#536359;font-size:.91rem}
.toolbar{display:flex;gap:16px;align-items:center;flex-wrap:wrap;margin:20px 0}.toolbar label{display:flex;align-items:center;gap:8px}
button,select,textarea{font:inherit}button,select{min-height:44px}button{cursor:pointer;border:1px solid var(--line);border-radius:7px;padding:8px 15px;background:white;color:var(--ink)}button.primary{background:var(--accent);color:white;border-color:var(--accent)}button:hover{filter:brightness(.95)}:focus-visible{outline:3px solid #be7026;outline-offset:3px}select,textarea{background:#fff;color:var(--ink);border:1px solid #b5bdb3;border-radius:6px;padding:8px;width:100%}.toolbar select{width:auto}textarea{min-height:76px;resize:vertical}
#gallery{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,340px),1fr));gap:24px}.card{border:1px solid var(--line);background:#fffdf8;border-radius:10px;overflow:hidden;align-self:start}.preview{padding:0;border:0;border-radius:0;background:#e7e2d8;width:100%;display:block}.preview img{display:block;width:100%;height:350px;object-fit:contain}.body{padding:18px}.body h2{font-size:1.05rem;overflow-wrap:anywhere;margin:0 0 6px}.meta{font-size:.84rem;color:#526259}.row{margin-top:13px}.row label{display:block;font-size:.9rem;font-weight:600;margin-bottom:5px}.row small{display:block;color:#526259;margin:5px 0}.card[data-decision="keep"]{border:2px solid #51805c}.card[data-decision="revise"]{border:2px solid #b47b39}.card[data-decision="discard"]{border-style:dashed}.error{color:#973a22;font-weight:600}.card[hidden]{display:none}#notice:empty{display:none}#notice{padding:10px 14px;border-left:4px solid #a65528;background:#fff7df}#summary{font-variant-numeric:tabular-nums}
dialog{padding:0;border:0;width:100vw;max-width:none;height:100dvh;max-height:none;background:#1a211deb;color:#fff}dialog::backdrop{background:#152019}.viewer-head{position:sticky;top:0;display:flex;gap:14px;align-items:center;justify-content:space-between;padding:12px 18px;background:#16231feb;z-index:1}#viewer-title{overflow-wrap:anywhere}#large-image{display:block;max-width:100%;max-height:calc(100dvh - 88px);width:auto;height:auto;margin:12px auto;object-fit:contain}dialog.zoomed #large-image{max-width:none;max-height:none}dialog.zoomed{overflow:auto}.viewer-actions{display:flex;gap:8px;flex-shrink:0}
@media(max-width:600px){header,main{padding:20px 14px}.toolbar{align-items:stretch;gap:12px}.toolbar label{flex:1}.toolbar button{flex:1}.preview img{height:320px}.viewer-head{flex-wrap:wrap}.viewer-actions{margin-left:auto}}
</style></head><body>
<header><h1>__TITLE__</h1>
<p>逐张看图，选择保留、修改或放弃。新结果初始为“待评价”；已有评价可从导入文件或当前浏览器恢复。这里记录你的选择，没有自动美学评分。</p>
<p class="muted">已核验每张 PNG 的文件哈希和尺寸。这些工程检查不代表艺术效果合格；原图像素信息来自生成记录。点击图片查看大图，Esc 关闭。</p>
<div class="toolbar"><button type="button" class="primary" id="export">导出 review.json</button><label for="filter">查看<select id="filter"><option value="all">全部作品</option><option value="pending">待评价</option><option value="keep">保留</option><option value="revise">修改</option><option value="discard">放弃</option></select></label><span id="summary" role="status" aria-live="polite"></span></div>
<p id="storage" class="muted">选择仅保存在当前浏览器，请导出文件留存。此页面可离线打开。</p>
<p id="notice" role="alert" tabindex="-1"></p></header>
<main><div id="gallery"></div><noscript>请启用 JavaScript 以查看图片并导出评价。此页面无需联网。</noscript></main>
<dialog id="viewer" aria-labelledby="viewer-title"><div class="viewer-head"><span id="viewer-title"></span><div class="viewer-actions"><button type="button" id="zoom">原始尺寸</button><button type="button" id="close">关闭（Esc）</button></div></div><img id="large-image" alt=""></dialog>
<script type="application/json" id="gallery-data">__DATA__</script>
<script>
'use strict';
const data = JSON.parse(document.getElementById('gallery-data').textContent);
const decisions = {pending:'待评价',keep:'保留',revise:'修改',discard:'放弃'};
const problems = {'':'未选择',missing_subject:'主体遗漏或变化',detail_overload:'细节过多',style_mismatch:'风格不符',layout:'构图与留白',text:'多余文字',color:'颜色不合适'};
const states = new Map(), controls = new Map();
const storageKey = 'photo-print-pairs-review-v1-' + data.batch_id;
const notice = document.getElementById('notice');
let stored = {}, storageAvailable = true;
function storageFailed(){storageAvailable=false;document.getElementById('storage').textContent='当前浏览器无法保存选择，关闭页面后会丢失；仍可导出 review.json 留存。此页面可离线打开。';}
try{const raw=localStorage.getItem(storageKey);if(raw){const parsed=JSON.parse(raw);if(parsed && typeof parsed==='object' && !Array.isArray(parsed)) stored=parsed;}}catch(error){storageFailed();}
function text(value){return typeof value==='string'?value:'';}
function restore(item){const raw=stored[item.output_sha256]||item.initial_review||{}, feedback=raw.feedback||{};const keep=Array.isArray(feedback.keep)?feedback.keep.filter(value=>typeof value==='string').join('\n'):text(feedback.keep);return {decision:Object.prototype.hasOwnProperty.call(decisions,raw.decision)?raw.decision:'pending',feedback:{problem:Object.prototype.hasOwnProperty.call(problems,feedback.problem)?feedback.problem:'',instruction:text(feedback.instruction).slice(0,2000),keep:keep.slice(0,2000)}};}
function persist(){if(!storageAvailable)return;try{localStorage.setItem(storageKey,JSON.stringify(Object.fromEntries(states)));}catch(error){storageFailed();}}
function element(tag,className,content){const el=document.createElement(tag);if(className)el.className=className;if(content!==undefined)el.textContent=content;return el;}
function select(options,id){const el=element('select');el.id=id;for(const [value,label]of Object.entries(options)){const opt=element('option',null,label);opt.value=value;el.append(opt);}return el;}
function field(label,control,help){const row=element('div','row');const caption=element('label',null,label);caption.htmlFor=control.id;row.append(caption,control);if(help)row.append(element('small',null,help));return row;}
function refresh(){const count={pending:0,keep:0,revise:0,discard:0};const filter=document.getElementById('filter').value;for(const item of data.items){const state=states.get(item.output_sha256),ui=controls.get(item.output_sha256);count[state.decision]++;ui.card.dataset.decision=state.decision;ui.card.hidden=filter!=='all'&&state.decision!==filter;ui.problem.required=state.decision==='revise';ui.instruction.required=state.decision==='revise';ui.problem.setAttribute('aria-required',String(ui.problem.required));ui.instruction.setAttribute('aria-required',String(ui.instruction.required));}document.getElementById('summary').textContent=`共 ${data.items.length} 张 · 待评价 ${count.pending} · 保留 ${count.keep} · 修改 ${count.revise} · 放弃 ${count.discard}`;}
const viewer=document.getElementById('viewer'),largeImage=document.getElementById('large-image'),zoom=document.getElementById('zoom');
function openImage(item){viewer.classList.remove('zoomed');zoom.textContent='原始尺寸';largeImage.src=item.image;largeImage.alt=item.name;document.getElementById('viewer-title').textContent=item.name;viewer.showModal();}
document.getElementById('close').addEventListener('click',()=>viewer.close());
viewer.addEventListener('close',()=>largeImage.removeAttribute('src'));
zoom.addEventListener('click',()=>{const active=viewer.classList.toggle('zoomed');zoom.textContent=active?'适应屏幕':'原始尺寸';});
for(const [index,item]of data.items.entries()){
  const state=restore(item);states.set(item.output_sha256,state);
  const card=element('article','card');const preview=element('button','preview');preview.type='button';preview.setAttribute('aria-label','查看大图：'+item.name);const img=element('img');img.src=item.thumbnail;img.alt=item.name+'，上方原照片，下方效果图';img.loading='lazy';preview.append(img);preview.addEventListener('click',()=>openImage(item));
  const body=element('div','body');body.append(element('h2',null,item.name),element('p','meta',item.style_name+' · '+item.output_size.join(' × ')),element('p','meta','原图像素记录：'+(item.source_pixels_equal_recorded?'与方向校正后的原图一致':'不完全一致（可能使用固定画幅缩放）')));
  if(!item.generation_plan_sha256)body.append(element('p','meta','未关联生成计划：可导出评价；自动修订还需要核对原计划。'));
  const choice=select(decisions,'decision-'+index);choice.value=state.decision;
  const problem=select(problems,'problem-'+index);problem.value=state.feedback.problem;
  const instruction=element('textarea');instruction.id='instruction-'+index;instruction.maxLength=2000;instruction.value=state.feedback.instruction;instruction.placeholder='希望怎样调整？';
  const keep=element('textarea');keep.id='keep-'+index;keep.maxLength=2000;keep.value=state.feedback.keep;keep.placeholder='哪些内容已经满意，请继续保留？';
  body.append(field('你的选择',choice),field('问题类型',problem,'选择“修改”时必填。'),field('修改说明',instruction,'选择“修改”时必填，其他选择可留空。'),field('希望保留的部分',keep,'可选，每行一项。'));
  function update(){state.decision=choice.value;state.feedback={problem:problem.value,instruction:instruction.value,keep:keep.value};notice.textContent='';problem.removeAttribute('aria-invalid');instruction.removeAttribute('aria-invalid');persist();refresh();}
  choice.addEventListener('change',update);problem.addEventListener('change',update);instruction.addEventListener('input',update);keep.addEventListener('input',update);
  card.append(preview,body);document.getElementById('gallery').append(card);controls.set(item.output_sha256,{card,choice,problem,instruction});
}
document.getElementById('filter').addEventListener('change',refresh);
document.getElementById('export').addEventListener('click',()=>{
  for(const item of data.items){const state=states.get(item.output_sha256);if(state.decision==='revise'&&(!state.feedback.problem||!state.feedback.instruction.trim())){document.getElementById('filter').value='all';refresh();const ui=controls.get(item.output_sha256),invalid=!state.feedback.problem?ui.problem:ui.instruction;invalid.setAttribute('aria-invalid','true');notice.textContent='尚未导出：请补全“'+item.name+'”的问题类型和修改说明。';invalid.focus();return;}}
  const result={schema_version:1,items:data.items.map(item=>{const state=states.get(item.output_sha256);return {output_sha256:item.output_sha256,photo_sha256:item.photo_sha256,generation_plan_sha256:item.generation_plan_sha256,decision:state.decision,feedback:{problem:state.feedback.problem,instruction:state.feedback.instruction.trim(),keep:state.feedback.keep.split(/\r?\n/).map(line=>line.trim()).filter(Boolean)}};})};
  const blob=new Blob([JSON.stringify(result,null,2)+'\n'],{type:'application/json;charset=utf-8'});const url=URL.createObjectURL(blob);const link=element('a');link.href=url;link.download='review.json';document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);notice.textContent='已请求下载 review.json，请查看浏览器下载记录。';
});
refresh();
</script></body></html>
'''


def build_gallery(records, output, title="照片作品评选", review=None):
    output = Path(output).expanduser().resolve()
    if output.suffix.lower() != ".html":
        raise ValueError("--output must be a new .html file")
    if output.exists():
        raise ValueError("Output already exists; choose a new .html path")
    items, duplicates = read_items(records)
    review_sha, imported, skipped = (import_review(review, items) if review is not None else (None, 0, 0))
    identities = sorted((item["output_sha256"], item["photo_sha256"], item["generation_plan_sha256"]) for item in items)
    batch_id = hashlib.sha256(safe_json([identities, review_sha]).encode("utf-8")).hexdigest()
    payload = {"schema_version": 1, "batch_id": batch_id, "items": items}
    # Replace data last: neither a title nor record value can become a template token.
    before, after = HTML.split("__DATA__")
    markup = (before.replace("__TITLE__", html.escape(title, quote=True))
              + safe_json(payload) + after)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        stream.write(markup)
    return {"output": str(output), "items": len(items), "duplicates_skipped": duplicates,
            "review_imported": imported, "review_skipped": skipped, "bytes": output.stat().st_size}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", required=True, help="Directory containing composition JSON records; not recursive")
    parser.add_argument("--output", required=True, help="New self-contained .html file (never overwritten)")
    parser.add_argument("--title", default="照片作品评选")
    parser.add_argument("--review", help="Previously exported review.json; inherit only identical output/source/plan hashes")
    args = parser.parse_args()
    try:
        print(json.dumps(build_gallery(args.records, args.output, args.title, args.review), ensure_ascii=False))
    except (OSError, ValueError) as exc:
        parser.exit(1, f"ERROR: {exc}\n")


if __name__ == "__main__":
    main()
