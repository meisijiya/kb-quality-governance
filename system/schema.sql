-- ============================================================================
-- 企业知识库质量治理系统 —— 数据库建表脚本（机器可读契约**草案**）
--
-- 状态：草案，未定稿。来源工单 Issue #3 已撤回为 needs-triage（2026-10-23），
--       其正文不再是已确认的规格来源；表结构本身取自技术方案 §4.3「数据库设计」，
--       拍板与讨论记录见 docs/技术方案/开发前准备清单.md §4。
--
-- 来源：docs/技术方案/企业知识库质量治理系统技术方案.md §4.3「数据库设计」
-- 契约（草案）：GitHub Issue #3「数据库（6 张表）」小节
--
-- 6 张表：document / ticket / cluster_result / knowledge_gap / stale_document
--         / duplicate_group
--   · document / ticket                —— 扫描的输入语料
--   · cluster_result / knowledge_gap / stale_document / duplicate_group
--                                    —— 三模块检测的落库目标
--
-- 幂等：全部 CREATE TABLE / CREATE INDEX 均带 IF NOT EXISTS，重复执行不报错、
--       不清空已有数据。
--
-- 执行方式（二选一）：
--   sqlite3 kbgovernance.sqlite < system/schema.sql
--   python -c "import sqlite3;sqlite3.connect('kbgovernance.sqlite').executescript(
--              open('system/schema.sql',encoding='utf-8').read())"
--
-- 与 §4.3 原文的差异（全部记录在案，未自行抹平）：
--   1) 主键：§4.3 原文写作 `INTEGER PRIMARY KEY AUTOINCREMENT`。AUTOINCREMENT 会让
--      SQLite 自动创建内部表 sqlite_sequence，使「库中 6 张业务表」变成 7 项。
--      为使验收命令的输出恰好是 6 张表，主键改用 `INTEGER PRIMARY KEY`：
--      行号语义不变（仍是 rowid 别名、仍自增），仅去掉 sqlite_sequence 记账。
--      要严格对齐 §4.3 原文，把 6 处改回 AUTOINCREMENT 即可，验收时过滤
--      sqlite_sequence。
--   2) 外键目标列：§4.3 原文把 ticket.linked_doc_id、stale_document.document_id、
--      duplicate_group.primary_doc_id 写成指向 document(id) 的 INTEGER 外键，把
--      knowledge_gap.cluster_id 写成指向 cluster_result(id) 的外键。实测这四个
--      外键与本项目自己的数据对不上：
--        · poc/kbgovernance/tickets.csv 的 linked_doc_id 取值是文档编码文本
--          （2000 行中 1629 行非空，全部匹配 docs.csv 的 doc_id），不是行号；
--        · poc/kbgovernance/corrupt_docs.csv 与 dup_groups_best.csv 同样用文档
--          编码而非行号指认文档；
--        · 聚类簇号（HDBSCAN 标签，0、1、2…）原先只在 detect.py 的内存里生成，
--          2026-10-25 口径更正后已落盘到 gap_clusters_best.csv 的 cluster_id 列
--          （95 行），簇号因此有了出处；但它仍不是 cluster_result.id 的自增行号。
--      因此：指向文档的三个外键改为 TEXT 并指向 document(doc_code)。
--      指向簇的 knowledge_gap.cluster_id 外键已随下文第 3 条（判定单元改业务意图）
--      一并取消。
--      **这一处改动改变了数据形态，属于 P2（数据形态）的待拍板范围**，
--      评审与拍板记录见 docs/技术方案/开发前准备清单.md §4.11 P2、§4.10 A17
--      （doc_code → document.id 的映射口径）与 §4.10 A16（每次扫描生成 scan_id）。
--   3) 判定单元与列集合：2026-10-25 口径更正后，缺口清单的**判定单元是业务意图**
--      （意图簇降为内部量与溯源），内容腐化**拆成内容过期（R1+R3）与维护周期
--      （R2+R4）两个口径各自独立判定**。§4.3 原文的 DDL 是簇级 + 单一 risk_score
--      的形态，与现行口径不一致，按「错误、过时就剔除、更正」的原则本草案改为：
--        · knowledge_gap 由「每簇一行」改为「每个业务意图一行」：删掉
--          granularity / min_cluster_size / cluster_id 三列与指向
--          cluster_result 的三列复合外键，新增 n_clusters（该意图下的簇数）。
--          cover_score 存**意图覆盖度**（该意图下各簇覆盖度的最小值），
--          ticket_count 存**该意图下的工单总数**（原为簇内工单数）。
--        · cluster_result 仍按簇存，补一列 cover_score（簇覆盖度中位数），
--          这样「某个意图由哪些簇构成、各簇覆盖度多少」可从库里查回，
--          意图级行与簇级行靠 intent_name ↔ main_intent 对应
--          （与 ticket.linked_doc_id → document(doc_code) 同样的软链接口径）。
--        · stale_document 增两列 cause_score_content_expiry /
--          cause_score_maintenance（两类口径各自的规则加权分），
--          risk_score 保留为**四规则合并分**（历史口径，不再用于任何判定）。
--      差异清单里第 2 条提到的「knowledge_gap.cluster_id 指向 cluster_result」
--      这一处因本条改动而不再适用。口径更正的依据与拍板记录见
--      docs/技术方案/开发前准备清单.md §4.11 P1、§6.2。
--
--      **推荐与代价（待拍板）——指向文档的外键**：
--        · 推荐（当前草案采用）：linked_doc_id 等三列存 doc_code 文本并指向
--          document(doc_code)，配 idx_ticket_linked_doc 等索引。理由：与 CSV 的
--          真实语义一致（tickets.csv 的 linked_doc_id 非空 1629 行全部匹配
--          docs.csv 的 doc_id），导入时不必做「编码 → 行号」的二次映射。
--          代价：① 编码列比行号宽（TEXT vs INTEGER），索引体积更大；
--          ② 文档被删后外键失效，删文档前必须先把引用它的工单外键置 NULL
--          （见 system/openapi.yaml 里 DELETE 语料的清库顺序）；
--          ③ 与 §4.3 原文的 INTEGER 外键不符，评审要显式接受这一偏离。
--        · 备选：保持 INTEGER 外键指向 document(id)，另建 doc_code → id 映射
--          （§4.10 A17 的方向）。代价：多一张表（库变 7 张表，与「6 张表」的
--          验收口径冲突），导入期多一次映射查找，且工单行里的编码值与库里
--          存的值不同源。
--
--      **推荐与代价（已随第 3 条失效）——指向簇的外键**：口径更正后
--      knowledge_gap 一行 = 一个业务意图，一个意图对应多个簇，无法用外键表达，
--      该外键已取消，改为 intent_name ↔ main_intent 软链接。
--
-- 字段映射（PoC 产物 ↔ 本库列名）：
--   docs.csv 的 doc_id      ↔ document.doc_code（取值相同，仅列名不同）
--   tickets.csv 的 ticket_id ↔ ticket.ticket_code
--   docs.csv 的 category     ↔ document.domain
--   docs.csv 的 ref_count    ↔ document.ref_count
--   tickets.csv 的 linked_doc_id ↔ ticket.linked_doc_id（文档编码文本）
--   document.title / content ↔ docs.csv 的 title / content
--
-- 数据类型约定（§4.3 原文）：
--   · 日期与时间统一以 ISO-8601 文本存 TEXT 列，字典序即时间序，索引仍可用
--   · duplicate_group.member_doc_ids 以 JSON 数组存组内成员文档编码，
--     不为「重复组—文档」多对多关系再引入第七张中间表
--
-- 时间列的精度与比较口径（**两类精度不同，不可跨表直接比较**）：
--   · document.created_at / last_modified / effective_date：精度到**日**，10 字符
--     （YYYY-MM-DD）。出处：poc/kbgovernance/docs.csv 同名列，300 行实测均为
--     10 字符。
--   · ticket.created_at：精度到**分钟**，16 字符（YYYY-MM-DDTHH:MM）。出处：
--     poc/kbgovernance/tickets.csv 同名列，2000 行实测均为 16 字符。
--   · 结果表（cluster_result / knowledge_gap / stale_document / duplicate_group）
--     的 created_at / detected_at：扫描时刻，同为 ISO-8601 文本，字典序即时间序。
--   **比较方式**：同表内可直接用字符串比较（=、>、BETWEEN 都走索引）；跨表的
--   时间范围过滤必须先统一精度——推荐一律归一到日（取 created_at 的前 10 字符），
--   不要拿 document.last_modified（到日）与 ticket.created_at（到分钟）直接比大小。
--
-- duplicate_group.member_doc_ids 的查询限制与替代方案：
--   · **限制**：JSON 数组不可被索引，「按某个成员文档查它属于哪个重复组」只能
--     全表扫描后在应用层解析（SQLite 的 json_each 是虚拟表，不走索引）。
--   · 替代方案（都不新增表）：① 常规查询走主文档列 primary_doc_id，命中
--     idx_dup_primary；② 需要按成员反查时，在应用层把 JSON 数组展开成
--     「doc_code → 组号」的内存映射（语料规模 300 篇文档，量级可接受）；
--     ③ 若要在库里做成员反查，只能另建一张反范式映射表（会变成 7 张表，与
--     「6 张表」的验收口径冲突，需另行拍板，本文件不擅自新增）。
--
-- 仍无出处的两列（保持可空并留注释，待 P2 拍板）：
--   · cluster_result.centroid_sim —— PoC 产物里没有对应的列值，无来源
--   · knowledge_gap.priority       —— 当前恒为 0，排序规则未定义
--
-- 三模块产物的列 ↔ 本库列（补全「字段映射」）：
--   gap_intents_best.csv intent            ↔ knowledge_gap.intent_name
--   gap_intents_best.csv n_clusters        ↔ knowledge_gap.n_clusters
--   gap_intents_best.csv min_cover_median  ↔ knowledge_gap.cover_score
--   gap_intents_best.csv total_tickets      ↔ knowledge_gap.ticket_count
--   gap_intents_best.csv rep_ticket        ↔ knowledge_gap.representative_ticket
--   gap_intents_best.csv rep_text          ↔ knowledge_gap.representative_text
--   gap_intents_best.csv threshold         ↔ knowledge_gap.threshold_used
--   gap_intents_best.csv is_true_gap       ↔ **不落库**：真值标注列，只在产物与论文中
--   gap_clusters_best.csv cluster_id        ↔ cluster_result.cluster_id
--   gap_clusters_best.csv intent           ↔ cluster_result.main_intent
--   gap_clusters_best.csv size             ↔ cluster_result.member_count
--   gap_clusters_best.csv cover_median     ↔ cluster_result.cover_score
--   gap_clusters_best.csv purity           ↔ cluster_result.purity
--   gap_clusters_best.csv rep_cover      ↔ **无对应列**：代表工单自身的覆盖度；
--                                          簇级清单展示用 cover_median，两者语义不同
--   gap_clusters_best.csv n_intent_members ↔ **无对应列**：簇内众数意图的工单数，
--                                          仅用于解释 purity，不单独落库
--   gap_clusters_best.csv is_gap/is_true_gap↔ **不落库**：判定结果与真值标注列
--   corrupt_docs.csv doc_id        ↔ stale_document.document_id（存 doc_code 文本）
--   corrupt_docs.csv risk_score    ↔ stale_document.risk_score（四规则合并分，
--                                    历史口径，不再用于任何判定）
--   corrupt_docs.csv cause_score_content_expiry ↔ stale_document 同名列
--   corrupt_docs.csv cause_score_maintenance   ↔ stale_document 同名列
--   corrupt_docs.csv rule_hits     ↔ stale_document.rule_hits
--   corrupt_docs.csv reasons       ↔ stale_document.reasons
--   corrupt_docs.csv fp_causes / fp_reason / in_control_sample / is_dup_copy /
--     dup_source                        ↔ **不落库**：真值派生与归因列
--   dup_groups_best.csv group      ↔ **无独立列**：group 是清单行号（1..22），
--                                    duplicate_group.id 是自增行号；落库按同一顺序
--                                    写入可保证两者取值一致，但它们不是同一个值
--   dup_groups_best.csv size       ↔ duplicate_group.group_size
--   dup_groups_best.csv primary_doc↔ duplicate_group.primary_doc_id
--   dup_groups_best.csv member_docs↔ duplicate_group.member_doc_ids（JSON 数组）
--   dup_groups_best.csv max_sim    ↔ duplicate_group.max_similarity
--   corrupt_rule_ablation_content_expiry.csv / corrupt_rule_ablation_maintenance.csv
--                                    ↔ **不落库**：两张分口径消融表是实验产物，
--                                      库只存扫描结果，不存实验对照
-- ============================================================================
-- 查询路径 → 索引对照（P2：保证查询性能；索引清单与 §4.3 对齐，只在既有列上建）
--
--   1) 按文档编码取一条文档
--      SQL : SELECT * FROM document WHERE doc_code = ?
--      索引：document.doc_code 的 UNIQUE 约束（隐式唯一索引），等值查找走索引。
--      覆盖：唯一索引只含 doc_code 一列，取其余列要回表。
--   2) 按业务域筛一批文档
--      SQL : SELECT * FROM document WHERE domain = ? ORDER BY last_modified
--      索引：idx_doc_domain 定位行集；idx_doc_mtime 供排序（免 filesort）。
--      覆盖：两个索引都不覆盖返回列，需回表；语料规模 300 行，暂不加
--            (domain, last_modified) 复合索引。
--   3) 按工单意图筛一批工单
--      SQL : SELECT * FROM ticket WHERE intent_label = ?
--      索引：idx_ticket_intent 等值定位。
--      覆盖：只覆盖 intent_label 一列，其余列回表。
--   4) 按关联文档取工单
--      SQL : SELECT * FROM ticket WHERE linked_doc_id = ?
--      索引：idx_ticket_linked_doc 等值定位（外键列，必须有索引，否则每次按文档
--            反查工单都要全表扫描）。
--      覆盖：只覆盖 linked_doc_id 一列，其余列回表。
--   5) 按工单创建时间取一段时间的工单
--      SQL : SELECT * FROM ticket WHERE created_at BETWEEN ? AND ?
--      索引：idx_ticket_time 范围扫描；created_at 是 16 字符 ISO-8601 文本，
--            字典序即时间序。
--      覆盖：范围扫描后仍需回表取其余列。
--   6) 按业务意图取缺口清单行（主清单的读法）
--      SQL : SELECT * FROM knowledge_gap WHERE intent_name = ?
--      索引：idx_gap_intent 等值定位。
--      覆盖：只覆盖 intent_name 一列，需回表取其余列。
--   7) 按业务意图取它下面的全部簇（溯源用：某意图由哪些簇构成）
--      SQL : SELECT * FROM cluster_result WHERE main_intent = ?
--      索引：idx_cluster_intent 等值定位。
--      覆盖：只覆盖 main_intent 一列；排序需加 cover_score，语料规模 95 簇，
--            回表代价可接受，暂不建 (main_intent, cover_score) 复合索引。
--   8) 按某一类口径的分数取腐化清单前 N 条
--      SQL : SELECT * FROM stale_document
--             WHERE cause_score_content_expiry >= 3
--             ORDER BY cause_score_content_expiry DESC LIMIT ?
--      索引：idx_stale_cause_expiry 范围扫描 + 降序，索引本身有序可免排序。
--      覆盖：不覆盖 document_id / rule_hits / reasons，需回表。
--      维护周期口径同理走 idx_stale_cause_maintenance。
--   9) 按组号取重复组成员
--      SQL : SELECT * FROM duplicate_group WHERE id = ?
--      索引：duplicate_group 的 INTEGER PRIMARY KEY（rowid 定位），主键即索引。
--      覆盖：rowid 定位后回表取 member_doc_ids 等列；member_doc_ids 是 JSON 数组，
--            不可索引（见上文「查询限制」）。
--   10) 按主文档取重复组
--      SQL : SELECT * FROM duplicate_group WHERE primary_doc_id = ?
--      索引：idx_dup_primary 等值定位（外键列）。
--      覆盖：只覆盖 primary_doc_id 一列。
--
-- 迁移组织方式（推荐做法与理由）：
--   · 用 PRAGMA user_version 记 schema 版本号（当前草案版本 = 1），每次结构
--     变更递增一次。
--   · 本文件同时承担「建表」与「迁移」两个角色：先 CREATE TABLE IF NOT EXISTS
--     建全部 6 张表（幂等基线），再接迁移段；迁移段写成
--     「IF <旧结构特征仍在> THEN <改结构> THEN user_version = <新版本>」，
--     全部带存在性判断，重复执行不报错。
--   · **不另建迁移文件**（如 migrations/001_init.sql）：本次可改范围只有
--     system/schema.sql 与 system/openapi.yaml 两份契约文件，另建迁移文件会
--     扩大改动面；且验收口径是「.sql 空库跑两遍」，建表与迁移同文件时一次执行
--     即可完成。代价是文件随版本增长变长，超过 3~4 版时应拆成
--     migrations/NNN_*.sql 并在此文件保留入口引用。
-- ============================================================================

