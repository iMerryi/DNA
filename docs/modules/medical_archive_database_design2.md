# 医疗档案数据库设计说明书

> 模块：数据持久层（`data_store.py`）
> 版本：**v2.1 说明版**
> 字段来源：`10.17医疗信息框架(4).docx`
> 施工依据：`database_v2_design.md` v2.1（含完整 DDL、索引、接口签名）
> 接口契约：`api_contract.md` v2.1

---

## 0. 这份文档是什么，不是什么

这是**给人读的**设计说明。它回答三个问题：为什么要这么设计、每张表在干什么、哪些地方最容易想错。

**它不是施工图。** 建表 SQL、索引语句、方法签名以 `database_v2_design.md` v2.1 为准；两者若有出入，以那份为准，并回来修本文档。

| 文档 | 读者 | 用途 | 冲突时 |
|---|---|---|---|
| 本文档 | 队友、指导老师、评委 | 理解设计意图、答辩讲解 | 次要 |
| `database_v2_design.md` v2.1 | 数据库开发者 | 照着写代码、执行 DDL | **以此为准** |
| `api_contract.md` v2.1 | 全体开发者 | 模块间调用约定 | 接口以它为准 |

> 为什么不合并成一份？因为「为什么」和「怎么做」的读者不同、更新节奏也不同。但**两份文档的技术事实必须一致**，所以本文档的字段数、表数、约束、索引全部与 v2.1 对齐，不自行发挥。

---

## 1. 设计目标

| 目标 | 具体手段 | 付出的代价 |
|---|---|---|
| 用户输入输出用中文，编码传输用 ASCII | 每个值双列存储 `value_cn` / `value_en`；编码时取英文列 | 每行多一列，存储约增加 1 倍（可接受） |
| 加字段不改表 | 内容进键值表，新增字段只在字典加一行 | 读一条档案要 JOIN 字典、跨多行组装 |
| 一份档案，中英双值 | 字典存 `label_cn/label_en`，条目存 `value_cn/value_en` | 需明确双语边界（见 §7.2），否则会误以为要翻译所有内容 |
| 内容来源唯一 | 所有 key 必须登记在 `field_definitions`，外键强约束 | 新增字段要走登记流程，不能临时造 key |
| 档案可长期冷存 | DNA 编码 + 载荷版本号 + 编码/解码双表留痕 | 编码表体积随版本累积增长 |

**一句话概括**：把"结构"从"数据"里抽出来。字段定义存一份、档案内容存一份，两者靠 `field_key` 相连——这样加字段是加数据，不是改表结构。

---

## 2. 数据来源与一次教训

唯一字段来源是 `10.17医疗信息框架(4).docx`，它的结构是：

- **铭文部分**：姓名、性别、民族、身份证号、常住地址、档案编号、建档日期
- **存储部分**
  - 一、患者基础与背景信息类：既往史/家族史、过敏史、个人生活史、婚育史/月经史
  - 二、临床主诉与现病史类：疾病分类、症状表现、体格检查（体征）

### 2.1 一个必须记住的教训

早期草稿（v2.0）只按这份框架文档整理了 **44 个字段**，把 v1 的 23 个物理字段当成"历史遗留"处理掉了。但 v1 的那 23 个是**儿童出生档案**：胎龄、出生体重、出生身长、Apgar 评分、父母姓名电话、血型——这不是垃圾数据，是产品最核心的信息。

两套口径的精确交集只有「体温」1 个：

| 体系 | 内容 | 字段数 |
|---|---|---|
| v1 儿童档案 | 出生史 + 父母 + 血型 + 出生指标 | 23 |
| 框架文档 | 既往史 + 过敏 + 生活史 + 婚育 + 主诉 + 体征 | 33 |
| **合并后实际需要** | | **60**（v2.1 补入 `birth` 分组 16 个字段） |

**结论**：字段来源不能只看一份文档。产品定位（儿童健康档案）决定了出生史必须是正式分组，不是 legacy 兜底。

---

## 3. 数据模型

### 3.1 结构图

