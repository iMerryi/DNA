# 医疗档案数据库主设计书 v3.1

> 模块：`data_store.py`（数据持久层）
> 版本：**v3.1（终稿，可直接施工）**
> 定位：**本文件是数据库开发的唯一依据。看完这一份就能开工，不需要再翻其他文档。**
> 取代关系：`database.md`、`database_design.md`、`database_v2_design.md`、`medical_archive_database_design.md`、`user_account_module_design.md` 全部归档，仅作历史记录，**冲突时以本文档为准**。
> 字段来源：`10.17医疗信息框架(4).docx`

**v3.1 变更（相对 v3.0）**：**移除账号体系**——单机单用户场景下账号不提供真实安全（能坐在电脑前的人可以直接打开 db 文件），只增加使用摩擦。删除 `users` 表、`archive_records.owner_id`、登录/注册/游客流程；**保留 `user_activity_log` 操作留痕**（去掉 user_id 列）。同时修复 v3.0 遗留问题：DDL 补上正文引用的 `legacy_disease_staging` 建表语句、`schema_meta` 加主键与幂等写入。

---

## 0. 怎么用这份文档

| 你是谁 | 只需要读 |
|---|---|
| 第一次接触项目 | §1 → §2 → §13（实施顺序），10 分钟能懂 |
| 数据库同学（写 `data_store.py`） | §3 → §4 → §5 → §6 → §8 → §12 |
| 前端同学（写 `ui_interface.py`） | §2 → §5（字段与枚举）→ §6 → §8（只调接口）→ §9 |
| 集成负责人（写 `main.py`） | §9 → §13 |

**三条铁律**（违反任何一条，集成必炸）：

1. `ui_interface.py` 不得出现 `sqlite3`，数据库读写只能调 `DataStore` 方法。
2. 所有可加密内容必须来自 §5 字段字典，业务代码不得临时造 `field_key`。
3. 编码载荷必须是纯 ASCII；开放文本不许为了"看起来像英文"去手工翻译。

---

## 1. 目标与不做什么

### 1.1 目标

| # | 目标 | 说明 |
|---|---|---|
| G1 | 界面中英分离 | 用户输入中文、看中文；DNA 编码与解码走英文/ASCII |
| G2 | 加字段不改表 | 内容键值化，新增字段只在字典加一行 |
| G3 | 一档双值 | 每个值同时存 `value_cn`（展示）与 `value_en`（编码） |
| G4 | 操作可追溯 | 保存、编码、解码、删除全程留痕（`user_activity_log`） |
| G5 | 结构可迁移 | `schema_meta` 记录版本，支持增量升级 |

### 1.2 明确不做（避免过度设计）

- 不做服务端、不做多用户并发写同一档案（单机桌面应用）。
- **不做账号体系（v3.1 定论）**：单机单用户下，账号既挡不住能物理接触电脑的人，也不参与"数据不出机 + DNA 编码 + 密钥哈希不落库"的真实防线，只增加每次启动的登录摩擦。若未来出现"一台电脑多操作员"的真实需求，再引入账号并补归属校验，不要提前设计。
- 不做开放文本的机器翻译入库存档（需要英文报告时另做"导出翻译"功能）。
- 不提前优化搜索：千条以内全表扫描可接受，FTS5 留到数据量上万再上。

---

## 2. 一页速览

### 2.1 数据流

```
用户界面（中文输入）
   │  表单 / 文档解析 / AI 识别
   ▼
data_classifier：中文标签 → field_key，枚举规范化，多值排 seq
   │
   ▼
record_entries：value_cn（展示用） + value_en（编码用，成对存储）
   │
   ▼
DNA 编码器：json.dumps(ensure_ascii=True, sort_keys=True) → 纯 ASCII 载荷 → ATCG 序列
   │
   ▼
解码：ASCII JSON → field_key 查字典取中文标签 → 回填 value_cn 展示
```

**一句话**：中文进、中文出，中间传输永远是英文/ASCII。

### 2.2 表关系

```
schema_meta            结构版本（v3.1）

archive_records        档案身份 + 状态（软删除）
   ├── record_entries   内容键值 ──> field_definitions  字段字典（60 条）
   ├── record_diseases  病症结果 ──> disease_terms      病症词典（236 条，term_key 不可变）
   └── dna_sequences    编码历史 ──> decode_records     解码历史（审计链）

user_activity_log      操作留痕（保存/编码/解码/删除/导出）
```

---

## 3. 数据模型（9 张表 + 1 张迁移暂存表）

### 3.1 `schema_meta` 结构版本

| 字段 | 类型 | 说明 |
|---|---|---|
| version | TEXT NOT NULL | 当前结构版本，如 `v3.1` |
| applied_at | TEXT NOT NULL | 应用时间 |

> `version` 建为 **PRIMARY KEY**：防止重复写入同一版本行（v3.0 版本表无主键，重复执行建表脚本会出现两行同版本记录）。
> 写入统一用 `INSERT ... SELECT ... WHERE NOT EXISTS`，保证幂等。

`init_database()` 先读本表最后一行：为空 → 建全表并写入当前版本；低于当前版本 → 依次跑迁移。

### 3.2 ~~`users` 账号~~（v3.1 已移除）

v3.0 曾设计账号表，v3.1 评估后移除（理由见 §1.2）。本节编号保留，避免全文编号漂移。

### 3.3 `archive_records` 档案身份与状态