PRAGMA foreign_keys = ON;   -- 外键约束：SQLite 按连接生效，应用需在每个连接上设置
PRAGMA journal_mode = WAL; -- 扫描读写并发（WAL 模式），重复执行不报错
PRAGMA user_version = 1;   -- schema 版本标记：当前草案版本 = 1（见上方「迁移组织方式」）

-- ---------------------------------------------------------------------------
-- 输入语料
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS document (
  id             INTEGER PRIMARY KEY,
  doc_code       TEXT    NOT NULL UNIQUE,
  title          TEXT    NOT NULL,
  content        TEXT    NOT NULL,
  domain         TEXT,
  created_at     TEXT    NOT NULL,
  last_modified  TEXT    NOT NULL,
  effective_date TEXT,
  status         TEXT    NOT NULL DEFAULT '生效',
  ref_count      INTEGER NOT NULL DEFAULT 0
);
-- idx_doc_mtime：查询路径 2「按业务域筛文档并按最后修改时间排序」的排序键；
--   单列索引，排序可免 filesort；不覆盖返回列（需回表）。
CREATE INDEX IF NOT EXISTS idx_doc_mtime ON document(last_modified);
-- idx_doc_domain：查询路径 2「按业务域筛一批文档」的等值定位键；不覆盖返回列。
CREATE INDEX IF NOT EXISTS idx_doc_domain ON document(domain);