```
schema_meta（结构版本，独立）

archive_records（身份 + 状态）
   ├── record_entries  ──>  field_definitions（字段字典，约束 field_key）
   ├── record_diseases ──>  disease_terms    （病症词典，约束 term）
   └── dna_sequences   ──>  decode_records   （编码 → 解码，全链路留痕）
```

### 3.2 为什么是"身份列 + 键值表"，而不是全键值

这是整个设计里最关键的一个取舍。三个方案对比：

| 方案 | 列表页 20 条档案的查询 | 新增字段 | 结论 |
|---|---|---|---|
| A. 60 个物理列 | 1 次查询、20 行 | **要 ALTER TABLE** | 每加一类字段改一次表，不可持续 |
| B. 全部键值化（连姓名也进 entries） | **1200 行 + 应用层聚合** | 加一行字典 | 列表、排序、搜索全部退化 |
| C. 身份列物理化 + 内容键值化（**采用**） | 1 次查询、20 行 | 加一行字典 | 两侧优点都拿到 |

选 C 的判断标准很简单：**这条字段会不会出现在列表页、会不会被用来排序和搜索？** 会 → 物理列；不会 → 键值表。

所以只有 7 个字段留在 `archive_records`：姓名、性别、民族、证件号、常住地址、档案编号、建档日期。其余 53 个进 `record_entries`。

---

## 4. 表结构说明

数据库文件：`data/db/medical_archive.db`（SQLite）。共 8 张表 + 1 张迁移暂存表。

### 4.1 `archive_records` 档案主表

存储身份标识与生命周期状态。**只放列表页和搜索要用的列**。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | INTEGER | PK AUTOINCREMENT | 内部主键 |
| record_id | TEXT | NOT NULL UNIQUE | 业务号 `ARCHIVE_{YYYYMMDD}_{NNN}` |
| archive_number | TEXT | DEFAULT '' | 档案编号（用户填） |
| name | TEXT | NOT NULL | 姓名 |
| gender | TEXT | DEFAULT '' | 规范值 `male`/`female`/`unknown` |
| nation | TEXT | DEFAULT '' | 民族 |
| id_number | TEXT | DEFAULT '' | 身份证号 |
| residence_address | TEXT | DEFAULT '' | 常住地址 |
| create_date | TEXT | DEFAULT '' | 建档日期（业务日期，用户填） |
| source | TEXT | DEFAULT 'manual' | `manual`/`upload`/`ai` |
| created_at | TEXT | NOT NULL | 系统写入 |
| updated_at | TEXT | NOT NULL | 系统写入 |
| is_deleted | INTEGER | DEFAULT 0 | 软删除标记 |

> **两个时间字段要分清**：`create_date` 是用户填的"建档日期"（业务含义），`created_at` 是系统写库时间。混用会导致报表对不上。
>
> **没有 `name_en`**：姓名没有规范英文值（"张三"→"Zhang San" 是音译）。真要护照名，那是独立字段 `passport_name`，不是 `name_en`——后者只会永远为空。

### 4.2 `field_definitions` 字段字典

全部业务字段的唯一登记处。前端表单渲染、AI 输出校验、写入合法性检查都靠它。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | INTEGER | PK | |
| field_key | TEXT | NOT NULL UNIQUE | 英文规范键，入库后**不可改名** |
| section | TEXT | NOT NULL | 9 个分组之一 |
| label_cn / label_en | TEXT | NOT NULL | 中英标签 |
| value_type | TEXT | DEFAULT 'text' | `text`/`date`/`number`/`enum`/`bool` |
| is_multi | INTEGER | DEFAULT 0 | 1=多值（seq 从 1 递增） |
| is_active | INTEGER | DEFAULT 1 | 0=停用：前端不渲染，历史值仍可读 |
| unit_cn / unit_en | TEXT | DEFAULT '' | 单位，如 `℃` |
| sort_order | INTEGER | DEFAULT 0 | 表单与导出顺序 |
| is_legacy | INTEGER | DEFAULT 0 | 1=从 v1 迁移而来 |

> `is_active` 的意义：字段不删只停用。删字段会让历史档案的那一行变成孤儿，停用则读得出、写不进。

