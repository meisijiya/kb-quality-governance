# system/ —— W7–W9 Web 交付的机器可读契约**草案**

> **状态：草案，未定稿。** 本目录是开发前准备阶段的**讨论素材**，不是已确认的契约。
> 依据来源 Issue #3 已关闭（2026-10-23 撤回分派 → 2026-10-24 按需求方要求关闭），
> 其正文不再是已确认的规格；API 取舍范围、数据形态、产品形态、UI 形态、功能范围、
> 交互细节、视觉文案七项的需求方拍板记录见 `docs/技术方案/开发前准备清单.md` §4.11。

本目录的三个文件：

| 文件 | 内容 | 消费方 |
|---|---|---|
| `schema.sql` | 6 张表的 SQLite 建表脚本（幂等，可重复执行）+ 迁移组织方式 + 查询路径→索引对照 | 后端建库 / 迁移 |
| `openapi.yaml` | 15 条路径 / 17 个操作 / 22 个 schema 的 OpenAPI 3.0 契约草案 | 讨论用；定稿后才供实现消费 |
| `README.md` | 本说明 | 人 |

本轮**只落草案，不含实现代码**：没有 FastAPI 应用、没有前端工程、没有依赖清单。

---

## 已按需求方口径落地的部分（2026-10-24）

需求方对 P1 / P2 / P5 / P3 给出了明确口径，契约已按该口径改写：

| 拍板项 | 口径 | 契约内的体现 |
|---|---|---|
| P1 API 契约范围 | 按推荐 | 15 条路径、22 个 schema；错误码枚举 10 个且**每个码值至少被一条路径引用**（无引用即不得留在枚举里）；补 422 + `VALIDATION_FAILED`，把 FastAPI 默认的 `{"detail":[...]}` 收编进统一错误体 |
| P1（附带）排序口径 | 按实施口径砍掉列排序 | 三个清单接口**不再提供 `sort` 参数**；行序 = 源 CSV 行序，由响应里的 `row_order` 字段声明，每一档行序都能按「文件路径 + 列名」复核 |
| P2 数据形态 | 按推荐，保证查询性能 | 指向文档的三个外键改 `TEXT` 并指向 `document(doc_code)`（与源数据真实语义一致）；指向簇的外键改三列复合键 `(granularity, min_cluster_size, cluster_id)`；索引 8 → **12 个**（补齐四个外键列的索引），并在 `schema.sql` 内给出 9 条典型查询 → 索引对照 |
| P3 产品形态 | 前后端分离 + 一条命令启动前后端 | 后端单进程（FastAPI + uvicorn）挂载前端构建产物；SQLite 走 WAL；契约的 `GET /` 即静态挂载点。启动形态与验收信号见 §4 |
| P5 功能范围 | 必要的 CRUD 要有 | 文档与工单各自提供 **POST（导入）/ GET（查询）/ DELETE（单条 + 整批清空）**；三类缺陷清单只读；内容字段落库后只读（在线编辑已按实施方案 §3 砍掉） |
| — 指标诚实性 | 无真值不编指标 | 三个清单的 envelope 新增 `has_ground_truth`；`precision` / `recall` / `f1` 改为**可为 null**（无真值语料时恒为 null，不是 0） |

仍需需求方拍板的地方，契约文件内一律以 **【待拍板】** 标注，不得当作已确认的契约。

---

## 为什么在实现之前先把契约落盘

1. **工单不是机器可读的。** 接口细节写在 GitHub Issue #3 正文里，人能读、前后端各写各的时会各自发明字段名、错误体和排序参数，联调期改一次的成本远高于落盘一次。
2. **契约要能被机械校验。** 建表脚本能被 `sqlite3` 幂等执行、OpenAPI 能被 `yaml.safe_load` 解析并数出路径数，于是「实现是否对齐契约」有了唯一判据，而不是靠人读文档。
3. **数字纪律在这里生效。** 契约里出现的每个指标值都来自 `poc/kbgovernance/metrics.json` 与对应 CSV（`top15_gaps.csv` / `corrupt_docs.csv` / `dup_groups_best.csv`），不从叙述性文本反推、不在前端代码里写死。先落盘等于先把数字的出处钉死。
4. **前端类型由后端 OpenAPI 生成。** 契约先行，前端的 TS 类型才有单一来源，不会出现「后端改了字段名、前端还按旧名编译」。

