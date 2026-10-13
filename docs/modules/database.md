# 数据库与文件处理模块开发文档

## 模块概述

| 属性 | 内容 |
|------|------|
| **模块名称** | data_store.py |
| **模块全称** | Data Storage（数据存储） |
| **负责角色** | 数据库开发（同学B） |
| **技术栈** | SQLite 3.x + python-docx + pdfplumber |
| **依赖模块** | 无（独立模块） |
| **代码位置** | `modules/data_store.py` |

---

## 1. 模块职责

| 编号 | 职责描述 | 优先级 |
|------|---------|--------|
| DS-01 | 搭建本地SQLite数据库 | P0 |
| DS-02 | 接收界面传入的图片/文档/文本，做数据预处理 | P0 |
| DS-03 | 存储原始文件、DNA编码结果、解码记录 | P0 |
| DS-04 | 对外提供读写数据库的接口 | P0 |
| DS-05 | 实现相似度检索功能（纠错用） | P1 |
| DS-06 | 实现数据备份与恢复 | P2 |

---

## 2. 数据库设计

### 2.1 数据库文件

- **路径**：`data/db/medical_archive.db`
- **类型**：SQLite 3.x
- **编码**：UTF-8

### 2.2 ER关系图

```
┌──────────────────┐       ┌──────────────────┐       ┌──────────────────┐
│  archive_records │       │  dna_sequences   │       │  decode_records  │
│------------------│       │------------------│       │------------------│
│ PK id            │       │ PK id            │       │ PK id            │
│    record_id     │───┐   │ FK record_id     │       │ FK dna_record_id │
│    name          │   │   │    dna_sequence  │◀──┐   │    decoded_text  │
│    ...           │   └──>│    cg_content    │   └──>│    confidence    │
└──────────────────┘       └──────────────────┘       └──────────────────┘
         │
         ▼
┌──────────────────┐
│  disease_terms   │
│------------------│
│ PK id            │
│    chinese_name  │
│    english_name  │
│    category      │
└──────────────────┘
```

### 2.3 表结构详细定义

#### 表1：`disease_terms` 病症词典表

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | 自增主键 |
| chinese_name | TEXT | NOT NULL | 中文病症名称 |
| english_name | TEXT | NOT NULL | 英文名称 |
| category | TEXT | DEFAULT '通用' | 分类（儿科/内科/外科/...） |

**初始数据**：236条预设词条（8大分类）

**索引**：
```sql
CREATE INDEX idx_disease_chinese ON disease_terms(chinese_name);
CREATE INDEX idx_disease_english ON disease_terms(english_name);
CREATE INDEX idx_disease_category ON disease_terms(category);
```

---

#### 表2：`archive_records` 档案记录表

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | 主键 |
| record_id | TEXT | NOT NULL UNIQUE | 业务唯一标识 |
| name | TEXT | NOT NULL | 姓名 |
| gender | TEXT | DEFAULT '' | 性别 |
| birth_date | TEXT | DEFAULT '' | 出生日期 |
| id_number | TEXT | DEFAULT '' | 证件号码 |
| hukou_address | TEXT | DEFAULT '' | 户籍地址 |
| residence_address | TEXT | DEFAULT '' | 常住地址 |
| organization | TEXT | DEFAULT '' | 建档机构 |
| create_date | TEXT | DEFAULT '' | 建档日期 |
| phone | TEXT | DEFAULT '' | 联系电话 |
| nation | TEXT | DEFAULT '' | 民族 |
| abo_blood_type | TEXT | DEFAULT '' | ABO血型 |
| rh_blood_type | TEXT | DEFAULT '' | Rh血型 |
| father_name | TEXT | DEFAULT '' | 父亲姓名 |
| father_phone | TEXT | DEFAULT '' | 父亲联系电话 |
| mother_name | TEXT | DEFAULT '' | 母亲姓名 |
| mother_phone | TEXT | DEFAULT '' | 母亲联系电话 |
| gestational_weeks | TEXT | DEFAULT '' | 出生孕周 |
| birth_weight | TEXT | DEFAULT '' | 出生体重 |
| birth_length | TEXT | DEFAULT '' | 出生身长 |
| delivery_org | TEXT | DEFAULT '' | 分娩机构 |
| apgar_1min | TEXT | DEFAULT '' | Apgar评分(1分钟) |
| apgar_5min | TEXT | DEFAULT '' | Apgar评分(5分钟) |
| follow_up_records | TEXT | DEFAULT '[]' | 随访记录(JSON数组) |
| disease_records | TEXT | DEFAULT '{}' | 病症记录(JSON对象) |
| source | TEXT | DEFAULT 'manual' | 数据来源 |
| created_at | TEXT | NOT NULL | 创建时间 |
| updated_at | TEXT | NOT NULL | 更新时间 |
| is_deleted | INTEGER | DEFAULT 0 | 软删除标记 |