CREATE TABLE IF NOT EXISTS ticket (
  id               INTEGER PRIMARY KEY,
  ticket_code      TEXT    NOT NULL UNIQUE,
  content          TEXT    NOT NULL,
  intent_label     TEXT    NOT NULL,
  channel          TEXT,
  urgency          TEXT,
  status           TEXT,
  handling_minutes INTEGER,
  -- 指向文档编码（与 poc/kbgovernance/tickets.csv 的 linked_doc_id 取值一致），
  -- 不是 document.id；空字符串不合法，未匹配到文档时写 NULL。
  -- **待拍板（A17 与本草案冲突）**：§4.10 A17 写「落库前建 doc_code → document.id
  -- 映射，未命中即拒绝该行」，而本列允许写 NULL（tickets.csv 2000 行里
  -- linked_doc_id 非空 1629 行，其余 371 行为空）。两种口径二选一：拒绝该行 =
  -- 整批导入失败；写 NULL = 保留该行但丢失关联。本草案按「写 NULL」落笔，等拍板。
  linked_doc_id    TEXT    NULL REFERENCES document(doc_code),
  created_at       TEXT    NOT NULL
);
-- idx_ticket_intent：查询路径 3「按工单意图筛一批工单」的等值定位键。
CREATE INDEX IF NOT EXISTS idx_ticket_intent ON ticket(intent_label);
-- idx_ticket_time：查询路径 5「按工单创建时间取一段时间的工单」的范围扫描键
--   （created_at 是 16 字符 ISO-8601 文本，字典序即时间序）。
CREATE INDEX IF NOT EXISTS idx_ticket_time ON ticket(created_at);
-- idx_ticket_linked_doc：查询路径 4「按关联文档取工单」的等值定位键；外键列
--   必须有索引，否则按文档反查工单要全表扫描。不覆盖返回列。
CREATE INDEX IF NOT EXISTS idx_ticket_linked_doc ON ticket(linked_doc_id);

