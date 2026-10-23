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
--      评审与拍板记录见 docs/技术方案/开发前准备清单.md §4.11 P2 与 §4.10 A16。
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
-- 两处未落盘产物的列（保持可空并留注释，待 P2 拍板）：
--   · cluster_result.purity 依赖真值标注，自有语料无真值时恒为 NULL
--   · knowledge_gap.priority 当前恒为 0，排序规则未定义
-- ============================================================================

PRAGMA foreign_keys = ON;   -- 外键约束：SQLite 按连接生效，应用需在每个连接上设置
PRAGMA journal_mode = WAL; -- 扫描读写并发（WAL 模式），重复执行不报错

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
CREATE INDEX IF NOT EXISTS idx_doc_mtime ON document(last_modified);
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
  linked_doc_id    TEXT    NULL REFERENCES document(doc_code),
  created_at       TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ticket_intent ON ticket(intent_label);
CREATE INDEX IF NOT EXISTS idx_ticket_time ON ticket(created_at);
CREATE INDEX IF NOT EXISTS idx_ticket_linked_doc ON ticket(linked_doc_id);

-- ---------------------------------------------------------------------------
-- 三模块检测的落库目标
-- ---------------------------------------------------------------------------

-- granularity 记录覆盖度检索所用的粒度（passage_level = 段落级，
-- doc_level = 整篇级）；本表记录的是工单聚类结果（聚类对象是工单，
-- 不是文档段落），故该列表达的是「覆盖度算在哪个粒度上」，不是聚类粒度。
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
CREATE INDEX IF NOT EXISTS idx_gap_score ON knowledge_gap(cover_score);
CREATE INDEX IF NOT EXISTS idx_gap_cluster ON knowledge_gap(cluster_id);

CREATE TABLE IF NOT EXISTS stale_document (
  id          INTEGER PRIMARY KEY,
  document_id TEXT    NOT NULL REFERENCES document(doc_code),
  risk_score  INTEGER NOT NULL,
  rule_hits   TEXT,
  reasons     TEXT,
  detected_at TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_stale_score ON stale_document(risk_score);
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
CREATE INDEX IF NOT EXISTS idx_dup_threshold ON duplicate_group(threshold_used);
CREATE INDEX IF NOT EXISTS idx_dup_primary ON duplicate_group(primary_doc_id);