---

## 如何验证

在仓库根目录执行（两条命令分别验证「建表脚本幂等且表名恰为 6 张、索引 12 个」与「OpenAPI 可解析且路径恰为 15 条」）：

```bash
cd /d/26code/毕设 && python - <<'PY'
import os, sqlite3
p = '/tmp/ct.sqlite'
os.path.exists(p) and os.remove(p)
sql = open('system/schema.sql', encoding='utf-8').read()
for i in (1, 2):
    c = sqlite3.connect(p)
    c.executescript(sql)
    print('run', i, sorted(r[0] for r in c.execute(
        "select name from sqlite_master where type='table'")))
    print('  idx =', c.execute(
        "select count(*) from sqlite_master where type='index' and name like 'idx_%'").fetchone()[0],
        'user_version =', c.execute('PRAGMA user_version').fetchone()[0])
    c.close()
PY
```

期望输出（同一脚本连续执行两次，第二次不报错、不清空已有数据）：

```
run 1 ['cluster_result', 'document', 'duplicate_group', 'knowledge_gap', 'stale_document', 'ticket']
  idx = 12 user_version = 1
run 2 ['cluster_result', 'document', 'duplicate_group', 'knowledge_gap', 'stale_document', 'ticket']
  idx = 12 user_version = 1
```

```bash
cd /d/26code/毕设 && python -c "import yaml;d=yaml.safe_load(open('system/openapi.yaml',encoding='utf-8'));print(d['openapi'],len(d['paths']),len(d['components']['schemas']))"
```

期望输出：

```
3.0.3 15 22
```

---

## 实现须知（读契约前先看这 10 条）

