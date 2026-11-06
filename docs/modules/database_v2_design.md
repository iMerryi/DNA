# 医疗档案数据库设计书 v2.1（键值 + 双语版）

> 模块：`data_store.py`
> 版本：**v2.1（定稿，可施工）**
> 依据：`10.17医疗信息框架(4).docx`（字段来源）、`api_contract.md` v2.1（接口契约）
> 定位：本文件是数据库开发的**唯一核心依据**；v1 字段不再采集，仅用于历史数据迁移

### v2.1 变更记录（相对 v2.0 草案）

| # | 变更 | 原因 |
|---|------|------|
| 1 | 新增 §5.2 `birth` 出生史分组（16 个字段） | v2.0 §8.2 引用的 16 个迁移字段在字段字典里不存在，迁移脚本会崩 |
| 2 | 删除 `archive_records.name_en` 列 | 姓名无规范英文值，且 §3.1/§5.1 均未登记，会永久为空 |
| 3 | 条目层取消软删除，`record_entries`/`record_diseases` 删除 `is_deleted` | 软删行仍占 `UNIQUE(record_id, field_key, seq)` 槽位，删后重加会撞约束 |
| 4 | §7 接口补全 Python 签名，`save_record` **保留单对象签名** | v2.0 的 `save_record(meta, entries, diseases)` 把存储结构泄漏到接口层，会强制前端所有调用点改造 |
| 5 | §3.8 修正索引说明，删除无效的 `value_cn`/`value_en` 索引 | `LIKE '%kw%'` 前置通配符无法使用 B-tree 索引，原注释论断错误 |
| 6 | 新增 `schema_meta` 表 | 需要记录库结构版本，否则以后无法做增量迁移 |
| 7 | `disease_terms` 新增 `term_key` 列 | DNA 载荷用 `{"key": "phenylketonuria"}`，`english_name` 可变不能当稳定标识 |
| 8 | 新增 §4.1 `PRAGMA foreign_keys` 说明、§3.1 `record_id` 生成算法 | 两者都是实际施工必然踩的坑 |
| 9 | §6.2 明确双语边界 | v2.0 表述易被误读为"每个中文都要英文翻译" |
| 10 | §8.3 增加 `legacy_disease_staging` 暂存表 | 防止 v1 脏中文名直接污染 236 条标准词典 |

---

## 1. 为什么要改（现状问题）

| 现状 | 后果 |
|---|---|
| 23 个固定物理列 | 框架文档里的既往史、过敏史、生活史、婚育史、主诉、体征……全都塞不进去，每加一类字段就要改表 |
| 中文 key 直接存 JSON | key 不稳定、跨表引用困难、代码不可读，容易拼写漂移 |
| 无中英对照 | 同一个概念在界面、AI、DNA 里有三套写法（`父亲电话` / `father_phone` / `Apgar(1min)`） |
| 保存只写 JSON 文件 | `archive_records` 永远 0 行，4 张表里 3 张是空壳 |
| 病症词典仅 3 条 | 搜索、标准词条映射全部失效 |

**v2 的核心目标：内容一律键值化、新增字段不改表、编码只走 ASCII。**

> ⚠️ **一个必须认清的事实**：v1 的 33 个字段（23 物理 + 7 病症 + 3 随访）**全部是新生儿出生档案信息**，而框架文档要求的 33 个字段（既往史 7 + 过敏 3 + 生活史 4 + 婚育 2 + 主诉症状 10 + 体征 7）**全部是病史主诉体征**。两者精确交集只有「体温」1 个。产品实际需要约 60 个字段，现有模型缺一半。**这个缺口与键值化无关，是需求本身没落地。**

---

## 2. 设计原则

1. **身份与内容分离**
   - 身份字段（姓名、性别、证件号等）保留物理列：列表、搜索、排序都要用，走列最快。
   - 其余全部内容进键值表，新增字段只往字典里加一行。
2. **`field_key` 是唯一真名**
   - 统一 `snake_case` 英文，如 `past_medical_history`；中文标签只用于展示，**任何代码不得用中文做 key**。
3. **双语成对存储，但只对枚举和词典要求真英文**
   - 每个值存 `value_cn` 与 `value_en`；字典里存 `label_cn` 与 `label_en`。
   - **只有枚举字段（性别/血型/病症结果/缓急）和病症词典需要真正的英文值。**
   - **开放文本的 `value_en` 直接等于 `value_cn`，禁止为凑英文而造不准确的翻译**（详见 §6.2）。
4. **多值用 `seq`，不搞 JSON 字符串**
   - 随访、多条过敏原等重复项用 `(record_id, field_key, seq)` 唯一约束表达行。
5. **编码统一走 ASCII**
   - DNA 编码输入为 `json.dumps(..., ensure_ascii=True, sort_keys=True)`；中文自动转 `\uXXXX`，**无损且纯 ASCII**，不需要拼音翻译。
6. **档案层软删除，内容层物理覆盖**
   - 档案删除用 `archive_records.is_deleted` 标记，不物理删。
   - 内容条目（`record_entries` / `record_diseases`）**不做软删除**，写入即覆盖、删除即物理删除。原因见 §6.1 R7。
   - 不用 `INSERT OR REPLACE`；更新走 `UPDATE`，避免主键漂移。