字段全部来自框架文档「铭文部分」，物理列化以支持列表、搜索、排序。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | INTEGER | PK AUTOINCREMENT | |
| record_id | TEXT | NOT NULL UNIQUE | 业务号 `ARCHIVE_{YYYYMMDD}_{NNN}` |
| archive_number | TEXT | DEFAULT '' | 档案编号（用户填） |
| name | TEXT | NOT NULL | 姓名 |
| gender | TEXT | DEFAULT '' | `male` / `female` / `unknown` |
| nation | TEXT | DEFAULT '' | 民族 |
| id_number | TEXT | DEFAULT '' | 身份证号 |
| residence_address | TEXT | DEFAULT '' | 常住地址 |
| create_date | TEXT | DEFAULT '' | **建档日期**（业务日期） |
| source | TEXT | DEFAULT 'manual' | `manual` / `upload` / `ai` |
| created_at | TEXT | NOT NULL | **系统创建时间** |
| updated_at | TEXT | NOT NULL | |
| is_deleted | INTEGER | DEFAULT 0 | 软删除标记 |

**不设 `name_en`**：姓名无规范英文值（"张三"→"Zhang San" 是音译）。需要护照英文名时另设 `passport_name` 字段。

**`record_id` 生成算法**（必须与插入在同一事务内）：

```python
def _next_record_id(self, conn) -> str:
    today = datetime.now().strftime("%Y%m%d")
    prefix = f"ARCHIVE_{today}_"
    row = conn.execute(
        "SELECT record_id FROM archive_records WHERE record_id LIKE ? "
        "ORDER BY record_id DESC LIMIT 1", (prefix + "%",)
    ).fetchone()
    n = int(row["record_id"][len(prefix):]) + 1 if row else 1
    return f"{prefix}{n:03d}"
```

并发撞号时 `UNIQUE` 抛 `IntegrityError`，捕获后重试最多 3 次。

### 3.4 `field_definitions` 字段字典（唯一真名登记处）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | INTEGER | PK AUTOINCREMENT | |
| field_key | TEXT | NOT NULL UNIQUE | 英文规范键，**入库后不可改名** |
| section | TEXT | NOT NULL | 9 个分组之一，见 §5 |
| label_cn | TEXT | NOT NULL | 中文标签（展示） |
| label_en | TEXT | NOT NULL | 英文标签（协议/报告） |
| value_type | TEXT | DEFAULT 'text' | `text` / `date` / `number` / `enum` / `bool` |
| is_multi | INTEGER | DEFAULT 0 | 1 = 多值，用 `seq` 1..n |
| is_active | INTEGER | DEFAULT 1 | 0 = 停用：前端不渲染，历史值仍可读 |
| unit_cn / unit_en | TEXT | DEFAULT '' | 单位，如 `℃` / `°C` |
| sort_order | INTEGER | DEFAULT 0 | 表单与导出顺序（§5 行序 ×10 递增） |
| is_legacy | INTEGER | DEFAULT 0 | 1 = 从 v1 迁移补录 |

> 字段只停用、不删除。删除会让历史档案里的那一行变成孤儿。

### 3.5 `record_entries` 内容键值表（核心）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | INTEGER | PK AUTOINCREMENT | |
| record_id | TEXT | NOT NULL，FK → archive_records | `ON DELETE CASCADE` |
| field_key | TEXT | NOT NULL，FK → field_definitions | 外键挡住拼写漂移 |
| seq | INTEGER | DEFAULT 0 | 单值固定 0；多值从 1 连续递增 |
| value_cn | TEXT | DEFAULT '' | 中文值（展示） |
| value_en | TEXT | DEFAULT '' | 英文/规范值（编码交换） |
| value_num | REAL | NULL | 数值副本，供范围查询 |
| updated_at | TEXT | NOT NULL | |

**约束**：`UNIQUE(record_id, field_key, seq)` —— 一个字段的一次取值只占一个槽。
**故意没有 `is_deleted`**，原因见 §11 误区 5。

### 3.6 `record_diseases` 病症结果

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | INTEGER | PK AUTOINCREMENT | |
| record_id | TEXT | NOT NULL，FK | CASCADE |
| disease_term_id | INTEGER | NOT NULL，FK → disease_terms.id | |
| result_cn | TEXT | DEFAULT '' | 阴性 / 阳性 / 未查 |
| result_en | TEXT | DEFAULT '' | `negative` / `positive` / `not_tested` |
| seq | INTEGER | DEFAULT 0 | 同一病症多次筛查序号 |
| checked_at | TEXT | DEFAULT '' | 检查日期 |
| updated_at | TEXT | NOT NULL | |

**约束**：`UNIQUE(record_id, disease_term_id, seq)` —— 支持"听力筛查复筛"。

### 3.7 `disease_terms` 病症词典

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | INTEGER | PK AUTOINCREMENT | |
| term_key | TEXT | NOT NULL UNIQUE | **不可变**英文标识，如 `phenylketonuria` |
| chinese_name | TEXT | NOT NULL UNIQUE | 中文名 |
| english_name | TEXT | NOT NULL | 英文展示名（可修改） |
| category | TEXT | DEFAULT 'general' | 分类，英文规范值 |
| is_active | INTEGER | DEFAULT 1 | |
| updated_at | TEXT | DEFAULT '' | |

> `term_key` 是身份（永不变），`english_name` 是展示（可改词）。DNA 载荷写前者，否则改一次英文名历史档案就解不回来。

### 3.8 `dna_sequences` 编码历史

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER | PK AUTOINCREMENT |
| record_id | TEXT NOT NULL，FK | → archive_records |
| dna_sequence | TEXT NOT NULL | ATCG 序列 |
| key_hash | TEXT NOT NULL | 密钥哈希，**不存明文密钥** |
| cg_content | REAL | GC 含量 |
| thermal_stability | REAL | 热稳定性系数 |
| padded_zeros | INTEGER | 补齐 0 位数 |
| sequence_length | INTEGER | 序列长度 |
| original_text | TEXT | 编码前明文（审计用） |
| encoded_at | TEXT NOT NULL | |
| is_valid | INTEGER DEFAULT 1 | 当前有效版本标记 |
| payload_version | TEXT DEFAULT 'v2' | 载荷格式版本（**与文档版本无关，改文档不改载荷结构**） |
| payload_mode | TEXT DEFAULT 'bilingual' | `bilingual` / `canonical_en` |

