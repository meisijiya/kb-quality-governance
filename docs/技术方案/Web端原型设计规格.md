# 企业知识库质量治理系统 · Web 端原型设计规格

> 交付物：**原型设计规格（不含代码）**，用于驱动 Open Design 生成三页 HTML 原型图。
> 边界：前后端彻底分离；后端 FastAPI 只出 JSON；前端独立 Vue 3 + Element Plus 工程；三个功能面对应三个页面。
> 数字纪律：本规格出现的每一个指标数字都标注了 `poc/kbgovernance/` 下的出处；取不到出处的，一律写定性表述（见附录 A）。
> 术语：严格按 `GLOSSARY.md`——**知识缺口 / 内容腐化 / 重复冗余**（不写"内容失效""文档过期""陈旧文档"；"重复冗余"不拆写）。

---

## 0. 原型生成说明（给 Open Design 的输入约定）

| 项 | 约定 |
|---|---|
| 产物形态 | 单文件 HTML 原型，三页各自可独立打开（顶栏切换），无路由跳转 |
| 交互深度 | 只做「展开/收起、Tab 切换、状态切换」三类本地交互；上传、扫描、下载用**静态态**表达（按钮点击不发起真实请求） |
| 状态演示 | 每页必须包含「空态 / 加载态 / 错误态」；扫描页必须包含「扫描进行中态」。原型内提供状态切换器便于评审逐态查看 |
| 数据填充 | 一律使用 `poc/kbgovernance/` 下的**真实行**做样例（样例值见附录 B），不得虚构数值 |
| 禁止出现 | 真值列与归因列：`is_true_gap`、`is_true_group`、`in_control_sample`、`is_dup_copy`、`dup_source`、`fp_reason`（红线，见第 2.3 节） |

---

## 1. 全局骨架与设计原则

### 1.1 页面骨架（三页共用）

```
┌───────────────────────────────────────────────────────────┐
│ el-header  顶栏：产品名 + 当前语料规模 + 扫描状态徽标        │  56px
├────────────┬──────────────────────────────────────────────┤
│ el-aside   │ el-main（内容区，最大宽 1280px，padding 24px）  │
│ 220px      │                                              │
│ el-menu    │   ┌ 区块卡片 el-card ─────────────────────┐   │
│ 三功能面   │   │ 区块标题（16px/600）                 │   │
│ 纵向       │   │ 区块内容                              │   │
└────────────┴──────────────────────────────────────────────┘
```

### 1.2 三页与功能面的对应

| 路由（前端） | 页面 | 对应功能面 | 对应后端接口 |
|---|---|---|---|
| `/upload` | 上传文档与工单 | 功能面① 文档/工单上传 | `POST /api/documents`、`POST /api/tickets`、`GET /api/corpus/stats` |
| `/scan` | 一键运行治理扫描 | 功能面② 一键运行治理扫描 | `GET /api/scan/status`、`POST /api/scan`、`GET /api/metrics` |
| `/lists` | 三类缺陷清单 | 功能面③ 三类缺陷清单列表 + 展开详情 | `GET /api/gaps`、`GET /api/stale`、`GET /api/duplicates`、`GET /api/downloads/{name}` |

> 清单页**不做独立详情页、不做路由跳转、不分页、不做列排序**（`docs/技术方案/本科版实施方案.md` §2.2、§3 砍掉表）。详情一律在列表行内就地展开。

### 1.3 数字与口径纪律

- 页面上每个指标数字都必须来自机读产物；不得由叙述性文本反推，不得手填。
- 耗时**按分项列**，不写"全链路总耗时"：`metrics.json` 无该字段，`total_seconds` 只覆盖三模块检测段（`docs/技术方案/本科版实施方案.md` §7.2）。
- 阈值与 F1 **必须直接显示在清单页**（实施方案 §6 W8 关卡 G8 验收项）。
- 若部署语料无评测基线（`has_ground_truth=false`），`precision/recall/f1` 为 `null` → 界面显示「—」并附说明「当前语料无评测基线」，不得补任何数。

---

## 2. 命名红线与文案规范

### 2.1 三类缺陷的标准称法

| 缺陷类 | 界面主标题 | 英文/副标题 | 判定对象单位 |
|---|---|---|---|
| 知识缺口 | 知识缺口 | Knowledge Gap | 缺口簇（1 簇 = 1 个业务意图下的工单群） |
| 内容腐化 | 内容腐化 | Content Staleness | 文档（1 篇 = 1 行） |
| 重复冗余 | 重复冗余 | Redundancy | 重复组（1 组 = 1 组重复文档） |

### 2.2 禁止词与替代词

| 禁止 | 改用 |
|---|---|
| 内容失效 / 文档过期 / 陈旧文档 / 过期文档 | **内容腐化** |
| 重复文档组 / 查重组 / 冗余组（拆写） | **重复冗余**（整词）、"重复组" |
| 语义覆盖率 / 相似度覆盖率 | **段落级语义覆盖度**（简称"覆盖度"，需首次出现时写全称） |
| 主题 / 话题簇 | **业务意图** |
| 质量分 / 健康分 | 风险分（`risk_score`）、覆盖度（`cover_median`）、组内最大余弦相似度（`max_sim`） |

### 2.3 数据红线（界面永不出现）

- `is_true_gap`、`is_true_group`——评测依据列，不外泄（`system/openapi.yaml` 字段映射表；`docs/技术方案/开发前准备清单.md` A14）。
- `in_control_sample`、`is_dup_copy`、`dup_source`、`fp_reason`——腐化清单的对照集/误报归因列，同样不透出。
- `rep_cover`——簇级产物 `gap_clusters_best.csv` 里与 `cover_median` 数值相同，但意图级主清单 `gap_intents_best.csv` 根本没有这一列；界面只展示一次覆盖度，不重复（见第 8.1 节）。

---

# 第一部分 · 三个页面的信息架构与区块顺序

## 3. 页面一：上传文档与工单

### 3.1 区块顺序

| 序 | 区块 | 内容 | 视觉容器 |
|---|---|---|---|
| 1 | 页面标题区 | 标题「上传文档与工单」+ 副标题「先导入语料，再运行治理扫描」 | 页面级标题 |
| 2 | 语料现状卡 | `n_docs` / `n_tickets` / `n_passages` 三个统计 + 「参考语料规模 300 篇文档 / 2000 条工单 / 1852 个文档段落」提示 | el-card + el-statistic 三列 |
| 3 | 文档导入区 | 拖拽上传（CSV/JSON）+ 文档列头对照表 + 导入结果 | el-card，内含 el-upload(drag) + el-table |
| 4 | 工单导入区 | 单文件上传 + 必填列提示 + 导入结果 | el-card，内含 el-upload + el-alert |
| 5 | 反馈与阻断区 | 导入成功/失败明细、阻断原因 | el-alert + el-descriptions |
| 6 | 下一步指引 | 「语料已就绪 → 去运行治理扫描」按钮；未就绪时禁用并说明 | el-card 内 el-button |

### 3.2 状态机

