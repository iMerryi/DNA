# 接口契约 (API Contract)

## DNA医疗档案系统 - 模块对外公开接口定义

---

| 文档信息 | 内容 |
|---------|------|
| **项目名称** | DNA医疗档案系统 |
| **文档版本** | **v2.1** |
| **基于SDD** | SDD.md v1.0 |
| **配套设计** | `docs/modules/database_v2_design.md` v2.1 |
| **编写日期** | 2026-10-13（v1.0） / 2026-11-02（v2.1） |
| **文档状态** | **已冻结，可作为开发依据** |

### v2.1 变更说明

**本次只改了 3 个地方，5 个数据库 CRUD 方法签名一个字都没动。**

| # | 位置 | 变更 | 影响 |
|---|------|------|------|
| 1 | §4.2 `ArchiveRecord` | 23 个扁平字段 + 2 个 JSON 字符串 → 身份字段属性 + `entries` 键值 + `diseases` 列表 | 前端构造档案的方式变，但 `record.name` 等身份字段访问不变 |
| 2 | §4.2 | 新增字段字典接口、`update_meta()`、`upsert_entries()`、病症结果接口 | 纯新增，不影响已有调用 |
| 3 | §7.1 / §7.2 | `PHYSICAL_FIELDS`/`DISEASE_FIELDS`/`REPEATED_FIELDS` 三个硬编码常量废弃，改为从 `field_definitions` 动态读取；`classify_fields()` 返回三分 → 两分 | 核心逻辑模块需要改造 |

**为什么改**：v1 的 33 个字段（23 物理 + 7 病症 + 3 随访）全部是新生儿出生信息，而框架文档要求的 33 个字段（既往史/过敏/生活史/婚育/主诉/体征）一个都装不下。产品实际需要约 60 个字段。这个缺口与键值化无关，是需求本身没落地 —— 固定列方案要加 29 列，且每加字段都要改表、改 dataclass、改前端、改 AI prompt。键值化只是把"必须补的字段"补一次到位。

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
    error_corrector: 'ErrorCorrector' = None,
    classifier: 'DataClassifier' = None
) -> None
```

**参数说明**：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| data_store | DataStore | 是 | 数据存储模块实例 |
| ai_client | OllamaClient | 是 | AI交互模块实例 |
| dna_codec | DNACodec | 是 | DNA编解码模块实例 |
| error_corrector | ErrorCorrector | 否 | 智能纠错模块实例 |
| classifier | DataClassifier | 否 | **v2.1 新增（可选）**：表单数据转换器。不传时内部自建 `DataClassifier(data_store)`，**不影响已有调用方** |

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

#### ⚠️ v2.1 给前端同学的第 1 条要求：表单必须动态渲染

v1 的 `frontend.md` 里列了 33 个写死字段，v2.1 废弃这个做法。原因：字段从 33 个变成 60 个，而且以后还会加。

**正确做法**：

```python
# 1. 启动时拉字段定义，按 section 分组
defs = self.data_store.list_field_definitions()
groups = group_by(defs, key=lambda d: d.section)

# 2. 每个分组渲染成一个折叠面板，内部按 sort_order 循环生成控件
for section, fields in groups.items():
    with ft.ExpansionTile(title=SECTION_TITLES[section]):
        for f in fields:
            if f.field_key in IDENTITY_KEYS:      # 身份字段走固定布局
                continue
            if f.is_multi:
                render_multi_input(f)             # 多值：可增删行
            elif f.value_type == "enum":
                render_dropdown(f)                # 枚举：下拉，选项来自枚举映射
            elif f.value_type == "number":
                render_number_field(f, suffix=f.unit_cn)
            elif f.value_type == "date":
                render_date_picker(f)
            else:
                render_text_field(f)
