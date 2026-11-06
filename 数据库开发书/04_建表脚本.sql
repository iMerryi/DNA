-- ============================================================
-- DNA 医疗档案系统 建表脚本
-- 数据库: SQLite   |   结构版本: v3.0（v2.1 + 账号模块）
-- 用法: sqlite3 data/db/medical_archive.db < 04_建表脚本.sql
-- 注意: PRAGMA foreign_keys 是连接级设置，本脚本执行后，
--       应用程序每次 connect() 仍须重新执行 PRAGMA foreign_keys = ON
-- 幂等: 表与索引均使用 IF NOT EXISTS，可重复执行
-- 配套: 字段字典种子 -> data/seed/seed_field_definitions.sql (60条)
--       病症词典种子 -> seed_disease_terms.sql (236条, 待数据库同学产出)
-- ============================================================

PRAGMA foreign_keys = ON;

-- ------------------------------------------------------------
-- 表8: 结构版本表
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS schema_meta (
    version TEXT NOT NULL PRIMARY KEY,        -- 如 v3.0, 主键防重复写入
    applied_at TEXT NOT NULL
);

-- ------------------------------------------------------------
-- 表9: 用户表 (v3.0 新增, 单机数据归属区分)
-- 注意: password_hash 存哈希不存明文, 推荐格式
--       pbkdf2$200000$salt_hex$hash_hex (hashlib.pbkdf2_hmac, 20万次迭代)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,           -- 统一转小写存储判重
    password_hash TEXT NOT NULL,             -- 哈希(盐内嵌), 绝不存明文
    display_name TEXT DEFAULT '',
    role TEXT DEFAULT 'user'                 -- user / admin
        CHECK (role IN ('user', 'admin')),
    is_active INTEGER DEFAULT 1              -- 0=停用(保留数据, 拒绝登录)
        CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL,
    last_login_at TEXT DEFAULT ''
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
    owner_id INTEGER,                        -- 归属用户id(v3.0新增), NULL=v1迁移的历史数据
    created_at TEXT NOT NULL,                -- 系统写入
    updated_at TEXT NOT NULL,                -- 系统写入
    is_deleted INTEGER DEFAULT 0             -- 软删除标记(档案级)
        CHECK (is_deleted IN (0, 1)),
    FOREIGN KEY (owner_id) REFERENCES users(id)
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
-- 表5: 病症词典 (236条, term_key 不可变)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS disease_terms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    term_key TEXT NOT NULL UNIQUE,           -- 不可变英文标识, DNA载荷用这个
    chinese_name TEXT NOT NULL UNIQUE,
    english_name TEXT NOT NULL,              -- 英文展示名(可修改)
    category TEXT DEFAULT 'general',
    is_active INTEGER DEFAULT 1
        CHECK (is_active IN (0, 1)),
    updated_at TEXT DEFAULT ''
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
-- 表10: 操作日志表 (v3.0 新增, 审计链; 写失败不得阻断主流程)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,                         -- NULL=游客操作
    action TEXT NOT NULL                     -- 固定十枚举, 禁止业务代码临时造值
        CHECK (action IN ('register', 'login', 'logout', 'create_record',
                          'update_record', 'delete_record', 'encode_dna',
                          'decode_dna', 'export_report', 'ai_extract')),
    target_record_id TEXT DEFAULT '',
    detail TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
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
-- 索引 (16个)
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
CREATE INDEX IF NOT EXISTS idx_archive_owner       ON archive_records(owner_id);
CREATE INDEX IF NOT EXISTS idx_activity_user       ON user_activity_log(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_activity_action     ON user_activity_log(action, created_at);

-- ------------------------------------------------------------
-- 写入结构版本
-- (init_database() 应先查本表: 为空则建表并写版本; 低于当前版本则跑迁移)
-- ------------------------------------------------------------
INSERT INTO schema_meta (version, applied_at)
SELECT 'v3.0', datetime('now')
WHERE NOT EXISTS (SELECT 1 FROM schema_meta WHERE version = 'v3.0');

-- ============================================================
-- 建表后必须执行的种子数据:
--   1. sqlite3 ... < data/seed/seed_field_definitions.sql   (字段字典 60 条)
--   2. sqlite3 ... < data/seed/seed_disease_terms.sql       (病症词典 236 条)
-- 验收自检:
--   SELECT COUNT(*) FROM field_definitions;  -- 期望 60
--   PRAGMA foreign_key_check;                -- 期望无输出
-- ============================================================