1. **表结构以本目录的 `schema.sql` 为准**，它与 `docs/技术方案/企业知识库质量治理系统技术方案.md` §4.3 有两处已记录的差异，均写在 `schema.sql` 头部：①主键由 `INTEGER PRIMARY KEY AUTOINCREMENT` 改为 `INTEGER PRIMARY KEY`（`AUTOINCREMENT` 会让 SQLite 自动创建内部表 `sqlite_sequence`，上面第一条命令的输出就不再是 6 张表；行号语义不变）；②指向文档的三个外键（`ticket.linked_doc_id` / `stale_document.document_id` / `duplicate_group.primary_doc_id`）改为 `TEXT` 并指向 `document(doc_code)`，指向簇的外键改为三列复合外键 `(granularity, min_cluster_size, cluster_id)`——因为源数据里用的是文档编码文本与 HDBSCAN 标签，不是行号。**第 ② 处改变了数据形态，属 P2 待拍板范围，`schema.sql` 头部已写出「推荐 + 代价 + 备选」。**
2. **类型约定。** 日期与时间以 ISO-8601 文本存 `TEXT` 列（字典序即时间序，索引仍可用）；`duplicate_group.member_doc_ids` 存 JSON 数组，不为「重复组—文档」多对多关系再引入第七张表。
3. **时间精度分两类，不可跨表直接比较。** `document.*` 的三个时间列精度到**日**（10 字符，源自 `docs.csv`）；`ticket.created_at` 精度到**分钟**（16 字符，源自 `tickets.csv`）；结果表的 `created_at` / `detected_at` 是扫描时刻。跨表做时间范围过滤必须先统一精度（推荐一律归一到日）。
4. **三类清单的行来自扫描落盘的 CSV**，字段名与 CSV 列一致（`category` / `doc_id` / `member_docs` 等沿用 CSV 写法，落库时才映射到 `document.domain` / `document.doc_code` / `duplicate_group.member_doc_ids`）。三个接口都返回「行 + 本次 threshold + 本次 P/R/F1 + row_order」。**清单接口不透出真值标注列**（`is_true_gap` / `is_true_group` 及腐化清单的归因列），真值只留在产物文件与论文中；下载件保留全量列。
5. **阈值与主指标一律从本次扫描落盘的 `metrics.json` 读**，前端不写死；清单接口**不实现分页、不提供列排序参数**，行序由 `row_order` 声明。**无真值语料时 `has_ground_truth=false` 且 P/R/F1 为 `null`**（不是 0）。
6. **错误响应体统一**为 `{code, message, location}`：机器可读错误码 + 中文说明 + 出错位置。请求体结构不合法返回 **422 + `VALIDATION_FAILED`**，与其它错误码同一形状。错误码枚举：`INVALID_IMPORT_FILE` / `VALIDATION_FAILED` / `DUPLICATE_DOC_CODE` / `DUPLICATE_TICKET_CODE` / `EMPTY_CORPUS` / `SCAN_IN_PROGRESS` / `SCAN_FAILED` / `MODEL_WEIGHTS_MISSING` / `DOWNLOAD_NOT_FOUND` / `NOT_FOUND`——**新增码值时必须同时给出一条引用它的路径，否则不得进枚举**。
7. **导入整批一次事务**：全成功或全回滚，不留半截数据；`doc_code` / `ticket_code` 重复在导入时即拒绝，并返回冲突的编码值（文档与工单用**不同**的错误码）。删除文档时先把引用它的 `stale_document` / `duplicate_group` 行删掉、把仍引用它的 `ticket.linked_doc_id` 置 NULL，再删 `document` 本身。
8. **扫描同步跑完**「向量化 → 聚类 → 三模块检测 → 落库」，产物落盘的文件名与路径和 `run_all.sh` 完全一致，因此「下载的 CSV 与磁盘源文件逐字节一致」与「Web 产物 vs 复跑产物逐字节一致」是同一条性质的验证。**逐字节一致按文件分档**：三个清单 CSV 成立；`metrics.json` 含计时字段，只能「剔除计时字段后一致」（口径见 `poc/kbgovernance/repro_check.json`）。`POST /api/scan` 的请求体用 `mode` 区分**复现模式**（沿用已固化阈值）与**自有语料模式**（不按真值择优）。
9. **数据库连接要逐个开外键**：`PRAGMA foreign_keys` 是连接级开关，建表脚本里那句只对执行它的连接生效，应用在**每个连接**上都要设（实测：新连接默认 `0`）。清库按外键依赖的子表 → 父表顺序执行（`knowledge_gap` → `cluster_result`，`stale_document` / `duplicate_group` → `document`），否则报 `FOREIGN KEY constraint failed`。
10. **扫描产物落盘目录尚未拍板（A1/A10）。** 若与 `poc/kbgovernance/` 共用目录，Web 扫描会覆盖论文溯源基线，并连带作废 `repro_check.json` 的逐字节基线；隔离方案与取舍见 `docs/技术方案/开发前准备清单.md` §4.10 A1。

---

## P3 形态：一条命令启动前后端（2026-10-24 需求方口径）

- **形态**：前后端彻底分离，但**现场只有一条命令**。后端是单进程（FastAPI + uvicorn），把前端构建产物静态挂载在同一端口；SQLite 以 WAL 模式运行。
- **答辩现场的启动顺序**：一条命令拉起后端 → 打开浏览器访问根路径即进入前端 → 现场跑一次扫描 → 打开三类清单。现场不需要 Node 工具链（构建产物入库，见准备清单 §4.10 A4）。
- **本目录不提供启动脚本**：后端实现尚未开工（实施排在 W7–W9，见准备清单 §3 可延后清单），现在写启动脚本只能是空壳。启动命令的最终形态与验收信号记在准备清单 C11。
- **与契约的关系**：契约里的 `GET /` 就是静态挂载点，`GET /docs` 返回 OpenAPI 契约 JSON（不返回 Swagger UI 的 HTML），业务接口的响应体一律是 JSON。

