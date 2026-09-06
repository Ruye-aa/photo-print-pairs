# 新风格试生成

2026-09-06 使用同一张紫花照片，以内置 `image_gen` 分别生成 C、D、E，均为首次结果。先生成独立艺术图，再通过拼接脚本保存完整上下对照，同时导出下半区。下面是实际生成结果，不是原始风格参考。

| C · 平面抽象 | D · 有限色丝网印刷 | E · 轻透插画 |
| --- | --- | --- |
| [![C](C-pair.png)](C-pair.png) | [![D](D-pair.png)](D-pair.png) | [![E](E-pair.png)](E-pair.png) |

三张成品均为 **1067×3200**。上方照片与本轮输入的方向校正后 RGB 像素一致；下半区等比适配，未裁去艺术内容。独立效果图：[C](C-pair_artwork.png)、[D](D-pair_artwork.png)、[E](E-pair_artwork.png)。

## 观察

- C：两串主要花簇、左右高低关系和下垂花梗可辨。以不透明色面表现，仍保留较多花瓣轮廓，偏具象的平面插画；更大胆的概括需要另行验证。
- D：花叶与枝条使用一致的平面印色和细碎掉墨，没有撕纸立体感；套色重叠表现较弱。
- E：轮廓清楚，色层和边缘较轻，接近轻透水彩插画；叶片内部细节仍较多。

三张均保留两串主要花簇，未观察到额外文字或新增实物。花瓣、细芽和部分叶片经过概括，不是逐个细节对应。这些评价来自助手查看结果，尚无独立评审或用户验收，也没有复杂街景、人物、多对象题材的重复试验。

## 输入与复现

[输入照片](sources/purple-flowers.png)取自仓库既有紫花对照图的完整上半区，解码像素保持一致。作者 Alejandra Montenegro，[照片页面](https://www.pexels.com/photo/purple-flowers-on-a-branch-18184147/)，[许可页面](https://www.pexels.com/license/)。本轮没有使用其他项目的示例图片。

[brief.json](brief.json)记录本张的内容约束。[manifest.json](manifest.json)保存三个实际完整提示词、输入和输出哈希、原生生成尺寸、拼接尺寸、底色及评价。模型版本、种子和费用因工具未提供而留空。运行期间使用的计划文件包含本地路径，未纳入仓库；可在新位置重新编译。

在仓库根目录运行：

```bash
python3 scripts/plan_artwork.py \
  --photo examples/style-trials/sources/purple-flowers.png \
  --brief examples/style-trials/brief.json \
  --style C --strength balanced --output /path/to/new-plan.json
```

将 `C` 换为 `D` 或 `E` 可准备另一种风格。图片生成需要在支持相应工具的环境中执行；相同提示词不保证得到相同像素。
