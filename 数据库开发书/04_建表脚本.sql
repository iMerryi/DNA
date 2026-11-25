-- ⚠️⚠️ 前代脚本（v3.1 键值模型，11 表含 users）：已废弃，勿执行！
-- 施工请用 04_建表脚本_v4.0.sql（内容 v4.1，10 表无账号）。本文件仅作历史追溯。

-- ============================================================
-- DNA 医疗档案系统 建表脚本
-- 数据库: SQLite   |   结构版本: v3.1（v3.0 + 国家临床版 ICD-10 码表）
-- 用法: 【全新库】sqlite3 data/db/medical_archive.db < 04_建表脚本.sql
--       【存量 v3.0 库】改跑 python scripts/migrate_v3_0_to_v3_1.py
--       （原因见文末「v3.0 -> v3.1 升级段」：ADD COLUMN 无法 IF NOT EXISTS，
--         本脚本在缺列的旧库上会在建 idx_terms_icd 时报 no such column）
-- 注意: PRAGMA foreign_keys 是连接级设置，本脚本执行后，
--       应用程序每次 connect() 仍须重新执行 PRAGMA foreign_keys = ON
-- 幂等: 全新库上表与索引均使用 IF NOT EXISTS，可重复执行；
--       存量库受 ADD COLUMN 限制，不具备脚本级幂等，须走迁移脚本
-- 配套: 字段字典种子 -> data/seed/seed_field_definitions.sql (60条)
--       病症词典种子 -> seed_disease_terms.sql (236条, 待数据库同学产出)
--       ICD码表导入   -> scripts/import_icd_codes.py (35,867条, 见 03 §11.2)
--       结构迁移     -> scripts/migrate_v3_0_to_v3_1.py (v3.0 -> v3.1)
-- ============================================================

PRAGMA foreign_keys = ON;

-- ------------------------------------------------------------
-- 表8: 结构版本表
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS schema_meta (
    version TEXT NOT NULL PRIMARY KEY,        -- 如 v3.1, 主键防重复写入
    applied_at TEXT NOT NULL
);

-- ------------------------------------------------------------
-- 表1: 档案主表 (身份与状态)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS archive_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id TEXT NOT NULL UNIQUE,          -- 业务号 ARCHIVE_{YYYYMMDD}_{NNN}
    archive_number TEXT DEFAULT '',          -- 档案编号(用户填)
    name TEXT NOT NULL,                      -- 姓名
    gender TEXT DEFAULT ''                   -- male / female / unknown
        CHECK (gender IN ('', 'male', 'female', 'unknown')),
    nation TEXT DEFAULT '',                  -- 民族
    id_number TEXT DEFAULT '',               -- 身份证号
    residence_address TEXT DEFAULT '',       -- 常住地址
    create_date TEXT DEFAULT '',             -- 建档日期(业务日期)
    source TEXT DEFAULT 'manual'             -- manual / upload / ai
        CHECK (source IN ('manual', 'upload', 'ai')),
    created_at TEXT NOT NULL,                -- 系统写入
    updated_at TEXT NOT NULL,                -- 系统写入
    is_deleted INTEGER DEFAULT 0             -- 软删除标记(档案级)
        CHECK (is_deleted IN (0, 1))
);

-- ------------------------------------------------------------
-- 表2: 字段字典 (唯一真名登记处)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS field_definitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    field_key TEXT NOT NULL UNIQUE,          -- 英文规范键, 入库后不可改名
    section TEXT NOT NULL,                   -- identity/birth/history/allergy/
                                             -- lifestyle/reproductive/complaint/exam/followup
    label_cn TEXT NOT NULL,                  -- 中文标签
    label_en TEXT NOT NULL,                  -- 英文标签
    value_type TEXT DEFAULT 'text'           -- text/date/number/enum/bool
        CHECK (value_type IN ('text', 'date', 'number', 'enum', 'bool')),
    is_multi INTEGER DEFAULT 0               -- 1=多值(seq 从1递增)
        CHECK (is_multi IN (0, 1)),
    is_active INTEGER DEFAULT 1              -- 0=停用(前端不渲染,历史可读)
        CHECK (is_active IN (0, 1)),
    unit_cn TEXT DEFAULT '',
    unit_en TEXT DEFAULT '',
    sort_order INTEGER DEFAULT 0,
    is_legacy INTEGER DEFAULT 0              -- 1=从v1迁移
        CHECK (is_legacy IN (0, 1))
);