```

**关键约束**：

1. 表单收集出来的 `form_data` 直接是 `{field_key: value_or_list}`，**不要再用中文 key**；
2. 保存时调用 `classifier.build_record(form_data)` 得到 `ArchiveRecord`，再 `data_store.save_record(record)`；
3. 随访那 4 个多值字段要**按次对齐**：界面上是一个"随访记录"表格，每行对应一个 `seq`；
4. **不要再调用 `to_pinyin()`**，也不要再把数据 `json.dumps` 存文件。

#### ⚠️ v2.1 给 AI 同学的第 1 条要求：字段清单通过参数传入

```python
# ❌ 错误：AI 模块 import data_store 自己查字典 —— 会破坏分层
# from data_store import DataStore

# ✅ 正确：调用方把字段清单作为 fields_hint 传进来
fields_hint = [
    {"field_key": f.field_key, "label_cn": f.label_cn,
     "type": f.value_type, "multi": f.is_multi}
    for f in self.data_store.list_field_definitions(only_active=True)
]
resp = self.ai_client.extract_fields(raw_text, on_progress, fields_hint=fields_hint)
```

AI 返回的 key 必须是 `field_key`（英文），中文名交给前端渲染时映射。
`ollama_api.py` **只依赖 ollama HTTP 服务**，不依赖 `data_store`、不依赖 `core`。

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
| `init_database() -> None` | None | 初始化数据库（建表、建索引、写 `schema_meta` 版本） |
| `init_field_definitions() -> int` | int | 灌入字段字典（v2.1 共 60 条），返回新增数量 |
| `init_disease_terms() -> int` | int | 初始化病症词典（236条），返回插入数量 |
| `get_connection() -> sqlite3.Connection` | Connection | 获取连接（行工厂返回 dict，**内部已执行 `PRAGMA foreign_keys = ON`**） |
| `close() -> None` | None | 关闭数据库连接 |

#### 字段字典操作（v2.1 新增）

| 方法签名 | 返回值 | 说明 |
|---------|--------|------|
| `list_field_definitions(section: str = None, only_active: bool = True) -> list[FieldDefinition]` | list[FieldDefinition] | **UI 动态渲染表单的唯一依据**，按 `(section, sort_order)` 排序 |
| `get_field_definition(field_key: str) -> Optional[FieldDefinition]` | Optional[FieldDefinition] | 按 key 取单个字段定义 |
| `add_field_definition(field_key: str, section: str, label_cn: str, label_en: str, value_type: str = "text", is_multi: bool = False, unit_cn: str = "", unit_en: str = "", sort_order: int = 0) -> int` | int | 新增字段定义，返回新 id；`field_key` 已存在抛 `IntegrityError` |

**FieldDefinition 数据类**：

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 主键 |
| field_key | str | 英文规范键（不可变） |
| section | str | `identity`/`birth`/`history`/`allergy`/`lifestyle`/`reproductive`/`complaint`/`exam`/`followup` |
| label_cn | str | 中文标签（界面显示） |
| label_en | str | 英文标签 |
| value_type | str | `text`/`date`/`number`/`enum`/`bool` |
| is_multi | bool | 是否多值（用 seq 1..n） |
| is_active | bool | 是否启用 |
| unit_cn / unit_en | str | 单位 |
| sort_order | int | 表单顺序 |
| is_legacy | bool | 是否 v1 迁移而来 |

#### 病典查询操作

| 方法签名 | 返回值 | 说明 |
|---------|--------|------|
| `search_disease(keyword: str, limit: int = 10) -> list[DiseaseTerm]` | list[DiseaseTerm] | 搜索病症词条（中英文模糊搜索） |
| `get_disease_by_chinese(chinese_name: str) -> Optional[DiseaseTerm]` | Optional[DiseaseTerm] | 根据中文名称获取病症 |
| `get_disease_by_english(english_name: str) -> Optional[DiseaseTerm]` | Optional[DiseaseTerm] | 根据英文名称获取病症 |
| `get_disease_by_key(term_key: str) -> Optional[DiseaseTerm]` | Optional[DiseaseTerm] | **v2.1 新增**：按 `term_key` 查（DNA 解码回填用） |
| `get_all_categories() -> list[str]` | list[str] | 获取所有病症分类 |
| `add_disease_term(term_key: str, chinese_name: str, english_name: str, category: str = "general") -> int` | int | 添加新病症词条，返回新ID |

**DiseaseTerm 数据类**：

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 主键 |
| term_key | str | **v2.1 新增**：不可变英文标识，如 `phenylketonuria`，DNA 载荷用这个 |
| chinese_name | str | 中文名称（UNIQUE） |
| english_name | str | 英文展示名（可变） |
| category | str | 分类 |
| is_active | bool | 是否启用 |

#### 病症结果操作（v2.1 新增）

| 方法签名 | 返回值 | 说明 |
|---------|--------|------|
| `list_disease_results(record_id: str) -> list[DiseaseResult]` | list[DiseaseResult] | 读取某档案的全部病症结果 |
| `upsert_disease_result(record_id: str, term_key: str, result_cn: str, seq: int = 0, checked_at: str = "") -> int` | int | 写入/覆盖病症结果；内部把 `result_cn` 转成 `result_en` 规范值 |

**DiseaseResult 数据类**：

| 字段 | 类型 | 说明 |
|------|------|------|
| term_key | str | 对应 `disease_terms.term_key` |
| result_cn | str | 阴性 / 阳性 / 未查 |
| result_en | str | `negative` / `positive` / `not_tested` |
| seq | int | 多次筛查序号 |
| checked_at | str | 检查日期 |

#### 文件解析操作

| 方法签名 | 返回值 | 说明 | 异常 |
|---------|--------|------|------|
| `parse_document(file_path: str) -> str` | str | 解析文档提取纯文本 | ValueError(不支持格式) |
| `save_upload_file(file_content: bytes, filename: str) -> str` | str | 保存上传文件，返回路径 | IOError |
| `cleanup_temp_files(older_than_hours: int = 24) -> int` | int | 清理过期临时文件，返回清理数量 | - |

**支持的文档格式**：`.txt` / `.docx` / `.pdf` / `.jpg` / `.jpeg` / `.png`

#### 档案记录 CRUD

> **v2.1 说明：以下 5 个方法签名与 v1 完全一致，调用方无需改动。**

| 方法签名 | 返回值 | 说明 |
|---------|--------|------|
| `save_record(record: ArchiveRecord) -> str` | str | 保存/更新档案，返回 record_id。单事务写入身份 + entries + diseases |
| `load_record(record_id: str) -> Optional[ArchiveRecord]` | Optional[ArchiveRecord] | 加载档案记录；不存在或已软删返回 None |
| `delete_record(record_id: str) -> bool` | bool | 删除档案记录（软删除，`is_deleted=1`） |
| `list_records(offset: int = 0, limit: int = 20, keyword: str = None) -> tuple[list[ArchiveRecord], int]` | tuple | 列出档案（分页），返回 (列表, 过滤后总数) |
| `update_record(record: ArchiveRecord) -> bool` | bool | 全量更新档案记录（entries/diseases 先删后插） |

**v2.1 新增的局部更新方法**：

| 方法签名 | 返回值 | 说明 |
|---------|--------|------|
| `update_meta(record_id: str, **fields) -> bool` | bool | 只更新身份字段（name/gender/nation/id_number/residence_address/archive_number/create_date） |
| `upsert_entries(record_id: str, entries: list[dict]) -> int` | int | 只更新部分内容，不重建整条记录；返回写入行数 |

`upsert_entries` 的 `entries` 元素格式：

```python
{"field_key": "chief_complaint", "seq": 0,
 "value_cn": "咳嗽三天", "value_en": "咳嗽三天", "value_num": None}