7. **结构版本可追溯**
   - `schema_meta` 表记录当前库结构版本，`init_database()` 据此判断是否需要迁移。
8. **外键每次连接都要启用**
   - `PRAGMA foreign_keys` 是连接级设置，必须在每次 `connect()` 后执行，详见 §4.1。

---

## 3. 数据模型

```
schema_meta (结构版本)
archive_records (身份/状态)
   └── record_entries (内容键值) ──> field_definitions (字段字典)
   └── record_diseases (病症结果) ──> disease_terms (病症词典)
   └── dna_sequences (编码结果) ──> decode_records (解码历史)
```

### 3.1 表1 `archive_records`（身份与状态，只保留查询必需的列）

字段全部来自框架文档的「铭文部分」：

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | INTEGER | PK AUTOINCREMENT | 自增主键 |
| record_id | TEXT | NOT NULL UNIQUE | 业务号 `ARCHIVE_{YYYYMMDD}_{NNN}` |
| archive_number | TEXT | DEFAULT '' | 档案编号（用户填） |
| name | TEXT | NOT NULL | 姓名 |
| gender | TEXT | DEFAULT '' | `male` / `female` / `unknown`（规范值） |
| nation | TEXT | DEFAULT '' | 民族 |
| id_number | TEXT | DEFAULT '' | 身份证号 |
| residence_address | TEXT | DEFAULT '' | 常住地址 |
| create_date | TEXT | DEFAULT '' | **建档日期**（业务日期，用户填） |
| source | TEXT | DEFAULT 'manual' | manual / upload / ai |
| created_at | TEXT | NOT NULL | **记录创建时间**（系统写） |
| updated_at | TEXT | NOT NULL | 记录更新时间（系统写） |
| is_deleted | INTEGER | DEFAULT 0 | 软删除标记 |

> **不设 `name_en`**：姓名无规范英文值（"张三"→"Zhang San" 是音译而非规范值）。若需护照英文名，属独立字段 `passport_name`，不叫 `name_en`。

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

并发冲突时 `UNIQUE` 抛 `IntegrityError`，捕获后重试最多 3 次。

### 3.2 表2 `field_definitions`（字段字典，唯一真名登记处）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | INTEGER | PK AUTOINCREMENT | |
| field_key | TEXT | NOT NULL UNIQUE | 英文规范键，如 `allergy_source` |
| section | TEXT | NOT NULL | 分组：`identity` / `birth` / `history` / `allergy` / `lifestyle` / `reproductive` / `complaint` / `exam` / `followup` |
| label_cn | TEXT | NOT NULL | 中文标签 |
| label_en | TEXT | NOT NULL | 英文标签 |
| value_type | TEXT | DEFAULT 'text' | `text` / `date` / `number` / `enum` / `bool` |
| is_multi | INTEGER | DEFAULT 0 | 1 = 可多值（用 seq 1..n） |
| is_active | INTEGER | DEFAULT 1 | 0 = 已停用（前端不再渲染，历史值仍可读） |
| unit_cn / unit_en | TEXT | DEFAULT '' | 单位，如 `℃` / `°C` |
| sort_order | INTEGER | DEFAULT 0 | 表单与导出顺序 |
| is_legacy | INTEGER | DEFAULT 0 | 1 = 从 v1 迁移而来 |

### 3.3 表3 `record_entries`（内容键值表，核心）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | INTEGER | PK AUTOINCREMENT | |
| record_id | TEXT | NOT NULL | 关联 `archive_records.record_id` |
| field_key | TEXT | NOT NULL | 关联 `field_definitions.field_key` |
| seq | INTEGER | DEFAULT 0 | **单值固定为 0**；多值从 1 连续递增 |
| value_cn | TEXT | DEFAULT '' | 中文值（展示） |
| value_en | TEXT | DEFAULT '' | 英文/规范值（编码交换） |
| value_num | REAL | NULL | `value_type=number` 时的数值，便于范围查询 |
| updated_at | TEXT | NOT NULL | 更新时间 |

**约束**：`UNIQUE(record_id, field_key, seq)`；外键指向 `archive_records.record_id` 与 `field_definitions.field_key`。
**无 `is_deleted`** —— 条目级不做软删除，见 §6.1 R7。

### 3.4 表4 `record_diseases`（病症结果，词典驱动）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | INTEGER | PK AUTOINCREMENT | |
| record_id | TEXT | NOT NULL | 档案号 |
| disease_term_id | INTEGER | NOT NULL | 关联 `disease_terms.id` |
| result_cn | TEXT | DEFAULT '' | 结果中文：阴性 / 阳性 / 未查 |
| result_en | TEXT | DEFAULT '' | `negative` / `positive` / `not_tested` |
| seq | INTEGER | DEFAULT 0 | 多次筛查序号 |
| checked_at | TEXT | DEFAULT '' | 检查日期 |
| updated_at | TEXT | NOT NULL | |

**约束**：`UNIQUE(record_id, disease_term_id, seq)`。

> 病症名称本身属于词典（`disease_terms`），不属于键值表；这样 236 条词条升级只改一处。