| 状态 | 触发 | 界面表现 |
|---|---|---|
| **空态** | `GET /api/corpus/stats` 返回 0 文档 0 工单 | 区块 3/4 的 el-upload 保持可点击，但结果区用 el-empty「尚未导入任何语料」；区块 2 三格显示 0；区块 6 按钮 disabled，提示「导入语料后才能运行扫描」 |
| **加载态** | 统计请求、上传解析中 | 区块 2 用 el-skeleton（3 行）；区块 3/4 的结果区用 el-skeleton（4 行）；上传按钮 `loading` 且禁用 |
| **错误态** | 见 3.3 逐码 | el-alert `type="error"` `closable="false"`，展示错误码 + 可读说明 + 出错行号/列名；错误下方保留已成功部分的表格 |
| **成功态** | 导入完成 | el-alert `type="success"`，展示「已导入 N 篇文档」/「已导入 N 条工单」；区块 6 按钮转为可点击 |
| **扫描占用态** | `GET /api/scan/status` = `running` | 区块 3/4 的上传控件整体 disabled，提示「扫描进行中，暂不能导入语料」；顶栏状态徽标显示「扫描中」 |

### 3.3 错误态逐条对应

| 错误码（`system/openapi.yaml` 枚举） | 触发条件 | 界面文案与处置 |
|---|---|---|
| `DUPLICATE_DOC_CODE` | 文档编码重复（`doc_id` 已在库或本批内重复） | 「文档编码重复，本批未入库」+ 列出冲突的 `doc_id` 与行号（`location.row`）；整批事务回滚（`doc_code` 重复→409 并回滚），已导入数据不受影响 |
| `DUPLICATE_TICKET_CODE` | 工单号重复（`ticket_id`） | 「工单号重复，该行未导入」+ 列出 `ticket_id` 与行号 |
| `INVALID_IMPORT_FILE` | 工单 CSV 缺列 | 「工单文件缺少必填列」+ 列出缺失列名 + 直接给出正确表头： `ticket_id, created_at, channel, content, intent_label, urgency, status, handling_minutes, linked_doc_id`；导入中止（技术方案 UC1 异常流） |
| `VALIDATION_FAILED` | 文档正文过短（< 20 字） | 「正文过短，未入库」+ 列出 `doc_id` 与正文长度 |
| `NOT_FOUND` | 关联工单的 `linked_doc_id` 在库中查不到 | 「关联文档不存在，该行未导入」+ 列出 `ticket_id`、`linked_doc_id`（A17：未命中即拒绝该行） |

---

## 4. 页面二：一键运行治理扫描

### 4.1 区块顺序

| 序 | 区块 | 内容 | 视觉容器 |
|---|---|---|---|
| 1 | 页面标题区 | 标题「一键运行治理扫描」+ 副标题「向量化 → 聚类 → 三模块检测 → 落库」 | 页面级标题 |
| 2 | 扫描前检查卡 | 语料是否就绪（`n_docs`/`n_tickets`）、模型权重是否就位 | el-card + el-descriptions（3 列） |
| 3 | 扫描操作区 | 主按钮「运行治理扫描」+ 耗时预期说明 + 清库确认 | el-card，按钮 160×40 |
| 4 | 扫描进行中态 | 四阶段进度（不定量进度条 + 阶段名） | el-card + el-progress(indeterminate) + el-steps(4) |
| 5 | 扫描结果总览 | 三模块主指标（阈值/精确率/召回率/F1/命中数） | el-card + el-table（三行）或 el-statistic |
| 6 | 耗时分项 | 分项耗时表 | el-card + el-table |
| 7 | 口径与说明 | 阈值口径、count 统计单元、耗时口径、无真值时的降级说明 | el-alert(type=info) + el-collapse |
| 8 | 去清单页 | 「查看三类缺陷清单」按钮 | el-card 内 el-button |

### 4.2 扫描进行中态（必须实现）

- 触发：`POST /api/scan` 返回 `202`/进行中，或 `GET /api/scan/status` = `running`。
- 表现：
  - 主按钮进入 `loading` 且 `disabled`；按钮文案「扫描进行中…」。
  - `el-steps` 四步：`向量化` → `语义聚类` → `三模块检测` → `结果落库`，当前步 `process-status="process"`。
  - **进度条不定量**：`el-progress` 不给 `:percentage`（百分比数在产物中不存在，禁编造），配文字「三模块检测段实测 3.09 秒（含聚类与检测，不含向量化）」只作为口径说明，不作为进度读数。
  - 顶部全局进度条（顶栏下方 2px）表示"请求在途"。
  - 页面其它区块（检查卡、上一轮结果）保持可见但只读。
- 并发保护：同一时刻只允许一个扫描；重复点击返回 `SCAN_IN_PROGRESS` → el-alert「已有扫描在进行，请稍候」。
- 轮询：`GET /api/scan/status`，间隔 1–2 秒；`never_scanned` 时 `seconds` 与 `modules` 为 `null`。

### 4.3 扫描结果总览（区块 5）字段

| 界面列 | 数据来源 | 真实产物键 |
|---|---|---|
| 缺陷类 | 固定 | 知识缺口 / 内容腐化 / 重复冗余 |
| 阈值 | `modules.*.threshold` | `gap.best.threshold` = 0.62；`corrupt.score_threshold` = 3；`dup.best.threshold` = 0.95 |
| 精确率 | `modules.*.precision` | 0.800 / 0.8158（维护周期口径）/ 1.0000（内容过期口径）/ 1.0000 |
| 召回率 | `modules.*.recall` | 0.800 / 1.0000 / 1.0000 / 1.0000 |
| F1 | `modules.*.f1` | 0.800 / 0.8986（维护周期口径）/ 1.0000（内容过期口径）/ 1.0000 |
| 命中数 | `modules.*.count` | 5（业务意图）/ 38（维护周期口径文档）/ 32（内容过期口径文档）/ 22（组） |
| 命中规模（补充） | 同上 | 缺口涉及意图簇 7 个；重复覆盖文档 49 篇；腐化埋入 62 篇 / 检出 69 篇 |

> **count 的统计单元不同**：缺口按业务意图、腐化按文档（且分两个口径各一个数）、重复按组（A15）。表头必须写明，否则这些数字不可横向比较。
> **腐化的两口径不合成一个 F1**（2026-10-25 口径更正）：内容过期（R1+R3）与维护周期（R2+R4）是两种成因不同的问题，各自独立判定、各自报 P/R/F1，界面并列显示，不给合计 F1。
> **重复类 F1 = 1.0000 是乐观值**（`docs/技术方案/企业知识库质量治理系统技术方案.md` 附录 D 已标注），界面需带脚注。
> **腐化三项命中数**（含 TP/FP/FN 与误报来源）属评测统计，建议收进区块 7 的折叠说明，不占主表。

### 4.4 耗时分项（区块 6）

| 界面列 | 真实产物键 | 本轮值 |
|---|---|---|
| 向量化 | `embedding.encode_seconds` | 14.61 秒 |
| 语义聚类 | — | **无产物字段**，显示「—」并注明「聚类耗时未落盘」 |
| 知识缺口识别 | `corrupt` 同级无 gap 段 | **无产物字段**（契约 `seconds.gap` 暂为 null），显示「—」 |
| 内容腐化检测 | `corrupt.seconds` | 0.46 秒 |
| 重复冗余检测 | `dup.best.seconds` | 0.0 秒 |
| 三模块检测段合计 | `total_seconds` | 3.82 秒（**仅覆盖检测段**，不含向量化） |

