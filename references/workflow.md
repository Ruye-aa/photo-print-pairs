# 生成计划、系列配置与批量预览

这些命令只准备提示词、拼接和整理结果。艺术图由当前环境的图片生成工具生成，命令不会发起网络请求或读取图片服务凭据。

## 从照片到计划

先查看照片，再按 [workflow-example.json](workflow-example.json) 填写本张描述。所有对象、数量和位置来自本张照片；示例里的内容不能直接用于其他输入。

```bash
python3 scripts/plan_artwork.py \
  --photo /path/to/photo.jpg \
  --brief /path/to/brief.json \
  --style C --strength balanced \
  --output /path/to/plan.json
```

使用计划中的完整 `prompt` 调用当前可用的图片生成工具。第一张输入是 `source.path`；如有风格参考，其后按 `references` 的顺序传入。计划保存源图哈希、方向校正后的尺寸、风格与内容约束；它不保证生图工具支持精确比例，也不表示作品合格。

`--style` 支持 `auto`、`A`、`B`、`C`、`D`、`E`。`auto` 根据描述中的题材在 A/B 中推荐；所有路由都是可调整的选择，不是质量结论。`--strength` 支持 `gentle`、`balanced`、`bold`。

如果使用风格参考，用 `--references /path/to/references.json` 传入图片路径数组。照片负责内容，其他图片只负责风格。修改工具实际输入时同步更新记录，不传未查看过的图。同风格修订默认继承参考并重新核对文件哈希；显式传入空数组可清空，切换风格时默认清空旧风格参考。

## 一组照片共用风格

用户明确选定一组视觉偏好后，保存系列 JSON：

```json
{
  "style": "D",
  "strength": "balanced",
  "palette": ["muted lilac", "soft olive green", "warm brown"],
  "paper_color": "#F3EFE4"
}
```

编译时加 `--series /path/to/series.json`。显式 `--style`、`--strength` 优先于系列值；单张内容描述依然独立填写。系列配色是用户选择的色调约束，遇到必须保留的身份色时先调整系列或本张约束，不能静默覆盖。

## 拼接并保存

```bash
python3 scripts/compose_pair.py \
  --photo /path/to/photo.jpg \
  --artwork /path/to/generated.png \
  --plan /path/to/plan.json \
  --output /path/to/results/photo_C.png \
  --export-artwork
```

默认总尺寸为原图 `W×2H`。`--export-artwork` 额外保存适配后的下半区，文件名为成品名加 `_artwork.png`；未加时仍只交付一张上下对照。`--size`、人工确认的 `--art-crop` 等现有参数继续有效。

纸底优先级为显式 `--paper-color`、计划中的系列纸色、计划中的风格纸色、默认 `#EEE8DA`。记录写到结果目录 `.records/`，包含完整计划和哈希。像素检查针对 EXIF 方向校正后的 RGB，不证明印刷色彩准确或艺术内容保真。

## 离线预览

```bash
python3 scripts/review_gallery.py \
  --records /path/to/results/.records \
  --output /path/to/results/review.html
```

直接打开 HTML 即可查看，不需要部署。生成预览时会验证记录对应 PNG 的哈希和尺寸；记录重复时合并相同输出，不同版本继续显示。预览自带图片，包含照片内容，分享前按实际需要选择文件。

用户可标记待评价、保留、修改、放弃。选择修改时填写问题类别、说明和需要保留的内容，再导出 `review.json`。浏览器中的标记只是本地草稿，导出后才能交给助手继续处理。没有选择的图片保持待评价，不自动通过。

新增或移除结果后重建页面，增加 `--review /path/to/review.json` 导入之前的评价。仅输出、照片和计划哈希都一致的图片继承原选择；新结果仍为待评价。导入中不在当前批次的图片跳过，同一输出却关联不同源图或计划时停止，避免把旧验收转给新版本。

## 从一句话反馈继续

助手可以将自然语言反馈写成一个小 JSON，用户无需自己编辑：

```json
{
  "problem": "detail_overload",
  "instruction": "合并花瓣内部的明暗，让两串花各自形成更完整的色面。",
  "keep": ["左高右低的关系", "两条下垂花梗"]
}
```

```bash
python3 scripts/plan_artwork.py \
  --photo /path/to/photo.jpg --brief /path/to/brief.json \
  --previous /path/to/plan.json --feedback /path/to/feedback.json \
  --output /path/to/plan-v2.json
```

从批量预览继续时，以 `--review /path/to/review.json --result-sha256 <所选输出的SHA256>` 替代 `--feedback`。只处理决定为 `revise` 的对应项，并核对其源照片哈希。`--previous` 指向被选中结果实际使用的计划，不能选择同照片的其他风格计划。

新计划保存前一版计划哈希、完整提示词和本轮反馈。选择已有艺术图作为编辑目标时，先查看该图，单独记录实际工具输入；计划中的 `source` 始终指内容照片。如果当前工具仅能从内容照片重生，应明确记录此方式。生成后重新评价全图，再通过拼接记录关联新版本。计划、预览文件已有时拒绝覆盖，请用新文件名；PNG 同名不同内容自动递增版本。
