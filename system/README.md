# system/ —— W7–W9 Web 交付的机器可读契约**草案**

> **状态：草案，未定稿。** 本目录三个文件是开发前准备阶段的**讨论素材**，不是已确认的契约。
> 依据来源 Issue #3 已撤回为 `needs-triage`（2026-10-23），其正文不再是已确认的规格；
> API 取舍范围、产品形态（前后端分离与否）、UI 形态、功能范围均尚未与需求方讨论定案。
> 待拍板项见 `docs/技术方案/开发前准备清单.md` §4，冲突项见本文件「已知歧义」。

本目录只有三个文件：

| 文件 | 内容 | 消费方 |
|---|---|---|
| `schema.sql` | 6 张表的 SQLite 建表脚本（幂等，可重复执行） | 后端建库 / 迁移 |
| `openapi.yaml` | 13 个接口的 OpenAPI 3.0 契约草案 | 讨论用；定稿后才供实现消费 |
| `README.md` | 本说明 | 人 |

本轮**只落草案，不含实现代码**：没有 FastAPI 应用、没有前端工程、没有依赖清单。

---

## 为什么在实现之前先把契约落盘

1. **工单不是机器可读的。** 接口细节写在 GitHub Issue #3 的正文里，人能读、前后端各写各的时会各自发明字段名、错误体和排序参数，联调期改一次的成本远高于落盘一次。
2. **契约要能被机械校验。** 建表脚本能被 `sqlite3` 幂等执行、OpenAPI 能被 `yaml.safe_load` 解析并数出 13 条路径，于是「实现是否对齐契约」有了唯一判据，而不是靠人读文档。
3. **数字纪律在这里生效。** 契约里出现的每个指标值都来自 `poc/kbgovernance/metrics.json` 与对应 CSV（`top15_gaps.csv` / `corrupt_docs.csv` / `dup_groups_best.csv`），不从叙述性文本反推、不在前端代码里写死。先落盘等于先把数字的出处钉死。
4. **前端类型由后端 OpenAPI 生成。** 契约先行，前端的 TS 类型才有单一来源，不会出现「后端改了字段名、前端还按旧名编译」。

---

## 如何验证

在仓库根目录执行（两条命令分别验证「建表脚本幂等且表名恰为 6 张」与「OpenAPI 可解析且路径恰为 13 条」）：

```bash
cd /d/26code/毕设 && python -c "import sqlite3,os;os.remove('/tmp/ct.sqlite') if os.path.exists('/tmp/ct.sqlite') else None;c=sqlite3.connect('/tmp/ct.sqlite');c.executescript(open('system/schema.sql',encoding='utf-8').read());c.executescript(open('system/schema.sql',encoding='utf-8').read());print(sorted(r[0] for r in c.execute(\"select name from sqlite_master where type='table'\")))"
```

期望输出（同一脚本连续执行两次，第二次不报错、不清空已有数据）：

```
['cluster_result', 'document', 'duplicate_group', 'knowledge_gap', 'stale_document', 'ticket']
```

```bash
cd /d/26code/毕设 && python -c "import yaml;d=yaml.safe_load(open('system/openapi.yaml',encoding='utf-8'));print(d['openapi'],len(d['paths']),sorted(d['paths']))"
```

期望输出：

```
3.0.3 13 ['/', '/api/corpus/stats', '/api/documents', '/api/downloads/{name}', '/api/duplicates', '/api/gaps', '/api/health', '/api/metrics', '/api/scan', '/api/scan/status', '/api/stale', '/api/tickets', '/docs']
```

---

## 实现须知（读契约前先看这 9 条）

1. **表结构以本目录的 `schema.sql` 为准**，它与 `docs/技术方案/企业知识库质量治理系统技术方案.md` §4.3 有两处已记录的差异，均写在 `schema.sql` 头部：①主键由 `INTEGER PRIMARY KEY AUTOINCREMENT` 改为 `INTEGER PRIMARY KEY`（`AUTOINCREMENT` 会让 SQLite 自动创建内部表 `sqlite_sequence`，上面第一条命令的输出就不再是 6 张表；行号语义不变）；②指向文档的三个外键（`ticket.linked_doc_id` / `stale_document.document_id` / `duplicate_group.primary_doc_id`）改为 `TEXT` 并指向 `document(doc_code)`，指向簇的外键改为三列复合外键 `(granularity, min_cluster_size, cluster_id)`——因为源数据里用的是文档编码文本与 HDBSCAN 标签，不是行号。**第 ② 处改变了数据形态，属于 P2 待拍板范围。**
2. **类型约定。** 日期与时间以 ISO-8601 文本存 `TEXT` 列（字典序即时间序，索引仍可用）；`duplicate_group.member_doc_ids` 存 JSON 数组，不为「重复组—文档」多对多关系再引入第七张表。
3. **三类清单的行来自扫描落盘的 CSV**，字段名与 CSV 列一致（`category` / `doc_id` / `member_docs` 等沿用 CSV 写法，落库时才映射到 `document.domain` / `document.doc_code` / `duplicate_group.member_doc_ids`）。三个接口都返回「行 + 本次 threshold + P/R/F1」。**清单接口不透出真值标注列**（`is_true_gap` / `is_true_group` 及腐化清单的归因列），真值只留在产物文件与论文中。
4. **阈值与主指标一律从本次扫描落盘的 `metrics.json` 读**，前端不写死；清单接口只支持一档排序参数，**不实现分页**，且排序参数的取值就是清单行的字段名（`size` / `risk_score` / `max_sim`）。
5. **错误响应体统一**为 `{code, message, location}`：机器可读错误码 + 中文说明 + 出错位置。请求体结构不合法返回 **422 + `VALIDATION_FAILED`**，与其它错误码同一形状。
6. **导入整批一次事务**：全成功或全回滚，不留半截数据；`doc_code` / `ticket_code` 重复在导入时即拒绝，并返回冲突的编码值。
7. **扫描同步跑完**「向量化 → 聚类 → 三模块检测 → 落库」，产物落盘的文件名与路径和 `run_all.sh` 完全一致，因此「下载的 CSV 与磁盘源文件逐字节一致」与「Web 产物 vs 复跑产物逐字节一致」是同一条性质的验证。**逐字节一致按文件分档**：三个清单 CSV 成立；`metrics.json` 含计时字段，只能「剔除计时字段后一致」（口径见 `poc/kbgovernance/repro_check.json`）。
8. **数据库连接要逐个开外键**：`PRAGMA foreign_keys` 是连接级开关，建表脚本里那句只对执行它的连接生效，应用在**每个连接**上都要设（实测：新连接默认 `0`）。清库按外键依赖的子表 → 父表顺序执行（`knowledge_gap` → `cluster_result`，`stale_document` / `duplicate_group` → `document`），否则报 `FOREIGN KEY constraint failed`。
9. **扫描产物落盘目录尚未拍板（A1）。** 若与 `poc/kbgovernance/` 共用目录，Web 扫描会覆盖论文溯源基线，并连带作废 `repro_check.json` 的逐字节基线；隔离方案与取舍见 `docs/技术方案/开发前准备清单.md` §4.10 A1。

