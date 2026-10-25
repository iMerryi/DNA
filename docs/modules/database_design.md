# 数据库与文件处理模块软件设计书

> 模块名称：data_store.py
> 版本：v1.0
> 编制日期：2026-10-25

---

## 1. 模块概述

### 1.1 模块定位

`data_store.py` 是 DNA 医疗档案系统的**数据持久层核心模块**，统一负责：

- **数据库管理**：SQLite 数据库的建表、索引、CRUD 操作、统计查询；
- **文件处理**：上传文件保存、多格式文档解析（TXT / DOCX / PDF）、临时文件清理；
- **数据交换**：档案导出（JSON / DOCX）、数据库备份与恢复；
- **辅助检索**：病症词典中英文模糊搜索、基于 fuzzywuzzy 的相似档案比对。

### 1.2 依赖环境

| 依赖 | 用途 |
|---|---|
| sqlite3 / os / json / uuid / shutil / hashlib / datetime | 标准库 |
| docx (python-docx) | DOCX 解析与导出 |
| pdfplumber | PDF 文本提取 |
| fuzzywuzzy | 文本相似度计算 |

### 1.3 存储目录结构

```
data/
├── db/
│   └── medical_archive.db     # 主数据库
├── uploads/
│   └── {YYYYMMDD}/            # 按日期分目录
│       └── {uuid8}_原文件名    # 上传文件（uuid 前缀防重名）
├── exports/
│   ├── json/                  # JSON 导出
│   └── docx/                  # DOCX 导出
├── backups/                   # 数据库备份
└── logs/                      # 日志目录
```

### 1.4 数据模型（dataclass）

| 数据类 | 对应表 | 说明 |
|---|---|---|
| `DiseaseTerm` | disease_terms | 病症词典条目 |
| `ArchiveRecord` | archive_records | 新生儿医疗档案（23 个物理字段 + 2 个 JSON 动态字段） |
| `DNASequenceRecord` | dna_sequences | DNA 编码序列及元信息 |
| `DecodeRecord` | decode_records | DNA 解码结果与纠错日志 |

---

## 2. 数据库表结构设计

数据库文件：`data/db/medical_archive.db`，共 **4 张表**，建表语句按 `database.md 2.3` 规范执行（`CREATE TABLE IF NOT EXISTS`，幂等可重复初始化）。

### 2.1 表1：disease_terms（病症词典表）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | 自增主键 |
| chinese_name | TEXT | NOT NULL | 中文病名 |
| english_name | TEXT | NOT NULL | 英文病名 |
| category | TEXT | DEFAULT '通用' | 病症分类 |

**索引**：`idx_disease_chinese(chinese_name)`、`idx_disease_english(english_name)`、`idx_disease_category(category)`

### 2.2 表2：archive_records（档案记录表）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | 自增主键 |
| record_id | TEXT | NOT NULL **UNIQUE** | 业务档案号，格式 `ARCHIVE_{YYYYMMDD}_{序号}` |
| archive_number | TEXT | DEFAULT '' | 档案编号 |
| name | TEXT | NOT NULL | 姓名 |
| gender / birth_date / id_number | TEXT | DEFAULT '' | 性别 / 出生日期 / 证件号 |
| hukou_address / residence_address | TEXT | DEFAULT '' | 户籍地址 / 居住地址 |
| organization / create_date / phone / nation | TEXT | DEFAULT '' | 机构 / 建档日期 / 电话 / 民族 |
| abo_blood_type / rh_blood_type | TEXT | DEFAULT '' | ABO 血型 / RH 血型 |
| father_name / father_phone / mother_name / mother_phone | TEXT | DEFAULT '' | 父母信息 |
| gestational_weeks / birth_weight / birth_length | TEXT | DEFAULT '' | 孕周 / 出生体重 / 出生身长 |
| delivery_org / apgar_1min / apgar_5min | TEXT | DEFAULT '' | 分娩机构 / Apgar 评分 |
| follow_up_records | TEXT | DEFAULT '[]' | 随访记录（JSON 数组，动态扩展） |
| disease_records | TEXT | DEFAULT '{}' | 病症记录（JSON 对象，动态扩展） |
| source | TEXT | DEFAULT 'manual' | 数据来源（manual / upload） |
| created_at / updated_at | TEXT | NOT NULL | 创建 / 更新时间 |
| is_deleted | INTEGER | DEFAULT 0 | **软删除标记**（0 正常 / 1 已删除） |