> 重新编码不删旧行，只把旧行 `is_valid=0`。必须能回答"这条档案被编码过几次、每次什么参数"。

### 3.9 `decode_records` 解码历史

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER | PK AUTOINCREMENT |
| dna_record_id | INTEGER NOT NULL，FK | → dna_sequences.id |
| decoded_text | TEXT NOT NULL | 解码原文 |
| corrected_text | TEXT DEFAULT '' | 纠错后文本 |
| confidence | REAL DEFAULT 0 | 0.0–1.0 |
| error_rate | REAL DEFAULT 0 | 0.0–1.0 |
| correction_log | TEXT DEFAULT '{}' | 纠错日志（JSON） |
| decoded_at | TEXT NOT NULL | |

### 3.10 `user_activity_log` 操作留痕

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER | PK AUTOINCREMENT |
| action | TEXT NOT NULL | 见下枚举 |
| target_record_id | TEXT DEFAULT '' | 关联档案号，可空 |
| detail | TEXT DEFAULT '' | 补充说明（错误原因、导出格式等） |
| created_at | TEXT NOT NULL | |

**action 枚举（固定，不得在业务代码临时造值）**：
`create_record` / `update_record` / `delete_record` / `encode_dna` / `decode_dna` / `export_report` / `ai_extract` / `app_start` / `app_exit` / `backup_database`

> v3.0 的 `register` / `login` / `logout` 随账号体系移除；新增 `app_start` / `app_exit` / `backup_database` 补足十枚举——单机应用里这三件事恰恰是最需要留痕的。
> **留痕 ≠ 权限控制**：本地库文件理论上可被直接编辑，这是操作追溯，不是审计级防篡改。

---

## 4. DDL（可直接执行）

```sql
-- ⚠️ PRAGMA foreign_keys 是连接级设置，每次 connect 都要执行，见 §4.1
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_meta (
    version TEXT NOT NULL PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS archive_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id TEXT NOT NULL UNIQUE,
    archive_number TEXT DEFAULT '',
    name TEXT NOT NULL,
    gender TEXT DEFAULT '',
    nation TEXT DEFAULT '',
    id_number TEXT DEFAULT '',
    residence_address TEXT DEFAULT '',
    create_date TEXT DEFAULT '',
    source TEXT DEFAULT 'manual',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    is_deleted INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS field_definitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    field_key TEXT NOT NULL UNIQUE,
    section TEXT NOT NULL,
    label_cn TEXT NOT NULL,
    label_en TEXT NOT NULL,
    value_type TEXT DEFAULT 'text',
    is_multi INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    unit_cn TEXT DEFAULT '',
    unit_en TEXT DEFAULT '',
    sort_order INTEGER DEFAULT 0,
    is_legacy INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS disease_terms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    term_key TEXT NOT NULL UNIQUE,
    chinese_name TEXT NOT NULL UNIQUE,
    english_name TEXT NOT NULL,
    category TEXT DEFAULT 'general',
    is_active INTEGER DEFAULT 1,
    updated_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS record_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id TEXT NOT NULL,
    field_key TEXT NOT NULL,
    seq INTEGER DEFAULT 0,
    value_cn TEXT DEFAULT '',
    value_en TEXT DEFAULT '',
    value_num REAL,
    updated_at TEXT NOT NULL,
    UNIQUE (record_id, field_key, seq),
    FOREIGN KEY (record_id) REFERENCES archive_records(record_id) ON DELETE CASCADE,
    FOREIGN KEY (field_key) REFERENCES field_definitions(field_key)
);

CREATE TABLE IF NOT EXISTS record_diseases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id TEXT NOT NULL,
    disease_term_id INTEGER NOT NULL,
    result_cn TEXT DEFAULT '',
    result_en TEXT DEFAULT '',
    seq INTEGER DEFAULT 0,
    checked_at TEXT DEFAULT '',
    updated_at TEXT NOT NULL,
    UNIQUE (record_id, disease_term_id, seq),
    FOREIGN KEY (record_id) REFERENCES archive_records(record_id) ON DELETE CASCADE,
    FOREIGN KEY (disease_term_id) REFERENCES disease_terms(id)
);

CREATE TABLE IF NOT EXISTS dna_sequences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id TEXT NOT NULL,
    dna_sequence TEXT NOT NULL,
    key_hash TEXT NOT NULL,
    cg_content REAL DEFAULT 0,
    thermal_stability REAL DEFAULT 0,
    padded_zeros INTEGER DEFAULT 0,
    sequence_length INTEGER DEFAULT 0,
    original_text TEXT DEFAULT '',
    encoded_at TEXT NOT NULL,
    is_valid INTEGER DEFAULT 1,
    payload_version TEXT DEFAULT 'v2',
    payload_mode TEXT DEFAULT 'bilingual',
    FOREIGN KEY (record_id) REFERENCES archive_records(record_id)
);

CREATE TABLE IF NOT EXISTS decode_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dna_record_id INTEGER NOT NULL,
    decoded_text TEXT NOT NULL,
    corrected_text TEXT DEFAULT '',
    confidence REAL DEFAULT 0,
    error_rate REAL DEFAULT 0,
    correction_log TEXT DEFAULT '{}',
    decoded_at TEXT NOT NULL,
    FOREIGN KEY (dna_record_id) REFERENCES dna_sequences(id)
);

CREATE TABLE IF NOT EXISTS user_activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    target_record_id TEXT DEFAULT '',
    detail TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    -- action 枚举的数据库级兜底（验收 T12 就是测它）
    CHECK (action IN ('create_record', 'update_record', 'delete_record', 'encode_dna',
                      'decode_dna', 'export_report', 'ai_extract',
                      'app_start', 'app_exit', 'backup_database'))
);

-- v1 迁移期暂存表（仅迁移脚本使用；正文 §10.3 第 5 步引用的就是它）
CREATE TABLE IF NOT EXISTS legacy_disease_staging (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_text TEXT NOT NULL,             -- v1 里的原始中文病症名
    record_id TEXT NOT NULL,               -- 来源档案号
    result_cn TEXT DEFAULT '',             -- 原结果
    matched_term_id INTEGER,               -- 自动匹配上的词典 id，NULL = 未匹配
    reviewed INTEGER DEFAULT 0,            -- 0 待审 / 1 已合并 / 2 已丢弃
    FOREIGN KEY (matched_term_id) REFERENCES disease_terms(id)
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_archive_name      ON archive_records(name);
CREATE INDEX IF NOT EXISTS idx_archive_created   ON archive_records(created_at);
CREATE INDEX IF NOT EXISTS idx_archive_deleted   ON archive_records(is_deleted, created_at);
CREATE INDEX IF NOT EXISTS idx_archive_deleted   ON archive_records(is_deleted, created_at);
CREATE INDEX IF NOT EXISTS idx_entries_record    ON record_entries(record_id);
CREATE INDEX IF NOT EXISTS idx_entries_field     ON record_entries(field_key);
CREATE INDEX IF NOT EXISTS idx_entries_num       ON record_entries(field_key, value_num);
CREATE INDEX IF NOT EXISTS idx_def_section       ON field_definitions(section, sort_order);
CREATE INDEX IF NOT EXISTS idx_def_active        ON field_definitions(is_active);
CREATE INDEX IF NOT EXISTS idx_disease_result    ON record_diseases(record_id, disease_term_id);
CREATE INDEX IF NOT EXISTS idx_disease_term      ON record_diseases(disease_term_id);
CREATE INDEX IF NOT EXISTS idx_dna_record        ON dna_sequences(record_id, is_valid);
CREATE INDEX IF NOT EXISTS idx_dna_sequence      ON dna_sequences(dna_sequence);
CREATE INDEX IF NOT EXISTS idx_decode_dna        ON decode_records(dna_record_id);
CREATE INDEX IF NOT EXISTS idx_activity_time     ON user_activity_log(created_at);

-- 幂等写入版本号（重复执行不会产生第二行）
INSERT INTO schema_meta (version, applied_at)
SELECT 'v3.1', datetime('now')
WHERE NOT EXISTS (SELECT 1 FROM schema_meta WHERE version = 'v3.1');
```

