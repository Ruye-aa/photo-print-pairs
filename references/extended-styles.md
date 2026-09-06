# 扩展风格参考

本目录包含 9 条艺术化路线、1 种邮票版式和 1 种胶片调色，依据实际查看的小红书图片和官网示例整理。11 条路线均已试生成并对照实际参考、原图和审美判据复核，共保留 15 个生成版本和 15 张上下拼接图，其中 11 张选作当前对照。选中结果包括 8 条带缺陷说明的艺术候选、1 条仍有材质失配的超现实拼贴、1 个未保留内嵌原照的邮票版式草图，以及 1 个尚未验证严格纯调色的胶片候选。每条路线只用了一个输入，选中不等于全部计划通过、稳定复现或用户验收，也不代表复现了官方模型。机器状态与全部版本见 [extended-styles.json](extended-styles.json)，结果与评价见[试生成报告](https://github.com/Ruye-aa/photo-print-pairs/blob/main/examples/research-trials/README.md)和[评价数据](https://github.com/Ruye-aa/photo-print-pairs/blob/main/examples/research-trials/evaluation.json)。

| 路线 ID | 适合先试的照片 | 画面要点与来源 |
| --- | --- | --- |
| `crayon-vignette` | 饮料、小物、宠物和轮廓清楚的风景 | 细轮廓、反复擦涂、颗粒露纸，小画面配低饱和横向底色。[蜡笔笔记，第 2、7、14、15 页](https://www.xiaohongshu.com/explore/6a9d7b59000000002803526b)；[宠物笔记，第 6、8–13 页](https://www.xiaohongshu.com/explore/6a97b18a0000000027008f40) |
| `doodle-outline` | 单个宠物或小物 | 圆头粗彩线勾轮廓，内部多留白，眼鼻用小色点。当前仅有一页参考。[宠物笔记，第 5 页](https://www.xiaohongshu.com/explore/6a97b18a0000000027008f40) |
| `clay-miniature` | 轮廓和花纹清楚的宠物 | 哑光手塑表面、浅凹凸与划痕、立体体积和接触阴影。已查看猫和婚纱人偶参考；视频补画了腿脚、底座，不默认照搬。[混合风格笔记，第 14 页](https://www.xiaohongshu.com/explore/6a9a3a970000000026009db4)；[婚纱人偶视频，实际 PTS 0、30 秒](https://www.xiaohongshu.com/explore/6a9cd521000000002502d045) |
| `surreal-photo-collage` | 用户允许改变构图的建筑或旅行照 | 保留摄影剪贴细节，用单色纸底组织悬浮或重组的场景。[混合风格笔记，第 2、5 页](https://www.xiaohongshu.com/explore/6a9a3a970000000026009db4) |
| `anime-scenic` | 湖景、古建筑、城市远景 | 二维线条与色面简化结构，柔和暖光配冷色阴影。[官网动漫示例](https://wiki.pixcakeai.com/ai-toolbox/yingxiang-baibaoxiang/yijian-dongman-zhuanhui) |
| `citypop-poster` | 城市街道、汽车、海岸建筑 | 深色描边、硬边阴影、蓝粉配色和细印刷颗粒。[官网 City Pop 示例](https://wiki.pixcakeai.com/ai-toolbox/yingxiang-baibaoxiang/citypop-zhuanhui) |
| `knitted-miniature` | 单体建筑、小型街景 | 毛线绕向遵循物体结构，结合线圈、散纤维和微缩景深。[官网毛绒示例](https://wiki.pixcakeai.com/ai-toolbox/yingxiang-baibaoxiang/yijian-maorong-zhuanhui) |
| `toy-brick-scene` | 几何建筑、静物、人数少的合照 | 真实积木体积、凸点、接缝和塑料高光；二维像素化不算完成。[官网积木示例](https://wiki.pixcakeai.com/ai-toolbox/yingxiang-baibaoxiang/yijian-jimu-zhuanhui) |
| `pixel-stretch` | 主体和空白区域分离清楚，允许加入抽象效果的照片 | 保留摄影场景，引出一条由密集平行线组成的宽幅弯曲彩带；以实际 PTS 8、10、12 秒为对照。[像素拉伸视频](https://www.xiaohongshu.com/explore/6a42440200000000110195ff) |

`postage-stamp-layout` 是版式模板：将摄影内容放入齿孔框，或用对应负形镂空。参考第 8 页的两个面板都经过设计，不能作为未处理原图；邮戳日期、地名和文案也不应直接带到新照片中。[混合风格笔记，第 8 页](https://www.xiaohongshu.com/explore/6a9a3a970000000026009db4)

`airy-film` 是摄影调色：适度提亮、柔和反差、微冷暗部和细颗粒，重点检查肤色、白衣和天空层次。它不计入绘画材质数量。[官网清新胶片示例](https://wiki.pixcakeai.com/ai-toolbox/yingxiang-baibaoxiang/rishi-qingxin-jiaopian)

默认仍是上方完整原图、下方效果图，沿用项目的尺寸与拼接流程。生成规则不添加新对象、文字、日期或装饰；参考中的圆点、星星、爱心、底座和邮戳均不自动复制。小红书参考的上下顺序不同，也不改变项目的默认输出顺序。

`pixel-stretch` 和超现实摄影拼贴都要求显式允许重构（`--allow-recompose`）。像素拉伸会增加一条抽象彩带，应先确定起点、遮挡和延伸方向；不能用几根细线、马赛克或全图模糊代替，也不代表本项目已实现动态视频。超现实摄影拼贴要求用户允许改变构图。即使选择这条路线，也只重组输入或用户提供参考中已有的对象；不能为模仿示例任意增加岩块、建筑或漂浮岛。希望保留原场景时，应选其余路线，并逐项核对主体数量、位置和关键结构。

官网“一键远山”放在 JSON 的 `deferred` 数组中：所见示例是写实人像背景替换，没有水墨笔触证据。它属于需要允许换景的背景编辑，不计为已观察到的水墨艺术风格。[官网远山示例](https://wiki.pixcakeai.com/ai-toolbox/huasheng-guofeng/yijian-yuanshan)

穿搭、食物、宠物和建筑首先是题材。已有 A 的纸片拼贴换成穿搭，或 B 的颗粒拓印换成叠石，不单独增加风格数量。本轮已把全部版本、选中标记、输出路径和评价入口写入 `generation_trials`，首版失败与修订过程均保留。后续应换用新题材检查材料特征与结构保真；当前不能计算跨题材成功率。

视频中的大红墙、空旷广场和大色块空间属于另一条“超现实色块环境重构”方向：它会简化或替换背景，并非静态悬浮摄影剪贴。该方向目前单独列入 `deferred`，未适配到可选风格，不与 `surreal-photo-collage` 合并。[环境重构视频，实际 PTS 3、6、11 秒](https://www.xiaohongshu.com/explore/6a9552bb000000001e01459c)

[逐风格参考映射](research/2026-09-06/style-reference-map.json) 为全部 11 条可选路线选了 22 个对照引用，每条 1–3 个。映射保存来源、页码或视频实际 PTS、哈希和具体视觉判据，不包含作者原图文件路径。评审时分别记录参考风格是否成立、原图结构是否保留，以及构图、色彩、材质和细节的审美判断；后者属于评审意见，不等于用户验收。

本轮选中蜡笔 v2、超现实摄影拼贴 v3、像素拉伸 v2，其余为首版。状态 `reviewed_with_limitations` 表示已完成带局限说明的视觉评审。下表列出具体边界；评分均为助手主观意见。

| 路线 | 当前状态 | 选中结果仍有的限制 |
| --- | --- | --- |
| `crayon-vignette` | 艺术候选 | 选中 v2：纸面留白、灰绿短横带和蜡笔擦涂改善；主体仍偏大，中央失焦花痕未清除，未通过全部计划约束。 |
| `doodle-outline` | 艺术候选 | 选中首版：彩线轮廓与主体关系成立；线条更接近精细植物线稿，与参考的圆头粗线涂鸦仍有差别。 |
| `clay-miniature` | 艺术候选 | 选中首版：手塑体积与七座塔可辨；位置略有重整，黄暖色偏重，局部接近石膏，不能视作严格结构保真。 |
| `surreal-photo-collage` | 实验性材质失配 | 选中 v3 作为实验性候选：灰阶黄底、留白与中央花痕清理改善；叶片仍像银灰浅浮雕，未达到摄影薄剪贴材质，不作为参考匹配通过的示范。 |
| `anime-scenic` | 艺术候选 | 选中首版：二维线条、色面及山湖轮廓成立；岩壁色面偏碎且密，属于一次候选，未验证其他题材。 |
| `citypop-poster` | 艺术候选 | 选中首版：描边、硬边色面与印刷颗粒成立，七个塔尖保留；整体更偏蓝橙白昼旅行版画，颗粒密度和暖色面积偏大。 |
| `knitted-miniature` | 艺术候选 | 选中首版：针织走向随山、水结构变化；更接近立体壁毯，天空织纹较密，瀑布更粗，未达到参考的柔软微缩景深。 |
| `toy-brick-scene` | 艺术候选 | 选中首版：实体积木、接缝与凸点成立；部分台阶和坡面重排，微小游客数量未可靠对应，也未证明实际可拼装。 |
| `postage-stamp-layout` | 版式草图，原照未完整保留 | 选中首版作为版式草图：齿孔、纸面和摄影窗口成立；内嵌照片被改写且未完整保留，严格仅加框要求不通过，正式保真版式应使用确定性排版。 |
| `airy-film` | 调色候选，严格纯调色未验证 | 选中首版作为胶片观感候选：柔和反差与细颗粒成立，色彩偏暖；花瓣和叶缘有重新清晰化，尚未证明只改色彩和颗粒、几何未重绘。 |
| `pixel-stretch` | 艺术候选 | 选中 v2：彩带根部藏于塔肩后，下垂尾段已移除；平行线仍偏粗亮、略像金属丝带，摄影底图细节和微小游客保留未严格验证。 |

15 张拼接图的上半部分均通过与源照片解码后 RGB 像素相同的检查；下半效果图的风格、内容和几何保真是另一组判断。尤其邮票内嵌照片已被生成模型改写，胶片和像素拉伸也未证明底图细节不变，不能用上半原图检查替代这些要求。各次生成的实际尺寸与最终拼接尺寸见[生成清单](https://github.com/Ruye-aa/photo-print-pairs/blob/main/examples/research-trials/manifest.json)。

数量口径保持分开：9 条艺术化路线中，8 条为带缺陷的候选，1 条为超现实摄影拼贴实验性失配；1 个版式和 1 个调色不计入艺术候选数。两条 `deferred` 方向仍是背景替换和环境重构，未纳入这 11 条路线的试生成。