### 4.3 `record_entries` 内容键值表（核心）

一条档案的内容 = 本表里 `record_id` 相同的一组行。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | INTEGER | PK | |
| record_id | TEXT | NOT NULL，**FK** → archive_records | ON DELETE CASCADE |
| field_key | TEXT | NOT NULL，**FK** → field_definitions | 字典外键，挡住拼写漂移 |
| seq | INTEGER | DEFAULT 0 | 单值固定 0；多值从 1 连续递增 |
| value_cn | TEXT | DEFAULT '' | 中文值（展示） |
| value_en | TEXT | DEFAULT '' | 英文/规范值（编码交换） |
| value_num | REAL | NULL | 数值副本，供范围查询 |
| updated_at | TEXT | NOT NULL | |

**约束**：`UNIQUE(record_id, field_key, seq)` —— 这是整个模型的"槽位"定义：一条档案的一个字段的一次取值，只占一个槽。

**故意没有 `is_deleted`**。原因见 §6.3，这是本项目踩过的坑。

### 4.4 `record_diseases` 病症结果表

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | INTEGER | PK | |
| record_id | TEXT | FK → archive_records | CASCADE |
| disease_term_id | INTEGER | FK → disease_terms.id | |
| result_cn / result_en | TEXT | DEFAULT '' | 阴性/阳性/未查 ↔ negative/positive/not_tested |
| seq | INTEGER | DEFAULT 0 | 同一病症多次筛查序号 |
| checked_at | TEXT | DEFAULT '' | 检查日期 |
| updated_at | TEXT | NOT NULL | |

**约束**：`UNIQUE(record_id, disease_term_id, seq)` —— 支持"听力筛查复筛"这类场景。

> 为什么病症名不直接存字符串？因为 236 条词条要统一升级、统一英文名、统一 DNA 载荷标识。存字符串等于让每条档案各写各的。

### 4.5 `disease_terms` 病症词典

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | INTEGER | PK | |
| term_key | TEXT | NOT NULL UNIQUE | **不可变**英文标识，如 `phenylketonuria` |
| chinese_name | TEXT | NOT NULL UNIQUE | 中文名 |
| english_name | TEXT | NOT NULL | 英文展示名（可修改） |
| category | TEXT | DEFAULT 'general' | 分类 |
| is_active | INTEGER | DEFAULT 1 | |
| updated_at | TEXT | DEFAULT '' | |

> **`term_key` 和 `english_name` 是两回事**：前者是身份，永不变；后者是展示，可以改词。DNA 载荷里写的是 `term_key`——否则改一次英文名，历史编码的档案就全部解不回来了。

### 4.6 `dna_sequences` DNA 序列表

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| record_id | TEXT NOT NULL FK | |
| dna_sequence | TEXT NOT NULL | ATCG 序列 |
| key_hash | TEXT NOT NULL | 密钥哈希（**不存明文密钥**） |
| cg_content / thermal_stability | REAL | 序列质量指标 |
| padded_zeros / sequence_length | INTEGER | 编码参数 |
| original_text | TEXT | 编码前明文 |
| encoded_at | TEXT NOT NULL | |
| is_valid | INTEGER DEFAULT 1 | 当前有效版本标记 |
| payload_version | TEXT DEFAULT 'v2' | **载荷格式版本** |
| payload_mode | TEXT DEFAULT 'bilingual' | `bilingual` / `canonical_en` |

> 重新编码不删除旧行，只把旧行 `is_valid=0`。冷存储系统必须能回答"这条档案历史上被编码过几次、每次什么参数"。

### 4.7 `decode_records` 解码记录表

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| dna_record_id | INTEGER NOT NULL FK | → dna_sequences.id |
| decoded_text | TEXT NOT NULL | 解码原文 |
| corrected_text | TEXT DEFAULT '' | AI 纠错后 |
| confidence / error_rate | REAL | 0.0–1.0 |
| correction_log | TEXT DEFAULT '{}' | 纠错日志（JSON） |
| decoded_at | TEXT NOT NULL | |

> 编解码双表构成审计链：任何一次"存进去是什么、拿出来是什么"都可追溯。这是医疗数据的基本要求。