需求阈值与实测值必须分栏显示：「单次全量扫描 ≤ 60 秒」「页面响应 ≤ 2 秒」标注为**需求阈值（非实测）**；实测值只来自上表。

### 4.5 状态机

| 状态 | 界面表现 |
|---|---|
| **从未扫描**（`status=never_scanned`） | 区块 5/6 用 el-empty「尚无扫描结果」；`seconds`/`modules` 为 null 处不显示"—"，整块隐藏 |
| **加载态** | 区块 5 用 el-skeleton（表头 + 3 行）；区块 6 用 el-skeleton（表头 + 5 行） |
| **扫描进行中** | 见 4.2 |
| **成功（completed）** | 区块 5/6 出数；区块 8 按钮可点击 |
| **错误态** | `SCAN_FAILED` → el-result 错误页 + el-alert「扫描失败，上一次结果已保留」；`EMPTY_CORPUS` → el-alert「语料为空，无法启动扫描」（技术方案 UC2 异常流）；`MODEL_WEIGHTS_MISSING` → el-alert 提示把 `HF_HOME` 设为 `D:/hf_cache`；`SCAN_IN_PROGRESS` → 见 4.2 |

### 4.6 扫描与语料的清库语义（需在 UI 上说明）

契约规定：重复扫描**旧结果清空不叠加**，清库按外键子表→父表顺序（`knowledge_gap`/`stale_document`/`duplicate_group` → `cluster_result` → `ticket` → `document`）。因此一次扫描会清掉 `document` 表行 → 扫描后语料为空，下次扫描需重新上传。

- UI 处置：点「运行治理扫描」前弹 `el-message-box` 确认：「本次扫描将清空当前库中数据并重新计算，是否继续？」。
- 扫描完成后在页面一顶部展示 el-alert「上次扫描已清空语料，如需再次扫描请重新上传」。

> ⚠️ **待拍板 OPEN-1**：是否每次扫描都清空文档表（当前契约推导出"是"）。若改为"扫描只清结果表、保留语料"，则页面一无需重新上传，确认弹窗文案也要改。见附录 C。

---

## 5. 页面三：三类缺陷清单

### 5.1 区块顺序

| 序 | 区块 | 内容 | 视觉容器 |
|---|---|---|---|
| 1 | 页面标题区 | 标题「三类缺陷清单」+ 副标题「知识缺口 / 内容腐化 / 重复冗余」 | 页面级标题 |
| 2 | 类别切换 | 三个 Tab，标签带命中数（`count`） | el-tabs（三个 el-tab-pane） |
| 3 | 指标条 | 阈值 / 精确率 / 召回率 / F1 / 命中数 / 统计单元口径 / 判定口径说明 | el-card + el-descriptions（横向 label-width 96px，5 项） |
| 4 | 列表区 | 明细表（不分页、不做列排序） | el-table + type="expand" |
| 5 | 展开详情 | 行内就地展开 | 展开行内：el-descriptions + el-alert + el-text |
| 6 | 下载区 | 下载对应 CSV | el-card 内 el-button |
| 7 | 口径与免责 | 阈值锚定说明、"乐观值"标注、无真值时说明 | el-alert(type=info) |

> 三类清单放在**同一个页面的三个 Tab** 内，不拆三页、不做路由跳转（实施方案 §2.2）。

### 5.2 状态机

| 状态 | 界面表现 |
|---|---|
| **从未扫描**（`status=never_scanned`） | 列表区 el-empty「尚无扫描结果，请先运行治理扫描」+ 「去运行扫描」按钮（技术方案 UC3 异常流） |
| **加载态** | 指标条与表格用 el-skeleton；切换 Tab 时只在表格区显示 `v-loading` |
| **该类无命中** | el-empty「本次扫描未发现该类缺陷」+ 仍保留指标条（阈值等照常显示） |
| **部分行未返回** | 当 `rows.length < count`（契约注明 rows 可能是子集）→ 表格上方 el-alert「共命中 N 项，已加载 M 条明细」 |
| **错误态** | 清单接口失败 → el-alert + el-result；下载失败 `DOWNLOAD_NOT_FOUND` → el-alert「结果文件缺失，请重新运行扫描」（UC5 异常流） |
| **无评测基线** | `precision/recall/f1` 为 null → 显示「—」+ 说明「当前语料无评测基线」（A13） |

### 5.3 三个 Tab 的指标条取值

| Tab | 阈值 | 精确率 | 召回率 | F1 | 命中数（count） | 统计单元 |
|---|---|---|---|---|---|---|
| 知识缺口 | 0.62 | 0.800 | 0.800 | 0.800 | 5 | 业务意图（涉及意图簇 7 个） |
| 内容腐化 · 内容过期口径 | 3 | 1.0000 | 1.0000 | 1.0000 | 32 | 文档 |
| 内容腐化 · 维护周期口径 | 3 | 0.8158 | 1.0000 | 0.8986 | 38 | 文档 |
| 重复冗余 | 0.95 | 1.0000 | 1.0000 | 1.0000 | 22 | 重复组（覆盖文档 49 篇） |

> 内容腐化 Tab 的指标条要同时给出**两个口径**的四项指标，标注各口径的规则集合（R1+R3 / R2+R4）。**不给合计 F1**——两条规则链的命中集合不重合，合成一个数没有解释力（2026-10-25 口径更正）。

---

# 第二部分 · 字段到真实产物列名的映射

> 规则：**界面列名一律为中文业务名，其数据来源必须是 `poc/kbgovernance/` 下真实存在的列/键**；凡产物中不存在的字段，界面一律不出现。

## 6. 页面一字段映射

### 6.1 文档导入（`POST /api/documents`，JSON 体 `{documents:[…]}`；源列 `poc/kbgovernance/docs.csv`）

| 界面字段 | 契约字段 | 真实产物列（docs.csv） | 必填 | 说明 |
|---|---|---|---|---|
| 文档编码 | `doc_code` | `doc_id` | ✅ | 唯一键；重复 → `DUPLICATE_DOC_CODE` |
| 标题 | `title` | `title` | ✅ | — |
| 正文 | `content` | `content` | ✅ | 过短（< 20 字）→ `VALIDATION_FAILED` |
| 业务域 | `domain` | `category` | — | 契约改名，产物列名不变 |
| 创建时间 | `created_at` | `created_at` | — | — |
| 最后修改时间 | `last_modified` | `last_modified` | — | 内容腐化规则 R2、R4 的判定输入 |
| 生效日期 | `effective_date` | `effective_date` | — | — |
| 状态 | `status` | `status` | — | 契约默认「生效」 |
| 引用次数 | `ref_count` | `ref_count` | — | 契约默认 0；主文档选举的输入之一 |

### 6.2 工单导入（`POST /api/tickets`，`multipart/form-data` 单文件；源列 `poc/kbgovernance/tickets.csv`）

