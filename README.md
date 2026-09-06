# photo-print-pairs

将照片转为撕纸拼贴、干刷版画或颗粒拓印，并保存为**上方原照片、下方艺术效果**的一张 PNG。

这是一个 Codex skill 仓库，包含参考素材、生成提示词、评价方法和确定性拼接工具。艺术效果由 Codex 中可用的图片生成工具完成；Python 脚本负责尺寸适配、拼接和文件验证。

## 能做什么

- **A 风格**：撕纸拼贴 / 干刷版画，用少量平面形状概括主体。
- **B 风格**：颗粒拓印 / 流动消散，保留关键轮廓，让次要边缘逐渐消散。
- 单张或批量处理，可为每张照片选择一种风格，也可生成 A/B 两版。
- 默认输出原图宽度不变、高度翻倍的独立 PNG，原照片不裁切、不缩放。
- 支持固定参考尺寸、等比留边和经人工确认的艺术区纸面裁切。
- 保存提示词、版本选择、输出尺寸和哈希，分别评价主体保留与风格接近程度。

## 安装为 Codex skill

需要 Python 3.9 或更新版本。拼接工具依赖 Pillow，安装脚本只使用 Python 标准库。

```bash
git clone https://github.com/Ruye-aa/photo-print-pairs.git
cd photo-print-pairs
python3 scripts/install_skill.py
```

安装脚本优先使用 CODEX_HOME 指定的目录，否则安装到当前用户的 ~/.codex/skills/photo-print-pairs。它仅复制 skill 所需文件，不复制 Git 历史、测试和仓库维护文件。

已有相同版本时直接复用。需要更新已有版本时运行：

```bash
python3 scripts/install_skill.py --replace
```

更新前会把原目录完整保留到 skills 旁边的 skill-backups 目录，避免旧版本混入已安装技能。自定义安装目录使用旁边的 .skill-backups 目录。可用 --target 指定一个完整的 skill 目标目录。安装后在新任务中调用；若当前应用尚未刷新技能列表，重新打开任务再试。

## 在 Codex 中使用

提供照片或一个照片文件夹，然后输入：

> 使用 $photo-print-pairs，按参考风格生成上下拼接图，保存到图片/生成。

可以补充“使用 A 风格”“每张各生成 A、B 两种”“尺寸与这张参考一致”或“只保存已有拼接图”。

默认无文字、不新增装饰对象，保留主体数量、方向、相对位置和遮挡。没有指定风格时逐图选一种适配风格。若图片生成工具不可用，skill 会说明限制；不会自动改用需要额外凭据的图片 API。

完整行为约定见 [SKILL.md](SKILL.md)。

## 单独运行拼接工具

已有原照片与效果图时，不需要图片生成服务，可直接拼接。

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt

python3 scripts/compose_pair.py \
  --photo /path/to/photo.jpg \
  --artwork /path/to/artwork.png \
  --output /path/to/results/photo_A.png
```

Windows 可使用 .venv\\Scripts\\activate 激活环境，或直接使用虚拟环境中的 Python。

| 模式 | 输入与输出 | 上方照片 |
| --- | --- | --- |
| 默认原尺寸 | W×H → W×2H | 方向校正后保留解码 RGB 像素 |
| 固定参考尺寸 | --size 1080x1620 | 等比缩放、居中留边 |
| 奇数总高度 | 如 --size 1080x1451 | 上方 725 像素，下方 726 像素 |

效果图始终等比适配，不进行非等比拉伸。默认完整保留艺术图并补暖白底。可用参数：

| 参数 | 用途 |
| --- | --- |
| --size WIDTHxHEIGHT | 指定最终单张 PNG 的总尺寸 |
| --paper-color '#EEE8DA' | 指定留边底色 |
| --art-crop L,T,R,B | 裁去已查看确认的艺术区空白，坐标基于方向校正后的艺术图 |
| --paper-sample L,T,R,B | 用已确认的空白纸底矩形补边；不能包含主体或文字 |
| --record /path/to/new.json | 自定义新记录文件，默认写入输出目录的 .records/ |

同名同内容复用已有 PNG；同名不同内容另存为 _v2、_v3 等版本。原照片和效果图文件均不会被覆盖。记录包含实际尺寸、输入与输出哈希、适配范围和像素检查结果。

“原照片像素保留”指 EXIF 方向校正并解码成 RGB 后的数值一致，不代表保留 JPEG 编码、EXIF、透明度或印刷色彩配置。固定尺寸模式可能缩放照片，放大导出也不会增加真实细节。

## 参考与效果评价

仓库保留 13 张用户提供的原始参考图；这些图都是上下对照，生成时只使用下方艺术区的风格。

- [参考目录与逐张分析](references/style-catalog.md)
- [参考尺寸与文件哈希](references/reference-manifest.json)
- [通用提示词与两种风格模板](references/prompting.md)
- [22 组历史提示词和修订记录](references/prompt-examples.json)
- [历史验证与失败案例](references/validation-notes.md)

历史验证覆盖 16 张输入、22 个目标版本和 3 次额外修订。紫花、单塔较接近参考；复杂街景容易保留过多细节，鱼群出现过小鱼省略。评价来自同一助手的视觉检查，没有独立评审或重复生成稳定性统计，不能将这些候选结果当作通用成功率依据。

参考图片随仓库保存用于复现该流程；原始文件未附带完整的作者和许可资料。仓库未为这些图片声明开源许可。

## 仓库结构

```text
photo-print-pairs/
├── README.md
├── SKILL.md
├── agents/openai.yaml
├── assets/reference-originals/   # 13 张参考原图
├── references/                  # 风格、提示词和历史评价
├── scripts/
│   ├── compose_pair.py          # 尺寸适配与上下拼接
│   └── install_skill.py         # 安装与备份更新
├── tests/                       # 不调用图片生成服务的验证
└── requirements.txt
```

## 开发与验证

```bash
python3 -m pip install -r requirements.txt
python3 -m unittest discover -s tests -v
```

测试检查原照片像素、固定尺寸、方向校正、同名保护、重复执行、无效裁切、安装更新和参考素材完整性。测试使用临时生成的检查图，不需要照片下载或图片生成 API。

提交风格或提示词变更时，应另用真实照片试生成，并记录内容缺失、构图变化和文字残留。通过拼接测试不能证明生成风格改善。
