-- =====================================================================
-- 数据库开发书 最终版 v4.1 · 建表脚本（全量、可执行、幂等）
-- 目标库：SQLite 3.8+（partial index 需 3.8，实测 3.53）
-- 依据：手绘最终呈现（8 表头 / 16 空全枚举，2026-11-17 定稿）
--       + 国家临床版 ICD-10 2.0（35,867 码）+ ICD-9-CM3 3.0（14,518 码）+ WS/T 364.5 值域
-- 结构：10 张表
--   schema_meta, archive_records,
--   sections, fields, options, answers,
--   icd_codes, dna_sequences, decode_records, user_activity_log
-- v4.1 变更：移除账号体系（users 表 / owner_id / 日志 user_id）——
--   单机单用户下账号不提供真实安全，只增加使用摩擦；操作日志保留
-- 说明：这是**全新库**的建表脚本。存量库（v3.0）升级另见 §升级路径，勿直接执行本脚本。
-- 生成日期：2026-11-12
-- =====================================================================

PRAGMA foreign_keys = ON;

-- ------------------------------------------------------------
-- 表1  schema_meta  结构版本
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS schema_meta (
    version    TEXT NOT NULL PRIMARY KEY,
    applied_at TEXT NOT NULL
);

-- ------------------------------------------------------------
-- 表2  archive_records  档案主表（铭文部分）
--      8 项铭文与列一一对应：姓名/性别/民族/身份证号/常住地址/档案编号/建档日期
--      铭文只用于展示与 DNA 密钥派生，不产生 fields / options
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS archive_records (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id         TEXT NOT NULL UNIQUE,   -- 业务号 ARCHIVE_{YYYYMMDD}_{NNN}
    archive_number    TEXT DEFAULT '',        -- 档案编号
    name              TEXT NOT NULL,
    gender            TEXT DEFAULT '' CHECK (gender IN ('', 'male', 'female', 'unknown')),
    nation            TEXT DEFAULT '',
    id_number         TEXT DEFAULT '',
    residence_address TEXT DEFAULT '',
    create_date       TEXT DEFAULT '',        -- 建档日期
    source            TEXT DEFAULT 'manual' CHECK (source IN ('manual', 'upload', 'ai')),
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    is_deleted        INTEGER DEFAULT 0 CHECK (is_deleted IN (0, 1))
);

-- ------------------------------------------------------------
-- 表3  icd_codes  标准诊断编码（只读镜像，唯一写入口 scripts/import_icd_codes.py）
--      35,867 条 / 22 章 / 2,046 类目；name 故意不设 UNIQUE（存在同名不同码）
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS icd_codes (
    code           TEXT PRIMARY KEY CHECK (code NOT GLOB '*[^A-Za-z0-9.+*/]*'),
    name           TEXT NOT NULL,
    category_code  TEXT NOT NULL,
    chapter_code   TEXT NOT NULL,
    chapter_name   TEXT NOT NULL,
    is_extension   INTEGER DEFAULT 0 CHECK (is_extension IN (0, 1)),
    is_combination INTEGER DEFAULT 0 CHECK (is_combination IN (0, 1)),
    version        TEXT NOT NULL DEFAULT 'CN-ICD10-2.0-2022',
    is_active      INTEGER DEFAULT 1 CHECK (is_active IN (0, 1)),
    updated_at     TEXT NOT NULL
);

-- ------------------------------------------------------------
-- 表4  sections  表头（14 条，三级）
--      level 1 = 铭文/存储（H1）；2 = 一/二/三（H2）；3 = 九个小标题（H3）
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sections (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    section_key TEXT    NOT NULL UNIQUE,
    name_cn     TEXT    NOT NULL,
    name_en     TEXT    NOT NULL,
    parent_id   INTEGER REFERENCES sections(id) ON DELETE RESTRICT,
    level       INTEGER NOT NULL CHECK (level IN (1, 2, 3)),
    sort_order  INTEGER NOT NULL,
    note        TEXT    NOT NULL DEFAULT ''
);

-- ------------------------------------------------------------
-- 表5  fields  空（42 条；文档 43 处「· xxx：」中两处分类合并为一）
--      value_type：multi_enum / enum / text / date / number / number_group
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fields (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    field_key   TEXT    NOT NULL UNIQUE,
    name_cn     TEXT    NOT NULL,
    name_en     TEXT    NOT NULL,
    section_id  INTEGER NOT NULL REFERENCES sections(id) ON DELETE RESTRICT,
    value_type  TEXT    NOT NULL CHECK (value_type IN
                    ('multi_enum', 'enum', 'text', 'date', 'number', 'number_group')),
    is_multi    INTEGER NOT NULL DEFAULT 0 CHECK (is_multi IN (0, 1)),
    is_required INTEGER NOT NULL DEFAULT 1 CHECK (is_required IN (0, 1)),
    derive_from TEXT    NOT NULL DEFAULT '',   -- 非空 = 由另一空派生，值为其 field_key
    unit_cn     TEXT    NOT NULL DEFAULT '',
    unit_en     TEXT    NOT NULL DEFAULT '',
    sort_order  INTEGER NOT NULL,
    note        TEXT    NOT NULL DEFAULT '',
    UNIQUE (section_id, sort_order)
);

