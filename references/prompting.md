# 逐图提示词

本页保留 A/B 的参考图工作方式。C/D/E 的材质规则在 [style-recipes.json](style-recipes.json)，用 [plan_artwork.py 工作流](workflow.md)编译；不要把这里的干刷、撕纸或颗粒要求附加到 C/E。完整风格选择见[风格指南](style-guide.md)。

以下花括号内容由实际照片填写。参考图只提供下方艺术区的风格，不能移植参考中的山、塔、花、文字或地理信息。先保留可辨识结构，再决定哪些纹理可以删减。

## 通用

    Use case: style-transfer.
    Create one standalone art print from IMAGE 1, the content photograph.
    IMAGE 2 is a paired reference: use only its LOWER ARTWORK AREA for style,
    materials, simplification and negative space. Do not copy its subject or text.
    Do not output a photo panel or comparison layout.
    Content invariants: {objects, visible count, positions, orientation, occlusion}.
    Allowed simplification/removal: {specific secondary detail/background}.
    Composition: {target artwork width:height ratio}, {subject placement},
    warm ivory uncoated paper and deliberate negative space.
    No new objects, invented symbols, lettering, numbers, signature, logo,
    watermark or copied geographic information. Empty paper instead of text.
    No photographic patches, glossy 3D paper, drop shadows, perfect vector
    outlines or cartoon outlines. Keep the source subject recognizable.

没有参考图的重新生成：删去 IMAGE 2 相关句子，保留内容照片，明确描述风格。不能把未传入的图写进输入说明。

## A：撕纸拼贴 / 干刷版画

    Style: flat torn-paper collage and dry-brush print with fibrous irregular
    edges, worn ink and small areas of exposed paper. Merge {specific shapes}
    into {a few broad planes appropriate to this scene}. Use {restrained colors}.
    Remove {fine texture that should not survive}. Preserve {distinctive outline}.
    Keep the layout sparse and flat; no layered paper sculpture or realistic shading.

颜色和色块数是构图选择，不是固定常数。可从 3–5 个主要印色、约一半以上留白尝试，按参考调整。复杂街景先明确保留哪辆车、哪些门窗；不能删除主要对象只为了减少细节。

## B：颗粒拓印 / 流动消散

    Style: sparse {one/two ink colors} monoprint rubbing with broken ink and dry
    abrasion. Keep {essential structure} readable. Dissolve {secondary edges}
    into sparse grains and rubbing marks flowing {specific direction}.
    Paper remains dominant. No evenly spread digital noise, luminous particles,
    smoke, explosions or a vortex obscuring the subject.

建筑保持塔冠、门洞、层叠底座；植物保持花簇和主枝方向；水纹可以用弧向干擦概括，但不要把所有对象卷成旋涡。

## 修订记录

每次保存输入图、参考、最终完整提示词、生成模式、实际返回的文件、版本号、发现的问题和最终版本选择。不知道的模型版本、种子、费用留空，并解释工具未提供。不能只存“再极简一点”而失去上下文。

- 细节太多：指出应合并的岩纹、树叶、窗格或瓷器纹饰，保留关键结构。
- 物体缺失：列出可见实例和相对位置，区分被遮挡部分，重新检查全图。
- 假字或水印：要求空白纸面，检查边角；重新生成后复核内容。
- 画幅不符：优先要求正确画幅；排版阶段等比适配，不能拉长建筑或自行车。