| 界面列（上传文件表头） | 产物列（tickets.csv） | 必填 | 说明 |
|---|---|---|---|
| 工单号 | `ticket_id` | ✅ | 唯一键 |
| 创建时间 | `created_at` | ✅ | — |
| 渠道 | `channel` | — | — |
| 正文 | `content` | ✅ | 意图聚类的输入 |
| 业务意图标签 | `intent_label` | ✅ | 聚类归并出业务意图 |
| 紧急度 | `urgency` | — | — |
| 状态 | `status` | — | — |
| 处理时长（分钟） | `handling_minutes` | — | — |
| 关联文档 | `linked_doc_id` | — | 是**文档编码文本**（形如 `DOC0123`），不是行号；A17：未命中即拒绝该行 |

> 页面上的"必填四列"提示固定文案：`ticket_id、created_at、content、intent_label`。
> `linked_doc_id` 在实测语料中 2000 条里 1629 条非空——界面提示写"可留空；填写时须为已入库的文档编码"。

### 6.3 页面一其它字段

| 界面字段 | 接口 | 来源键 | 说明 |
|---|---|---|---|
| 文档数 | `GET /api/corpus/stats` | `n_docs` | 参考值 300（`metrics.json` → `embedding.n_docs`） |
| 工单数 | 同上 | `n_tickets` | 参考值 2000 |
| 文档段落数 | 同上 | `n_passages` | 参考值 1852 |

## 7. 页面二字段映射

| 界面字段 | 接口字段 | 真实产物键 |
|---|---|---|
| 扫描状态 | `status` | `never_scanned / running / completed / failed`（枚举，非产物列） |
| 各模块阈值/精确率/召回率/F1/命中数 | `modules.{gap,corrupt,duplicate}.{threshold,precision,recall,f1,count}`；腐化按 `modules.corrupt.by_cause.{content_expiry,maintenance}.*` 分两口径 | `gap.best.*`、`corrupt.by_cause.*`、`corrupt.score_threshold`、`dup.best.*` |
| 向量化耗时 | `seconds.encoding` | `embedding.encode_seconds` = 14.61 |
| 聚类耗时 | — | **无产物键** → 显示「—」 |
| 知识缺口识别耗时 | `seconds.gap`（契约暂为 null） | **无产物键** → 显示「—」 |
| 内容腐化耗时 | `seconds.corrupt` | `corrupt.seconds` = 0.46 |
| 重复冗余耗时 | `seconds.duplicate` | `dup.best.seconds` = 0.0 |
| 检测段合计 | `seconds.total` | `total_seconds` = 3.82（口径：仅三模块检测段） |
| 缺口命中意图数 | `modules.gap.count` | `gap.best.gap_clusters` = 7（簇级，溯源用）；**判定单元是业务意图，清单行数 = `gap.n_gap_intents` = 5** |
| 聚类参数 | — | `gap.best.min_cluster_size` = 5；`gap.clusters["5"]` = 95 簇 / 0 噪声（说明"簇"的来源） |
| 腐化规则权重 | — | `corrupt.rule_weight` = R1 3 / R2 2 / R3 2 / R4 1 |
| 腐化规则命中数 | — | `corrupt.rule_hit_counts` = R1 32 / R2 38 / R3 32 / R4 88（口径：全部 300 篇文档） |

## 8. 页面三字段映射（三个 Tab 各自的真实列）

### 8.1 知识缺口 Tab（源 `poc/kbgovernance/gap_intents_best.csv`，判定单元 = 业务意图）

| 界面列 | 真实产物列 | 展示位置 | 说明 |
|---|---|---|---|
| 业务意图 | `intent` | 列表 + 展开 | 例：公积金提取材料、海外出差报销标准、密码策略例外申请、社保转移办理、终端病毒处置 |
| 意图下的簇数 | `n_clusters` | 列表 + 展开 | 本轮 5 行均为 3；这是实现细节（一个意图可切成多个簇），不参与判定 |
| 意图覆盖度 | `min_cover_median` | 列表 + 展开 | 段落级语义覆盖度，取该意图下**各簇覆盖度的最小值**；本轮区间 0.5629–0.6179 |
| 意图下的工单总数 | `total_tickets` | 列表 + 展开 | 本轮区间 62–85 |
| 判定阈值 | `threshold` | 展开 | 0.62（判定线：意图覆盖度低于它即入选） |
| 代表工单号 | `rep_ticket` | 展开 | 形如 `TK00119`（`TK` + 5 位数字） |
| 代表工单文本 | `rep_text` | 展开 | 工单正文样例 |

> **判定单元是业务意图，不是簇**（2026-10-25 口径更正）：意图覆盖度 = 该意图下各簇覆盖度的最小值，「存在一个簇低于阈值」与「意图覆盖度低于阈值」等价，所以意图级与簇级检出集合一致，差别只在展示粒度。界面一行 = 一个业务意图，本轮 5 行；簇级明细（95 行）只作溯源，不进列表。
> 列表不设「排名」列：意图级产物没有全局名次这一列（`gap_intents_best.csv` 无 `rank`）。顺序按 `min_cover_median` 升序（覆盖度最低在前），该顺序由后端给定，界面不提供切换。

### 8.2 内容腐化 Tab（源 `poc/kbgovernance/corrupt_docs.csv`）

| 界面列 | 真实产物列 | 展示位置 | 说明 |
|---|---|---|---|
| 文档编码 | `doc_id` | 列表 + 展开 | 例：`DOC0241` |
| 标题 | `title` | 列表 + 展开 | — |
| 业务域 | `category` | 列表 + 展开 | — |
| 最后修改时间 | `last_modified` | 列表 + 展开 | — |
| 内容过期口径分 | `cause_score_content_expiry` | 列表 + 展开 | 规则 R1 + R3 加权；≥ 3 即在该口径下命中 |
| 维护周期口径分 | `cause_score_maintenance` | 列表 + 展开 | 规则 R2 + R4 加权；≥ 3 即在该口径下命中 |
| 四规则合并分 | `risk_score` | 展开 | 只作溯源与对照，**不再用于任何判定**；严重度色标改按两口径分别给 |
| 命中规则 | `rule_hits` | 列表 + 展开 | 原值形如 `R1_正文过期日期｜R2_更新时间超18个月｜R3_正文含绝对过期年份｜R4_同类存在更新文档`（**规则编号 + 下划线 + 规则说明**，管道符分隔）；列表只取规则编号摘要，展开展示原值全文 |
| 判定理由 | `reasons` | 展开 | 分号分隔的逐条理由 |

> 不透出：`in_control_sample`、`is_dup_copy`、`dup_source`、`fp_reason`。
> **判定按两口径各自独立进行**（2026-10-25 口径更正）：内容过期（R1+R3）与维护周期（R2+R4）各自打分、各自判阈值 ≥ 3。同一篇文档可能两个口径都命中（如 DOC0241 得分 5 / 3），也可能一个都不命中。`risk_score` 只是四规则合并分，保留在展开区作溯源。

### 8.3 重复冗余 Tab（源 `poc/kbgovernance/dup_groups_best.csv`）