### 4.8 `schema_meta` 结构版本表

| 字段 | 类型 | 说明 |
|---|---|---|
| version | TEXT NOT NULL | 如 `v2.1` |
| applied_at | TEXT NOT NULL | 应用时间 |

`init_database()` 先读本表：为空则建全表并写版本；低于当前版本则依次跑迁移。

> 没有这张表，一年后没人说得清线上库是什么结构，也没法做增量迁移。**成本 2 行 DDL，收益是整个项目的可维护性。**

---

## 5. 字段字典（60 个）

按框架文档章节组织，便于和原始文档核对。完整清单（含每个字段的枚举值与单位）见项目根目录 `数据库开发书/01_数据字典.md`。

| 分组 | 内容 | 字段数 | 存储位置 |
|---|---|---:|---|
| identity | 铭文（身份） | 7 | `archive_records` |
| birth | 出生史与家庭信息 | 16 | `record_entries` |
| history | 既往史 / 家族史 | 7 | `record_entries` |
| allergy | 过敏史 | 3 | `record_entries` |
| lifestyle | 个人生活史 | 4 | `record_entries` |
| reproductive | 婚育史 / 月经史 | 2 | `record_entries` |
| complaint | 临床主诉与现病史 | 10 | `record_entries` |
| exam | 体格检查（体征） | 7 | `record_entries` |
| followup | 随访 | 4 | `record_entries` |
| **合计** | | **60** | 其中 53 个进键值表 |

### 5.1 identity 铭文（物理列）

| field_key | 中文 | 类型 |
|---|---|---|
| name | 姓名 | text |
| gender | 性别 | enum: male/female/unknown |
| nation | 民族 | text |
| id_number | 身份证号 | text |
| residence_address | 常住地址 | text |
| archive_number | 档案编号 | text |
| create_date | 建档日期 | date |

### 5.2 birth 出生史与家庭信息

| field_key | 中文 | 类型 |
|---|---|---|
| birth_date | 出生日期 | date |
| organization | 建档机构 | text |
| abo_blood_type | ABO血型 | enum: A/B/AB/O/unknown |
| rh_blood_type | Rh血型 | enum: positive/negative/unknown |
| father_name / father_phone | 父亲姓名 / 电话 | text |
| mother_name / mother_phone | 母亲姓名 / 电话 | text |
| gestational_weeks | 胎龄（周） | number |
| birth_weight | 出生体重(g) | number |
| birth_length | 出生身长(cm) | number |
| delivery_org | 分娩机构 | text |
| apgar_1min / apgar_5min | Apgar 评分 | number |
| contact_phone | 联系电话 | text |
| hukou_address | 户籍地址 | text |

### 5.3～5.8 其余分组

| 分组 | field_key 清单 |
|---|---|
| history | past_medical_history, surgery_history, trauma_history, transfusion_history, vaccination_history, family_history, high_risk_factor(multi) |
| allergy | allergy_source(multi), allergy_reaction(multi), drug_allergy |
| lifestyle | smoking_history, alcohol_history, diet_habit, sleep_habit |
| reproductive | marriage_history, menstrual_history |
| complaint | disease_category, chief_complaint, symptom_onset(date), symptom_severity(enum: acute/chronic/recurrent), symptom_duration, accompanying_symptoms(multi), mental_state, appetite, sleep_quality, bowel_urine |
| exam | temperature(number ℃), pulse(number 次/分), respiration(number 次/分), blood_pressure(text), specialty_exam, positive_signs(multi), negative_signs(multi) |
| followup | followup_date(date,multi), current_weight(number,multi), current_temperature(number,multi), followup_note(text,multi) |

> 随访四件套共用同一 `seq`（seq=1 即第 1 次随访），读取时按 seq 排序组装。这是"用行表达数组"，比 JSON 字符串可靠。

---

## 6. 关键设计取舍（这部分是本文档的重点）

### 6.1 为什么不用 JSON 字符串存随访和病症

v1 的做法是：`follow_up_records` 存一个 JSON 数组字符串，`disease_records` 存一个 JSON 对象字符串。后果在第一次多人协作时就暴露了——**前后端对 JSON 的字段名、嵌套层级、空值约定理解不一致，联调时数据静默丢失**。