---

## 已知歧义（待需求方讨论拍板，本轮不自行拍板）

契约文件对下列各点按最贴近 Issue #3 原文的写法暂定，**待确认后同步回契约**：

0. **清单是否分页。** Issue #3 要求不实现分页，实施方案 §2.2 第 104 行 与 §3 第 120 行 也把分页列为砍掉项；契约按「不分页、不提供列排序参数」写。若将来要分页，需同时改契约与实施方案两处。
1. **`GET /docs` 与 `GET /` 的返回内容。** Issue #3 的断言清单要求「后端全部响应体为 JSON，不含 HTML 页面」，但 FastAPI 默认的 `/docs` 是 Swagger UI（HTML）；契约暂按「`/docs` 返回 OpenAPI 契约 JSON」写。`GET /` 按 P3 口径是前端构建产物的静态入口（后端不渲染页面），这与「响应体不含 HTML」字面冲突，待确认该断言只针对业务接口。
2. **重复检测的阈值口径。** Issue #3 断言用 0.95（`metrics.json → dup.best`，组级 F1 1.0）；论文正文口径是 0.90（组级 F1 0.7037，见产物索引）。清单接口返回的 `threshold` 应是**本次扫描实际采用**的阈值，需确认扫描默认取哪一个。
3. **重复清单的 P/R/F1 口径。** `metrics.json → dup.best` 同时给出组级（`group_*`）与文档级（`doc_*`）两套值；契约的 envelope 暂取组级，需确认。
4. **缺口阶段耗时没有产物字段。** `metrics.json` 有 `embedding.encode_seconds` / `corrupt.seconds` / `dup.best.seconds` / `total_seconds`，但没有 `gap.seconds`；契约的 `ScanTiming.gap` 暂为 `null`，需确认是落盘时补该字段，还是保持空缺。
5. **文档上传是否也收文件。** Issue #3 同时提到「原样保存上传文件」与「校验必填列」；契约把文档与工单统一按 multipart 文件上传写，需确认是否改成 JSON 体、两种形态是否统一。
6. **扫描是否清空语料表。** 契约的 DELETE 接口存在（重导的前置动作），但「扫描是否自动清空语料表」尚未拍板；这直接决定上传页要不要「重新上传」提示与扫描确认框的文案（规格书 OPEN-1）。
7. **`linked_doc_id` 未命中是拒绝该行还是写 NULL。** 现行草案按 A17「未命中即拒绝该行」写，但 A17 的方向是建 `doc_code → id` 映射后仍存行号，与现行「存编码文本」的方案冲突；两者只能选一套。
8. **清单行字段与落库列的一处缺口。** `top15_gaps.csv` 有 `rep_cover` 列，但六表 DDL 里没有对应列（`knowledge_gap.cover_score` 存的是 `cover_median`）；新增列会偏离 §4.3 的六表 DDL，需拍板。
9. **腐化清单的行范围与判定符。** `corrupt_docs.csv` 是 300 篇逐篇打分表，不是命中清单；契约取 `risk_score >= 本次阈值` 的子集（阈值 3 时 69 行，与 `metrics.json → corrupt.detected` 一致），需确认判定用 `>=`（当前写法）而非 `>`。
10. **耗时字段是每次复跑重写的值**（`total_seconds` / `corrupt.seconds`），不是稳定指标，跨机器必然波动；契约里的示例值取自当前工作树产物。
11. **下载件是否含真值列。** `GET /api/downloads/{name}` 若原样返回源 CSV，`is_true_gap` / `is_true_group` / `in_control_sample` / `is_dup_copy` / `dup_source` / `fp_reason` 六列会一并交到用户硬盘——界面层已实测这一破口（界面藏住真值列，下载一次就泄露）。两条口径待选：**裁剪视图下载**（默认，对外不含真值列）＋ **本地复现专用全量文件**（论文复现用，只落在 `poc/kbgovernance/`），或**保留原样下载但在下载区明示「含评测标注列」**。选哪条决定 `GET /api/downloads/{name}` 的响应是 CSV 还是裁剪视图，也决定准备清单 C7 的验收方式。
12. **三个清单接口的统计单元必须显式标注。** 缺口清单的 count 单位是「缺口簇」、腐化清单是「篇文档」、重复清单是「组」；而缺口 P/R/F1 的分母是**去重后的业务意图数**（`detect.py:117-125`，当前为 5），与「7 个缺口簇」不是同一个数（簇级真值 6/7=0.8571 ≠ 页面 0.800）。契约的 `count` 与 envelope 里的 P/R/F1 需要各自带单位标注，否则读者按簇级复算必错。