---

## 已知歧义（待需求方讨论拍板，本轮不自行拍板）

契约文件对下列各点按最贴近 Issue #3 原文的写法暂定，**待确认后同步回契约与工单**：

0. **D1 清单页是否支持列排序（跨文档冲突，优先级最高）。** Issue #3 第 201 行要求清单接口提供最小排序参数（工单数 / 风险分 / 组内最大相似度）且不实现分页，其 US25 同样要求排序能力；而 `docs/技术方案/本科版实施方案.md` §2.2 第 104 行把清单页收敛为「列表 + 展开详情（不分页、不做列排序、不做独立详情页与路由跳转）」，§3 砍掉表 第 120 行同样把「列排序」列为砍掉项。契约中三个 `sort` 参数目前是**占位**，两种口径的取舍未决。
1. **排序方向未定义。** Issue #3 只写「最小排序参数（工单数 / 风险分 / 组内最大相似度）」，未说明升序还是降序；契约暂按「降序（最严重的在前）」。
2. **`GET /docs` 的返回内容。** Issue #3 的断言清单要求「后端全部响应体为 JSON，不含 HTML 页面」，但 FastAPI 默认的 `/docs` 是 Swagger UI（HTML）；契约暂按「`/docs` 返回 OpenAPI 契约 JSON」写，需确认是改挂 `/openapi.json`，还是该断言只针对业务接口。
3. **`GET /` 返回 HTML。** Issue #3 的端点表里有 `GET /`，同时又要求响应体不含 HTML；契约暂按「前端构建产物的静态入口（后端不渲染页面）」写，需确认该端点的实际职责。
4. **重复检测的阈值口径。** Issue #3 断言用 0.95（`metrics.json → dup.best`，组级 F1 1.0）；论文正文口径是 0.90（组级 F1 0.7037，见产物索引）。清单接口返回的 `threshold` 应是**本次扫描实际采用**的阈值，需确认扫描默认取哪一个。
5. **重复清单的 P/R/F1 口径。** `metrics.json → dup.best` 同时给出组级（`group_*`）与文档级（`doc_*`）两套值；契约的 envelope 暂取组级，需确认。
6. **缺口阶段耗时没有产物字段。** `metrics.json` 有 `embedding.encode_seconds` / `corrupt.seconds` / `dup.best.seconds` / `total_seconds`，但没有 `gap.seconds`；契约的 `ScanTiming.gap` 暂为 `null`，需确认是落盘时补该字段，还是保持空缺。
7. **错误码枚举与字段名未定。** Issue #3 只规定「机器可读错误码 + 中文说明 + 出错位置」，未给具体码值与字段名；契约暂用 `code` / `message` / `location`，码值见 `components.schemas.Error`。
8. **`POST /api/documents` 的请求体形状。** Issue #3 同时提到「原样保存上传文件」与「校验必填列」；契约暂按 JSON 体 `{documents: [...]}` 写（`doc_code` / `title` / `content` / `last_modified` 必填），需确认是否与工单一样走文件上传。
9. **腐化清单的行范围。** `corrupt_docs.csv` 是 300 篇逐篇打分表，不是命中清单；契约取 `risk_score >= 本次阈值` 的子集（阈值 3 时 69 行，与 `metrics.json → corrupt.detected` 一致），需确认判定用 `>=`（当前写法）而非 `>`。
10. **耗时字段是每次复跑重写的值**（`total_seconds` / `corrupt.seconds`），不是稳定指标，跨机器必然波动；契约里的示例值取自当前工作树产物。

---

## 契约变更流程

```
改 system/ 下的契约文件（schema.sql / openapi.yaml）
        ↓
同步 Issue #3（工单正文是契约的对外说明，两者必须一致）
        ↓
前端类型由后端 OpenAPI 生成（后端契约是 TS 类型的唯一来源，不手写）
```

顺序不可颠倒：**先改契约文件，再同步工单，最后生成前端类型**。任何一处单独改动都会让「契约—工单—前端类型」三者失配。

新增或修改接口时，同步更新：

- `system/openapi.yaml` 的 `paths` 与 `components.schemas`；
- `system/schema.sql`（涉及表结构变化时，且按幂等方式改写）；
- Issue #3 正文；
- 本文件「已知歧义」中被拍板的条目（拍板后从列表移除，不留并列的旧写法）。