-- ------------------------------------------------------------
-- 表11: 标准诊断编码表 (v3.1 新增, 国家临床版ICD-10 2.0 2022)
-- 只读镜像: 唯一写入口是 scripts/import_icd_codes.py
-- 规模: 35,867 条 / 22 章节 / 2,046 个类目
-- 注意: name 故意不设 UNIQUE —— 存在同名不同码
--       (结核性关节炎 / 绿脓杆菌感染 / 梅毒性腹膜炎 各 2 个码)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS icd_codes (
    code TEXT PRIMARY KEY                   -- 诊断编码, 去首尾空格原样保存
        CHECK (code NOT GLOB '*[^A-Za-z0-9.+*/]*'),
    name TEXT NOT NULL,                     -- 官方疾病名称, 不改写不归并
    category_code TEXT NOT NULL,            -- 3位类目码(A00/D63), 复合码取'+'前
    chapter_code TEXT NOT NULL,             -- ICD-10章节 I..XXII
    chapter_name TEXT NOT NULL,             -- 章节中文名
    is_extension INTEGER DEFAULT 0          -- 1=含x的临床版扩展码
        CHECK (is_extension IN (0, 1)),
    is_combination INTEGER DEFAULT 0        -- 1=含+/ *的星剑号复合码
        CHECK (is_combination IN (0, 1)),
    version TEXT NOT NULL DEFAULT 'CN-ICD10-2.0-2022',
    is_active INTEGER DEFAULT 1             -- 0=新版停用(历史仍可解析)
        CHECK (is_active IN (0, 1)),
    updated_at TEXT NOT NULL
);

-- ------------------------------------------------------------
-- 表5: 病症词典 (236条, term_key 不可变)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS disease_terms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    term_key TEXT NOT NULL UNIQUE,           -- 不可变英文标识, DNA载荷用这个
    chinese_name TEXT NOT NULL UNIQUE,
    english_name TEXT NOT NULL,              -- 英文展示名(可修改)
    category TEXT DEFAULT 'general',
    icd_code TEXT,                           -- v3.1: 对应标准码, NULL=无对应(无/不详/正常)
    icd_match TEXT DEFAULT 'none'            -- v3.1: exact/manual/ai/none
        CHECK (icd_match IN ('exact', 'manual', 'ai', 'none')),
    is_active INTEGER DEFAULT 1
        CHECK (is_active IN (0, 1)),
    updated_at TEXT DEFAULT '',
    FOREIGN KEY (icd_code) REFERENCES icd_codes(code)
);

-- ------------------------------------------------------------
-- 表3: 内容键值表 (核心, 53个业务字段的取值)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS record_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id TEXT NOT NULL,
    field_key TEXT NOT NULL,
    seq INTEGER NOT NULL DEFAULT 0           -- 单值固定0; 多值从1连续递增
        CHECK (seq >= 0),                    -- NOT NULL: 防NULL绕过唯一约束
    value_cn TEXT DEFAULT '',                -- 中文值(展示)
    value_en TEXT DEFAULT '',                -- 英文/规范值(编码交换)
    value_num REAL,                          -- number类型的数值副本
    updated_at TEXT NOT NULL,
    -- 注意: 条目层不做软删除, 故意没有 is_deleted 列
    UNIQUE (record_id, field_key, seq),
    FOREIGN KEY (record_id) REFERENCES archive_records(record_id) ON DELETE CASCADE,
    FOREIGN KEY (field_key) REFERENCES field_definitions(field_key)
);

-- ------------------------------------------------------------
-- 表4: 病症结果表 (词典驱动)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS record_diseases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id TEXT NOT NULL,
    disease_term_id INTEGER NOT NULL,
    result_cn TEXT DEFAULT '',               -- 阴性/阳性/未查
    result_en TEXT DEFAULT ''                -- negative/positive/not_tested
        CHECK (result_en IN ('', 'negative', 'positive', 'not_tested')),
    seq INTEGER NOT NULL DEFAULT 0           -- 同一病症多次筛查序号
        CHECK (seq >= 0),
    checked_at TEXT DEFAULT '',
    updated_at TEXT NOT NULL,
    UNIQUE (record_id, disease_term_id, seq),
    FOREIGN KEY (record_id) REFERENCES archive_records(record_id) ON DELETE CASCADE,
    FOREIGN KEY (disease_term_id) REFERENCES disease_terms(id)
);