拆成键值行之后：

- 结构由表约束保证，不是靠两边"约定"；
- 单个随访的某项可以直接 `UPDATE`，不必读出整串再改再写回；
- 任何一项都能被 SQL 查询和索引；
- 新增一项只需加一条 `field_key`，JSON 结构不用改。

**通用判断**：**能被单独查询、单独修改的数据，不要序列化成字符串。**

### 6.2 为什么身份字段要物理化，不能全键值

全键值化看起来"更纯粹"，但列表页会付出代价：20 条档案 × 60 字段 = 1200 行，还要在应用层按 `record_id` 聚合，再加上姓名搜索要扫全表。而物理化后列表页只需 1 次查询 20 行。

**键值化解决的是"字段会不断新增"，不是"所有字段都该键值化"。** 滥用会换来一身性能债。

### 6.3 为什么条目层坚决不做软删除

这是 v2.0 的一个真实缺陷，值得记下来。

场景：一条档案有 3 次随访（seq = 1/2/3）。用户删掉第 2 次——如果条目层也是软删除，那行还在，只是 `is_deleted=1`。随后用户重新添加一次随访，新行拿到 seq=2 → **撞上 `UNIQUE(record_id, field_key, seq)`，报错**。正常编辑被挡住。

两种修法：

| 修法 | 问题 |
|---|---|
| 软删行"复活"（写复杂逻辑找已删行） | 逻辑绕、易漏，每次 upsert 都要查一遍 |
| **条目层不做软删，写入即覆盖、删除即物理删（采用）** | 需接受"条目无删除痕迹" |

保留档案层软删除（`archive_records.is_deleted`）满足审计需要；条目层的变更痕迹由 `updated_at` 和 DNA 编码历史承担。

**一条经验**：**唯一约束和软删除天然冲突。有唯一约束的槽位表，不要加软删标记。**

### 6.4 为什么开放文本不翻译

v2.0 的表述容易被误读成"每个中文都要配英文"。那不是设计，那是给队友派活。

真实边界只有两类需要**真英文**：

| 类型 | 例子 | 原因 |
|---|---|---|
| 枚举字段 | `gender`=`male`、`symptom_severity`=`acute` | 规范值本身就是英文，且要跨系统交换 |
| 病症词典 | `term_key`=`phenylketonuria` | 稳定标识，用于 DNA 载荷 |

其余全部 `value_en = value_cn`。理由很硬：

1. 编码器只需要 ASCII，`json.dumps(ensure_ascii=True)` 会把中文转成 `\uXXXX`，**无损可逆**；
2. 让队友手工翻译 50 多个字段，既增加工作量，又制造不准确的翻译；
3. 纠错环节要拿解码结果和原文比对，中英不一致反而无法比对。

**如果将来要出英文报告，那是独立的"导出翻译"功能，用 LLM 现翻，不要污染存储层。**

### 6.5 为什么接口保持单对象签名

v2.0 曾提议 `save_record(meta, entries, diseases)`。这等于**把存储结构泄漏到接口层**：调用方本来只需要说"保存这条档案"，现在却要知道数据会被拆成三段。

代价是多处的：前端每个保存入口都要拆三段；`load_record` 返回值从对象变 dict，所有 `record.xxx` 访问全要改；将来换存储模型，接口全废。

**采用**：`save_record(record: ArchiveRecord) -> str`，拆行/组装全部在 `DataStore` 内部完成；需要局部更新时另加 `upsert_entries(record_id, entries)`。

### 6.6 为什么不为 `value_cn` 建索引

直觉上"搜内容要索引"，但 SQLite 的 B-tree 索引对 `LIKE '%关键词%'` 完全无效——前置通配符导致无法使用索引，照样全表扫描，索引只是白占空间、拖慢写入。

当前数据量（单机、千条以内）全表扫描在 10ms 量级。**数据量超过 1 万条、或用户明显感知卡顿时**，再上 FTS5 虚表（方案写在 v2.1 附录 A）。不提前优化。

