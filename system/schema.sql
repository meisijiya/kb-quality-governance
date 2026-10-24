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
--        · poc/kbgovernance/top15_gaps.csv 的簇号是 HDBSCAN 标签（0、1、2…），
--          与 cluster_result.id 的自增行号无关。
--      因此：指向文档的三个外键改为 TEXT 并指向 document(doc_code)；指向簇的
--      外键改为三列复合外键 (granularity, min_cluster_size, cluster_id)，
--      cluster_result 上加 UNIQUE 约束支撑该复合外键。
--      **这一处改动改变了数据形态，属于 P2（数据形态）的待拍板范围**，
--      评审与拍板记录见 docs/技术方案/开发前准备清单.md §4.11 P2、§4.10 A17
--      （doc_code → document.id 的映射口径）与 §4.10 A16（每次扫描生成 scan_id）。
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
--      **推荐与代价（待拍板）——指向簇的外键**：
--        · 推荐（当前草案采用）：cluster_id 列存业务标签（HDBSCAN label），
--          用 (granularity, min_cluster_size, cluster_id) 复合唯一键承载
--          「同一参数轮次下的同一个簇」，knowledge_gap 用同样的三列复合外键
--          引用它。
--          代价：① 对外的簇号是 cluster_id，不是 cluster_result.id，两者不可
--          混用；② 复合外键比单列外键宽，knowledge_gap 插入要带全三列；
--          ③ 与 §4.3 原文的 `cluster_id INTEGER NOT NULL REFERENCES
--          cluster_result(id)` 不符。
--        · 备选：把 cluster_result 主键改成 (scan_id, granularity,
--          min_cluster_size, label) 复合主键。代价：复合主键宽；且本库目前
--          没有 scan_id 列（每次扫描生成 scan_id 是 §4.10 A16 的口径，落库时
--          需新增列），同样偏离 §4.3 原文。
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
-- 四列在 PoC 产物中零命中（保持可空并留注释，待 P2 拍板）：
--   · cluster_result.centroid_sim —— PoC 产物里没有对应的列值，无来源
--   · cluster_result.main_intent  —— PoC 产物里没有对应的列值，无来源
--   · cluster_result.purity        —— 依赖真值标注，自有语料无真值时恒为 NULL
--   · knowledge_gap.priority        —— 当前恒为 0，排序规则未定义
--
-- 三模块产物的列 ↔ 本库列（补全「字段映射」）：
--   top15_gaps.csv  cover_median   ↔ knowledge_gap.cover_score
--   top15_gaps.csv  size           ↔ knowledge_gap.ticket_count
--   top15_gaps.csv  intent         ↔ knowledge_gap.intent_name
--   top15_gaps.csv  rep_ticket     ↔ knowledge_gap.representative_ticket
--   top15_gaps.csv  rep_text       ↔ knowledge_gap.representative_text
--   top15_gaps.csv  rank           ↔ **无对应列**：rank 是清单行号（knowledge_gap.id
--                                    升序的第 N 行），不落库为列
--   top15_gaps.csv  rep_cover      ↔ **无对应列**：cover_score 存的是 cover_median，
--                                    代表工单自身的覆盖度（rep_cover）没有列可存。
--                                    **待拍板（P2 数据形态）**：新增一列 rep_cover，
--                                    还是接受清单接口用 cover_median 同时顶替两者；
--                                    新增列会偏离 §4.3 的六表 DDL。
--   corrupt_docs.csv doc_id        ↔ stale_document.document_id（存 doc_code 文本）
--   corrupt_docs.csv risk_score    ↔ stale_document.risk_score
--   corrupt_docs.csv rule_hits     ↔ stale_document.rule_hits
--   corrupt_docs.csv reasons       ↔ stale_document.reasons
--   dup_groups_best.csv group      ↔ **无独立列**：group 是清单行号（1..22），
--                                    duplicate_group.id 是自增行号；落库按同一顺序
--                                    写入可保证两者取值一致，但它们不是同一个值
--   dup_groups_best.csv size       ↔ duplicate_group.group_size
--   dup_groups_best.csv primary_doc↔ duplicate_group.primary_doc_id
--   dup_groups_best.csv member_docs↔ duplicate_group.member_doc_ids（JSON 数组）
--   dup_groups_best.csv max_sim    ↔ duplicate_group.max_similarity
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
--   6) 按 cluster 取该簇的缺口
--      SQL : SELECT * FROM knowledge_gap WHERE cluster_id = ?
--      索引：idx_gap_cluster 等值定位（外键列）。
--      覆盖：只覆盖 cluster_id 一列；knowledge_gap 的外键是三列复合
--            (granularity, min_cluster_size, cluster_id)，若查询带全三列，应把
--            idx_gap_cluster 扩成三列复合索引——当前按「只按簇号取」这一条
--            典型查询建单列索引。
--   7) 按风险分取腐化清单前 N 条
--      SQL : SELECT * FROM stale_document ORDER BY risk_score DESC LIMIT ?
--      索引：idx_stale_score 降序扫描，索引本身有序可免排序。
--      覆盖：不覆盖 document_id / rule_hits / reasons，需回表。
--   8) 按组号取重复组成员
--      SQL : SELECT * FROM duplicate_group WHERE id = ?
--      索引：duplicate_group 的 INTEGER PRIMARY KEY（rowid 定位），主键即索引。
--      覆盖：rowid 定位后回表取 member_doc_ids 等列；member_doc_ids 是 JSON 数组，
--            不可索引（见上文「查询限制」）。
--   9) 按主文档取重复组
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
  centroid_sim      REAL,
  main_intent       TEXT,
  purity            REAL,      -- 依赖真值标注；自有语料无真值时为 NULL
  threshold_used    REAL,
  created_at        TEXT    NOT NULL,
  UNIQUE (granularity, min_cluster_size, cluster_id)
);
-- idx_cluster_gmcs：定位「某一轮参数（粒度 + min_cluster_size）下的全部簇」，
--   是 knowledge_gap 三列复合外键在父表一侧的定位键；不覆盖返回列。
CREATE INDEX IF NOT EXISTS idx_cluster_gmcs ON cluster_result(granularity, min_cluster_size);