-- ---------------------------------------------------------------------------
-- 三模块检测的落库目标
-- ---------------------------------------------------------------------------

-- granularity 记录**覆盖度检索所用的粒度**：passage_level = 段落级，
-- doc_level = 整篇级（§4.3 第 297 行）。它**不是聚类对象粒度**——本表记录的
-- 是工单聚类结果，聚类对象恒为工单（ticket），「覆盖度算在文档的哪个粒度上」
-- 才由本列区分；库里没有单独表达「聚类对象粒度」的列（不擅自新增列，避免偏离
-- §4.3 的六表 DDL）。
-- knowledge_gap.granularity 与本列同义：复合外键 (granularity,
-- min_cluster_size, cluster_id) 要求两表同值，因此它同时是「同一参数轮次下
-- 同一簇」的匹配键。
-- min_cluster_size 与 threshold_used 记录该轮扫描采用的参数。
CREATE TABLE IF NOT EXISTS cluster_result (
  id                INTEGER PRIMARY KEY,
  granularity       TEXT    NOT NULL DEFAULT 'passage_level',
  min_cluster_size  INTEGER NOT NULL,
  cluster_id        INTEGER NOT NULL,
  member_count      INTEGER NOT NULL,
  centroid_sim      REAL,      -- 无机读产物列值，无来源，保持可空
  main_intent       TEXT,      -- 簇内工单意图标签的众数
  purity            REAL,      -- 众数意图占簇内工单的比例；不依赖 ground truth
  cover_score       REAL,      -- 簇覆盖度中位数
  threshold_used    REAL,
  created_at        TEXT    NOT NULL,
  UNIQUE (granularity, min_cluster_size, cluster_id)
);
-- idx_cluster_gmcs：定位「某一轮参数（粒度 + min_cluster_size）下的全部簇」；
--   不覆盖返回列。
CREATE INDEX IF NOT EXISTS idx_cluster_gmcs ON cluster_result(granularity, min_cluster_size);
-- idx_cluster_intent：查询路径 7「按业务意图取它下面的全部簇」的等值定位键。
CREATE INDEX IF NOT EXISTS idx_cluster_intent ON cluster_result(main_intent);