### 6.7 为什么外键是"每次连接"都要开

`PRAGMA foreign_keys = ON` 是**连接级**设置，不是数据库级。只在建表脚本里写一次，之后程序新建的每个连接，外键约束都是关闭的：脏数据随便插、`ON DELETE CASCADE` 永远不生效。

它不会报错、不会警告，只会安静地失效——**这是 SQLite 最容易被忽略的陷阱**。所以 `DataStore._connect()` 里必须每次执行，并且要有验收用例专门验它（见 §9 的 T9）。

### 6.8 为什么迁移必须"先灌字典，再迁数据"

规则 R1 规定：`field_key` 未登记则拒绝写入。如果迁移脚本先搬数据再灌字典，会在第一步就被外键和数据校验全部拦下。

正确顺序：建新表 → 灌 60 条字段字典 → 灌 236 条病症词典 → 再迁档案。**顺序错了，不是数据错，是根本跑不通。**

---

## 7. 中英与编码规则

### 7.1 写入规则

| 规则 | 说明 |
|---|---|
| R1 | `field_key` 必须已登记且 `is_active=1`，否则拒绝写入（防拼写漂移） |
| R2 | 界面输入存 `value_cn`；编码传输取 `value_en` |
| R3 | 枚举必须存规范英文值：`male/female/unknown`、`A/B/AB/O`、`positive/negative`、`negative/positive/not_tested`、`acute/chronic/recurrent` |
| R4 | `value_type=number` 必须同步写 `value_num`，原字符串保留在 `value_cn/value_en` |
| R5 | 多值字段 `seq` 从 1 连续递增；单值固定 0；禁止重复槽位 |
| R6 | 开放文本若无可靠英文，`value_en` 必须等于 `value_cn`（**不可留空**），编码器负责转 ASCII |
| R7 | 条目不做软删除：命中已有槽位即 `UPDATE` 覆盖；删除条目走物理 `DELETE` |

### 7.2 DNA 编码载荷

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

编码器要求：

- `json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))`；
- 中文自动转 `\uXXXX`，载荷纯 ASCII、**无损可逆**；
- `sort_keys=True` 保证同一档案多次编码字节级一致，便于比对、纠错、相似度计算；
- 多值字段在 `fields` 里是有序数组，顺序由 `seq` 决定；
- 病症用 `term_key`（不可变），不用 `english_name`（可变）。

### 7.3 解码回填

1. DNA 解码得到 ASCII JSON；
2. 校验 `v` 与 `record_id`；
3. 按 `field_key` 从字典取中文标签；
4. 界面展示优先取档案原 `value_cn`，不存在再显示解码文本；
5. 遇到未登记的 `field_key` / `term_key`，**记入纠错日志，不静默丢弃**。

第 5 条很重要：静默丢弃会让"数据漂移"变成"数据消失"，再也查不出来。

---

## 8. 接口概览

完整签名见 `database_v2_design.md` §7 与 `api_contract.md` v2.1。这里只列分组与判断标准。

| 分组 | 主要接口 | 说明 |
|---|---|---|
| 初始化 | `init_database` / `init_field_definitions` / `init_disease_terms` / `get_connection` / `close` | 建表与灌种子，幂等 |
| 档案 CRUD | `save_record` / `load_record` / `update_record` / `delete_record` / `list_records` / `update_meta` / `upsert_entries` | **全部单对象签名** |
| 字段字典 | `list_field_definitions` / `get_field_definition` / `add_field_definition` | 前端动态渲染的唯一依据 |
| 病症 | `search_disease` / `get_disease_by_chinese` / `get_disease_by_key` / `list_disease_results` / `upsert_disease_result` / `get_all_categories` / `add_disease_term` | |
| 文件处理 | `parse_document` / `save_upload_file` / `cleanup_temp_files` | 前端上传 docx/pdf 靠这组 |
| DNA/解码 | `save_dna_sequence` / `load_dna_sequence` / `load_dna_by_sequence` / `list_dna_sequences` / `invalidate_dna_sequence` / `save_decode_record` / `list_decode_records` | |
| 相似度 | `find_similar_records` / `find_similar_dna_sequences` | 纠错模块的支持接口 |
| 导出统计 | `export_record_to_json` / `export_record_to_docx` / `backup_database` / `restore_database` / `get_statistics` | |