CREATE TABLE IF NOT EXISTS knowledge_gap (
  id                    INTEGER PRIMARY KEY,
  -- 复合外键：指向 cluster_result 的 (granularity, min_cluster_size, cluster_id)，
  -- 其中 cluster_id 是 HDBSCAN 标签，不是 cluster_result.id 的自增行号。
  granularity           TEXT    NOT NULL DEFAULT 'passage_level',
  min_cluster_size      INTEGER NOT NULL,
  cluster_id            INTEGER NOT NULL,
  intent_name           TEXT    NOT NULL,
  ticket_count          INTEGER NOT NULL,
  cover_score           REAL    NOT NULL,
  threshold_used        REAL    NOT NULL,
  representative_ticket TEXT,
  representative_text   TEXT,
  priority              INTEGER NOT NULL DEFAULT 0,  -- 排序规则未定义，当前恒 0
  detected_at           TEXT    NOT NULL,
  FOREIGN KEY (granularity, min_cluster_size, cluster_id)
    REFERENCES cluster_result(granularity, min_cluster_size, cluster_id)
);
-- idx_gap_score：按覆盖度取缺口（清单页取高分簇 / 缺口自检）。
CREATE INDEX IF NOT EXISTS idx_gap_score ON knowledge_gap(cover_score);
-- idx_gap_cluster：查询路径 6「按 cluster 取该簇的缺口」的等值定位键；外键列
--   必须有索引。不覆盖返回列。
CREATE INDEX IF NOT EXISTS idx_gap_cluster ON knowledge_gap(cluster_id);

CREATE TABLE IF NOT EXISTS stale_document (
  id          INTEGER PRIMARY KEY,
  document_id TEXT    NOT NULL REFERENCES document(doc_code),
  risk_score  INTEGER NOT NULL,
  rule_hits   TEXT,
  reasons     TEXT,
  detected_at TEXT    NOT NULL
);
-- idx_stale_score：查询路径 7「按风险分取腐化清单前 N 条」的降序扫描键；
--   索引本身有序，可免排序。不覆盖 document_id / rule_hits / reasons，需回表。
CREATE INDEX IF NOT EXISTS idx_stale_score ON stale_document(risk_score);
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