---

## P6 评审结论（2026-10-24 子代理 ego-browser 交叉评估，三份独立报告）

需求方口径：交互细节交由子代理用 `/ego-browser` 体验原型来评估，多个子代理交叉验证。三份报告各自独立走查、互不参考，结论已回写 `docs/技术方案/开发前准备清单.md` §2.8（H1 ~ H7）：

| 报告 | 发现条数 | 分布 | 落点 |
|---|---|---|---|
| 交互规范 | 20 | 阻塞 1 / 高 3 / 中 8 / 低 8 | H1（H1 上传无响应 = 阻塞）、H2、H3、H4 |
| 操作效率 | 24 | 阻断 2 / 高 9 / 中 8 / 低 5 | H1、H2、H3 |
| 数据呈现与可信度 | 26 | 阻塞 2 / 高 9 / 中 12 / 低 3 | H3、H5、H6、H7 |

**其中两条直接落在契约上，不只是原型问题**：

1. **下载通道泄露真值列**（C1，阻塞）→ 上面「已知歧义」第 11 条。
2. **统计单元未声明**（C2，阻塞）→ 上面「已知歧义」第 12 条。

另有两处口径与本目录的实现须知相关：**耗时口径**——`metrics.json → total_seconds` 是 `detect.py` 主流程全程（读 CSV + 聚类 + 三检测），不含向量化；`dup.best.seconds` 只包住阈值分组循环，不含 300×300 余弦矩阵（该矩阵只 `print` 不落盘）。契约的 `ScanTiming` 描述需按实际计时范围表述，不能让前端复算出分项。

评审同时确认的底线（不必重复查）：界面 DOM 全量扫描真值列 0 泄漏；「—」不填 0、降级不补数；F1=1.0000 乐观值提醒 4 处都在；重复清单 22 行与产物逐行一致且下载 = 展示；28 组关键数字逐行对上产物。

---

## 契约变更流程

```
改 system/ 下的契约文件（schema.sql / openapi.yaml）
        ↓
回写 docs/技术方案/开发前准备清单.md（拍板记录 + 冲突处置）
        ↓
前端类型由后端 OpenAPI 生成（后端契约是 TS 类型的唯一来源，不手写）
```

**顺序不可颠倒：先改契约文件，再回写清单，最后生成前端类型。** 任何一处单独改动都会让「契约—清单—前端类型」三者失配。

> **关于工单同步**：原流程的第二步是「同步 Issue #3」。该工单已于 2026-10-24 按需求方要求关闭，契约变更不再回写工单正文；改为回写准备清单。待 W7 开工时，若要把定稿契约分配到人，再按 §3 可延后清单的规则新开工单——**不得依赖已关闭的工单承载未开工的工作**。

新增或修改接口时，同步更新：

- `system/openapi.yaml` 的 `paths` 与 `components.schemas`；
- `system/schema.sql`（涉及表结构变化时，且按幂等方式改写，并递增 `PRAGMA user_version`）；
- 本文件「已知歧义」中被拍板的条目（拍板后从列表移除，不留并列的旧写法）；
- `docs/技术方案/开发前准备清单.md` 的对应条目。