### 3.5 表5 `disease_terms`（词典，新增 `term_key`）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | INTEGER | PK AUTOINCREMENT | |
| term_key | TEXT | NOT NULL UNIQUE | **不可变的英文标识**，如 `phenylketonuria`，DNA 载荷用这个 |
| chinese_name | TEXT | NOT NULL UNIQUE | 中文名 |
| english_name | TEXT | NOT NULL | 英文展示名（可变） |
| category | TEXT | DEFAULT 'general' | 分类用英文规范值 |
| is_active | INTEGER | DEFAULT 1 | 词条启停 |
| updated_at | TEXT | DEFAULT '' | |

> **`term_key` 一旦入库不再改名**；`english_name` 允许修词（如 `Phenylketonuria` → `phenylketonuria`），不影响已编码的 DNA 载荷。

### 3.6 表6 `dna_sequences`（沿用，增加载荷版本）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | 主键 |
| record_id | TEXT NOT NULL | 关联档案 |
| dna_sequence | TEXT NOT NULL | DNA 序列 |
| key_hash | TEXT NOT NULL | 密钥哈希 |
| cg_content | REAL | GC 含量 |
| thermal_stability | REAL | 热稳定性系数 |
| padded_zeros | INTEGER | 补齐的 0 位数 |
| sequence_length | INTEGER | 序列长度 |
| original_text | TEXT | 编码前明文 |
| encoded_at | TEXT NOT NULL | 编码时间 |
| is_valid | INTEGER DEFAULT 1 | 是否有效 |
| payload_version | TEXT DEFAULT 'v2' | **编码载荷格式版本，必须可追溯** |
| payload_mode | TEXT DEFAULT 'bilingual' | `bilingual` / `canonical_en` |

外键：`record_id` → `archive_records.record_id`。

### 3.7 表7 `decode_records`

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | 主键 |
| dna_record_id | INTEGER NOT NULL | 外键 → `dna_sequences.id` |
| decoded_text | TEXT NOT NULL | 解码原文 |
| corrected_text | TEXT DEFAULT '' | 纠错后文本 |
| confidence | REAL DEFAULT 0 | 置信度 0.0-1.0 |
| error_rate | REAL DEFAULT 0 | 错误率 0.0-1.0 |
| correction_log | TEXT DEFAULT '{}' | 纠错日志（JSON） |
| decoded_at | TEXT NOT NULL | 解码时间 |

### 3.8 表8 `schema_meta`（结构版本）

| 字段 | 类型 | 说明 |
|---|---|---|
| version | TEXT NOT NULL | 如 `v2.1` |
| applied_at | TEXT NOT NULL | 应用时间 |

`init_database()` 先读本表最后一行：为空则建全表并写入当前版本；低于当前版本则依次跑迁移脚本。

### 3.9 索引

```sql
CREATE INDEX idx_archive_name        ON archive_records(name);
CREATE INDEX idx_archive_created     ON archive_records(created_at);
CREATE INDEX idx_archive_deleted     ON archive_records(is_deleted, created_at);
CREATE INDEX idx_entries_record      ON record_entries(record_id);
CREATE INDEX idx_entries_field       ON record_entries(field_key);
CREATE INDEX idx_entries_num         ON record_entries(field_key, value_num);
CREATE INDEX idx_def_section         ON field_definitions(section, sort_order);
CREATE INDEX idx_def_active          ON field_definitions(is_active);
CREATE INDEX idx_disease_result      ON record_diseases(record_id, disease_term_id);
CREATE INDEX idx_disease_term        ON record_diseases(disease_term_id);
CREATE INDEX idx_dna_record          ON dna_sequences(record_id, is_valid);
CREATE INDEX idx_dna_sequence        ON dna_sequences(dna_sequence);
CREATE INDEX idx_decode_dna          ON decode_records(dna_record_id);
```

> **关于 `LIKE '%关键词%'`**：前置通配符无法使用 B-tree 索引，SQLite 会退化为全表扫描。
> 本设计**不为 `value_cn` / `value_en` 单独建索引**，因为那种索引在包含匹配下不会生效，只白占空间。
> 当前数据量（单机、千条以内）全表扫描在 10ms 量级，可接受。
> **数据量超过 1 万条或用户明显感知卡顿时**，再启用 FTS5 虚表（DDL 见附录 A），不要提前优化。

---

## 4. DDL（可直接执行）

```sql
PRAGMA foreign_keys = ON;   -- 注意：连接级设置，每次 connect 都要执行，见 §4.1

CREATE TABLE IF NOT EXISTS schema_meta (
    version TEXT NOT NULL,
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

INSERT INTO schema_meta (version, applied_at) VALUES ('v2.1', datetime('now'));
```

### 4.1 关于 `PRAGMA foreign_keys`

**这是连接级（per-connection）设置，不是数据库级。** 只在建表脚本里写一次，之后所有新连接的外键约束都是关闭的，脏数据可以随便插入，`ON DELETE CASCADE` 也永远不生效。

必须这样写：

```python
def _connect(self) -> sqlite3.Connection:
    conn = sqlite3.connect(self.db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")   # ← 每次连接都要
    return conn
```

---

## 5. 字段字典（来源：`10.17医疗信息框架(4).docx` + v1 迁移补录）

> 规则：`field_key` 一旦入库不再改名；新增字段只允许追加。中文标签可改，`field_key` 不可改。
> 所有字段按 `section` 分组，`sort_order` 决定表单顺序。