```

- 未在 `entries` 中出现的 `field_key` 保持原值
- 命中 `(record_id, field_key, seq)` 已有行 → `UPDATE` 覆盖
- `field_key` 未登记或已停用 → 抛 `FieldKeyNotRegisteredError`
- 同一 `field_key` 下 `seq` 重复 → 抛 `DuplicateSeqError`

**ArchiveRecord 数据类（v2.1 重构）**：

```python
@dataclass
class EntryValue:
    seq: int = 0                  # 单值固定 0；多值 1..n
    value_cn: str = ""            # 界面展示值
    value_en: str = ""            # 编码/交换值（开放文本时 = value_cn）
    value_num: float | None = None  # value_type=number 时同步填

@dataclass
class DiseaseResult:
    term_key: str = ""            # 对应 disease_terms.term_key
    result_cn: str = ""           # 阴性 / 阳性 / 未查
    result_en: str = ""           # negative / positive / not_tested
    seq: int = 0
    checked_at: str = ""

@dataclass
class ArchiveRecord:
    # ── 身份字段：保留为属性（列表、搜索、排序、身份核验用）
    record_id: str = ""
    archive_number: str = ""
    name: str = ""
    gender: str = ""              # male / female / unknown
    nation: str = ""
    id_number: str = ""
    residence_address: str = ""
    create_date: str = ""
    source: str = "manual"
    created_at: str = ""
    updated_at: str = ""
    is_deleted: bool = False

    # ── 内容：全部键值化，key 为 field_key
    entries: dict[str, list[EntryValue]] = field(default_factory=dict)

    # ── 病症结果
    diseases: list[DiseaseResult] = field(default_factory=list)

    # ── 便利访问器（让调用方写法尽量不变）
    def get(self, key: str, default: str = "") -> str: ...
    def get_multi(self, key: str) -> list[str]: ...
    def set(self, key: str, value, value_en: str = "") -> None: ...
    def set_multi(self, key: str, values: list) -> None: ...
    def to_payload(self) -> dict: ...   # 生成 DNA 编码载荷，见 database_v2_design §6.3