**异常定义**（不能只抛裸 `Exception`，否则调用方无法区分处理）：

```python
class DataStoreError(Exception): ...
class FieldKeyNotRegisteredError(DataStoreError): ...   # field_key 未登记或已停用
class DuplicateSeqError(DataStoreError): ...           # 同一 field_key 下 seq 重复
class RecordNotFoundError(DataStoreError): ...
```

---

## 9. 常见误区清单（给队友看的）

| # | 误区 | 实际情况 |
|---|---|---|
| 1 | "先在业务代码里用个新 key，回头再登记" | 外键直接拒绝写入；必须先 `add_field_definition()` |
| 2 | "中文值也顺手翻译成英文存进去" | 开放文本 `value_en` 应与 `value_cn` 相同；翻译会引入错误且增加工作 |
| 3 | "列表页顺便把病症也查出来" | 会触发 N+1 查询；`list_records` 只返回身份 + entries |
| 4 | "删除档案直接用 DELETE" | 医疗数据要求软删除（`is_deleted=1`），物理删除仅限管理操作 |
| 5 | "加个 `is_deleted` 到 record_entries 更规范" | 与唯一约束冲突，删后重加会报错（§6.3） |
| 6 | "外键在建表脚本里写了就够了" | 连接级设置，每个连接都要开（§6.7） |
| 7 | "多值字段直接存 JSON 数组更方便" | 无法查询、无法局部更新、协作时格式易错 |
| 8 | "英文名改了没关系" | `english_name` 可改，`term_key` 不可改；载荷引用的是后者 |

---

## 10. 验收标准

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
| T10 | v1 迁移 | 前后记录数一致；抽查 3 条，23 个字段全部落位；词典未被污染 |

> T4 和 T9 是专门为踩过的坑设的。**没有这两条，前面 8 条全过也可能带着 bug 上线。**

---

## 11. 实施顺序

1. 按 v2.1 §4 建表（**先确认 `PRAGMA foreign_keys` 在每个连接都开**）；
2. 灌 60 条字段字典 + 236 条病症词典（必须先于任何数据写入）；
3. 实现 `save_record` / `load_record` 单事务读写；
4. 实现 `upsert_entries` 与 R1/R4/R5 校验；
5. 实现 `data_classifier`：表单/AI 结果 → 键值条目（中英映射、枚举规范化、seq 对齐）；
6. 前端按 `field_definitions` 动态渲染分组表单；
7. DNA 编码按 §7.2 生成载荷；
8. 按 §10 执行验收。

---

## 附录：这份文档从 v2.0 到 v2.1 改了什么

保留这段是因为它本身就是设计过程的记录——答辩时能讲清"我们怎么发现并修正问题"。

| # | v2.0 的问题 | v2.1 的修正 | 教训 |
|---|---|---|---|
| 1 | 只覆盖 44 字段，缺儿童出生史 | 补 `birth` 分组 16 字段，共 60 | 字段来源不能只看一份文档 |
| 2 | 无 DDL、无主键外键、无索引 | 完整可执行 DDL + 13 索引 | 设计说明 ≠ 施工图，两者都要有 |
| 3 | `record_entries` 带 `is_deleted` | 条目层取消软删 | 唯一约束与软删除天然冲突 |
| 4 | `save_record(meta, entries, diseases)` | 回归单对象签名 | 存储结构不应泄漏到接口层 |
| 5 | 病症用 `english_name` 标识 | 新增 `term_key` | 可变值不能当稳定标识 |
| 6 | 无结构版本表 | 新增 `schema_meta` | 没有版本号就没有迁移能力 |
| 7 | 称"LIKE + 索引即可" | 删除无效索引，FTS5 留待二期 | 前置通配符用不上 B-tree |
| 8 | 迁移"匹配不到就 INSERT 新词条" | 新增 `legacy_disease_staging` 暂存 + 人工审核 | 迁移脚本不能污染标准词典 |