**不为 `value_cn` / `value_en` 建索引**：`LIKE '%关键词%'` 的前置通配符用不上 B-tree 索引，只会白占空间、拖慢写入。千条以内全表扫描在 10ms 量级。

### 4.1 `PRAGMA foreign_keys` 必须每次连接都开

**它是连接级（per-connection）设置，不是数据库级。** 只在建表脚本里写一次，之后程序新建的每个连接外键都是关闭的：脏数据随便插、`ON DELETE CASCADE` 永远不生效，而且**不报错、不警告，安静失效**。

```python
def _connect(self) -> sqlite3.Connection:
    conn = sqlite3.connect(self.db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")   # ← 每次连接都要
    return conn
```

---

## 5. 字段字典（60 个）

规则：`field_key` 入库后不可改名；新增字段只允许追加；`sort_order` 按本表行序 ×10 递增。

| 分组 | 内容 | 字段数 | 存储位置 |
|---|---|---:|---|
| identity | 铭文（身份） | 7 | `archive_records` 物理列 |
| birth | 出生史与家庭信息 | 16 | `record_entries` |
| history | 既往史 / 家族史 | 7 | `record_entries` |
| allergy | 过敏史 | 3 | `record_entries` |
| lifestyle | 个人生活史 | 4 | `record_entries` |
| reproductive | 婚育史 / 月经史 | 2 | `record_entries` |
| complaint | 临床主诉与现病史 | 10 | `record_entries` |
| exam | 体格检查（体征） | 7 | `record_entries` |
| followup | 随访 | 4 | `record_entries` |
| **合计** | | **60** | 53 个进键值表 |

### 5.1 identity 铭文（物理列）

| field_key | 中文 | 英文 | 类型 |
|---|---|---|---|
| name | 姓名 | name | text |
| gender | 性别 | gender | enum: male/female/unknown |
| nation | 民族 | nation | text |
| id_number | 身份证号 | ID number | text |
| residence_address | 常住地址 | residence address | text |
| archive_number | 档案编号 | archive number | text |
| create_date | 建档日期 | archive creation date | date |

### 5.2 birth 出生史与家庭信息