-- ------------------------------------------------------------
-- 表6  options  枚举项（系统下拉/多选的唯一来源）
--      source：icd=来自码表 / custom=自建 / derived=由码表或另一空加工
--      icd_code 可空、不唯一；名称一律 JOIN icd_codes，不冗余存
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS options (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    option_key  TEXT    NOT NULL UNIQUE,
    name_cn     TEXT    NOT NULL,
    name_en     TEXT    NOT NULL DEFAULT '',   -- S4 批量生成，允许暂空
    field_id    INTEGER NOT NULL REFERENCES fields(id) ON DELETE CASCADE,
    icd_code    TEXT    REFERENCES icd_codes(code),
    source      TEXT    NOT NULL DEFAULT 'custom' CHECK (source IN ('icd', 'icd9', 'wst', 'custom', 'derived')),
    is_active   INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    sort_order  INTEGER NOT NULL DEFAULT 0,
    reviewed_by TEXT    NOT NULL DEFAULT '',
    reviewed_at TEXT    NOT NULL DEFAULT '',
    UNIQUE (field_id, name_cn)                  -- 同一个空下不重名，跨空可重名
);

-- ------------------------------------------------------------
-- 表7  answers  填写结果
--      枚举型：option_id 非空、值列全空；值型：option_id 为空、对应值列非空
--      seq：多次随访/多值序号，0 起
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS answers (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id  TEXT    NOT NULL REFERENCES archive_records(record_id) ON DELETE CASCADE,
    field_id   INTEGER NOT NULL REFERENCES fields(id) ON DELETE RESTRICT,
    option_id  INTEGER          REFERENCES options(id) ON DELETE RESTRICT,
    value_text TEXT    NOT NULL DEFAULT '',
    value_num  REAL,
    value_date TEXT    NOT NULL DEFAULT '',
    seq        INTEGER NOT NULL DEFAULT 0 CHECK (seq >= 0),
    updated_at TEXT    NOT NULL,
    CHECK (
        (option_id IS NOT NULL AND value_text = '' AND value_num IS NULL AND value_date = '')
        OR
        (option_id IS NULL     AND (value_text <> '' OR value_num IS NOT NULL OR value_date <> ''))
    )
);

-- ------------------------------------------------------------
-- 表8  dna_sequences  DNA 序列（沿用 v3.0）
--      未设 CASCADE：物理删除档案会被外键拒绝，防止审计链丢失
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dna_sequences (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id        TEXT NOT NULL,
    dna_sequence     TEXT NOT NULL,
    key_hash         TEXT NOT NULL,
    cg_content       REAL DEFAULT 0,
    thermal_stability REAL DEFAULT 0,
    padded_zeros     INTEGER DEFAULT 0,
    sequence_length  INTEGER DEFAULT 0 CHECK (sequence_length >= 0),
    original_text    TEXT DEFAULT '',
    encoded_at       TEXT NOT NULL,
    is_valid         INTEGER DEFAULT 1 CHECK (is_valid IN (0, 1)),
    payload_version  TEXT DEFAULT 'v3',
    payload_mode     TEXT DEFAULT 'bilingual' CHECK (payload_mode IN ('bilingual', 'canonical_en')),
    FOREIGN KEY (record_id) REFERENCES archive_records(record_id)
);

-- ------------------------------------------------------------
-- 表9  decode_records  解码与纠错日志（沿用 v3.0）
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS decode_records (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    dna_record_id   INTEGER NOT NULL,
    decoded_text    TEXT NOT NULL,
    corrected_text  TEXT DEFAULT '',
    confidence      REAL DEFAULT 0 CHECK (confidence BETWEEN 0 AND 1),
    error_rate      REAL DEFAULT 0 CHECK (error_rate BETWEEN 0 AND 1),
    correction_log  TEXT DEFAULT '{}',
    decoded_at      TEXT NOT NULL,
    FOREIGN KEY (dna_record_id) REFERENCES dna_sequences(id)
);