CREATE TABLE IF NOT EXISTS knowledge_gap (
  id                    INTEGER PRIMARY KEY,
  -- 判定单元 = 业务意图。**不是** §4.3 原文的簇级形态：现行口径是
  -- 「意图覆盖度 = 该意图下各簇覆盖度的最小值」，一个意图对应多个簇，
  -- 因此本表一行装一个意图，不再有 cluster_id 外键。
  -- intent_name 与 cluster_result.main_intent 对应（软链接口径，同
  -- ticket.linked_doc_id → document(doc_code)）。
  intent_name           TEXT    NOT NULL,
  n_clusters            INTEGER NOT NULL,   -- 该意图下的簇数
  ticket_count          INTEGER NOT NULL,   -- 该意图下的工单总数
  cover_score           REAL    NOT NULL,     -- 意图覆盖度 = 各簇 cover_median 的最小值
  threshold_used        REAL    NOT NULL,
  representative_ticket TEXT,
  representative_text   TEXT,
  priority              INTEGER NOT NULL DEFAULT 0,  -- 排序规则未定义，当前恒 0
  detected_at           TEXT    NOT NULL
);
-- idx_gap_score：按覆盖度取缺口（清单页按覆盖度升序取最差的意图）。
CREATE INDEX IF NOT EXISTS idx_gap_score ON knowledge_gap(cover_score);
-- idx_gap_intent：查询路径 6「按业务意图取缺口清单行」的等值定位键。
CREATE INDEX IF NOT EXISTS idx_gap_intent ON knowledge_gap(intent_name);