| 界面列 | 真实产物列 | 展示位置 | 说明 |
|---|---|---|---|
| 组号 | `group` | 列表 + 展开 | 1–22 |
| 组内文档数 | `size` | 列表 + 展开 | 取值 3（5 组）或 2（17 组） |
| 主文档 | `primary_doc` | 列表 + 展开 | 主文档选举结果 |
| 成员文档 | `member_docs` | 展开 | 管道符分隔的编码串，如 `DOC0001｜DOC0002｜DOC0003` |
| 组内最大余弦相似度 | `max_sim` | 列表 + 展开 | 本轮区间 0.9545–0.9845 |

> 不透出：`is_true_group`。
> 主文档选举降级态：未选出唯一主文档时，展开区主文档位置显示「待人工确认」el-tag（UC4 异常流）。本轮 22 组均已选出主文档，故该态为兜底规格。

---

# 第三部分 · 三类清单的展示列、展开详情与严重度视觉

## 9. 展示与展开规格

### 9.1 知识缺口清单

| 项 | 规格 |
|---|---|
| 列表列 | 业务意图 `intent` ｜ 意图下的簇数 `n_clusters` ｜ 意图覆盖度 `min_cover_median`（含进度条） ｜ 意图下的工单总数 `total_tickets` ｜ 严重度标（见 9.4） |
| 行操作 | 展开按钮（el-table `type="expand"` 的箭头列） |
| 展开详情 | ① 代表工单卡：工单号 `rep_ticket` + 正文 `rep_text`（可复制）；② 覆盖度卡：`min_cover_median` 精确值 + 阈值 0.62 对比（低于阈值才入选，说明文字）；③ 规模卡：意图下的簇数 `n_clusters` + 意图下的工单总数 `total_tickets`；④ 口径提示 el-alert(info)：「判定单元是业务意图，覆盖度取该意图下各簇的最小值；同一意图可能包含多个簇」 |
| 展开区布局 | el-descriptions `:column="2"` `size="small"` + 下方单卡片承载代表工单正文 |

### 9.2 内容腐化清单

| 项 | 规格 |
|---|---|
| 列表列 | 文档编码 `doc_id` ｜ 标题 `title` ｜ 业务域 `category` ｜ 最后修改时间 `last_modified` ｜ 内容过期口径分 `cause_score_content_expiry` ｜ 维护周期口径分 `cause_score_maintenance` ｜ 命中规则 `rule_hits` |
| 行操作 | 展开按钮 |
| 展开详情 | ① 判定理由卡：`reasons` 逐条拆成 el-descriptions 或列表，逐条对应到 `rule_hits` 中的规则；② 命中规则卡：`rule_hits` 原值（规则编号 + 规则说明）逐条列出，并标出该规则属于哪个口径（R1/R3 → 内容过期；R2/R4 → 维护周期），附规则权重（`corrupt.rule_weight`：R1 3 / R2 2 / R3 2 / R4 1）；③ 两口径判定卡：内容过期口径 `cause_score_content_expiry` ≥ 3 / 维护周期口径 `cause_score_maintenance` ≥ 3，各自给命中与否；④ 文档信息卡：`doc_id`/`title`/`category`/`last_modified`；⑤ 口径说明 el-alert(warning)：两类成因分别判定，不合成单一分数 |
| 展开区布局 | 上：理由卡（整宽）；下：左规则卡 / 右文档信息卡（el-row `:gutter="16"` 两列各 50%） |

### 9.3 重复冗余清单

| 项 | 规格 |
|---|---|
| 列表列 | 组号 `group` ｜ 组内文档数 `size` ｜ 主文档 `primary_doc` ｜ 组内最大余弦相似度 `max_sim`（含条形） ｜ 严重度标（见 9.4） |
| 行操作 | 展开按钮 |
| 展开详情 | ① 成员文档卡：`member_docs` 拆分为 el-tag 列表（DOC 编码），主文档标「主文档」；② 主文档选举说明卡：选举依据为引用次数、最后修改时间、标题包含度的归一化加权（定性表述，不显示无出处的权重数值）；③ 相似度卡：`max_sim` 精确值 + 阈值 0.95 对比；④ 待人工确认态：主文档为空时 el-alert(warning)「未选出唯一主文档，需人工确认」 |
| 展开区布局 | 上：成员文档 tag 云；下：左相似度卡 / 右主文档选举卡 |

### 9.4 严重度视觉区分手段

**总原则（三种缺陷各不相同，均由产物字段支撑）：**

| 缺陷类 | 严重度数据来源 | 视觉手段 | 分档与否及理由 |
|---|---|---|---|
| **内容腐化** | `cause_score_content_expiry`（0 / 3 / 5）与 `cause_score_maintenance`（0 / 1 / 3） | 两个口径分各一个 el-tag + 行左侧 4px 色条 + 数值常显 | **按口径分别分档**：每个口径的取值就是产物里的真实分值，不合并 |
| **知识缺口** | `min_cover_median`（连续值 0.5629–0.6179） | 覆盖度进度条（连续）+ 距阈值差值 + 意图下工单总数 tag | **不分档**：产物中没有严重度字段，离散分档需自造切点（见下） |
| **重复冗余** | `size`（2 或 3）与 `max_sim`（0.9545–0.9845） | 组规模 tag（3 篇 = 强调档）+ 相似度条（连续）+ 数值常显 | **规模分两档**（仅两个真实取值）；相似度连续化 |

**内容腐化的分档按口径分别给（每档锚定真实分值与真实规则组合）：**

内容过期口径（规则 R1 + R3，权重 3 / 2，阈值 3）：

| 口径分 | 命中规则组合 | 篇数 | 视觉 |
|---|---|---|---|
| 5 | R1+R3 | 32 | el-tag `type="danger"` 浅底 + 行左红条 |
| 0 | 未达阈值 | 268 | 无标（该口径未命中） |

维护周期口径（规则 R2 + R4，权重 2 / 1，阈值 3）：

| 口径分 | 命中规则组合 | 篇数 | 视觉 |
|---|---|---|---|
| 3 | R2+R4 | 38 | el-tag `type="warning"` + 行左橙条 |
| 1 | 仅 R4（未达阈值） | 45 | el-tag `type="info"` 浅底 + 行左灰条 |
| 0 | 未命中 | 217 | 无标 |

> 两个口径的命中集合不重合（内容过期 32 篇、维护周期 38 篇、并集 69 篇、有 1 篇同时属两类），所以**同一行可能两个标都亮，也可能只亮一个**。界面按「该口径命中 / 未命中」给两枚标；颜色不是唯一编码——每行同时给出两个口径分值与规则组合文本，色觉障碍用户可只读数字与文字分辨（WCAG 1.4.1）。

**知识缺口为什么不分档（重要取舍）：**

`gap_intents_best.csv` 没有严重度列。切成「严重/中等/轻微」需要自造覆盖度切点（如 0.58、0.61），这些数字在产物中不存在，违反数字纪律。推荐做法：

- 只用**连续编码**：覆盖度进度条（条越短 = 覆盖越低 = 越严重）+ 「低于阈值 0.62 约 0.00X」差值（派生值，差值由两个产物值相减得到）+ 意图下工单总数 tag 表示影响面。
- 固定排序（后端默认 `min_cover_median` 升序）承担"最严重在前"的表达。
- 若需求方坚持离散分档，切点必须先拍板并登记进「派生指标登记表」（`docs/技术方案/开发前准备清单.md` N1），才能进页面。

