# 接口契约 (API Contract)

## DNA医疗档案系统 - 模块对外公开接口定义

---

| 文档信息 | 内容 |
|---------|------|
| **项目名称** | DNA医疗档案系统 |
| **文档版本** | v1.0 |
| **基于SDD** | SDD.md v1.0 |
| **编写日期** | 2026-10-13 |
| **文档状态** | 初稿（待评审） |

---

## 目录

1. [模块依赖关系](#1-模块依赖关系)
2. [接口稳定性规则](#2-接口稳定性规则)
3. [模块1：前端界面 `ui_interface.py`](#3-模块1前端界面-ui_interfacepy)
4. [模块2：数据存储 `data_store.py`](#4-模块2数据存储-data_storepy)
5. [模块3：AI交互 `ollama_api.py`](#5-模块3ai交互-ollama_apipy)
6. [模块4：DNA编解码 `dna_codec.py`](#6-模块4dna编解码-dna_codecpy)
7. [模块5：核心逻辑 `core/`](#7-模块5核心逻辑-core)

---

## 1. 模块依赖关系

```
                    ┌─────────────────┐
                    │   main.py       │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  ui_interface.py │ ◄── 用户直接交互
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┬──────────────┐
              │              │              │              │
     ┌────────▼────────┐    │     ┌────────▼────────┐    │
     │  data_store.py  │    │     │  ollama_api.py  │    │
     └────────┬────────┘    │     └────────┬────────┘    │
              │              │              │              │
     ┌────────▼────────┐    │              │     ┌────────▼────────┐
     │  SQLite / 文件   │    │              │     │  Ollama 服务    │
     └─────────────────┘    │              │     └─────────────────┘
                            │              │
                   ┌────────▼────────┐    │
                   │  dna_codec.py   │    │
                   └────────┬────────┘    │
                            │              │
                   ┌────────▼────────┐    │
                   │  C++ .exe       │    │
                   └─────────────────┘    │
                                          │
                            ┌─────────────▼──────────┐
                            │      core/ (纯逻辑)     │
                            └────────────────────────┘
```

**调用方向**：`ui_interface` → 调用 → `data_store` / `ollama_api` / `dna_codec` / `core/*`

**独立模块（不依赖其他业务模块）**：`data_store`、`ollama_api`、`dna_codec`、`core/*`

---

## 2. 接口稳定性规则

| 规则编号 | 规则描述 |
|---------|---------|
| IF-01 | 公共方法签名不可随意改动，修改需全体确认 |
| IF-02 | 新增方法可以随时添加，不影响已有调用方 |
| IF-03 | 返回值类型必须严格符合约定 |
| IF-04 | 异常类型必须显式声明在 docstring 中 |
| IF-05 | 所有涉及IO操作的方法必须有超时机制 |

---

## 3. 模块1：前端界面 `ui_interface.py`

### 3.1 类：`HealthArchiveApp`

**文件路径**：`modules/ui_interface.py`

**构造函数**

```python
def __init__(
    self,
    data_store: 'DataStore',
    ai_client: 'OllamaClient',
    dna_codec: 'DNACodec',
    error_corrector: 'ErrorCorrector' = None
) -> None
```

**参数说明**：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| data_store | DataStore | 是 | 数据存储模块实例 |
| ai_client | OllamaClient | 是 | AI交互模块实例 |
| dna_codec | DNACodec | 是 | DNA编解码模块实例 |
| error_corrector | ErrorCorrector | 否 | 智能纠错模块实例 |

---

### 3.2 公共方法列表

#### 应用生命周期

| 方法签名 | 返回值 | 说明 |
|---------|--------|------|
| `start() -> None` | None | 启动Flet应用（入口方法） |

#### 视图导航

| 方法签名 | 返回值 | 说明 |
|---------|--------|------|
| `navigate_to(view_type: ViewType, **kwargs) -> None` | None | 导航到指定视图 |

**ViewType 枚举值**：
- `ViewType.SPLASH` - 开场动画页
- `ViewType.LOGIN` - 登录页
- `ViewType.MAIN` - 主界面（加密/解密选择）
- `ViewType.ENCRYPT` - 加密操作页
- `ViewType.DECRYPT` - 解密操作页
- `ViewType.PROFILE` - 个人中心页

#### 加密流程回调

| 方法签名 | 返回值 | 说明 |
|---------|--------|------|
| `on_file_uploaded(file_path: str) -> None` | None | 文件上传完成回调 |
| `on_text_input(text: str) -> None` | None | 文本输入回调 |
| `on_image_uploaded(image_path: str) -> None` | None | 图片上传完成回调（预留OCR） |
| `on_trigger_ai_extract(raw_text: str) -> None` | None | 触发AI字段提取（异步） |
| `on_save_record(record: dict) -> str` | str | 保存档案记录，返回record_id |
| `on_encode_dna(record: dict, encryption_key: str) -> None` | None | 执行DNA编码（异步任务） |
| `on_encode_complete(task_id: str, result: dict) -> None` | None | DNA编码完成回调 |

#### 解密流程回调

| 方法签名 | 返回值 | 说明 |
|---------|--------|------|
| `on_decode_dna(dna_sequence: str, decryption_key: str) -> None` | None | 执行DNA解码（异步任务） |
| `on_decode_complete(task_id: str, result: dict) -> None` | None | DNA解码完成回调 |
| `on_export_result(result_data: dict, format: str) -> str` | str | 导出解密结果，返回文件路径 |

#### 任务管理

| 方法签名 | 返回值 | 说明 |
|---------|--------|------|
| `create_task(task_type: str, source_file: str = None) -> str` | str | 创建新任务，返回任务ID |
| `update_task_progress(task_id: str, progress: float, message: str, status: TaskStatus = None) -> None` | None | 更新任务进度 |
| `cancel_task(task_id: str) -> bool` | bool | 取消任务，返回是否成功 |
| `get_task_list() -> list[TaskInfo]` | list[TaskInfo] | 获取所有任务列表 |

**TaskStatus 枚举值**：`PENDING` / `RUNNING` / `COMPLETED` / `FAILED` / `CANCELLED`

**TaskInfo 数据类**：

| 字段 | 类型 | 说明 |
|------|------|------|
| task_id | str | 任务唯一ID |
| task_type | str | 任务类型: "encrypt" / "decrypt" |
| status | TaskStatus | 当前状态 |
| progress | float | 进度百分比 (0.0-100.0) |
| message | str | 状态描述文字 |
| created_at | str | 创建时间 |
| source_file | Optional[str] | 源文件路径 |
| result | Optional[Any] | 任务结果（完成后） |

#### UI更新方法（被其他模块/线程调用）

| 方法签名 | 返回值 | 说明 |
|---------|--------|------|
| `show_progress(percent: int, message: str) -> None` | None | 更新进度条（线程安全） |
| `show_result(result_data: dict) -> None` | None | 显示结果 |
| `show_error(error_msg: str) -> None` | None | 显示错误提示 |
| `show_success(success_msg: str) -> None` | None | 显示成功提示 |
| `show_confirmation(title: str, content: str, on_confirm: Callable = None, on_cancel: Callable = None) -> None` | None | 显示确认对话框 |

---

## 4. 模块2：数据存储 `data_store.py`

### 4.1 类：`DataStore`

**文件路径**：`modules/data_store.py`

**构造函数**

```python
def __init__(self, db_path: str = None, data_dir: str = None) -> None
```

**参数说明**：
| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| db_path | str | config中DB_PATH | SQLite数据库路径 |
| data_dir | str | config中DATA_DIR | 数据根目录 |

---

### 4.2 公共方法列表

#### 数据库初始化

| 方法签名 | 返回值 | 说明 |
|---------|--------|------|
| `init_database() -> None` | None | 初始化数据库（建表、建索引） |
| `init_disease_terms() -> int` | int | 初始化病症词典（236条），返回插入数量 |
| `get_connection() -> sqlite3.Connection` | Connection | 获取数据库连接（行工厂返回dict） |
| `close() -> None` | None | 关闭数据库连接 |

#### 病典查询操作

| 方法签名 | 返回值 | 说明 |
|---------|--------|------|
| `search_disease(keyword: str, limit: int = 10) -> list[DiseaseTerm]` | list[DiseaseTerm] | 搜索病症词条（中英文模糊搜索） |
| `get_disease_by_chinese(chinese_name: str) -> Optional[DiseaseTerm]` | Optional[DiseaseTerm] | 根据中文名称获取病症 |
| `get_disease_by_english(english_name: str) -> Optional[DiseaseTerm]` | Optional[DiseaseTerm] | 根据英文名称获取病症 |
| `get_all_categories() -> list[str]` | list[str] | 获取所有病症分类 |
| `add_disease_term(chinese_name: str, english_name: str, category: str) -> int` | int | 添加新病症词条，返回新ID |

**DiseaseTerm 数据类**：

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 主键 |
| chinese_name | str | 中文名称 |
| english_name | str | 英文名称 |
| category | str | 分类 |

#### 文件解析操作

| 方法签名 | 返回值 | 说明 | 异常 |
|---------|--------|------|------|
| `parse_document(file_path: str) -> str` | str | 解析文档提取纯文本 | ValueError(不支持格式) |
| `save_upload_file(file_content: bytes, filename: str) -> str` | str | 保存上传文件，返回路径 | IOError |
| `cleanup_temp_files(older_than_hours: int = 24) -> int` | int | 清理过期临时文件，返回清理数量 | - |

**支持的文档格式**：`.txt` / `.docx` / `.pdf` / `.jpg` / `.jpeg` / `.png`

#### 档案记录 CRUD

| 方法签名 | 返回值 | 说明 |
|---------|--------|------|
| `save_record(record: ArchiveRecord) -> str` | str | 保存/更新档案，返回record_id |
| `load_record(record_id: str) -> Optional[ArchiveRecord]` | Optional[ArchiveRecord] | 加载档案记录 |
| `delete_record(record_id: str) -> bool` | bool | 删除档案记录（软删除） |
| `list_records(offset: int = 0, limit: int = 20, keyword: str = None) -> tuple[list[ArchiveRecord], int]` | tuple | 列出档案（分页），返回(列表, 总数) |
| `update_record(record: ArchiveRecord) -> bool` | bool | 更新档案记录 |

**ArchiveRecord 数据类关键字段**：

| 分类 | 字段示例 |
|------|---------|
| 物理存储（23个） | archive_number, name, gender, birth_date, id_number, phone, nation, blood_type... |
| 反复存储（JSON） | follow_up_records: `[{"随访日期": "", "当前体重": "", "体温": ""}]` |
| 病症记录（JSON） | disease_records: `{"苯丙酮尿症": "阴性", ...}` |
| 元数据 | created_at, updated_at, source, is_deleted |

#### DNA序列存储

| 方法签名 | 返回值 | 说明 |
|---------|--------|------|
| `save_dna_sequence(dna_record: DNASequenceRecord) -> int` | int | 保存DNA编码结果，返回新记录ID |
| `load_dna_sequence(record_id: str) -> Optional[DNASequenceRecord]` | Optional[DNASequenceRecord] | 加载DNA序列记录 |
| `load_dna_by_sequence(dna_sequence: str) -> Optional[DNASequenceRecord]` | Optional[DNASequenceRecord] | 根据DNA序列查找（模糊匹配） |
| `list_dna_sequences(offset: int = 0, limit: int = 20) -> list[DNASequenceRecord]` | list[DNASequenceRecord] | 列出DNA序列记录 |
| `invalidate_dna_sequence(dna_id: int) -> bool` | bool | 标记DNA序列为无效 |

**DNASequenceRecord 数据类**：

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Optional[int] | 主键 |
| record_id | str | 关联的档案记录ID |
| dna_sequence | str | DNA序列 |
| encryption_key | str | 加密密钥（哈希存储） |
| cg_content | float | GC含量 |
| thermal_stability | float | 热稳定性系数 |
| original_text | str | 编码前原始文本 |
| encoded_at | str | 编码时间 |
| is_valid | bool | 序列是否有效 |

#### 解码记录

| 方法签名 | 返回值 | 说明 |
|---------|--------|------|
| `save_decode_record(decode_record: DecodeRecord) -> int` | int | 保存解码记录，返回新ID |
| `list_decode_records(dna_record_id: int = None, limit: int = 20) -> list[DecodeRecord]` | list[DecodeRecord] | 列出解码记录 |

**DecodeRecord 数据类**：

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Optional[int] | 主键 |
| dna_record_id | int | 关联的DNA序列记录ID |
| decoded_text | str | 解码后的文本 |
| corrected_text | str | 纠错后的文本 |
| confidence | float | 置信度 (0.0-1.0) |
| error_rate | float | 错误率 (0.0-1.0) |
| correction_log | str | 纠错日志（JSON格式） |
| decoded_at | str | 解码时间 |

#### 相似度查询（纠错支持）

| 方法签名 | 返回值 | 说明 |
|---------|--------|------|
| `find_similar_records(text: str, threshold: float = 0.7, limit: int = 5) -> list[tuple[ArchiveRecord, float]]` | list[tuple] | 查找相似档案记录（用于纠错比对） |
| `find_similar_dna_sequences(dna_sequence: str, threshold: float = 0.8, limit: int = 5) -> list` | list | 查找相似DNA序列（检测数据损坏） |

#### 数据导出与备份

| 方法签名 | 返回值 | 说明 |
|---------|--------|------|
| `export_record_to_json(record_id: str) -> str` | str | 导出为JSON，返回文件路径 |
| `export_record_to_docx(record_id: str, template_path: str = None) -> str` | str | 导出为DOCX，返回文件路径 |
| `backup_database(backup_dir: str = None) -> str` | str | 备份数据库，返回备份路径 |
| `restore_database(backup_path: str) -> bool` | bool | 从备份恢复数据库 |

#### 统计查询

| 方法签名 | 返回值 | 说明 |
|---------|--------|------|
| `get_statistics() -> dict` | dict | 获取数据库统计信息 |

---

## 5. 模块3：AI交互 `ollama_api.py`

### 5.1 类：`OllamaClient`

**文件路径**：`modules/ollama_api.py`

**构造函数**

```python
def __init__(
    self,
    model_name: str = None,
    base_url: str = None,
    timeout: int = 300,
    max_retries: int = 2
) -> None
```

**参数说明**：
| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| model_name | str | config中OLLAMA_MODEL | 模型名称 |
| base_url | str | config中OLLAMA_BASE_URL | Ollama服务地址 |
| timeout | int | 300 | 请求超时秒数 |
| max_retries | int | 2 | 最大重试次数 |

---

### 5.2 公共方法列表

| 方法签名 | 返回值 | 说明 | 异常 |
|---------|--------|------|------|
| `test_connection() -> tuple[bool, str]` | tuple[bool, str] | 测试Ollama服务可用性，返回(是否成功, 消息) | ConnectionError |
| `extract_fields(document_text: str, on_progress: Callable = None, fields_hint: list = None) -> AIResponse` | AIResponse | 从文档提取结构化字段（流式调用） | ConnectionError, TimeoutError |
| `correct_errors(corrupted_text: str, reference_texts: list, on_progress: Callable = None) -> AIResponse` | AIResponse | AI辅助纠错（解码后使用） | ConnectionError, TimeoutError |
| `chat(prompt: str, system_prompt: str = None, temperature: float = 0.7) -> AIResponse` | AIResponse | 通用对话接口（预留扩展） | ConnectionError |

**AIResponse 数据类**：

| 字段 | 类型 | 说明 |
|------|------|------|
| success | bool | 是否成功 |
| data | Optional[Any] | 响应数据（具体结构视方法而异） |
| error_message | str | 错误信息 |
| tokens_used | int | 消耗token数 |
| duration_seconds | float | 耗时（秒） |

**extract_fields 返回的 data 结构**：
```python
{
    "物理存储": {"姓名": "张三", "性别": "男", ...},
    "反复存储": [{"随访日期": "2026-10-01", ...}, ...],
    "病症记录": {"苯丙酮尿症": "阴性", ...}
}
```

**correct_errors 返回的 data 结构**：
```python
{
    "corrected_text": "纠错后文本",
    "corrections": [{"position": 10, "original": "A", "corrected": "T"}],
    "confidence": 0.95
}
```

**ModelType 枚举值**：
- `FIELD_EXTRACTOR` = "qwen2.5:7b-instruct"
- `ERROR_CORRECTOR` = "qwen2.5:14b-instruct"
- `GENERAL_CHAT` = "qwen2.5:7b-chat"
- `CUSTOM` = "custom"

**on_progress 回调签名**：`Callable[[int, str], None]` → `(percent: int, message: str) -> None`

---

## 6. 模块4：DNA编解码 `dna_codec.py`

### 6.1 类：`DNACodec`

**文件路径**：`modules/dna_codec.py`

**构造函数**

```python
def __init__(
    self,
    encoder_path: str = None,
    decoder_path: str = None,
    timeout: int = 60
) -> None
```

**参数说明**：
| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| encoder_path | str | config中ENCODER_PATH | DNA_encoder.exe路径 |
| decoder_path | str | config中DECODER_PATH | DNA_decoder.exe路径 |
| timeout | int | 60 | 子进程超时秒数 |

---

### 6.2 公共方法列表

| 方法签名 | 返回值 | 说明 | 异常 |
|---------|--------|------|------|
| `generate_key(identity_info: dict) -> str` | str (静态方法) | 基于身份信息生成16字符密钥 | ValueError |
| `encode(plaintext: str, key: str) -> EncodeResult` | EncodeResult | 执行DNA编码 | RuntimeError, TimeoutError |
| `decode(dna_sequence: str, key: str) -> DecodeResult` | DecodeResult | 执行DNA解码 | RuntimeError, TimeoutError |
| `validate_dna_sequence(sequence: str) -> tuple[bool, str]` | tuple[bool, str] (静态方法) | 验证DNA序列合法性 | - |

**identity_info 参数要求**（generate_key）：
```python
{
    "name": str,        # 姓名（必填）
    "birth_date": str   # 出生日期（必填）
}
```

**EncodeResult 数据类**：

| 字段 | 类型 | 说明 |
|------|------|------|
| status | CodecStatus | 编码状态 |
| dna_sequence | str | 编码后的DNA序列 |
| cg_content | float | GC含量 (0.0-1.0) |
| thermal_stability | float | 热稳定性系数 |
| padded_zeros | int | 填充零位数 |
| sequence_length | int | 序列长度 |
| ciphertext | str | XOR加密后的中间结果 |
| error_message | str | 错误信息（失败时） |

**DecodeResult 数据类**：

| 字段 | 类型 | 说明 |
|------|------|------|
| status | CodecStatus | 解码状态 |
| original_text | str | 解码后的原始文本 |
| error_message | str | 错误信息（失败时） |

**CodecStatus 枚举值**：
- `SUCCESS` - 成功
- `ENCODER_ERROR` - 编码器错误
- `DECODER_ERROR` - 解码器错误
- `TIMEOUT` - 超时
- `INVALID_INPUT` - 输入无效

---

## 7. 模块5：核心逻辑 `core/`

### 7.1 字段常量 (`field_extractor.py`)

**文件路径**：`core/field_extractor.py`

**公开常量**：

| 常量名 | 类型 | 值 | 说明 |
|--------|------|-----|------|
| `PHYSICAL_FIELDS` | list[str] | 23个元素 | 物理存储字段名列表 |
| `DISEASE_FIELDS` | list[str] | 7个元素 | 病症记录字段名列表 |
| `REPEATED_FIELDS` | list[str] | 3个元素 | 反复存储字段名列表 |
| `ALL_FIELDS` | list[str] | 33个元素 | 所有字段名列表 |

**PHYSICAL_FIELDS 完整列表**：
```
档案编号, 姓名, 性别, 出生日期, 证件号码,
户籍地址, 常住地址, 建档机构, 建档日期, 联系电话,
民族, ABO血型, Rh血型,
父亲姓名, 父亲联系电话, 母亲姓名, 母亲联系电话,
出生孕周, 出生体重, 出生身长, 分娩机构,
Apgar_1分钟, Apgar_5分钟
```

**DISEASE_FIELDS 完整列表**：
```
苯丙酮尿症, 先天性甲状腺功能减低症, 听力筛查,
过敏史, 先天异常, 既往住院史, 家族遗传病史
```

**REPEATED_FIELDS 完整列表**：
```
随访日期, 当前体重, 体温
```

---

### 7.2 数据分类器 (`data_classifier.py`)

**文件路径**：`core/data_classifier.py`

**公共方法**（待实现类 `DataClassifier`）：

| 方法签名 | 返回值 | 说明 |
|---------|--------|------|
| `classify_fields(raw_data: dict) -> dict` | dict | 将原始数据分类为物理存储/反复存储/病症记录三类 |
| `get_physical_fields(data: dict) -> dict` | dict | 提取物理存储部分 |
| `get_repeated_fields(data: dict) -> list[dict]` | list[dict] | 提取反复存储部分 |
| `get_disease_fields(data: dict) -> dict` | dict | 提取病症记录部分 |

**classify_fields 返回结构**：
```python
{
    "physical": { "姓名": "张三", "性别": "男", ... },
    "repeated": [{"随访日期": "...", ...}],
    "diseases": {"苯丙酮尿症": "阴性", ...}
}
```

---

### 7.3 拼音转换工具 (`pinyin_utils.py`)

**文件路径**：`core/pinyin_utils.py`

**公共方法**（待实现类 `PinyinUtils` 或函数）：

| 方法签名 | 返回值 | 说明 |
|---------|--------|------|
| `chinese_to_pinyin(chinese_str: str) -> str` | str | 中文转拼音（无空格） |
| `chinese_to_pinyin_with_space(chinese_str: str) -> str` | str | 中文转拼音（带空格分隔） |

---

### 7.4 相似度计算 (`similarity.py`)

**文件路径**：`core/similarity.py`

**公共方法**（待实现类 `SimilarityCalculator`）：

| 方法签名 | 返回值 | 说明 |
|---------|--------|------|
| `text_similarity(text1: str, text2: str) -> float` | float | 计算文本相似度 (0.0-1.0) |
| `dna_similarity(seq1: str, seq2: str) -> float` | float | 计算DNA序列相似度 (0.0-1.0) |
| `find_best_match(target: str, candidates: list[str], threshold: float = 0.7) -> tuple[int, float]` | tuple | 找最佳匹配，返回(索引, 相似度) |

---

## 附录：跨模块调用汇总表

| 调用方 | 被调用方 | 方法 | 用途 |
|-------|---------|------|------|
| ui_interface | data_store | `save_record(record)` | 保存档案 |
| ui_interface | data_store | `parse_document(file_path)` | 解析文档 |
| ui_interface | data_store | `search_disease(keyword)` | 搜索病症 |
| ui_interface | ollama_api | `extract_fields(text, on_progress)` | AI字段提取 |
| ui_interface | ollama_api | `correct_errors(corrupted, references)` | AI纠错 |
| ui_interface | dna_codec | `encode(plaintext, key)` | DNA编码 |
| ui_interface | dna_codec | `decode(dna_sequence, key)` | DNA解码 |
| ui_interface | dna_codec | `generate_key(identity_info)` | 生成密钥 |
| error_corrector | data_store | `find_similar_records(text)` | 相似档案比对 |
| error_corrector | ollama_api | `correct_errors(...)` | AI纠错推断 |

---

*本文档从 SDD.md v1.0 提取，是模块对接的唯一依据。*