| field_key | 中文 | 英文 | 类型 |
|---|---|---|---|
| birth_date | 出生日期 | date of birth | date |
| organization | 建档机构 | registering organization | text |
| abo_blood_type | ABO血型 | ABO blood type | enum: A/B/AB/O/unknown |
| rh_blood_type | Rh血型 | Rh blood type | enum: positive/negative/unknown |
| father_name | 父亲姓名 | father's name | text |
| father_phone | 父亲电话 | father's phone | text |
| mother_name | 母亲姓名 | mother's name | text |
| mother_phone | 母亲电话 | mother's phone | text |
| gestational_weeks | 胎龄（周） | gestational age (weeks) | number |
| birth_weight | 出生体重 | birth weight | number，g |
| birth_length | 出生身长 | birth length | number，cm |
| delivery_org | 分娩机构 | delivery institution | text |
| apgar_1min | Apgar评分(1分钟) | Apgar score (1 min) | number |
| apgar_5min | Apgar评分(5分钟) | Apgar score (5 min) | number |
| contact_phone | 联系电话 | contact phone | text |
| hukou_address | 户籍地址 | registered residence | text |

### 5.3 history 既往史 / 家族史

| field_key | 中文 | 英文 | 类型 |
|---|---|---|---|
| past_medical_history | 既往患病史 | past medical history | text |
| surgery_history | 手术史 | surgical history | text |
| trauma_history | 外伤史 | trauma history | text |
| transfusion_history | 输血史 | transfusion history | text |
| vaccination_history | 预防接种史 | vaccination history | text |
| family_history | 家族史 | family history | text |
| high_risk_factor | 高危因素 | high-risk factor | text，multi |

### 5.4 allergy 过敏史

| field_key | 中文 | 英文 | 类型 |
|---|---|---|---|
| allergy_source | 过敏原 | allergen | text，multi |
| allergy_reaction | 过敏反应 | allergic reaction | text，multi |
| drug_allergy | 药物过敏史 | drug allergy history | text |

### 5.5 lifestyle 个人生活史

| field_key | 中文 | 英文 | 类型 |
|---|---|---|---|
| smoking_history | 吸烟史（量化） | smoking history (quantified) | text |
| alcohol_history | 饮酒史（量化） | alcohol history (quantified) | text |
| diet_habit | 饮食情况 | diet habit | text |
| sleep_habit | 作息情况 | sleep pattern | text |

### 5.6 reproductive 婚育史 / 月经史

| field_key | 中文 | 英文 | 类型 |
|---|---|---|---|
| marriage_history | 婚育史 | marriage and childbearing history | text |
| menstrual_history | 月经史 | menstrual history | text |

### 5.7 complaint 临床主诉与现病史

| field_key | 中文 | 英文 | 类型 |
|---|---|---|---|
| disease_category | 疾病分类 | disease category | text |
| chief_complaint | 主诉 | chief complaint | text |
| symptom_onset | 起病时间 | onset time | date |
| symptom_severity | 缓急程度 | severity | enum: acute/chronic/recurrent |
| symptom_duration | 持续时间 | duration | text |
| accompanying_symptoms | 伴随症状 | accompanying symptoms | text，multi |
| mental_state | 精神状态 | mental state | text |
| appetite | 食欲 | appetite | text |
| sleep_quality | 睡眠 | sleep quality | text |
| bowel_urine | 大小便 | bowel and urine | text |

### 5.8 exam 体格检查（体征）

| field_key | 中文 | 英文 | 类型 |
|---|---|---|---|
| temperature | 体温 | temperature | number，℃ |
| pulse | 脉搏 | pulse | number，次/分 |
| respiration | 呼吸 | respiration | number，次/分 |
| blood_pressure | 血压 | blood pressure | text（如 90/60 mmHg） |
| specialty_exam | 专科查体 | specialty examination | text |
| positive_signs | 阳性体征 | positive signs | text，multi |
| negative_signs | 阴性体征 | negative signs | text，multi |

### 5.9 followup 随访

| field_key | 中文 | 英文 | 类型 |
|---|---|---|---|
| followup_date | 随访日期 | follow-up date | date，multi |
| current_weight | 当前体重 | current weight | number，multi |
| current_temperature | 当前体温 | current temperature | number，multi |
| followup_note | 随访备注 | follow-up note | text，multi |

> 随访四件套共用同一 `seq`（seq=1 即第 1 次随访），读取按 `seq` 排序组装。这是"用行表达数组"，比 JSON 字符串可靠。

---

## 6. 双语与编码规范

### 6.1 写入规则（R1–R9）

| 规则 | 内容 |
|---|---|
| R1 | `field_key` 必须已登记且 `is_active=1`，否则拒绝写入（防拼写漂移） |
| R2 | 界面输入存 `value_cn`；编码传输取 `value_en` |
| R3 | 枚举必须存规范英文值：`male/female/unknown`、`A/B/AB/O`、`positive/negative`、`negative/positive/not_tested`、`acute/chronic/recurrent` |
| R4 | `value_type=number` 必须同步写 `value_num`，原始字符串保留在 `value_cn/value_en` |
| R5 | 多值 `seq` 从 1 连续递增；单值固定 0；禁止重复槽位 |
| R6 | 开放文本若无可靠英文，`value_en` **必须等于 `value_cn`**（不可留空），编码器负责转 ASCII |
| R7 | 条目不做软删除：命中已有槽位即 `UPDATE` 覆盖；删除条目走物理 `DELETE` |
| R8 | 关键动作必须写 `user_activity_log`，`action` 取自 §3.10 枚举，禁止临时造值 |
| R9 | 日志写失败**不得阻断主流程**（内部吞异常并打印）；日志与业务使用同一连接 + WAL 模式，避免"另一连接被锁后日志被静默丢弃" |

### 6.2 双语的边界

只有两类字段需要**真正的英文值**：

| 类型 | 例子 | 原因 |
|---|---|---|
| 枚举字段 | `gender`=`male`、`symptom_severity`=`acute` | 规范值本身是英文，且跨系统交换 |
| 病症词典 | `term_key`=`phenylketonuria` | 稳定标识，用于 DNA 载荷 |

