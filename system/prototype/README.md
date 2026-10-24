# Web 端原型（讨论稿）

> **状态：讨论稿，不是定稿，也不构成契约。**
> 本目录是按 `docs/技术方案/Web端原型设计规格.md` 生成的静态原型，用于在开工前把产品形态、UI 形态、交互细节和视觉基调摆到桌面上讨论。
> P1 / P2 / P3 / P5 已由需求方拍板（见 `docs/技术方案/开发前准备清单.md` §4.11）；P4（UI 形态）与 P7（视觉与文案）**待需求方在本目录三套变体中选定**。
> 交互细节（P6）已由三名子代理用 `/ego-browser` 独立交叉评估，整改结果见 `docs/技术方案/开发前准备清单.md` §2.8。

## 怎么看

直接用浏览器打开 `index.html` 即可，不需要起服务、不需要装任何依赖（纯静态、无外部 CDN、无网络请求）。

三个功能面对应三个页面，左侧导航切换：

| 页面 | 内容 |
|---|---|
| 语料准备（上传文档与工单） | 语料现状、拖拽导入、导入记录、导入错误码对照、文档列头对照表 |
| 治理扫描（一键运行） | 扫描前检查、扫描操作与阶段步进、三模块判定指标总览、耗时分项与口径 |
| 治理清单（三类缺陷清单） | 知识缺口 / 内容腐化 / 重复冗余三个 Tab；判定指标 + 统计单元口径 + 明细列表（行内就地展开）+ 下载 CSV + 口径与免责 |

每个页面右下角有「原型状态演示」开关，可切换成功态 / 未扫描 / 加载态 / 错误态 / 扫描占用等状态，用来核对各状态下的文案、空态与「数据状态诚实」规则（0 打印 0，缺失打印灰破折号，不补数）。

## 三套视觉与文案变体（P7 待选）

`variants/` 下三页结构完全相同，只换视觉 token 与文案语气，用来让需求方直接看图选：

| 变体 | 文件 | 视觉 | 文案语气 |
|---|---|---|---|
| A | `variants/v1-ledger.html` | 学术清朗（白底、近黑强调、无彩色 chrome） | 克制学术：先口径后结论 |
| B | `variants/v2-accent-ladder.html` | 紧凑数据（白底、玫红强调） | 紧凑数据术语：术语优先、短标签 |
| C | `variants/v3-framed-sheet.html` | 解释治理（浅灰底、青色强调、字号更大） | 解释型：带因果与操作指引 |

三页共用 `../styles.css` / `../app.js` / `../data.js` / `../copy.js`，差异只在 `<body data-variant>` 与 `copy.js` 里对应变体的文案表。

## 数据从哪来

`data.js` 里的每个数字都取自 `poc/kbgovernance/` 的机读产物（`metrics.json` / `top15_gaps.csv` / `corrupt_docs.csv` / `dup_groups_best.csv` / `dup_threshold.csv` / `gap_threshold.csv` / `standardize/scenario_meta.json` / `repro_check.json`），与页面上的文案一一对应。原型页面不发起任何真实请求，界面上的接口路径、数据来源、统计单元口径都是**设计标注**，用来核对将来实现时应当对齐的契约。

页面上出现的边界是刻意保留的诚实标注，不是没做完：

- 重复冗余 F1 = 1.0000 是**乐观值**，页面同时给出阈值 0.90 下的组级 F1 0.7037 作为真实预期基线；
- 聚类耗时与缺口阶段耗时在产物里没有对应字段，页面写「—」并说明原因；
- `total_seconds` 是 `detect.py` 主流程全程（读 CSV + 聚类 + 三检测，不含向量化），页面按 `detect.py` 的实际计时范围表述，不复算不出的分项；
- 缺口页声明「本次仅显示 15 个意图簇中的 7 个」，并给出 0.60 / 0.62 / 0.64 / 0.66 四档阈值的敏感性对比；
- 清单页不展示任何评测依据列（`is_true_gap` / `is_true_group` 等），但下载区明示下载的是含标注列的原始产物。

## 校验

三个脚本都只读、不改产物，退出码非 0 即视为不通过：

```bash
# 1) 数字纪律：data.js 的每个取值都能在产物里逐条对上，且未透出评测依据列
python system/prototype/check_prototype.py

# 2) 渲染：三个页面 + 三个清单 Tab + 三套变体实际渲染，无控制台错误、无横向溢出、无 NaN/undefined
python system/prototype/render_check.py

# 3) 交互验收：逐条核验准备清单 §2.8 H1~H7 的验收信号（25 项）
python system/prototype/acceptance_check.py
```

三者互不重叠：`check_prototype.py` 管数字出处与禁列，`render_check.py` 管渲染与截图，`acceptance_check.py` 管交互与无障碍行为。第三个是长期脚本而不是一次性核验——H1~H7 的验收信号是原型的长期约束，只靠一次人工核验挡不住后续改动把问题带回来。

`check_prototype.py` 也是防止原型数字随产物复跑而漂移的哨兵：产物一重跑，它就会因对不上而失败，届时按 `poc/kbgovernance/sync_timings.py` 的同一思路重新生成 `data.js`。

`render_check.py` 会在 `shots/` 下留下五个状态的整页截图（上传页 / 扫描页 / 缺口 Tab / 腐化 Tab / 重复 Tab），在 `shots/variants/` 下留下三套变体的整页截图。截图前会把扫描与清单页统一切到信息量最大的状态（扫描成功 / 清单有数据），否则拍到的全是入口空态。

## 目录

```
system/prototype/
├── index.html          # 三页结构（v1 变体，与 variants/v1-ledger.html 同构）
├── styles.css          # 视觉基座 + v1/v2/v3 三套 token 覆写
├── copy.js             # 三套变体的文案表（window.COPY.v1 / .v2 / .v3，键集一致）
├── app.js              # 文案与数值注入、三页状态机、清单渲染、展开、键盘模型、弹窗与抽屉
├── data.js             # 来自 poc/kbgovernance/ 产物的样例数据（含 audit 段）
├── check_prototype.py  # 数字溯源校验（含 audit 段逐项核对与真值列红线扫描）
├── render_check.py     # 渲染校验 + 截图（含三套变体）
├── acceptance_check.py # 交互验收（准备清单 §2.8 H1~H7 的 25 项验收信号）
├── variants/           # 三套视觉与文案变体（P7 待选）
└── shots/              # 渲染截图（校验副产物）
```

## 与规格书的关系

`docs/技术方案/Web端原型设计规格.md` 是生成依据，含 Element Plus 组件选型、布局尺寸规范、三套视觉基调方案与八项待拍板项（附录 C 的 OPEN-1 ~ OPEN-8）。本原型已按三份 `/ego-browser` 独立评审的结论重做交互（整改项见准备清单 §2.8 H1 ~ H7），并把规格书的 A / B / C 三套基调各落成一页变体供需求方选。