**索引**：
```sql
CREATE INDEX idx_archive_record_id ON archive_records(record_id);
CREATE INDEX idx_archive_name ON archive_records(name);
CREATE INDEX idx_archive_created ON archive_records(created_at);
```

---

#### 表3：`dna_sequences` DNA序列表

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | 主键 |
| record_id | TEXT | NOT NULL | 关联档案ID |
| dna_sequence | TEXT | NOT NULL | DNA序列字符串 |
| key_hash | TEXT | NOT NULL | 密钥SHA-256哈希 |
| cg_content | REAL | DEFAULT 0 | GC含量(0-1) |
| thermal_stability | REAL | DEFAULT 0 | 热稳定性系数 |
| padded_zeros | INTEGER | DEFAULT 0 | 填充零位数 |
| sequence_length | INTEGER | DEFAULT 0 | 序列长度 |
| original_text | TEXT | DEFAULT '' | 编码前原始文本 |
| encoded_at | TEXT | NOT NULL | 编码时间 |
| is_valid | INTEGER | DEFAULT 1 | 是否有效(1=有效) |

**索引**：
```sql
CREATE INDEX idx_dna_record_id ON dna_sequences(record_id);
CREATE INDEX idx_dna_sequence ON dna_sequences(dna_sequence);
CREATE INDEX idx_dna_encoded ON dna_sequences(encoded_at);
```

---

#### 表4：`decode_records` 解码记录表

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | 主键 |
| dna_record_id | INTEGER | NOT NULL | 关联DNA序列ID |
| decoded_text | TEXT | NOT NULL | 解码后文本 |
| corrected_text | TEXT | DEFAULT '' | 纠错后文本 |
| confidence | REAL | DEFAULT 0 | 置信度(0-1) |
| error_rate | REAL | DEFAULT 0 | 错误率(0-1) |
| correction_log | TEXT | DEFAULT '{}' | 纠错日志(JSON) |
| decoded_at | TEXT | NOT NULL | 解码时间 |

**索引**：
```sql
CREATE INDEX idx_decode_dna_id ON decode_records(dna_record_id);
CREATE INDEX idx_decode_time ON decode_records(decoded_at);
```

---

## 3. 对外接口（需实现的公共方法）

> 详细签名见 `api_contract.md` 第4节，此处按功能分组。

### 3.1 数据库初始化

| 方法 | 说明 | 备注 |
|------|------|------|
| `init_database()` | 建表、建索引 | 启动时调用一次 |
| `init_disease_terms()` | 插入236条病症数据 | 返回插入数量 |
| `get_connection()` | 获取数据库连接 | 行工厂返回dict |
| `close()` | 关闭连接 | 程序退出时调用 |

### 3.2 病典查询

| 方法 | 说明 | SQL要点 |
|------|------|---------|
| `search_disease(keyword, limit)` | 中英文模糊搜索 | LIKE '%keyword%' |
| `get_disease_by_chinese(name)` | 中文名精确查找 | WHERE chinese_name = ? |
| `get_disease_by_english(name)` | 英文名精确查找 | WHERE english_name = ? |
| `get_all_categories()` | 获取所有分类 | SELECT DISTINCT category |
| `add_disease_term(cn, en, cat)` | 添加新词条 | INSERT INTO disease_terms |

