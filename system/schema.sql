-- ============================================================================
-- 企业知识库质量治理系统 —— 数据库建表脚本（机器可读契约**草案**）
--
-- 状态：草案，未定稿。来源工单 Issue #3 已撤回为 needs-triage（2026-10-23），
--       其正文不再是已确认的规格；表结构本身取自技术方案 §4.3「数据库设计」，
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
-- 与 §4.3 原文的唯一差异（已在 README「实现须知」中同步）：
--   §4.3 原文主键写作 `INTEGER PRIMARY KEY AUTOINCREMENT`。AUTOINCREMENT 会让
--   SQLite 自动创建内部表 sqlite_sequence，使「库中 6 张业务表」变成 7 项。
--   为使验收命令的输出恰好是 6 张表，主键改用 `INTEGER PRIMARY KEY`：
--   行号语义不变（仍是 rowid 别名、仍自增），仅去掉 sqlite_sequence 记账。
--   若要严格对齐 §4.3 原文，把 6 处改回 AUTOINCREMENT 即可，验收时过滤
--   sqlite_sequence。DDL 的表、列、类型、约束、索引一律未增删改。
--
-- 数据类型约定（§4.3 原文）：
--   · 日期与时间统一以 ISO-8601 文本存 TEXT 列，字典序即时间序，索引仍可用
--   · duplicate_group.member_doc_ids 以 JSON 数组存组内成员文档 ID，
--     不为「重复组—文档」多对多关系再引入第七张中间表
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
  linked_doc_id    INTEGER NULL REFERENCES document(id),
  created_at       TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ticket_intent ON ticket(intent_label);
CREATE INDEX IF NOT EXISTS idx_ticket_time ON ticket(created_at);

-- ---------------------------------------------------------------------------
-- 三模块检测的落库目标
-- ---------------------------------------------------------------------------

-- granularity 记录该簇是在 passage_level 还是 doc_level 粒度下算出的；
-- min_cluster_size 与 threshold_used 记录该轮扫描采用的参数
CREATE TABLE IF NOT EXISTS cluster_result (
  id                INTEGER PRIMARY KEY,
  granularity       TEXT    NOT NULL DEFAULT 'passage_level',
  min_cluster_size  INTEGER NOT NULL,
  cluster_id        INTEGER NOT NULL,
  member_count      INTEGER NOT NULL,
  centroid_sim      REAL,
  main_intent       TEXT,
  purity            REAL,
  threshold_used    REAL,
  created_at        TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cluster_gmcs ON cluster_result(granularity, min_cluster_size);

CREATE TABLE IF NOT EXISTS knowledge_gap (
  id                    INTEGER PRIMARY KEY,
  cluster_id            INTEGER NOT NULL REFERENCES cluster_result(id),
  intent_name           TEXT    NOT NULL,
  ticket_count          INTEGER NOT NULL,
  cover_score           REAL    NOT NULL,
  threshold_used        REAL    NOT NULL,
  representative_ticket TEXT,
  representative_text   TEXT,
  priority              INTEGER NOT NULL DEFAULT 0,
  detected_at           TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_gap_score ON knowledge_gap(cover_score);

CREATE TABLE IF NOT EXISTS stale_document (
  id          INTEGER PRIMARY KEY,
  document_id INTEGER NOT NULL REFERENCES document(id),
  risk_score  INTEGER NOT NULL,
  rule_hits   TEXT,
  reasons     TEXT,
  detected_at TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_stale_score ON stale_document(risk_score);

-- member_doc_ids 存 JSON 数组（如 ["DOC0001","DOC0002","DOC0003"]），不建第七张表
CREATE TABLE IF NOT EXISTS duplicate_group (
  id              INTEGER PRIMARY KEY,
  threshold_used  REAL    NOT NULL,
  group_size      INTEGER NOT NULL,
  primary_doc_id  INTEGER NOT NULL REFERENCES document(id),
  member_doc_ids  TEXT    NOT NULL,
  max_similarity  REAL,
  detected_at     TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_dup_threshold ON duplicate_group(threshold_used);