```

**ArchiveRecord 字段说明**：

| 分类 | 字段 | 存哪里 |
|------|------|--------|
| 身份（7+5） | record_id, archive_number, name, gender, nation, id_number, residence_address, create_date, source, created_at, updated_at, is_deleted | `archive_records` 物理列 |
| 内容（53） | `entries[field_key]`，见 `database_v2_design.md` §5.2~§5.9 | `record_entries` 键值行 |
| 病症 | `diseases` 列表 | `record_diseases` |

> **注意**：v1 的 `follow_up_records` / `disease_records` 两个 JSON 字符串字段**已删除**。随访改为 `entries["followup_date"]` 等多值字段（seq 对齐），病症改为 `diseases` 列表。手工 `json.dumps` / `json.loads` 的地方全部去掉，统一由 `to_payload()` 生成载荷。

> **双语规则**：只有枚举字段（gender/abo_blood_type/rh_blood_type/symptom_severity/result）和病症词典需要真正的英文值；开放文本的 `value_en` 直接等于 `value_cn`，由 `ensure_ascii` 在编码时转义。**不要为凑英文去做翻译。**

**异常定义**：

```python
class DataStoreError(Exception): ...
class FieldKeyNotRegisteredError(DataStoreError): ...   # field_key 不在字典或已停用
class DuplicateSeqError(DataStoreError): ...            # 同一 field_key 下 seq 重复
class RecordNotFoundError(DataStoreError): ...
```

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
| key_hash | str | 加密密钥哈希 |
| cg_content | float | GC含量 |
| thermal_stability | float | 热稳定性系数 |
| padded_zeros | int | 补齐的 0 位数 |
| sequence_length | int | 序列长度 |
| original_text | str | 编码前原始文本 |
| encoded_at | str | 编码时间 |
| is_valid | bool | 序列是否有效 |
| payload_version | str | **v2.1 新增**：编码载荷格式版本（默认 `'v2'`），必须可追溯 |
| payload_mode | str | **v2.1 新增**：`bilingual` / `canonical_en`（默认 `bilingual`） |

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

**extract_fields 返回的 data 结构（v2.1，改为 field_key 驱动）**：
```python
{
    "fields": {
        # key 必须是 field_key（英文），不是中文标签
        "name": "张三",
        "gender": "male",                 # 枚举已规范化为英文值
        "chief_complaint": "咳嗽三天",
        "temperature": "36.8",
        "allergy_source": ["花粉", "青霉素"],   # 多值字段返回 list
    },
    "diseases": {
        "phenylketonuria": "阴性",          # key 为 term_key，value 为中文结果
    },
    "unrecognized": ["文档里出现但字段清单中没有的内容"],
}
```

**`fields_hint` 参数格式（调用方传入，AI 模块不自己查数据库）**：
```python
[
    {"field_key": "chief_complaint", "label_cn": "主诉", "type": "text",  "multi": False},
    {"field_key": "gender",          "label_cn": "性别", "type": "enum",  "multi": False,
     "options": {"male": "男", "female": "女", "unknown": "未知"}},
    {"field_key": "allergy_source",  "label_cn": "过敏原","type": "text", "multi": True},
]
```

> **分层约束**：`ollama_api.py` **不得 import `data_store`**。字段清单由调用方（UI 的 `HealthArchiveApp`）从 `data_store.list_field_definitions()` 取出后通过 `fields_hint` 传入。
> `fields_hint` 为 `None` 时，AI 按文档内容自由抽取，返回的 key 交由 `DataClassifier` 归一化。

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

> **v2.1 说明：本模块接口完全不变。**
> 变的是传进来的 `plaintext` 怎么生成 —— 由 `ArchiveRecord.to_payload()` 产出 dict 后序列化：
>
> ```python
> payload = json.dumps(record.to_payload(), ensure_ascii=True,
>                      sort_keys=True, separators=(",", ":"))
> result = dna_codec.encode(payload, key)
> data_store.save_dna_sequence(DNASequenceRecord(
>     record_id=record.record_id, dna_sequence=result.dna_sequence,
>     cg_content=result.cg_content, thermal_stability=result.thermal_stability,
>     padded_zeros=result.padded_zeros, sequence_length=result.sequence_length,
>     original_text=payload, encoded_at=now(),
>     payload_version="v2", payload_mode="bilingual",
> ))
> ```
>
> **`ensure_ascii=True` 是硬要求**：没有它，中文会以 UTF-8 原文进入编码器，C++ 侧处理不一致，且不同平台字节序不同导致同一档案编码结果不一致。

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

### 7.1 字段来源 (`field_extractor.py`)

**文件路径**：`core/field_extractor.py`

> **v2.1 重大变更**：`PHYSICAL_FIELDS` / `DISEASE_FIELDS` / `REPEATED_FIELDS` 三个硬编码常量**已废弃**。
> 字段清单的唯一来源改为数据库的 `field_definitions` 表 —— 这样加字段只需往字典加一行，不用改代码、改文档、改 prompt 三个地方。

**公开接口**：

| 成员 | 类型 | 说明 |
|------|------|------|
| `get_all_fields(data_store) -> list[FieldDefinition]` | 函数 | 从 `field_definitions` 读取全部启用字段 |
| `get_fields_by_section(data_store, section: str) -> list[FieldDefinition]` | 函数 | 按分组取字段（UI 渲染用） |
| `get_field_map(data_store) -> dict[str, FieldDefinition]` | 函数 | 返回 `{field_key: FieldDefinition}`，供快速查中文标签 |

**枚举规范值常量**（这部分仍然硬编码，因为它是业务约定不是配置）：

```python
GENDER_MAP = {"男": "male", "女": "female", "": "unknown"}          # 输入 → 规范值
GENDER_DISPLAY = {"male": "男", "female": "女", "unknown": "未知"}   # 规范值 → 界面