-- ------------------------------------------------------------
-- 表6: DNA序列表 (编码结果, 保留历史版本)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dna_sequences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id TEXT NOT NULL,
    dna_sequence TEXT NOT NULL,              -- DNA序列(ATCG)
    key_hash TEXT NOT NULL,                  -- 密钥哈希(不存明文密钥)
    cg_content REAL DEFAULT 0,               -- GC含量
    thermal_stability REAL DEFAULT 0,        -- 热稳定性系数
    padded_zeros INTEGER DEFAULT 0,          -- 二进制补零位数
    sequence_length INTEGER DEFAULT 0        -- 序列长度
        CHECK (sequence_length >= 0),
    original_text TEXT DEFAULT '',           -- 编码前明文(明文风险见安全说明)
    encoded_at TEXT NOT NULL,
    is_valid INTEGER DEFAULT 1               -- 是否当前有效版本
        CHECK (is_valid IN (0, 1)),
    payload_version TEXT DEFAULT 'v2',       -- 载荷格式版本(可追溯)
    payload_mode TEXT DEFAULT 'bilingual'    -- bilingual / canonical_en
        CHECK (payload_mode IN ('bilingual', 'canonical_en')),
    -- 未设 ON DELETE CASCADE: 物理删除档案会被外键拒绝, 防止 DNA 审计链丢失
    FOREIGN KEY (record_id) REFERENCES archive_records(record_id)
);

-- ------------------------------------------------------------
-- 表7: 解码记录表 (解码历史与纠错日志)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS decode_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dna_record_id INTEGER NOT NULL,
    decoded_text TEXT NOT NULL,
    corrected_text TEXT DEFAULT '',
    confidence REAL DEFAULT 0                -- 置信度 0.0-1.0
        CHECK (confidence BETWEEN 0 AND 1),
    error_rate REAL DEFAULT 0                -- 错误率 0.0-1.0
        CHECK (error_rate BETWEEN 0 AND 1),
    correction_log TEXT DEFAULT '{}',        -- 纠错日志(JSON)
    decoded_at TEXT NOT NULL,
    FOREIGN KEY (dna_record_id) REFERENCES dna_sequences(id)
);

-- ------------------------------------------------------------
-- 表9: 操作日志表 (v3.0 引入, v3.1 去账号后保留; 写失败不得阻断主流程)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL                     -- 固定十枚举, 禁止业务代码临时造值
        CHECK (action IN ('create_record', 'update_record', 'delete_record',
                          'encode_dna', 'decode_dna', 'export_report',
                          'ai_extract', 'app_start', 'app_exit', 'backup_database')),
    target_record_id TEXT DEFAULT '',
    detail TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

-- ------------------------------------------------------------
-- 附表: v1迁移病症暂存表 (仅迁移期使用, 防止脏词条污染词典)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS legacy_disease_staging (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_text TEXT NOT NULL,               -- v1里的原始中文名
    record_id TEXT NOT NULL,
    result_cn TEXT DEFAULT '',
    matched_term_id INTEGER,                 -- 匹配上的词典id, NULL=未匹配
    reviewed INTEGER DEFAULT 0               -- 0待审 / 1已合并 / 2已丢弃
        CHECK (reviewed IN (0, 1, 2)),
    FOREIGN KEY (matched_term_id) REFERENCES disease_terms(id)
);