### 3.3 文件解析

| 方法 | 支持格式 | 依赖库 |
|------|---------|--------|
| `parse_document(file_path)` | .txt, .docx, .pdf | python-docx, pdfplumber |
| `save_upload_file(content, filename)` | 任意二进制 | 内置os/shutil |
| `cleanup_temp_files(hours)` | - | 按修改时间过滤 |

**解析规则**：
- `.txt`：直接读取文本内容
- `.docx`：提取所有段落文本
- `.pdf`：提取所有页面文本
- 图片格式：暂不解析（预留OCR接口）

### 3.4 档案记录 CRUD

| 方法 | 说明 | SQL操作 |
|------|------|---------|
| `save_record(record)` | 新增或更新 | INSERT OR REPLACE |
| `load_record(record_id)` | 按ID加载 | SELECT * WHERE record_id = ? |
| `delete_record(record_id)` | 软删除 | UPDATE SET is_deleted = 1 |
| `list_records(offset, limit, keyword)` | 分页列表 | SELECT + LIMIT/OFFSET + LIKE |
| `update_record(record)` | 更新记录 | UPDATE SET ... WHERE id = ? |

**record_id 生成规则**：`ARCHIVE_{YYYYMMDD}_{NNN}` （如 ARCHIVE_20261013_001）

### 3.5 DNA序列操作

| 方法 | 说明 |
|------|------|
| `save_dna_sequence(dna_record)` | 保存编码结果 |
| `load_dna_sequence(record_id)` | 按档案ID加载最新序列 |
| `load_dna_by_sequence(dna_seq)` | 按DNA序列模糊查找 |
| `list_dna_sequences(offset, limit)` | 分页列出 |
| `invalidate_dna_sequence(dna_id)` | 标记无效 |

**密钥存储规范**：只存储 SHA-256 哈希，不存储明文密钥。

### 3.6 解码记录

| 方法 | 说明 |
|------|------|
| `save_decode_record(decode_record)` | 保存解码结果 |
| `list_decode_records(dna_record_id, limit)` | 列出某DNA的解码历史 |

### 3.7 相似度查询（纠错支持）

| 方法 | 说明 | 使用场景 |
|------|------|---------|
| `find_similar_records(text, threshold, limit)` | 文本相似档案比对 | 纠错时参考 |
| `find_similar_dna_sequences(dna_seq, threshold, limit)` | DNA序列相似比对 | 检测数据损坏 |

**相似度算法建议**：基于 SQLite FTS5 全文搜索 + 编辑距离计算

### 3.8 数据导出与备份

| 方法 | 说明 | 输出格式 |
|------|------|---------|
| `export_record_to_json(record_id)` | 导出为JSON | JSON文件 |
| `export_record_to_docx(record_id, template)` | 导出为DOCX | Word文档 |
| `backup_database(backup_dir)` | 备份数据库 | .db副本 |
| `restore_database(backup_path)` | 恢复数据库 | 覆盖当前db |

### 3.9 统计查询

| 方法 | 返回内容 |
|------|---------|
| `get_statistics()` | `{total_records, total_dna, total_decodes, db_size_bytes}` |

---

## 4. 数据类定义

### 4.1 DiseaseTerm

```python
@dataclass
class DiseaseTerm:
    id: int
    chinese_name: str      # 中文名称
    english_name: str      # 英文名称
    category: str          # 分类
```

### 4.2 ArchiveRecord