> 📦 **已生成种子数据**：`data/seed/seed_field_definitions.sql`（60 条，可直接执行）。
> 由 `scripts/gen_field_seed.py` 从本节表格自动提取，**改字段请改本节的表，再重跑脚本**，不要手工改 SQL。
> 脚本带 `ON CONFLICT(field_key) DO UPDATE`，重复执行幂等，可作为版本升级的补录手段。

### 5.1 `identity` 铭文（物理列，不进 entries）

| field_key | 中文 | 英文 | 物理列 | 类型 |
|---|---|---|---|---|
| name | 姓名 | name | `archive_records.name` | text |
| gender | 性别 | gender | `archive_records.gender` | enum: male/female/unknown |
| nation | 民族 | nation | `archive_records.nation` | text |
| id_number | 身份证号 | ID number | `archive_records.id_number` | text |
| residence_address | 常住地址 | residence address | `archive_records.residence_address` | text |
| archive_number | 档案编号 | archive number | `archive_records.archive_number` | text |
| create_date | 建档日期 | archive creation date | `archive_records.create_date` | date |

> 界面显示用中文，数据库存规范值（如 `male`/`female`）。

### 5.2 `birth` 出生史与家庭信息 ⭐ v2.1 新增

来自 v1 的 23 个物理字段中不属于身份列的部分。**这是儿童健康档案的核心信息，不是 legacy 垃圾**，作为正式字段采集。

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
| birth_weight | 出生体重(g) | birth weight (g) | number |
| birth_length | 出生身长(cm) | birth length (cm) | number |
| delivery_org | 分娩机构 | delivery institution | text |
| apgar_1min | Apgar评分(1分钟) | Apgar score (1 min) | number |
| apgar_5min | Apgar评分(5分钟) | Apgar score (5 min) | number |
| contact_phone | 联系电话 | contact phone | text |
| hukou_address | 户籍地址 | registered residence | text |

### 5.3 `history` 患者基础与背景信息类

来自框架文档「一、1. 既往史/家族史」。

| field_key | 中文 | 英文 | 类型 |
|---|---|---|---|
| past_medical_history | 既往患病史 | past medical history | text |
| surgery_history | 手术史 | surgical history | text |
| trauma_history | 外伤史 | trauma history | text |
| transfusion_history | 输血史 | transfusion history | text |
| vaccination_history | 预防接种史 | vaccination history | text |
| family_history | 家族史 | family history | text |
| high_risk_factor | 高危因素 | high-risk factor | text, multi |

### 5.4 `allergy` 过敏史

来自框架文档「一、2. 过敏史」。

| field_key | 中文 | 英文 | 类型 |
|---|---|---|---|
| allergy_source | 过敏原 | allergen | text, multi |
| allergy_reaction | 过敏反应 | allergic reaction | text, multi |
| drug_allergy | 药物过敏史 | drug allergy history | text |

### 5.5 `lifestyle` 个人生活史

来自框架文档「一、3. 个人生活史」。

| field_key | 中文 | 英文 | 类型 |
|---|---|---|---|
| smoking_history | 吸烟史（量化） | smoking history (quantified) | text |
| alcohol_history | 饮酒史（量化） | alcohol history (quantified) | text |
| diet_habit | 饮食情况 | diet habit | text |
| sleep_habit | 作息情况 | sleep pattern | text |

### 5.6 `reproductive` 婚育史 / 月经史

来自框架文档「一、4. 婚育史/月经史」。

| field_key | 中文 | 英文 | 类型 |
|---|---|---|---|
| marriage_history | 婚育史 | marriage and childbearing history | text |
| menstrual_history | 月经史 | menstrual history | text |

### 5.7 `complaint` 临床主诉与现病史类

来自框架文档「二、1. 疾病分类」「二、2. 症状表现」。

| field_key | 中文 | 英文 | 类型 |
|---|---|---|---|
| disease_category | 疾病分类 | disease category | text |
| chief_complaint | 主诉 | chief complaint | text |
| symptom_onset | 起病时间 | onset time | date |
| symptom_severity | 缓急程度 | severity | enum: acute/chronic/recurrent |
| symptom_duration | 持续时间 | duration | text |
| accompanying_symptoms | 伴随症状 | accompanying symptoms | text, multi |
| mental_state | 精神状态 | mental state | text |
| appetite | 食欲 | appetite | text |
| sleep_quality | 睡眠 | sleep quality | text |
| bowel_urine | 大小便 | bowel and urine | text |

### 5.8 `exam` 体格检查（体征）

来自框架文档「二、3. 体格检查（体征）」。

| field_key | 中文 | 英文 | 类型 |
|---|---|---|---|
| temperature | 体温 | temperature | number（℃） |
| pulse | 脉搏 | pulse | number（次/分） |
| respiration | 呼吸 | respiration | number（次/分） |
| blood_pressure | 血压 | blood pressure | text（如 90/60 mmHg） |
| specialty_exam | 专科查体 | specialty examination | text |
| positive_signs | 阳性体征 | positive signs | text, multi |
| negative_signs | 阴性体征 | negative signs | text, multi |

### 5.9 `followup` 随访

框架文档未单列随访，但 v1 功能需要保留，作为动态补充项。

| field_key | 中文 | 英文 | 类型 |
|---|---|---|---|
| followup_date | 随访日期 | follow-up date | date, multi |
| current_weight | 当前体重 | current weight | number, multi |
| current_temperature | 当前体温 | current temperature | number, multi |
| followup_note | 随访备注 | follow-up note | text, multi |