**重复冗余的两档：**

| 组内文档数 `size` | 组数 | 视觉 |
|---|---|---|
| 3 | 5 | el-tag `type="warning"`「3 篇成组」+ 行左橙条 |
| 2 | 17 | el-tag `type="info"`「2 篇成组」+ 行左灰条 |

组内最大余弦相似度用 0–1 的连续条（长度 = `max_sim`），阈值 0.95 以刻度线标出；本轮最低值 0.9545 恰好贴近阈值，故条长差异很小——不要为拉开差异而做非线性映射（会扭曲数值）。

---

# 第四部分 · 组件选型与布局尺寸建议

## 10. Element Plus 组件选型

| 区域 | 组件 | 关键参数 / 用法 |
|---|---|---|
| 整体骨架 | `el-container` / `el-header` / `el-aside` / `el-main` | aside 宽 220px；main `max-width: 1280px; margin: 0 auto; padding: 24px` |
| 侧边导航 | `el-menu`（`router`） | 三项：上传文档与工单 / 一键运行治理扫描 / 三类缺陷清单；`default-active` 跟随路由 |
| 顶栏状态 | `el-tag` + `el-tooltip` | 扫描状态徽标：未扫描（info）/ 扫描中（warning，带 loading 图标）/ 已完成（success）/ 失败（danger） |
| 统计数字 | `el-statistic` | 语料三格、模块命中数；`title` 14px、`content` 24px/600 |
| 指标条 | `el-descriptions` | `border` `size="small"` `:column="5"`，`label-width="96px"`；无值处写「—」 |
| 主列表 | `el-table` | `stripe` `border` `size="small"`；**不设 `sortable`**（不做列排序）；`row-key` 用 `rank`/`doc_id`/`group`；`max-height` 由视口计算，页面内滚 |
| 行展开 | `el-table` 的 `type="expand"` | 展开槽内用 `el-row :gutter="16"` 排左右卡；展开区背景 `--el-fill-color-light` |
| 严重度标记 | `el-tag` + 自定义行左色条 | `type="danger|warning|info"`；色条用 `border-left: 4px solid var(--x)`；数值常显（不只靠颜色） |
| 覆盖度 / 相似度 | `el-progress` | `:percentage` = `Math.round(cover_median × 100)` / `Math.round(max_sim × 100)`，**旁边必须同时显示原始小数**（0.5629 / 0.9545），避免整数化造成精度误读 |
| 阈值刻度 | `el-progress` 的 `format` 插槽 / 自定义刻度线 | 在条上标 0.62 / 0.95 位置（纯 CSS 刻度，不改数值） |
| 上传 | `el-upload` | `:auto-upload="false"` `drag` `accept=".csv,.json"`；上传列表 `el-upload-list`；失败项 `el-upload-list__item.is-failed` |
| 按钮 | `el-button` | 主按钮 `type="primary" size="large"`（160×40）；次要 `plain`；禁用态必带 tooltip 说明原因 |
| 表单说明 | `el-alert` | 必填列/表头提示用 `type="info" :closable="false" show-icon`；错误用 `type="error"`；成功用 `type="success"` |
| 错误兜底 | `el-result` | 致命错误（整页失败）用 `icon="error"` + `sub-title` + `extra` 按钮；可恢复错误用 `el-alert` |
| 空态 | `el-empty` | 三处：未导入语料 / 尚无扫描结果 / 本次未发现该类缺陷；`description` 写清下一步动作 |
| 骨架屏 | `el-skeleton` | 统计区 3 行、表格区「表头 + 4 行」 |
| 加载中 | `v-loading` / `el-progress` | 表格区 `v-loading="true"` `element-loading-text="加载中"`；扫描中用不定量 `el-progress`（无 `:percentage`） |
| 步骤条 | `el-steps` `:simple` | 扫描四阶段：向量化 → 语义聚类 → 三模块检测 → 结果落库 |
| 折叠说明 | `el-collapse` | 口径说明、规则说明、评测统计收纳 |
| 确认 | `el-message-box` | 扫描前清库确认；下载前提示"下载的是源 CSV 原文" |
| 轻提示 | `ElMessage` / `ElNotification` | 导入成功、下载开始 |
| 下载 | `el-button` + `Download` 图标 | `GET /api/downloads/{name}`，`name` 仅允许四个枚举值 |
| 表格行提示 | `el-tooltip` | 长标题、业务域、规则组合超长时截断 + tooltip |
| 复制 | `el-text` + 复制图标 | 代表工单号、文档编码支持一键复制 |

## 11. 布局与尺寸规范

| 项 | 建议值 |
|---|---|
| 页面最大宽度 | 1280px 居中；主表允许 100% 宽 |
| 页面内边距 | 24px；卡片之间 16px；卡片内边距 16–20px |
| 圆角 / 描边 | 卡片 `border-radius: 8px`，`shadow="never"`，`--el-border-color-lighter` 描边（毕设截图需克制，避免重投影） |
| 字体 | 正文 14px / 行高 1.6；区块标题 16px / 600；辅助说明 12px `--el-text-color-secondary`；数字 24–28px / 600 |
| 表格 | 行高 `size="small"`；表头 13px / 600；列宽建议：编码列 120px、业务意图列 180px、覆盖度列 200px、风险分列 100px、规则组合列 260px |
| 展开区 | 内边距 16px；左右卡各 50%（`el-col :span="12"`），间距 `gutter=16` |
| 侧边菜单 | 高 44px/项，图标 16px，选中项左侧 3px 主色条 |
| 状态区高度 | 指标条 64px；空态区 240px；骨架屏 3×32px |
| 响应式 | ≥1440px：侧边菜单常驻；1024–1440px：侧边菜单折叠为图标；<1024px：侧边菜单收进 `el-drawer`，表格列允许横向滚动 |
| 键盘可达 | 展开按钮可 Tab 聚焦并回车触发；`el-alert` 关键错误支持 `role="alert"`；焦点环保留 2px 可见描边 |

---

# 第五部分 · 视觉基调方案（3 套，供需求方挑选）

> 说明：配色为**设计值**，不属于指标数字，不受数字纪律约束；但页面上的任何数字仍必须来自第 10 节的产物出处。

## 方案 A｜学术清朗（默认推荐）

| 项 | 内容 |
|---|---|
| 配色倾向 | 白底 `#ffffff` + 中性灰阶（`#303133` 标题 / `#606266` 正文 / `#909399` 辅助 / `#EBEEF5` 分隔）+ Element Plus 主蓝 `#409EFF` 作唯一强调色；严重度沿用红 `#F56C6C` / 橙 `#E6A23C` / 灰 `#909399` |
| 信息密度 | **高**。指标条压到一行 5 项，表格 `size="small"`，行高 44px；口径说明全部折叠进 `el-collapse`，只留一行提示条 |
| 适用场景 | **论文配图与答辩截图**（实施方案要求 3 张界面截图：上传页 / 扫描结果总览页 / 三类缺陷清单页）。浅底在投影与打印 A4 上最清晰，且与论文正文风格一致 |
| 代价 | 长时间盯屏舒适度一般；演示时视觉冲击弱 |