**索引**：`idx_archive_record_id(record_id)`、`idx_archive_name(name)`、`idx_archive_created(created_at)`

> 设计要点：随访与病症采用 **JSON 动态字段**，避免频繁改表；生理、家族等 23 个高频固定字段采用物理列，保证查询效率。

### 2.3 表3：dna_sequences（DNA 序列表）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | 自增主键 |
| record_id | TEXT | NOT NULL | 关联档案号 |
| dna_sequence | TEXT | NOT NULL | DNA 编码序列（ATCG） |
| key_hash | TEXT | NOT NULL | 编码密钥哈希 |
| cg_content | REAL | DEFAULT 0 | GC 含量 |
| thermal_stability | REAL | DEFAULT 0 | 热稳定性 |
| padded_zeros | INTEGER | DEFAULT 0 | 填充零位数 |
| sequence_length | INTEGER | DEFAULT 0 | 序列长度 |
| original_text | TEXT | DEFAULT '' | 编码前原文 |
| encoded_at | TEXT | NOT NULL | 编码时间 |
| is_valid | INTEGER | DEFAULT 1 | 序列有效性标记 |

**索引**：`idx_dna_record_id(record_id)`、`idx_dna_sequence(dna_sequence)`、`idx_dna_encoded(encoded_at)`

> 同一档案允许多条序列，读取时按 `id DESC` 取**最新有效版本**（`is_valid = 1`）。

### 2.4 表4：decode_records（解码记录表）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | 自增主键 |
| dna_record_id | INTEGER | NOT NULL | 关联 dna_sequences.id |
| decoded_text | TEXT | NOT NULL | 原始解码文本 |
| corrected_text | TEXT | DEFAULT '' | 纠错后文本 |
| confidence | REAL | DEFAULT 0 | 置信度 |
| error_rate | REAL | DEFAULT 0 | 错误率 |
| correction_log | TEXT | DEFAULT '{}' | 纠错日志（JSON） |
| decoded_at | TEXT | NOT NULL | 解码时间 |

**索引**：`idx_decode_dna_id(dna_record_id)`、`idx_decode_time(decoded_at)`

---

## 3. 核心接口列表说明

### 3.1 初始化与连接

| 接口 | 签名 | 说明 |
|---|---|---|
| 构造 | `__init__(db_path, data_dir)` | 创建目录结构，惰性建连 |
| 连接 | `get_connection()` | 单例连接；`row_factory=Row` 使查询返回字典；开启外键约束 |
| 建库 | `init_database()` | 建 4 张表及全部索引，幂等 |
| 词典预置 | `init_disease_terms()` | 空表时插入预置词条（目标 236 条，当前内置 3 条测试数据） |

### 3.2 档案记录 CRUD

| 接口 | 签名 | 说明 |
|---|---|---|
| 增/改 | `save_record(record) -> record_id` | record_id 为空时自动生成 `ARCHIVE_{日期}_{时间戳尾3位}`；`INSERT OR REPLACE` 全字段写入 |
| 查 | `load_record(record_id) -> Optional[ArchiveRecord]` | 按 record_id 查单条，自动过滤已删除 |
| 删 | `delete_record(record_id) -> bool` | **软删除**：仅置 `is_deleted=1` 并刷新 updated_at |
| 列表 | `list_records(offset, limit, keyword)` | 分页 + 姓名模糊搜索，按创建时间倒序 |

### 3.3 文件处理

| 接口 | 签名 | 说明 |
|---|---|---|
| 保存上传 | `save_upload_file(content, filename) -> path` | 按日期分目录，uuid 前 8 位防重名 |
| 文档解析 | `parse_document(file_path) -> str` | 支持 .txt（UTF-8）、.docx（python-docx）、.pdf（pdfplumber 逐页提取）；失败返回空串 |
| 临时清理 | `cleanup_temp_files(hours=24) -> int` | 遍历 uploads 目录，删除 mtime 超过 24 小时的文件，返回删除数 |

### 3.4 病症词典