> 随访四件套用同一 `seq` 对齐（seq=1 表示第一次随访），不再用 JSON 数组。
> 读取时 `SELECT ... WHERE field_key IN (...) ORDER BY seq` 即可按次组装。

### 5.10 字段统计

| section | 数量 |
|---|---|
| identity（物理列） | 7 |
| birth | 16 |
| history | 7 |
| allergy | 3 |
| lifestyle | 4 |
| reproductive | 2 |
| complaint | 10 |
| exam | 7 |
| followup | 4 |
| **合计** | **60**（其中 53 个进 `record_entries`） |

---

## 6. 双语与编码规范

### 6.1 写入规则

| 规则 | 说明 |
|---|---|
| R1 | `field_key` 必须已登记在 `field_definitions` 且 `is_active=1`，否则拒绝写入（防止拼写漂移） |
| R2 | 界面输入存 `value_cn`；编码传输取 `value_en` |
| R3 | 枚举类必须存规范英文值：`male`/`female`/`unknown`、`A`/`B`/`AB`/`O`、`positive`/`negative`、`negative`/`positive`/`not_tested`、`acute`/`chronic`/`recurrent`，中文只做展示 |
| R4 | `value_type=number` 必须把数值同时写入 `value_num`，且 `value_cn`/`value_en` 存原始字符串 |
| R5 | 多值字段 `seq` 从 1 连续递增，单值字段 `seq` 固定为 0；禁止重复 `(record_id, field_key, seq)` |
| R6 | **开放文本若无可靠英文翻译，`value_en` 必须与 `value_cn` 相同（不可留空）**；禁止为凑英文造不准确的翻译 |
| R7 | **条目不做软删除**：写入 `(record_id, field_key, seq)` 命中已有行 → `UPDATE` 覆盖；未提交的字段不动；删除条目走物理 `DELETE` |

**关于 R7 的原因**（v2.0 的设计缺陷，v2.1 修正）：

`UNIQUE(record_id, field_key, seq)` + 条目级 `is_deleted` 会互相打架。场景：一条档案有 3 次随访（seq=1/2/3），用户删掉第 2 次（`is_deleted=1`，行仍在），随后重新添加一次随访 → 新行 seq=2 → **撞唯一约束报错**。正常编辑会被挡住。

取消条目级软删除后：
- 语义干净：一个槽位一行，"写入即覆盖"；
- 不需要在 `upsert_entries()` 里写"软删行复活"的特殊逻辑；
- 档案级软删除（`archive_records.is_deleted`）仍然保留，满足审计需求。

### 6.2 双语的边界（必须写进代码注释）

**只有两类字段需要真正的英文值：**

| 类型 | 例子 | 说明 |
|---|---|---|
| 枚举字段 | `gender`=`male`、`symptom_severity`=`acute`、`abo_blood_type`=`A` | 规范值本身就是英文 |
| 病症词典 | `disease_terms.term_key` = `phenylketonuria` | 跨系统与 DNA 载荷的稳定标识 |

**其余全部是开放文本，`value_en` 直接等于 `value_cn`。** 例如：

- `chief_complaint` = 主诉"咳嗽三天" → `value_cn` = "咳嗽三天"，`value_en` = **"咳嗽三天"**（不是 `"cough for three days"`）
- `past_medical_history` = "2019年肺炎住院" → `value_en` 同样存中文

**理由**：编码器只需要 ASCII，`ensure_ascii=True` 会把中文转成 `\uXXXX`，无损可逆。为了让"看起来像英文"而让队友去手工翻译 50 多个字段，既增加工作量又制造不准确的翻译，后续纠错时反而无法比对。

**如果某天需要给 AI 或外部系统提供英文版报告**，那是独立的"翻译/导出"功能，用 LLM 现翻，不要污染存储层。

### 6.3 DNA 编码载荷

**编码前准备**：先把一条档案转成 `fields` 字典，每个字段取 `value_en`（如为空则回退到 `value_cn`），然后：

```python
payload_obj = {
    "v": "v2",
    "record_id": "ARCHIVE_20261101_001",
    "fields": {
        "name": "Zhang San",
        "gender": "male",
        "nation": "Han",
        "residence_address": "...",
        "disease_category": "...",
        "temperature": "36.8",
        "chief_complaint": "..."
    },
    "diseases": [
        {"key": "phenylketonuria", "result": "negative"}
    ],
}
payload = json.dumps(payload_obj, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
```

- `ensure_ascii=True` 保证载荷**纯 ASCII**，中文变成 `\uXXXX`，**可逆、无损**；
- `sort_keys=True` 保证同一份档案每次编码结果稳定（便于比对、纠错、相似度）；
- 界面显示：从 `record_entries` 读 `value_cn`；编码传输：读 `value_en`；两者独立；
- 多值字段在 `fields` 里是**有序数组**，顺序由 `seq` 决定；
- 病症用 `disease_terms.term_key`（不可变），不用 `english_name`（可变）。

### 6.4 解码与回填

1. DNA 解码得到纯 ASCII JSON；
2. 校验 `v` 与 `record_id`；
3. 按 `field_key` 从 `field_definitions` 取中文标签，回填界面展示 `value_cn`；
4. 病症按 `term_key` 反查 `disease_terms`；
5. 遇到字典里不存在的 `field_key` / `term_key` 视为数据漂移，**进纠错日志而不是静默丢弃**。