CREATE TABLE IF NOT EXISTS stale_document (
  id          INTEGER PRIMARY KEY,
  document_id TEXT    NOT NULL REFERENCES document(doc_code),
  -- risk_score = 四条规则的合并加权分（历史口径）。现行判定按两类口径**各自**
  -- 算分，见下面两列；risk_score 不再用于任何判定，只保留作溯源与对照。
  risk_score  INTEGER NOT NULL,
  -- 内容过期口径（R1 + R3）的加权分；>= 3 时该篇在内容过期口径下命中。
  cause_score_content_expiry INTEGER NOT NULL DEFAULT 0,
  -- 维护周期口径（R2 + R4）的加权分；>= 3 时该篇在维护周期口径下命中。
  cause_score_maintenance   INTEGER NOT NULL DEFAULT 0,
  rule_hits   TEXT,
  reasons     TEXT,
  detected_at TEXT    NOT NULL
);
-- idx_stale_score：按合并分取腐化清单前 N 条的降序扫描键；索引本身有序，
--   可免排序。不覆盖 document_id / rule_hits / reasons，需回表。
CREATE INDEX IF NOT EXISTS idx_stale_score ON stale_document(risk_score);
-- idx_stale_cause_expiry：查询路径 8「按内容过期口径的分数取清单前 N 条」。
CREATE INDEX IF NOT EXISTS idx_stale_cause_expiry ON stale_document(cause_score_content_expiry);
-- idx_stale_cause_maintenance：同上，维护周期口径。
CREATE INDEX IF NOT EXISTS idx_stale_cause_maintenance ON stale_document(cause_score_maintenance);
-- idx_stale_document：按文档取腐化记录（外键列，等值定位）；不覆盖返回列。
CREATE INDEX IF NOT EXISTS idx_stale_document ON stale_document(document_id);

-- member_doc_ids 存 JSON 数组（如 ["DOC0001","DOC0002","DOC0003"]），不建第七张表
CREATE TABLE IF NOT EXISTS duplicate_group (
  id              INTEGER PRIMARY KEY,
  threshold_used  REAL    NOT NULL,
  group_size      INTEGER NOT NULL,
  primary_doc_id  TEXT    NOT NULL REFERENCES document(doc_code),
  member_doc_ids  TEXT    NOT NULL,
  max_similarity  REAL,
  detected_at     TEXT    NOT NULL
);
-- idx_dup_threshold：定位「某一轮阈值下的重复组」（外键无关的过滤键）。
CREATE INDEX IF NOT EXISTS idx_dup_threshold ON duplicate_group(threshold_used);
-- idx_dup_primary：查询路径 9「按主文档取重复组」的等值定位键；不覆盖返回列。
CREATE INDEX IF NOT EXISTS idx_dup_primary ON duplicate_group(primary_doc_id);