| 接口 | 签名 | 说明 |
|---|---|---|
| 模糊搜索 | `search_disease(keyword, limit=10)` | 中英文名 LIKE 双向匹配 |
| 精确查询 | `get_disease_by_chinese / get_disease_by_english` | 按中/英文名精确匹配 |
| 分类列表 | `get_all_categories()` | DISTINCT 查询所有分类 |
| 新增词条 | `add_disease_term(...) -> int` | 插入并返回自增 ID |

### 3.5 DNA 存储与解码记录

| 接口 | 签名 | 说明 |
|---|---|---|
| 存序列 | `save_dna_sequence(dna_record) -> int` | 自动补 encoded_at 时间戳，返回自增 ID |
| 取最新序列 | `load_dna_sequence(record_id) -> Optional[DNASequenceRecord]` | 按 id 倒序取最新有效（is_valid=1）序列 |
| 存解码 | `save_decode_record(decode_record) -> int` | 自动补 decoded_at，含置信度与纠错日志 |

### 3.6 相似度检索与纠错辅助

| 接口 | 签名 | 说明 |
|---|---|---|
| 相似比对 | `find_similar_records(text, threshold=0.7, limit=5)` | 全量加载未删除档案，`fuzz.ratio` 与姓名比对，降序取 Top-N，返回 `(record, score)` 元组列表 |

### 3.7 导出、备份与统计

| 接口 | 签名 | 说明 |
|---|---|---|
| JSON 导出 | `export_record_to_json(record_id) -> path` | dataclass → dict → JSON（ensure_ascii=False，缩进 4） |
| DOCX 导出 | `export_record_to_docx(record_id, template_path=None) -> path` | 生成含标题与关键字段的 Word 文档 |
| 备份 | `backup_database(backup_dir=None) -> path` | commit 后 `shutil.copy2` 复制为 `medical_archive_{时间戳}.db` |
| 恢复 | `restore_database(backup_path) -> bool` | 先关闭现有连接再覆盖主库文件 |
| 统计 | `get_statistics() -> dict` | 返回档案数、DNA 数、解码数、库文件字节数 |

---

## 4. 安全机制

### 4.1 数据安全

- **软删除**：档案删除仅置 `is_deleted=1`，物理数据保留，可恢复、可审计；所有查询接口默认过滤已删除记录。
- **备份恢复**：`backup_database()` 提供基于文件复制的全量备份（时间戳命名不覆盖历史备份）；`restore_database()` 恢复前主动关闭连接，避免文件占用与数据不一致。
- **幂等建库**：`init_database()` 全部使用 `IF NOT EXISTS`，重复初始化不会破坏已有数据。

### 4.2 完整性与约束

- **主键/唯一约束**：archive_records.record_id 设置 UNIQUE，防止档案号重复。
- **外键约束**：连接后执行 `PRAGMA foreign_keys = ON`，启用 SQLite 外键检查。
- **NOT NULL 保护**：核心业务字段（姓名、序列、时间戳）均有 NOT NULL 约束。

### 4.3 查询安全

- **参数化查询**：全部 SQL 使用 `?` 占位符传参，杜绝 SQL 注入；模糊搜索的关键词在 Python 侧拼装 `%...%` 后作为参数传入。

### 4.4 文件安全

- **上传防冲突**：uuid 前 8 位前缀 + 日期目录，避免文件覆盖与目录爆炸。
- **临时文件生命周期**：`cleanup_temp_files()` 定期清理 24 小时以上过期上传文件。
- **备份原子性**：使用 `shutil.copy2`（保留元数据），备份前先 commit 确保落盘数据一致。

### 4.5 并发与健壮性

- **线程容错**：`check_same_thread=False` 允许多线程共享连接（配合上层加锁使用）。
- **解析容错**：`parse_document` 全程 try/except，解析失败返回空串而非抛出异常，保证上层流程不中断。
- **时间戳自动补全**：save_dna_sequence / save_decode_record 在未提供时间时自动补齐，防止空值入库。

---

## 5. 已知限制与后续优化建议

1. **record_id 生成**：当前取时间戳尾 3 位作序号，并发下有撞号风险，建议改为查库计数或 UUID。
2. **相似度检索性能**：`find_similar_records` 为全表内存比对，数据量大时需引入分块或倒排索引。
3. **词典数据**：236 条预置词条尚未内置，需从外部数据文件导入。
4. **连接管理**：单连接未加锁，restore 后旧游标引用需注意；建议引入连接池或线程锁。