## 方案 B｜数据看板（石墨灰）

| 项 | 内容 |
|---|---|
| 配色倾向 | 深灰底 `#1F2329` / 卡面 `#262B33`，文字 `#E6E6E6`，强调色青蓝 `#4FC3F7`，严重度用 `#F56C6C` / `#E6A23C` / `#8A94A6`；指标数字用等宽字形（如 `Roboto Mono`）强化"数值感" |
| 信息密度 | **高**，且视觉重心在数字区：三模块主指标做成大号 `el-statistic` 卡片墙（阈值 / P / R / F1 / 命中数），表格降为次级 |
| 适用场景 | **现场演示与录屏讲解**：数值对比在暗色底上更跳，指标墙一眼讲清"三模块各命中多少、F1 多少" |
| 代价 | Element Plus 需引 `dark/css-vars.css` 做深色变量覆盖；深底**不适合投影与论文截图**（打印耗墨、投影偏灰），截图必须回到方案 A 或做浅色导出 |

## 方案 C｜墨蓝治理（克制的品牌感）

| 项 | 内容 |
|---|---|
| 配色倾向 | 墨蓝主色 `#2F4B7C` + 米白底 `#F7F8FA` + 卡面纯白 + 朱砂强调 `#C0392B`（仅用于最高风险与主按钮）；表格表头用墨蓝底白字，区块标题左侧 3px 墨蓝竖条 |
| 信息密度 | **中**。每张卡片标题带一行说明文字（不超过 40 字），展开详情用左标题右内容的 `el-descriptions` 排版，纵向留白比方案 A/B 大 |
| 适用场景 | **面向需求方/评审的原型走查**：有明确的"治理系统"品牌感与层次，讲解时不容易迷失在表格里 |
| 代价 | 纵向更长，三类清单 Tab 切换后行数与方案的视觉体量不一致；截图进论文时版面偏"产品截图"而非"系统截图" |

### 选型建议

| 使用场景 | 建议 |
|---|---|
| 论文图 3-8 三张界面截图 | **方案 A**（浅底、投影与打印友好） |
| 答辩现场演示 | **方案 B** 演示 + **方案 A** 备用截图（避免深色在投影仪偏色） |
| 需求方评审走查 | **方案 C**（层次清晰、讲得清） |

### 拍板结论（2026-10-24）

**选定方案 A｜学术清朗**，三套均已出图供复核（`system/prototype/variants/v1-ledger.html`、`v2-accent-ladder.html`、`v3-framed-sheet.html`，整页截图在 `system/prototype/shots/variants/`）。

落地口径：白底 + 近黑强调、无彩色 chrome、数值与文字同权重、面板无投影、数字右对齐；论文三张界面截图与答辩现场演示统一用 A，不另起深色主题。方案 B / C 保留为备选——两者与 A 的差异只在 token 覆写与文案语气，页面结构完全相同，换风格不需改结构。

实现时对应的 Element Plus 主题要点：浅色模式默认变量不做深色覆盖；主色改为近黑系而非 Element Plus 默认主蓝；`el-table` 去掉斑马纹、保留表头底色与分隔线；`el-statistic` 不用卡片墙，指标压成一行文字条（对齐本方案「KPI 是文字不是卡片」的规则）。

---

# 附录 A · 数字溯源表

> 页面上出现的每个数字 → `poc/kbgovernance/` 下的出处。**不在表中的数字不得出现在页面。**

| 数字 | 值 | 出处（文件 + 列/键） |
|---|---|---|
| 文档数 | 300 | `poc/kbgovernance/metrics.json` → `embedding.n_docs` |
| 工单数 | 2000 | `metrics.json` → `embedding.n_tickets` |
| 文档段落数 | 1852 | `metrics.json` → `embedding.n_passages` |
| 向量化文本规模 | 4152 | 派生：300 + 2000 + 1852（均由 `metrics.json` 得出） |
| 缺口阈值 | 0.62 | `metrics.json` → `gap.best.threshold` |
| 缺口命中簇 | 7 | `metrics.json` → `gap.best.gap_clusters`（= `gap.n_gap_clusters`） |
| 缺口涉及业务意图 | 5 | `metrics.json` → `gap.best.detected_intents` |
| 缺口 P / R / F1 | 0.800 / 0.800 / 0.800 | `metrics.json` → `gap.best.precision/recall/f1` |
| 缺口意图覆盖度区间 | 0.5629–0.6179 | `gap_intents_best.csv` → `min_cover_median` |
| 缺口意图工单总数区间 | 62–85 | `gap_intents_best.csv` → `total_tickets` |
| 缺口意图簇数 | 3（5 个意图均为 3） | `gap_intents_best.csv` → `n_clusters` |
| 腐化阈值 | 3 | `metrics.json` → `corrupt.score_threshold` |
| 腐化检出文档 | 69 | `metrics.json` → `corrupt.detected` |
| 腐化埋入文档 | 62 | `metrics.json` → `corrupt.embedded` |
| 腐化 TP / FP / FN | 62 / 7 / 0 | `metrics.json` → `corrupt.tp/fp/fn` |
| 腐化 · 内容过期口径 P / R / F1 | 1.0000 / 1.0000 / 1.0000 | `metrics.json` → `corrupt.by_cause.content_expiry.{precision,recall,f1}` |
| 腐化 · 维护周期口径 P / R / F1 | 0.8158 / 1.0000 / 0.8986 | `metrics.json` → `corrupt.by_cause.maintenance.{precision,recall,f1}` |
| 腐化规则权重 | R1 3 / R2 2 / R3 2 / R4 1 | `metrics.json` → `corrupt.rule_weight` |
| 腐化规则命中数 | R1 32 / R2 38 / R3 32 / R4 88 | `metrics.json` → `corrupt.rule_hit_counts`（口径：全部 300 篇） |
| 腐化风险分分布 | 0:186 / 1:45 / 3:37 / 5:26 / 6:5 / 8:1 | `metrics.json` → `corrupt.score_hist`（与 `corrupt_docs.csv` 实测一致） |
| 腐化误报来源 | 对照 6 / 重复继承 1 | `metrics.json` → `corrupt.by_cause.maintenance.fp_attribution`（`control_stale`=6 / `dup_inherited_stale`=1） |
| 重复阈值 | 0.95 | `metrics.json` → `dup.best.threshold` |
| 重复组数 | 22 | `metrics.json` → `dup.best.dup_groups` |
| 重复覆盖文档 | 49 | `metrics.json` → `dup.best.detected_docs` |
| 重复 P / R / F1 | 1.0000 / 1.0000 / 1.0000 | `metrics.json` → `dup.best.group_precision/group_recall/group_f1`（乐观值，论文附录 D 已标注） |
| 组内最大余弦区间 | 0.9545–0.9845 | `dup_groups_best.csv` → `max_sim`（22 行） |
| 组规模分布 | 3 篇 × 5 组；2 篇 × 17 组 | `dup_groups_best.csv` → `size` |
| 向量化耗时 | 14.61 秒 | `metrics.json` → `embedding.encode_seconds` |
| 腐化检测耗时 | 0.4 秒 | `metrics.json` → `corrupt.seconds` |
| 重复检测耗时 | 0.0 秒 | `metrics.json` → `dup.best.seconds` |
| 三模块检测段合计 | 3.09 秒 | `metrics.json` → `total_seconds`（**仅覆盖检测段**） |
| 聚类参数 | mcs=5 → 95 簇 / 0 噪声 | `metrics.json` → `gap.best.min_cluster_size`、`gap.clusters["5"]` |
| 需求阈值 | 全量扫描 ≤ 60 秒；页面响应 ≤ 2 秒 | `docs/技术方案/本科版实施方案.md` §2 验收标准（**需求阈值，非实测**） |
| 工单正文过短下限 | 20 字 | `docs/技术方案/企业知识库质量治理系统技术方案.md` §3.3 UC1 异常流（规则，非指标） |
| `linked_doc_id` 非空工单数 | 1629 / 2000 | `docs/技术方案/开发前准备清单.md` A17（实测统计） |