-- ------------------------------------------------------------
-- 表9  user_activity_log  操作日志（写失败不得阻断主流程）
--      v4.1：去掉 user_id（无账号）；action 枚举更新
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_activity_log (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    action           TEXT NOT NULL CHECK (action IN
        ('create_record', 'update_record', 'delete_record', 'encode_dna',
         'decode_dna', 'export_report', 'ai_extract',
         'app_start', 'app_exit', 'backup_database')),
    target_record_id TEXT DEFAULT '',
    detail           TEXT DEFAULT '',
    created_at       TEXT NOT NULL
);

-- =====================================================================
-- 索引（显式 21 个，其中 1 个为 partial 唯一索引 uq_answers_enum）
-- =====================================================================
CREATE INDEX IF NOT EXISTS idx_archive_name     ON archive_records(name);
CREATE INDEX IF NOT EXISTS idx_archive_created  ON archive_records(created_at);
CREATE INDEX IF NOT EXISTS idx_archive_deleted  ON archive_records(is_deleted, created_at);

CREATE INDEX IF NOT EXISTS idx_sections_parent  ON sections(parent_id);
CREATE INDEX IF NOT EXISTS idx_sections_sort    ON sections(level, sort_order);

CREATE INDEX IF NOT EXISTS idx_fields_section   ON fields(section_id);
CREATE INDEX IF NOT EXISTS idx_fields_vtype     ON fields(value_type);

CREATE INDEX IF NOT EXISTS idx_options_field    ON options(field_id, sort_order);
CREATE INDEX IF NOT EXISTS idx_options_icd      ON options(icd_code);
CREATE INDEX IF NOT EXISTS idx_options_source   ON options(source, is_active);

CREATE INDEX IF NOT EXISTS idx_answers_record   ON answers(record_id);
CREATE INDEX IF NOT EXISTS idx_answers_field    ON answers(field_id);
CREATE INDEX IF NOT EXISTS idx_answers_option   ON answers(option_id);
-- 同一档案同一空同一序号下，同一个枚举项只允许出现一次（多选去重）
CREATE UNIQUE INDEX IF NOT EXISTS uq_answers_enum
    ON answers(record_id, field_id, option_id, seq) WHERE option_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_icd_name         ON icd_codes(name);
CREATE INDEX IF NOT EXISTS idx_icd_category     ON icd_codes(category_code);
CREATE INDEX IF NOT EXISTS idx_icd_chapter      ON icd_codes(chapter_code);

CREATE INDEX IF NOT EXISTS idx_dna_record       ON dna_sequences(record_id, is_valid);
CREATE INDEX IF NOT EXISTS idx_dna_sequence     ON dna_sequences(dna_sequence);

CREATE INDEX IF NOT EXISTS idx_decode_dna       ON decode_records(dna_record_id);

CREATE INDEX IF NOT EXISTS idx_activity_action  ON user_activity_log(action, created_at);

-- =====================================================================
-- 版本写入
-- =====================================================================
INSERT INTO schema_meta (version, applied_at)
VALUES ('v4.1', strftime('%Y-%m-%dT%H:%M:%S', 'now'))
ON CONFLICT(version) DO UPDATE SET applied_at = excluded.applied_at;

-- =====================================================================
-- 自检（期望：10 / 21 / 6 / 9 / 1）
-- =====================================================================
SELECT '--- v4.1 建表自检 ---' AS check_point;
SELECT '表数' AS item, COUNT(*) AS actual, 11 AS expected
  FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
UNION ALL SELECT '显式索引',
  (SELECT COUNT(*) FROM sqlite_master
    WHERE type = 'index' AND (name LIKE 'idx_%' OR name LIKE 'uq_%')), 21
UNION ALL SELECT '带外键的表',
  (SELECT COUNT(*) FROM sqlite_master
    WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
      AND (sql LIKE '%FOREIGN KEY%' OR sql LIKE '%REFERENCES%')), 6
UNION ALL SELECT '外键列',
  (SELECT COUNT(*) FROM pragma_foreign_key_list('archive_records'))
 + (SELECT COUNT(*) FROM pragma_foreign_key_list('sections'))
 + (SELECT COUNT(*) FROM pragma_foreign_key_list('fields'))
 + (SELECT COUNT(*) FROM pragma_foreign_key_list('options'))
 + (SELECT COUNT(*) FROM pragma_foreign_key_list('answers'))
 + (SELECT COUNT(*) FROM pragma_foreign_key_list('dna_sequences'))
 + (SELECT COUNT(*) FROM pragma_foreign_key_list('decode_records'))
 + (SELECT COUNT(*) FROM pragma_foreign_key_list('user_activity_log')), 9
UNION ALL SELECT '版本', (SELECT COUNT(*) FROM schema_meta WHERE version = 'v4.1'), 1;