BLOOD_TYPE_MAP = {"A": "A", "B": "B", "AB": "AB", "O": "O"}
RH_MAP = {"阳性": "positive", "+": "positive", "阴性": "negative", "-": "negative"}

DISEASE_RESULT_MAP = {"阴性": "negative", "阳性": "positive", "未查": "not_tested"}
DISEASE_RESULT_DISPLAY = {"negative": "阴性", "positive": "阳性", "not_tested": "未查"}

SEVERITY_MAP = {"急性": "acute", "慢性": "chronic", "反复发作": "recurrent"}
```

---

#### 附：v1 字段清单（仅用于迁移映射，新代码不要引用）

v1 的 33 个字段与框架文档的 33 个字段几乎不重叠，v2.1 已把 v1 字段拆成「身份列 7 + 出生史 entries 16 + 病症 7 + 随访 3」。迁移映射见 `database_v2_design.md` §8.2。

```
v1 PHYSICAL_FIELDS（23）：
档案编号, 姓名, 性别, 出生日期, 证件号码,
户籍地址, 常住地址, 建档机构, 建档日期, 联系电话,
民族, ABO血型, Rh血型,
父亲姓名, 父亲联系电话, 母亲姓名, 母亲联系电话,
出生孕周, 出生体重, 出生身长, 分娩机构,
Apgar_1分钟, Apgar_5分钟