---

## 7. DataStore 接口（v2.1，与 `api_contract.md` v2.1 一致）

> **核心原则**：接口签名保持 v1 的形态，**不把存储结构（meta/entries/diseases 三段）暴露给调用方**。
> 调用方永远只跟 `ArchiveRecord` 一个对象打交道，拆行/组装由 `DataStore` 内部完成。

### 7.1 初始化

```python
def init_database(self) -> None
def init_field_definitions(self) -> int          # 灌 §5 字段字典，返回新增数
def init_disease_terms(self) -> int              # 灌 236 条词条，返回新增数
def get_connection(self) -> sqlite3.Connection   # 内部已执行 PRAGMA foreign_keys=ON
def close(self) -> None
```

### 7.2 档案 CRUD（签名与 v1 完全一致）

```python
def save_record(self, record: ArchiveRecord) -> str
    """单事务写入身份 + entries + diseases。
    已存在（按 record_id）则整条替换；不存在则新建并生成 record_id。返回 record_id。"""

def load_record(self, record_id: str) -> Optional[ArchiveRecord]
    """返回完整 ArchiveRecord；不存在或已软删返回 None。"""

def update_record(self, record: ArchiveRecord) -> bool
    """全量覆盖：身份字段 UPDATE，entries 先 DELETE 该 record 的全部行再 INSERT，
    diseases 同理。一个事务内完成。"""

def delete_record(self, record_id: str) -> bool
    """软删除：archive_records.is_deleted = 1，entries/diseases 保留不动。"""

def list_records(self, offset: int = 0, limit: int = 20,
                 keyword: str = None) -> tuple[list[ArchiveRecord], int]
    """分页列表，返回 (items, 过滤后总数)。
    keyword 匹配 name / archive_number / id_number。
    items 中的 ArchiveRecord 只带身份字段 + entries（不加载 diseases，避免 N+1）。"""

def update_meta(self, record_id: str, **fields) -> bool
    """只更新身份字段（name/gender/nation/id_number/residence_address/
    archive_number/create_date）。用于列表页快速编辑。"""

def upsert_entries(self, record_id: str, entries: list[dict]) -> int
    """局部更新内容，不重建整条记录。返回写入行数。
    entries 元素格式：
        {"field_key": "chief_complaint", "seq": 0,
         "value_cn": "咳嗽三天", "value_en": "咳嗽三天", "value_num": None}
    未在 entries 中出现的 field_key 保持原值。
    内部按 R1 校验 field_key、按 R5 校验 seq、按 R4 同步 value_num。
    未登记的 field_key 抛 FieldKeyNotRegisteredError。"""
```

**异常定义**：

```python
class DataStoreError(Exception): ...
class FieldKeyNotRegisteredError(DataStoreError): ...   # field_key 不在字典或已停用
class DuplicateSeqError(DataStoreError): ...           # 同一 field_key 下 seq 重复
class RecordNotFoundError(DataStoreError): ...
```

### 7.3 字段字典

```python
def list_field_definitions(self, section: str = None,
                           only_active: bool = True) -> list[FieldDefinition]
    """UI 动态渲染表单的唯一依据。返回按 (section, sort_order) 排序。"""

def get_field_definition(self, field_key: str) -> Optional[FieldDefinition]

def add_field_definition(self, field_key: str, section: str, label_cn: str,
                         label_en: str, value_type: str = "text",
                         is_multi: bool = False, unit_cn: str = "",
                         unit_en: str = "", sort_order: int = 0) -> int
    """新增字段定义，返回新 id。field_key 已存在时抛 IntegrityError。
    新增字段必须在 PR 中说明来源，禁止业务代码临时造 key。"""
```

### 7.4 病症

```python
def search_disease(self, keyword: str, limit: int = 10) -> list[DiseaseTerm]
def get_disease_by_chinese(self, chinese_name: str) -> Optional[DiseaseTerm]
def get_disease_by_english(self, english_name: str) -> Optional[DiseaseTerm]
def get_disease_by_key(self, term_key: str) -> Optional[DiseaseTerm]     # 新增，解码回填用
def list_disease_results(self, record_id: str) -> list[DiseaseResult]    # 新增
def upsert_disease_result(self, record_id: str, term_key: str,
                          result_cn: str, seq: int = 0,
                          checked_at: str = "") -> int                   # 新增，内部转 result_en
def get_all_categories(self) -> list[str]
def add_disease_term(self, term_key: str, chinese_name: str,
                     english_name: str, category: str = "general") -> int
```

### 7.5 文件处理（v1 已有，v2.0 漏抄，此处补回）

```python
def parse_document(self, file_path: str) -> str
    """解析 .txt/.docx/.pdf 提取纯文本。不支持格式抛 ValueError。"""
def save_upload_file(self, file_content: bytes, filename: str) -> str
    """保存到 data/uploads/{YYYYMMDD}/{uuid8}_{filename}，返回路径。"""
def cleanup_temp_files(self, older_than_hours: int = 24) -> int
```

### 7.6 DNA 与解码

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

### 7.7 相似度（纠错支持）