-- ------------------------------------------------------------
-- 索引 (21个)
-- 注: idx_entries_record / idx_disease_result 与两表的 UNIQUE 约束
--     自动索引前缀重复，保留不影响正确性，仅增加少量写入开销
-- ------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_archive_name        ON archive_records(name);
CREATE INDEX IF NOT EXISTS idx_archive_created     ON archive_records(created_at);
CREATE INDEX IF NOT EXISTS idx_archive_deleted     ON archive_records(is_deleted, created_at);
CREATE INDEX IF NOT EXISTS idx_entries_record      ON record_entries(record_id);
CREATE INDEX IF NOT EXISTS idx_entries_field       ON record_entries(field_key);
CREATE INDEX IF NOT EXISTS idx_entries_num         ON record_entries(field_key, value_num);
CREATE INDEX IF NOT EXISTS idx_def_section         ON field_definitions(section, sort_order);
CREATE INDEX IF NOT EXISTS idx_def_active          ON field_definitions(is_active);
CREATE INDEX IF NOT EXISTS idx_disease_result      ON record_diseases(record_id, disease_term_id);
CREATE INDEX IF NOT EXISTS idx_disease_term        ON record_diseases(disease_term_id);
CREATE INDEX IF NOT EXISTS idx_dna_record          ON dna_sequences(record_id, is_valid);
CREATE INDEX IF NOT EXISTS idx_dna_sequence        ON dna_sequences(dna_sequence);
CREATE INDEX IF NOT EXISTS idx_decode_dna          ON decode_records(dna_record_id);
CREATE INDEX IF NOT EXISTS idx_activity_action     ON user_activity_log(action, created_at);
CREATE INDEX IF NOT EXISTS idx_activity_time       ON user_activity_log(created_at);
-- v3.1: 码表与词条绑定
CREATE INDEX IF NOT EXISTS idx_icd_name            ON icd_codes(name);
CREATE INDEX IF NOT EXISTS idx_icd_category        ON icd_codes(category_code);
CREATE INDEX IF NOT EXISTS idx_icd_chapter         ON icd_codes(chapter_code);
CREATE INDEX IF NOT EXISTS idx_terms_icd           ON disease_terms(icd_code);
CREATE INDEX IF NOT EXISTS idx_terms_category      ON disease_terms(category, is_active);

-- ------------------------------------------------------------
-- 写入结构版本
-- (init_database() 应先查本表: 为空则建表并写版本; 低于当前版本则跑迁移)
-- ------------------------------------------------------------
INSERT INTO schema_meta (version, applied_at)
SELECT 'v3.1', datetime('now')
WHERE NOT EXISTS (SELECT 1 FROM schema_meta WHERE version = 'v3.1');

-- ============================================================
-- v3.0 -> v3.1 升级段（仅已有 v3.0 库需要，全新库跳过）
--
-- ⚠ 存量 v3.0 库不要直接执行本脚本：SQLite 的 ADD COLUMN 不支持
--   IF NOT EXISTS，本脚本的 `CREATE INDEX idx_terms_icd ON
--   disease_terms(icd_code)` 会因 icd_code 列还不存在而报
--   `no such column: icd_code`，且 executescript 中断时前面的语句
--   已提交，会留下「码表已建、列未加、版本未写」的半升级状态。
--
-- 正确做法 —— 使用迁移脚本（可重复执行，自带顺序与自检）：
--   python scripts/migrate_v3_0_to_v3_1.py --db data/db/medical_archive.db \
--          --xlsx "（1）疾病分类与代码国家临床版2.0（2022汇总版）.xlsx"
--
-- 脚本内部顺序（不可颠倒）：
--   1) 建 icd_codes + 3 个码表索引
--   2) 导入 35,867 条码表
--   3) PRAGMA table_info 判断后，逐列 ADD COLUMN：
--        ALTER TABLE disease_terms ADD COLUMN icd_code TEXT REFERENCES icd_codes(code);
--        ALTER TABLE disease_terms ADD COLUMN icd_match TEXT DEFAULT 'none'
--            CHECK (icd_match IN ('exact','manual','ai','none'));
--   4) 对齐 21 条索引清单（含补建 v3.0 漏掉的 idx_activity_action）
--   5) 写 schema_meta = v3.1
--   6) integrity_check / foreign_key_check / 条数自检
-- ============================================================

-- ============================================================
-- 建表后必须执行的种子数据:
--   1. sqlite3 ... < data/seed/seed_field_definitions.sql   (字段字典 60 条)
--   2. sqlite3 ... < data/seed/seed_disease_terms.sql       (病症词典 236 条)
--   3. python scripts/import_icd_codes.py --db ... --xlsx ... (ICD 码表 35,867 条)
-- 验收自检:
--   SELECT COUNT(*) FROM field_definitions;  -- 期望 60
--   SELECT COUNT(*) FROM icd_codes;          -- 期望 35867
--   SELECT COUNT(*) FROM icd_codes WHERE chapter_code IS NULL; -- 期望 0
--   PRAGMA foreign_key_check;                -- 期望无输出
-- ============================================================