**无出处的项（界面只能写定性表述）**：

| 想显示的东西 | 处置 |
|---|---|
| 聚类耗时 | 无产物键 → 写「—」+「聚类耗时未落盘」 |
| 知识缺口识别阶段耗时 | 契约 `seconds.gap` 为 null，无产物键 → 写「—」 |
| 全链路总耗时 | `metrics.json` 无此字段 → **禁止显示合计秒数**，只列分项 |
| 端到端页面响应实测 | 未做压测（范围收缩项）→ 只写需求阈值并标注「非实测」 |
| 语义覆盖度「严重/中等/轻微」切点 | 无产物字段 → 不分档（见 9.4） |
| 主文档选举的权重具体数值 | 产物只给归一化合成式描述 → 只写定性表述 |

---

# 附录 B · 原型样例数据（直接取自产物，供 Open Design 填充）

**知识缺口**（`gap_intents_best.csv` 全 5 行，全部 5 行都进列表；判定单元是业务意图）：

| rank | intent | size | cover_median | rep_ticket | rep_text |
|---|---|---|---|---|---|
| 1 | 公积金提取材料 | 18 | 0.5629 | TK00119 | 租房提取和购房提取材料一样吗，麻烦帮忙确认一下流程 |
| 2 | 海外出差报销标准 | 28 | 0.5712 | TK00004 | 去东南亚出差的住宿标准是多少，麻烦帮忙确认一下流程 |
| 3 | 海外出差报销标准 | 26 | 0.5728 | TK01795 | 海外出差津贴怎么算币种，麻烦帮忙确认一下流程 |
| 4 | 密码策略例外申请 | 19 | 0.604 | TK00009 | 系统强制改密码和我的老密码冲突，能申请例外吗 |
| 5 | 社保转移办理 | 25 | 0.6083 | TK00023 | 跨省社保转移多久能到账，麻烦帮忙确认一下流程 |
| 6 | 社保转移办理 | 29 | 0.6175 | TK00046 | 社保转移现在要线上还是线下，麻烦帮忙确认一下流程 |
| 7 | 终端病毒处置 | 21 | 0.6179 | TK00279 | 终端要隔离重装吗，麻烦帮忙确认一下流程 |

> 7 行全部为命中行（`cover_median < 0.62`）；rank 8–15 的覆盖度 0.624–0.6398 不在清单内。

**内容腐化**（`corrupt_docs.csv` 真实行，覆盖四档；`rule_hits` 与 `reasons` 为原值）：

| doc_id | title | category | last_modified | risk_score | rule_hits | 档 |
|---|---|---|---|---|---|---|
| DOC0241 | 关于客户信息查询授权适用范围的说明（第21版） | 客户服务 | 2024-05-26 | 8 | R1_正文过期日期｜R2_更新时间超18个月｜R3_正文含绝对过期年份｜R4_同类存在更新文档 | 最高风险 |
| DOC0171 | 关于合同用印审批所需材料的说明（第15版） | 采购合同 | 2025-08-13 | 6 | R1_正文过期日期｜R3_正文含绝对过期年份｜R4_同类存在更新文档 | 高 |
| DOC0243 | 关于客户信息查询授权所需材料的说明（第21版） | 客户服务 | 2026-02-13 | 5 | R1_正文过期日期｜R3_正文含绝对过期年份 | 中 |
| DOC0101 | 关于VPN远程接入申请额度标准的说明（第9版） | 信息技术 | 2025-01-05 | 3 | R2_更新时间超18个月｜R4_同类存在更新文档 | 低（达阈值） |

`reasons` 原值样例（DOC0241）：「正文含早于2026年的日期表述+过期标记词; last_modified=2024-05-26, 距基准日超过18个月; 正文含绝对过期年份 [2024]; 同'客户服务'下有 9 篇更新且标题重合的文档」——展开区按分号拆条展示，原文保留。

**重复冗余**（`dup_groups_best.csv` 样例）：

| group | size | primary_doc | member_docs | max_sim | severity |
|---|---|---|---|---|---|
| 1 | 3 | DOC0003 | `DOC0001｜DOC0002｜DOC0003` | 0.9824 | 3 篇成组 |
| 18 | 2 | DOC0206 | `DOC0205｜DOC0206` | 0.9545 | 2 篇成组（全表最低相似度） |
| 22 | 2 | DOC0254 | `DOC0253｜DOC0254` | 0.9766 | 2 篇成组 |

---

# 附录 C · 待拍板项（影响原型，需需求方确认）

| 编号 | 事项 | 影响 | 建议 |
|---|---|---|---|
| OPEN-1 | 扫描是否清空文档表（契约推导出"清空"） | 页面一是否需要"重新上传"提示；页面二清库确认文案 | 若保留语料可省一次上传；否则需在 UI 上明说 |
| OPEN-2 | 清单默认排序方向的最终口径（契约暂按降序，README 歧义 1） | 列表固定顺序文案 | 保持"固定降序、不可点击切换"，文案写"按 X 降序（固定）" |
| OPEN-3 | 重复检测阈值取 0.95 还是 0.90（README 歧义 4） | 重复 Tab 的阈值与命中数（22 组/49 篇 ↔ 32 组/77 篇） | 以本次扫描实际采用值为准，界面显示接口返回的 threshold，不写死 |
| OPEN-4 | 缺口清单是否允许按意图去重 | 同轮命中 7 簇但仅 5 个业务意图，是否分组展示 | 建议不去重（保持 rank 顺序），在展开区提示 |
| OPEN-5 | 知识缺口是否需要离散严重度档位 | 需自造覆盖度切点 | 若需要，切点先登记进派生指标登记表再上页面 |
| OPEN-6 | 重复清单 P/R/F1 用组级还是文档级（README 歧义 5） | 指标条数值 | 本轮两者同为 1.0，建议标注"组级口径" |
| OPEN-7 | 无评测基线语料下指标条怎么显示（A13） | 页面是否出现「—」 | 按本规格显示「—」+ 说明 |
| OPEN-8 | 视觉基调选哪套 | 全部三页配色 | 见第五部分选型建议 |