```python
def find_similar_records(self, text: str, threshold: float = 0.7,
                         limit: int = 5) -> list[tuple[ArchiveRecord, float]]
def find_similar_dna_sequences(self, dna_sequence: str, threshold: float = 0.8,
                               limit: int = 5) -> list
```

### 7.8 导出与统计

```python
def export_record_to_json(self, record_id: str) -> str
    """导出结构 = §6.3 载荷对象（含 meta/fields/diseases），返回文件路径。"""
def export_record_to_docx(self, record_id: str, template_path: str = None) -> str
    """按 §5 分组与中文标签生成 Word。"""
def backup_database(self, backup_dir: str = None) -> str
def restore_database(self, backup_path: str) -> bool
def get_statistics(self) -> dict
```

---

## 8. 从 v1 迁移

### 8.1 迁移步骤

1. `ALTER TABLE archive_records RENAME TO archive_records_v1;`（其余 3 张表同理加 `_v1` 后缀）
2. 执行 §4 DDL 建新表
3. **先灌字段字典**（§5 全部 60 条）与 236 条病症词典 —— 否则第 5 步会被 R1 拒绝
4. 身份列写入新 `archive_records`（record_id / name / gender / nation / id_number / residence_address / archive_number / create_date / source / 时间戳 / is_deleted）
5. 其余物理列按 §8.2 映射写入 `record_entries`（`is_legacy=1`）
6. `follow_up_records`（JSON 数组）→ `record_entries`，同一数组下标 + 1 作为 `seq`
7. `disease_records`（JSON 对象）→ **先写 `legacy_disease_staging`**，人工审核后再合并（见 §8.3）
8. 迁移完成后核对：
   - v1 行数 == 新表档案数
   - 每行 v1 的 23 个字段中非空的数量 == 对应 entries 行数 + 身份列非空数
   - 每条档案至少有一条 `record_entries`
9. 保留 `*_v1` 表只读一个版本，确认无误后备份并删除
10. `schema_meta` 追加一行 `v2.1`

### 8.2 字段映射（v1 23 个物理列 → 新结构）

| v1 列 | 目标 | field_key |
|---|---|---|
| 档案编号 | 身份列 | `archive_number` |
| 姓名 | 身份列 | `name` |
| 性别 | 身份列 | `gender`（男/女 → male/female） |
| 证件号码 | 身份列 | `id_number` |
| 常住地址 | 身份列 | `residence_address` |
| 建档日期 | 身份列 | `create_date` |
| 民族 | 身份列 | `nation` |
| 出生日期 | entries (§5.2) | `birth_date` |
| 户籍地址 | entries (§5.2) | `hukou_address` |
| 建档机构 | entries (§5.2) | `organization` |
| 联系电话 | entries (§5.2) | `contact_phone` |
| ABO血型 | entries (§5.2) | `abo_blood_type`（枚举规范化） |
| Rh血型 | entries (§5.2) | `rh_blood_type`（阳性/阴性 → positive/negative） |
| 父亲姓名 | entries (§5.2) | `father_name` |
| 父亲联系电话 | entries (§5.2) | `father_phone` |
| 母亲姓名 | entries (§5.2) | `mother_name` |
| 母亲联系电话 | entries (§5.2) | `mother_phone` |
| 出生孕周 | entries (§5.2) | `gestational_weeks` |
| 出生体重 | entries (§5.2) | `birth_weight` |
| 出生身长 | entries (§5.2) | `birth_length` |
| 分娩机构 | entries (§5.2) | `delivery_org` |
| Apgar_1分钟 | entries (§5.2) | `apgar_1min` |
| Apgar_5分钟 | entries (§5.2) | `apgar_5min` |

**7 个身份列 + 16 个 entries = 23** ✓ 全部有归属，无遗漏。

**v1 的 7 个病症字段**需要逐个决策，因为与框架字段语义重叠：

| v1 病症字段 | 建议处理 |
|---|---|
| 苯丙酮尿症 | → `disease_terms` 词条 `phenylketonuria`，存 `record_diseases` |
| 先天性甲状腺功能减低症 | → `disease_terms` 词条 `congenital_hypothyroidism` |
| 听力筛查 | → `disease_terms` 词条 `hearing_screening` |
| 先天异常 | → `disease_terms` 词条 `congenital_anomaly` |
| 过敏史 | ⚠️ 与 §5.4 `drug_allergy` 重叠 → 建议迁到 `record_entries.drug_allergy`，不再作病症 |
| 既往住院史 | ⚠️ 与 §5.3 `past_medical_history` 重叠 → 建议迁到 entries |
| 家族遗传病史 | ⚠️ 与 §5.3 `family_history` 重叠 → 建议迁到 entries |

后 3 条需要你拍板。**建议合并到 entries**，避免同一信息在两个地方存储、双份维护。

### 8.3 病症词典保护（防止污染）

v2.0 的迁移第 5 步"匹配不到就 `INSERT` 新词条"会让 v1 的脏写法（"苯丙酮尿症" / "苯丙酮尿症筛查" / "PKU"）全部灌进标准词典，之后搜索出现重复项、DNA 编码取英文名无从选择。

改为先落暂存表：