其余全部开放文本，`value_en = value_cn`。例如 `chief_complaint` = "咳嗽三天" → `value_en` 也是 "咳嗽三天"，**不是** "cough for three days"。

理由：
1. 编码器只需 ASCII，`ensure_ascii=True` 把中文转 `\uXXXX`，**无损可逆**；
2. 让队友手工翻译 50 多个字段，工作量大且制造不准确翻译；
3. 纠错环节要拿解码结果与原文比对，中英不一致反而无法比对。

需要英文报告时，用独立的"导出翻译"功能现翻，**不要污染存储层**。

### 6.3 DNA 编码载荷

```json
{
  "v": "v2",
  "record_id": "ARCHIVE_20261101_001",
  "fields": {
    "name": "Zhang San",
    "gender": "male",
    "temperature": "36.8",
    "chief_complaint": "\u54b3\u55fd\u4e09\u5929"
  },
  "diseases": [
    {"key": "phenylketonuria", "result": "negative"}
  ]
}
```

```python
payload = json.dumps(payload_obj, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
```

- `ensure_ascii=True` → 载荷**纯 ASCII、可逆、无损**；
- `sort_keys=True` → 同一档案多次编码字节级一致，便于比对、纠错、相似度计算；
- 多值字段在 `fields` 里是**有序数组**，顺序由 `seq` 决定；
- 病症用 `term_key`（不可变），不用 `english_name`（可变）。

### 6.4 解码回填

1. 解码得到纯 ASCII JSON；
2. 校验 `v` 与 `record_id`；
3. 按 `field_key` 从字典取中文标签，展示优先取档案原 `value_cn`，不存在则显示解码文本；
4. 病症按 `term_key` 反查词典，`result_en` 反查中文；
5. 遇到未登记的 `field_key` / `term_key`，**记入纠错日志，不静默丢弃**（静默丢弃会把"数据漂移"变成"数据消失"）。

---

## 7. 访问边界（v3.1）

无账号体系，**不要对外宣称"权限控制"**：

| 层级 | 做了什么 | 没做什么 |
|---|---|---|
| 操作留痕 | `log_activity` 记录编码/解码/删除等关键动作，可追溯 | 不是审计级不可篡改日志（本地库文件理论上可被直接编辑） |
| 数据访问 | 单机单用户，启动即可用，无登录摩擦 | 无隔离——能物理接触这台电脑的人即可读写全部数据 |

单机桌面应用的真实防线是**数据不出机 + DNA 编码 + 密钥哈希不落库**，账号不参与这道防线。

---

## 8. 接口契约（`DataStore`）

> **核心原则**：调用方永远只跟 `ArchiveRecord` 一个对象打交道；拆行/组装在 `DataStore` 内部完成。**不把 meta/entries/diseases 三段结构暴露给界面层。**
> 签名只加可选参数，不改已有必填参数，避免前端返工。

### 8.1 初始化

```python
def init_database(self) -> None                        # 建表 + 索引 + schema_meta
def init_field_definitions(self) -> int                # 灌 §5 的 60 条，返回新增数
def init_disease_terms(self) -> int                    # 灌 236 条词条，返回新增数；按缺失增量插入
def get_connection(self) -> sqlite3.Connection         # 内部已执行 PRAGMA foreign_keys=ON
def close(self) -> None
```

### 8.2 操作日志

```python
def log_activity(self, action: str,
                 target_record_id: str = "", detail: str = "") -> None
    """action 必须取自 §3.10 枚举；内部捕获异常，不阻断主流程。单机单用户，无 user_id。"""

def list_activity(self, action: str = None,
                  limit: int = 50, offset: int = 0) -> tuple[list, int]
    """查询操作历史，返回 (记录列表, 总数)。"""
```

### 8.3 档案 CRUD

```python
def save_record(self, record: ArchiveRecord) -> str
    """单事务写入身份 + entries + diseases，返回 record_id。
    不存在则生成 record_id；已存在则整条替换。"""

def load_record(self, record_id: str) -> Optional[ArchiveRecord]
    """返回完整档案；不存在或已软删返回 None。"""

def update_record(self, record: ArchiveRecord) -> bool
    """全量覆盖：身份 UPDATE；entries/diseases 该 record 的行先 DELETE 再 INSERT。单事务。"""

def delete_record(self, record_id: str) -> bool
    """软删除 archive_records.is_deleted=1；entries/diseases 保留；写 delete_record 日志。"""

def list_records(self, offset: int = 0, limit: int = 20, keyword: str = None) -> tuple[list[ArchiveRecord], int]
    """分页，返回 (items, 过滤后总数)。keyword 匹配 name/archive_number/id_number。
    items 只带身份 + entries，不加载 diseases（避免 N+1）。"""

def update_meta(self, record_id: str, **fields) -> bool
    """只更新身份列，供列表页快速编辑。"""

def upsert_entries(self, record_id: str, entries: list[dict]) -> int
    """局部更新内容。元素格式：
       {"field_key": "chief_complaint", "seq": 0,
        "value_cn": "咳嗽三天", "value_en": "咳嗽三天", "value_num": None}
    未出现的 field_key 保持原值；内部校验 R1/R4/R5。"""
```

### 8.4 字段字典

```python
def list_field_definitions(self, section: str = None,
                           only_active: bool = True) -> list[FieldDefinition]
    """UI 动态渲染表单的唯一依据，按 (section, sort_order) 排序。"""

def get_field_definition(self, field_key: str) -> Optional[FieldDefinition]

def add_field_definition(self, field_key: str, section: str, label_cn: str,
                         label_en: str, value_type: str = "text",
                         is_multi: bool = False, unit_cn: str = "",
                         unit_en: str = "", sort_order: int = 0) -> int
    """新增字段。field_key 已存在抛 IntegrityError。必须在 PR 中说明来源。"""
```