v1 DISEASE_FIELDS（7）：
苯丙酮尿症, 先天性甲状腺功能减低症, 听力筛查,
过敏史, 先天异常, 既往住院史, 家族遗传病史

v1 REPEATED_FIELDS（3）：
随访日期, 当前体重, 体温
```

---

### 7.2 数据分类器 (`data_classifier.py`)

**文件路径**：`core/data_classifier.py`

> **v2.1 变更**：返回结构由「物理/反复/病症」三分改为「entries/diseases」两分。
> 原来的 `get_physical_fields` / `get_repeated_fields` 合并为 `to_entries()`，因为存储层不再区分单值/多值表 —— 都进 `record_entries`，只靠 `seq` 区分。

**构造**：

```python
class DataClassifier:
    def __init__(self, data_store) -> None
        """需要 data_store 是为了查 field_definitions 做 field_key 校验与类型转换。"""
```

**公共方法**：

| 方法签名 | 返回值 | 说明 |
|---------|--------|------|
| `classify_fields(raw_data: dict) -> dict` | dict | 主入口：原始表单/AI 数据 → `{"entries": {...}, "diseases": [...], "unknown_keys": [...]}` |
| `to_entries(raw_data: dict) -> dict[str, list[EntryValue]]` | dict | 只转内容部分，含双语、枚举规范化、seq 分配 |
| `to_diseases(raw_diseases: dict) -> list[DiseaseResult]` | list[DiseaseResult] | 只转病症部分，中文名 → `term_key` 映射 |
| `build_record(raw_data: dict, record_id: str = "") -> ArchiveRecord` | ArchiveRecord | 一步到位构造完整对象，供 UI 保存时调用 |

**`classify_fields` 返回结构**：

```python
{
    "entries": {
        # 单值字段：seq=0
        "chief_complaint": [EntryValue(seq=0, value_cn="咳嗽三天",
                                       value_en="咳嗽三天", value_num=None)],
        "gender":          [EntryValue(seq=0, value_cn="男",
                                       value_en="male", value_num=None)],
        "birth_weight":    [EntryValue(seq=0, value_cn="3200",
                                       value_en="3200", value_num=3200.0)],
        # 多值字段：seq 从 1 开始
        "allergy_source":  [EntryValue(seq=1, value_cn="花粉", value_en="花粉", value_num=None),
                            EntryValue(seq=2, value_cn="青霉素", value_en="青霉素", value_num=None)],
        "followup_date":   [EntryValue(seq=1, value_cn="2026-09-01", ...),
                            EntryValue(seq=2, value_cn="2026-10-01", ...)],
    },
    "diseases": [
        DiseaseResult(term_key="phenylketonuria", result_cn="阴性", result_en="negative", seq=0),
    ],
    "unknown_keys": ["某个字典里没有的字段名"],   # 不静默丢弃，交给调用方决定
}
```

**转换规则（必须实现）**：

| 规则 | 说明 |
|------|------|
| 1 | 输入 key 可以是 `field_key` 也可以是中文标签，先按 `label_cn` 查字典归一化 |
| 2 | 字典里查不到的 key → 放进 `unknown_keys`，不抛异常也不入库 |
| 3 | 枚举字段按 §7.1 的 `*_MAP` 转规范英文值，转不了就保留原文并记 warning |
| 4 | `value_type=number` 的字段同时填 `value_num`；解析失败则 `value_num=None` |
| 5 | `is_multi=1` 的字段：输入为 list 或按换行/逗号拆分，分配 `seq=1..n`；空值跳过 |
| 6 | `is_multi=0` 的字段：`seq` 固定 0，输入为 list 时只取第一项 |
| 7 | 随访类字段（`followup_*`）按**输入顺序**对齐 `seq`：第 1 次随访所有字段 seq=1，第 2 次全为 2 |
| 8 | 开放文本 `value_en = value_cn`；**禁止调用翻译** |

---

### 7.3 拼音转换工具 (`pinyin_utils.py`)

**文件路径**：`core/pinyin_utils.py`

> **v2.1 降级说明**：v1 曾计划用拼音解决"DNA 编码不能处理中文"的问题。
> v2.1 改用 `json.dumps(..., ensure_ascii=True)` 直接把中文转成 `\uXXXX`，**无损可逆，不再需要拼音翻译**。
> 本模块**可以不做**，或保留仅用于可选的拼音检索/排序。**任何编码路径不得调用它。**

**公共方法**（可选实现）：

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
| ui_interface | data_store | `list_field_definitions(section)` | **v2.1 新增**：动态渲染表单分组 |
| ui_interface | data_store | `save_record(record)` | 保存档案 |
| ui_interface | data_store | `load_record(record_id)` | 加载档案（编辑时） |
| ui_interface | data_store | `list_records(offset, limit, keyword)` | 档案列表分页 |
| ui_interface | data_store | `upsert_entries(record_id, entries)` | **v2.1 新增**：局部更新内容 |
| ui_interface | data_store | `parse_document(file_path)` | 解析上传文档 |
| ui_interface | data_store | `save_upload_file(content, filename)` | 保存上传文件 |
| ui_interface | data_store | `search_disease(keyword)` | 搜索病症词条 |
| ui_interface | data_store | `list_disease_results(record_id)` | **v2.1 新增**：读取病症结果 |
| ui_interface | core | `DataClassifier.build_record(raw_data)` | **v2.1 新增**：表单数据 → ArchiveRecord |
| ui_interface | ollama_api | `extract_fields(text, on_progress)` | AI字段提取 |
| ui_interface | ollama_api | `correct_errors(corrupted, references)` | AI纠错 |
| ui_interface | dna_codec | `encode(plaintext, key)` | DNA编码 |
| ui_interface | dna_codec | `decode(dna_sequence, key)` | DNA解码 |
| ui_interface | dna_codec | `generate_key(identity_info)` | 生成密钥 |
| ollama_api | — | **无跨模块依赖** | **v2.1 约束**：只依赖 ollama HTTP 服务；字段清单由调用方通过 `fields_hint` 传入 |
| error_corrector | data_store | `find_similar_records(text)` | 相似档案比对 |
| error_corrector | ollama_api | `correct_errors(...)` | AI纠错推断 |
| main | data_store | `init_database()` / `init_field_definitions()` / `init_disease_terms()` | **启动初始化（顺序不能乱）** |

### 启动初始化顺序（`main.py`）

```python
data_store = DataStore(db_path, data_dir)
data_store.init_database()            # 1. 建表 + schema_meta
data_store.init_field_definitions()   # 2. 灌字段字典（60 条）——必须先于任何档案写入
data_store.init_disease_terms()       # 3. 灌病症词典（236 条）

ai_client = OllamaClient(model="qwen2.5:7b-instruct")
dna_codec = DNACodec(exe_dir=EXE_DIR)
classifier = DataClassifier(data_store)

app = HealthArchiveApp(data_store, ai_client, dna_codec,
                       error_corrector, classifier)
app.start()
```

---

*本文档 v2.1，与 `docs/modules/database_v2_design.md` v2.1 配套，是模块对接的唯一依据。*
*v1.0 契约已作废，历史代码迁移见 `database_v2_design.md` §8。*