```python
@dataclass
class ArchiveRecord:
    id: Optional[int] = None
    record_id: str = ""

    # 物理存储（23个字段）
    archive_number: str = ""
    name: str = ""
    gender: str = ""
    birth_date: str = ""
    id_number: str = ""
    hukou_address: str = ""
    residence_address: str = ""
    organization: str = ""
    create_date: str = ""
    phone: str = ""
    nation: str = ""
    abo_blood_type: str = ""
    rh_blood_type: str = ""
    father_name: str = ""
    father_phone: str = ""
    mother_name: str = ""
    mother_phone: str = ""
    gestational_weeks: str = ""
    birth_weight: str = ""
    birth_length: str = ""
    delivery_org: str = ""
    apgar_1min: str = ""
    apgar_5min: str = ""

    # 动态存储（JSON）
    follow_up_records: str = '[]'    # JSON数组
    disease_records: str = '{}'      # JSON对象

    # 元数据
    created_at: str = ""
    updated_at: str = ""
    source: str = "manual"
```

### 4.3 DNASequenceRecord

```python
@dataclass
class DNASequenceRecord:
    id: Optional[int] = None
    record_id: str = ""
    dna_sequence: str = ""
    encryption_key: str = ""     # 哈希存储
    cg_content: float = 0.0
    thermal_stability: float = 0.0
    padded_zeros: int = 0
    sequence_length: int = 0
    original_text: str = ""
    encoded_at: str = ""
    is_valid: bool = True
```

### 4.4 DecodeRecord

```python
@dataclass
class DecodeRecord:
    id: Optional[int] = None
    dna_record_id: int = 0
    decoded_text: str = ""
    corrected_text: str = ""
    confidence: float = 0.0
    error_rate: float = 0.0
    correction_log: str = "{}"
    decoded_at: str = ""
```

---

## 5. 文件存储规范

### 5.1 目录结构

```
data/
├── db/
│   └── medical_archive.db        # SQLite数据库
├── uploads/
│   └── {YYYYMMDD}/
│       └── {uuid}_原文件名        # 上传的原始文件
├── exports/
│   ├── json/
│   │   └── {record_id}.json      # JSON导出
│   └── docx/
│       └── {record_id}.docx      # Word导出
├── backups/
│   └── medical_archive_{YYYYMMDD_HHMMSS}.db  # 数据库备份
└── logs/
    └── datastore_{YYYYMMDD}.log  # 操作日志
```

### 5.2 文件命名规则

| 类型 | 命名格式 | 示例 |
|------|---------|------|
| 上传文件 | `{uuid}_{原文件名}` | `a1b2c3d4_体检报告.pdf` |
| JSON导出 | `{record_id}.json` | `ARCHIVE_20261013_001.json` |
| DOCX导出 | `{record_id}.docx` | `ARCHIVE_20261013_001.docx` |
| 数据库备份 | `medical_archive_{时间戳}.db` | `medical_archive_20261013_143000.db` |

---

## 6. 交付物清单

### 第一阶段交付

- [ ] `DataStore` 类完整实现
- [ ] 4张表的DDL语句（含索引）
- [ ] 236条病症词典数据的初始化SQL/Python
- [ ] 文档解析功能（txt/docx/pdf）
- [ ] 档案记录CRUD完整实现
- [ ] DNA序列CRUD完整实现
- [ ] 解码记录CRUD完整实现
- [ ] 相似度查询功能
- [ ] 数据导出功能（JSON/DOCX）
- [ ] 数据库备份/恢复功能
- [ ] 单元测试 `tests/test_data_store.py`

### 测试覆盖要求

| 测试项 | 要求 |
|--------|------|
| 数据库初始化 | 建表成功、索引存在 |
| 病典查询 | 精确查找、模糊搜索、分类筛选 |
| 文档解析 | 三种格式正确提取文本 |
| 档案CRUD | 新增、查询、更新、删除、分页 |
| DNA序列 | 保存、加载、失效标记 |
| 相似度查询 | 相似/不相似场景 |
| 并发安全 | 多线程读写不冲突 |

---

## 7. 注意事项

1. **独立模块**：不依赖其他业务模块，可独立开发和测试
2. **线程安全**：SQLite连接默认线程安全，但注意事务隔离
3. **软删除**：档案记录不物理删除，仅标记 is_deleted=1
4. **密钥安全**：只存哈希，不存明文
5. **JSON字段**：follow_up_records 和 disease_records 存储为JSON字符串
6. **文件清理**：定期清理超过24小时的临时上传文件