### 8.5 病症

```python
def search_disease(self, keyword: str, limit: int = 10) -> list[DiseaseTerm]
def get_disease_by_chinese(self, chinese_name: str) -> Optional[DiseaseTerm]
def get_disease_by_english(self, english_name: str) -> Optional[DiseaseTerm]
def get_disease_by_key(self, term_key: str) -> Optional[DiseaseTerm]      # 解码回填用
def list_disease_results(self, record_id: str) -> list[DiseaseResult]
def upsert_disease_result(self, record_id: str, term_key: str, result_cn: str,
                          seq: int = 0, checked_at: str = "") -> int     # 内部转 result_en
def get_all_categories(self) -> list[str]
def add_disease_term(self, term_key: str, chinese_name: str,
                     english_name: str, category: str = "general") -> int
```

### 8.6 文件处理

```python
def parse_document(self, file_path: str) -> str
    """解析 .txt/.docx/.pdf 提取纯文本；不支持格式抛 ValueError（不得静默返回空串）。"""
def save_upload_file(self, file_content: bytes, filename: str) -> str
    """保存到 data/uploads/{YYYYMMDD}/{uuid8}_{filename}。"""
def cleanup_temp_files(self, older_than_hours: int = 24) -> int
```

### 8.7 DNA 与解码

```python
def save_dna_sequence(self, dna_record: DNASequenceRecord) -> int
def load_dna_sequence(self, record_id: str) -> Optional[DNASequenceRecord]
def load_dna_by_sequence(self, dna_sequence: str) -> Optional[DNASequenceRecord]
def list_dna_sequences(self, offset: int = 0, limit: int = 20) -> list[DNASequenceRecord]
def invalidate_dna_sequence(self, dna_id: int) -> bool
def save_decode_record(self, decode_record: DecodeRecord) -> int
def list_decode_records(self, dna_record_id: int = None,
                        limit: int = 20) -> list[DecodeRecord]
```

### 8.8 相似度与导出

```python
def find_similar_records(self, ...) 
def find_similar_dna_sequences(self, dna_sequence: str, threshold: float = 0.8,
                               limit: int = 10) -> list
def export_record_to_json(self, record_id: str, output_path: str = None) -> str
def export_record_to_docx(self, record_id: str, output_path: str = None) -> str
def backup_database(self) -> str
def restore_database(self, backup_path: str) -> bool
def get_statistics(self) -> dict
```

### 8.9 异常定义

```python
class DataStoreError(Exception): ...
class FieldKeyNotRegisteredError(DataStoreError): ...    # field_key 未登记或已停用
class DuplicateSeqError(DataStoreError): ...             # 同 field_key 下 seq 重复
class RecordNotFoundError(DataStoreError): ...
```

---

## 9. 档案流程（前后端串联，v3.1 无账号版）

### 9.1 启动

`app_start` 日志 → 直达主界面（无登录页）。启动即用，无任何前置步骤。

### 9.2 保存档案

界面收集表单 → `data_classifier` 转 entries → `save_record(record)` →
成功：`log_activity("create_record", record_id)`。

### 9.3 编码 / 解码

编码成功：`log_activity("encode_dna", record_id)`；
解码成功：`log_activity("decode_dna", record_id)`；
失败：`detail` 里写失败原因（如 `key mismatch`）。

### 9.4 退出

`app_exit` 日志 → 正常关闭。

---

## 10. 迁移

### 10.1 从 v3.0 / v2.x 库升级到 v3.1

1. `init_database()` 读 `schema_meta` 最后一行；
2. 若版本 < v3.1：
   - 删除 `users` 表（`DROP TABLE IF EXISTS users`）；
   - `archive_records` 删除 `owner_id` 列（SQLite 3.35+ 支持 `ALTER TABLE ... DROP COLUMN`；更老版本需建新表搬数据）；
   - `user_activity_log` 重建（去掉 `user_id` 列），既有日志的 user_id 信息随迁移丢弃（单机无账号，本就无意义）；
   - 删除 `data/users.json`（若存在）——**明文密码文件留在磁盘上比在库里的哈希更危险**；
   - 索引补齐，写入新版本号。
3. **不重建业务表、不清档案数据。**

### 10.2 从 v1 迁移档案（历史数据）

顺序错误会直接跑不通，必须严格按此执行：

1. 建 v3.1 表；
2. 灌 60 条字段字典；
3. 灌 236 条病症词典；
4. 再迁档案数据（v1 的 23 个物理列 → §5 对应 `field_key`，7 个病症 → `record_diseases`，3 个随访 → `seq`）；
5. v1 的脏中文病症名先进 `legacy_disease_staging` 暂存表（§4 DDL 已含建表语句），人工审核后再并入标准词典，**不得直接 INSERT 新词条**。

---

## 11. 常见误区（给队友看的）

| # | 误区 | 实际情况 |
|---|---|---|
| 1 | "先在业务代码用个新 key，回头再登记" | 外键直接拒绝写入；必须先 `add_field_definition()` |
| 2 | "中文值顺手翻译成英文存进去" | 开放文本 `value_en = value_cn`；翻译会引入错误且增加工作量 |
| 3 | "列表页顺便把病症也查出来" | 触发 N+1 查询；`list_records` 只返回身份 + entries |
| 4 | "删除档案直接 DELETE" | 医疗数据要求软删除，物理删除仅限管理操作 |
| 5 | "加个 `is_deleted` 到 record_entries 更规范" | 与唯一约束冲突：删第 2 次随访后重加会撞 `UNIQUE` 报错 |
| 6 | "外键在建表脚本里写了就够了" | 连接级设置，每个连接都要 `PRAGMA foreign_keys=ON` |
| 7 | "多值字段直接存 JSON 数组更方便" | 无法查询、无法局部更新、协作时格式必错 |
| 8 | "英文名改了没关系" | `english_name` 可改，`term_key` 不可改；载荷引用后者 |
| 9 | "账号密码放 json 更简单" | **v3.1 已移除账号**：单机单用户下账号不提供真实安全，只增加摩擦；见 §1.2 |
| 10 | "日志随便记点什么都行" | `action` 是 CHECK 约束的十枚举，临时造值直接被数据库拒绝 |