```sql
CREATE TABLE IF NOT EXISTS legacy_disease_staging (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_text TEXT NOT NULL,          -- v1 里的原始中文名
    record_id TEXT NOT NULL,
    result_cn TEXT DEFAULT '',
    matched_term_id INTEGER,            -- 自动匹配上的词典 id，NULL 表示没匹配上
    reviewed INTEGER DEFAULT 0,         -- 0 待审 / 1 已合并 / 2 已丢弃
    FOREIGN KEY (matched_term_id) REFERENCES disease_terms(id)
);
```

流程：迁移时先全部写入暂存表（能匹配的填 `matched_term_id`，匹配不上的留空）→ 人工过一遍（合并到标准词条 / 新建词条 / 直接丢弃）→ `reviewed=1` 的才真正写进 `record_diseases`。

---

## 9. 验收标准

| 编号 | 用例 | 期望 |
|---|---|---|
| T1 | 保存一条填了 20 个字段的档案 | `archive_records` 1 行；`record_entries` **20 行**；无 JSON 字符串残留；所有 `field_key` 都能在字典命中 |
| T2 | 同一档案存两次 | 主键不变、`updated_at` 变化、不产生重复行、已软删档案不被复活 |
| T3 | 多值字段存 3 条随访 | `seq` 为 1/2/3，按 seq 排序读出 |
| T4 | **删除第 2 条随访后再新增一条** | 不抛唯一约束错误；新行 seq=2；总数仍为 3 |
| T5 | 病症结果写入 | 只能选 `disease_terms` 内词条；词典外中文名抛错，必须先入库 |
| T6 | 生成 DNA 载荷 | payload 全为 ASCII；两次编码 byte 级一致；解码后中文 `value_cn` 与原始输入一致 |
| T7 | 列表分页 | `list_records` 返回 `(items, total)`，total 为过滤后总数 |
| T8 | 字典校验 | 写入未登记的 `field_key` 抛 `FieldKeyNotRegisteredError` |
| T9 | 外键生效 | 手动插入 `record_entries.record_id = 'NOT_EXIST'` 必须被拒绝（验证 `PRAGMA` 已开） |
| T10 | 迁移 | 迁移前后记录数一致；抽查 3 条档案，23 个 v1 字段全部落到正确位置；`legacy_disease_staging` 有数据且 `disease_terms` 未被污染 |

---

## 10. 实施顺序与分工

| 阶段 | 内容 | 负责 | 预估 |
|---|---|---|---|
| P0 | 本设计 v2.1 + `api_contract.md` v2.1 评审冻结 | 全员 | — |
| P1 | `data_store.py` v2：建表 + 字典灌入 + CRUD + `upsert_entries` | 数据库同学 | 2 天 |
| P2 | 迁移脚本 + `legacy_disease_staging` 人工审核 | 数据库同学 | 0.5 天 |
| P3 | 236 条病症词典种子文件（`term_key` + 中英文 + 分类） | 数据库同学 | 0.5 天 |
| P4 | `core/data_classifier.py`：表单/AI 结果 → `entries`（双语、枚举规范化、seq 对齐） | 数据库同学 + PM | 1 天 |
| P5 | UI 按 `field_definitions` 动态渲染分组；保存改调 `save_record` | 前端同学 | 1 天 |
| P6 | `dna_codec` 接 §6.3 载荷；解码按 §6.4 回填 | PM | 0.5 天 |
| P7 | 按 §9 跑验收 | 全员 | 半天 |

---

## 11. 待确认事项

1. **DNA 容量**：`bilingual` 载荷比 `canonical_en` 大约一倍。**这个当场能测**——拿一条真实档案两种模式各编码一次量长度即可，不必等编码器定完上限。
2. **性别/血型枚举规范值**：本稿采用 `male/female/unknown`、`A`/`B`/`AB`/`O`、`positive`/`negative`。如需对接国标编码请提出。
3. **v1 的 3 个重叠病症字段**（过敏史 / 既往住院史 / 家族遗传病史）是否合并到 entries —— 见 §8.2，建议合并。
4. **框架文档新增字段的审批方式**：所有新 `field_key` 走 `add_field_definition()`，由 PM 合并，禁止在业务代码里临时造 key。

---

## 附录 A：FTS5 全文检索（数据量超 1 万条时启用，现在不要建）

```sql
CREATE VIRTUAL TABLE record_entries_fts USING fts5(
    record_id UNINDEXED,
    field_key UNINDEXED,
    value_cn,
    tokenize = 'unicode61'
);

-- 首次填充
INSERT INTO record_entries_fts (record_id, field_key, value_cn)
SELECT record_id, field_key, value_cn FROM record_entries;

-- 同步触发器
CREATE TRIGGER record_entries_ai AFTER INSERT ON record_entries BEGIN
    INSERT INTO record_entries_fts (record_id, field_key, value_cn)
    VALUES (new.record_id, new.field_key, new.value_cn);
END;

CREATE TRIGGER record_entries_ad AFTER DELETE ON record_entries BEGIN
    DELETE FROM record_entries_fts WHERE rowid = old.id;
END;

CREATE TRIGGER record_entries_au AFTER UPDATE ON record_entries BEGIN
    UPDATE record_entries_fts SET value_cn = new.value_cn WHERE rowid = old.id;
END;

-- 查询
SELECT record_id FROM record_entries_fts WHERE record_entries_fts MATCH '咳嗽';
```

> `unicode61` 分词器对中文按字切分，效果一般。真要做中文全文检索，需用 `simple` 分词器或外部分词（如 jieba），属二期课题。