---

## 12. 验收标准

| 编号 | 用例 | 期望结果 |
|---|---|---|
| T1 | 保存一条填 20 个字段的档案 | `archive_records` 1 行；`record_entries` **20 行**；无 JSON 字符串残留 |
| T2 | 同一档案存两次 | 主键不变、`updated_at` 变化、无重复行、已软删档案不被复活 |
| T3 | 存 3 次随访 | `seq` = 1/2/3，按 seq 排序读出 |
| T4 | **删掉第 2 次随访后再新增一次** | **不抛唯一约束错误**；新行 seq=2；总数仍为 3 |
| T5 | 病症结果写入 | 只能用词典内词条；词典外中文名抛错 |
| T6 | 生成 DNA 载荷 | 全 ASCII；两次编码字节级一致；解码后中文与输入一致 |
| T7 | 列表分页 | 返回 `(items, total)`，total 为过滤后总数 |
| T8 | 写入未登记 `field_key` | 抛 `FieldKeyNotRegisteredError` |
| T9 | 外键生效 | 插入不存在的 `record_id` 必须被拒绝（验证 PRAGMA 已开） |
| T10 | v1 迁移 | 前后记录数一致；抽查 3 条 23 个字段全部落位；词典未被污染 |
| T11 | 保存档案后查日志 | `user_activity_log` 新增 1 行，`action='create_record'`，`target_record_id` 正确 |
| T12 | 故意写非法 action（如 `'hack'`） | 被 CHECK 约束拒绝 |
| T13 | 日志写入失败模拟（锁表） | 主流程不受影响；同连接 + WAL 下不产生静默丢失 |
| T14 | 重复执行建表脚本 | `schema_meta` 仍只有 1 行 v3.1（幂等） |
| T15 | 插入 v1 脏病症名到暂存表 | `legacy_disease_staging` 可写入；未审核不得并入 `disease_terms` |
| T16 | 从 v3.0 库启动 | 自动删 `users`/`owner_id`、重建日志表，档案数据无丢失 |

> T4 和 T9 是专门为踩过的坑设的。**没有这两条，前面全过也可能带着 bug 上线。**

---

## 13. 实施顺序与分工

| 阶段 | 内容 | 责任 | 完成标志 |
|---|---|---|---|
| P1 | 建 9 表 + 暂存表 + 索引 + `schema_meta`（v3.1）；`_connect()` 每连接开外键 | 数据库同学 | 空库可建，T9、T14 通过 |
| P2 | 灌 60 条字段字典 + 236 条病症词典（种子文件放 `docs/seed/`，避免 `data/` 被 gitignore） | 数据库同学 | 字典可查，重复执行幂等 |
| P3 | `save_record` / `load_record` / `update_record` / `list_records` / `upsert_entries`（单事务 + R1/R4/R5/R7） | 数据库同学 | T1–T4、T7、T8 通过 |
| P4 | 操作日志：`log_activity` / `list_activity`（同连接 + WAL，吞异常） | 数据库同学 | T11–T13 通过 |
| P5 | 迁移：v3.0/v2.x → v3.1、v1 档案 | 数据库同学 | T10、T15、T16 通过 |
| P6 | 界面：改调 `DataStore`，保存/编码/解码入口调 `log_activity`；**无登录页，启动直达主界面** | 前端同学 | 保存落库，日志可查 |
| P7 | `data_classifier`：表单/AI 结果 → entries（中文标签映射、枚举规范化、seq 对齐） | 集成负责人 | 表单能真正写进 `record_entries` |
| P8 | DNA 按 §6.3 生成载荷，接 `dna_codec` | 编解码同学 + 集成负责人 | T6 通过 |

> P1–P4 完成即可用脚本先跑 T1–T15，不必等界面。

---

## 14. 待确认项

| # | 问题 | 当前默认 |
|---|---|---|
| 1 | DNA 编码器单条序列容量上限 | 待编解码同学给数值，据此定默认 `bilingual` 还是 `canonical_en` |
| 2 | 性别/血型是否对接国标编码 | 暂用 `male/female/unknown`、`A/B/AB/O` |
| 3 | 新 `field_key` 是否必须走 PR 审批 | 默认必须，禁止业务代码临时造 key |

---

## 附录 A：这份文档从哪来

| 来源 | 吸收了什么 |
|---|---|
| `medical_archive_database_design.md` | 表结构说明、字段字典 60 个、8 条设计取舍、R1–R7、误区清单、验收用例 |
| `database_v2_design.md` v2.1 | 完整 DDL、索引、接口签名、`record_id` 生成算法、迁移细则、`PRAGMA` 说明 |
| `user_account_module_design.md` | `user_activity_log` 操作留痕（v3.1 保留）；账号/权限部分已随 v3.1 评估移除 |
| `10.17医疗信息框架(4).docx` | 字段来源与分组依据 |

**归档建议**：上述前三份移入 `docs/modules/archive/`，标题加"已归档，见 `database_master_design.md`"，避免队友误用旧稿。
