# 核心算法模块开发文档

## 模块概述

| 属性 | 内容 |
|------|------|
| **模块名称** | core/ + dna_codec.py + error_corrector.py |
| **模块全称** | Core Algorithm & DNA Codec |
| **负责角色** | PM/核心算法（你） |
| **技术栈** | Python 3.8+ (pure logic) + C++17 (编译后exe) |
| **依赖模块** | 无（独立模块） |
| **代码位置** | `core/`, `modules/dna_codec.py`, `modules/error_corrector.py` |

---

## 1. 模块组成

| 子模块 | 文件 | 职责 | 外部依赖 |
|--------|------|------|---------|
| 字段定义 | `core/field_extractor.py` | 字段常量定义、字段验证 | 无 |
| 数据分类 | `core/data_classifier.py` | 数据分类（物理/反复/病症） | 无 |
| 拼音转换 | `core/pinyin_utils.py` | 中文转拼音 | 无（或pypinyin） |
| 相似度计算 | `core/similarity.py` | 文本/DNA相似度 | 无 |
| DNA编解码 | `modules/dna_codec.py` | 封装C++编解码器调用 | C++ exe |
| 智能纠错 | `modules/error_corrector.py` | 纠错流程编排 | data_store, ollama_api |

---

## 2. 模块职责

### 2.1 core/ 纯逻辑层

| 编号 | 职责描述 | 优先级 |
|------|---------|--------|
| CORE-01 | 定义所有字段常量（33个字段） | P0 |
| CORE-02 | 实现数据分类逻辑（物理/反复/病症） | P0 |
| CORE-03 | 实现拼音转换（反复存储字段用） | P0 |
| CORE-04 | 实现相似度计算（纠错用） | P1 |

**特点**：纯Python逻辑，无外部依赖，方便单元测试。

### 2.2 dna_codec.py DNA编解码

| 编号 | 职责描述 | 优先级 |
|------|---------|--------|
| CODEC-01 | 封装C++编码器调用 | P0 |
| CODEC-02 | 封装C++解码器调用 | P0 |
| CODEC-03 | 密钥生成（基于身份信息） | P0 |
| CODEC-04 | DNA序列合法性校验 | P0 |

### 2.3 error_corrector.py 智能纠错

| 编号 | 职责描述 | 优先级 |
|------|---------|--------|
| EC-01 | 编排纠错流程（相似度+AI） | P1 |
| EC-02 | 生成纠错报告 | P1 |
| EC-03 | 计算数据损坏程度 | P1 |

---

## 3. 字段定义常量 (`field_extractor.py`)

### 3.1 公开常量

```python
# 物理存储字段（固定信息，23个）
PHYSICAL_FIELDS = [
    "档案编号", "姓名", "性别", "出生日期", "证件号码",
    "户籍地址", "常住地址", "建档机构", "建档日期", "联系电话",
    "民族", "ABO血型", "Rh血型",
    "父亲姓名", "父亲联系电话", "母亲姓名", "母亲联系电话",
    "出生孕周", "出生体重", "出生身长", "分娩机构",
    "Apgar_1分钟", "Apgar_5分钟"
]

# 病症记录字段（7个）
DISEASE_FIELDS = [
    "苯丙酮尿症", "先天性甲状腺功能减低症", "听力筛查",
    "过敏史", "先天异常", "既往住院史", "家族遗传病史"
]

# 反复存储字段（动态信息，3个）
REPEATED_FIELDS = ["随访日期", "当前体重", "体温"]

ALL_FIELDS = PHYSICAL_FIELDS + DISEASE_FIELDS + REPEATED_FIELDS  # 共33个
```

### 3.2 辅助方法（建议实现）

| 方法签名 | 返回值 | 说明 |
|---------|--------|------|
| `is_physical_field(field_name) -> bool` | bool | 判断是否为物理存储字段 |
| `is_disease_field(field_name) -> bool` | bool | 判断是否为病症字段 |
| `is_repeated_field(field_name) -> bool` | bool | 判断是否为反复存储字段 |
| `validate_field_value(field_name, value) -> tuple[bool, str]` | tuple | 验证字段值合法性 |
| `get_field_category(field_name) -> str` | str | 获取字段所属分类 |

---

## 4. 数据分类器 (`data_classifier.py`)

### 4.1 类：DataClassifier

**职责**：将AI提取的原始字典数据，按照业务规则分类整理。

### 4.2 对外接口

| 方法签名 | 返回值 | 说明 |
|---------|--------|------|
| `classify_fields(raw_data: dict) -> dict` | dict | 分类为三类数据 |
| `get_physical_fields(data: dict) -> dict` | dict | 提取物理存储部分 |
| `get_repeated_fields(data: dict) -> list[dict]` | list[dict] | 提取反复存储部分 |
| `get_disease_fields(data: dict) -> dict` | dict | 提取病症记录部分 |

### 4.3 输入输出示例

**输入**（AI提取的原始数据）：
```python
{
    "姓名": "张三",
    "性别": "男",
    "苯丙酮尿症": "阴性",
    "随访日期": "2026-10-01",
    "当前体重": "4.5kg",
    # ... 其他字段
}
```

**输出**（分类后）：
```python
{
    "physical": {
        "姓名": "张三",
        "性别": "男",
        # ... 其他物理字段
    },
    "repeated": [
        {
            "随访日期": "2026-10-01",
            "当前体重": "4.5kg",
            "体温": ""  # 可能为空
        }
    ],
    "diseases": {
        "苯丙酮尿症": "阴性",
        # ... 其他病症字段
    }
}
```

### 4.4 分类规则

1. **物理存储**：字段名在 `PHYSICAL_FIELDS` 中 → 归入 `physical`
2. **病症记录**：字段名在 `DISEASE_FIELDS` 中 → 归入 `diseases`
3. **反复存储**：字段名在 `REPEATED_FIELDS` 中 → 归入 `repeated`（多条记录用列表）
4. **未知字段**：警告日志，归入 `physical`（兜底）

---

## 5. 拼音转换工具 (`pinyin_utils.py`)

### 5.1 使用场景

反复存储字段（随访日期、体重、体温）在编码前需要转换为拼音，因为 C++ 编码器只处理英文字符。

### 5.2 对外接口

| 方法签名 | 返回值 | 说明 |
|---------|--------|------|
| `chinese_to_pinyin(chinese_str: str) -> str` | str | 中文→拼音（无空格） |
| `chinese_to_pinyin_with_space(chinese_str: str) -> str` | str | 中文→拼音（带空格） |

### 5.3 转换示例

| 输入 | 输出（无空格） | 输出（带空格） |
|------|---------------|---------------|
| 随访日期 | suifangriqi | sui fang ri qi |
| 当前体重 | dangqianzhongliang | dang qi zhong liang |
| 体温 | tiwen | ti wen |

### 5.4 实现方案

**推荐**：使用 `pypinyin` 库（轻量，纯Python）
```python
from pypinyin import pinyin, Style

def chinese_to_pinyin(chinese_str: str) -> str:
    result = pinyin(chinese_str, style=Style.NORMAL)
    return "".join([item[0] for item in result])
```

**备选**：自制简单映射表（仅支持常用字，不推荐）

---

## 6. 相似度计算 (`similarity.py`)

### 6.1 使用场景

智能纠错时，需要在数据库中查找与解码文本相似的已知记录，作为AI纠错的参考。

### 6.2 对外接口

| 方法签名 | 返回值 | 说明 |
|---------|--------|------|
| `text_similarity(text1: str, text2: str) -> float` | float | 文本相似度 (0.0-1.0) |
| `dna_similarity(seq1: str, seq2: str) -> float` | float | DNA序列相似度 (0.0-1.0) |
| `find_best_match(target: str, candidates: list[str], threshold: float = 0.7) -> tuple[int, float]` | tuple | 找最佳匹配 (索引, 相似度) |

### 6.3 算法选型

| 场景 | 推荐算法 | 复杂度 |
|------|---------|--------|
| 文本相似度 | 余弦相似度（TF-IDF向量）或编辑距离归一化 | O(n*m) |
| DNA序列相似度 | 序列比对（局部比对）或汉明距离 | O(n*m) |

### 6.4 相似度阈值建议

| 阈值范围 | 含义 | 处理方式 |
|---------|------|---------|
| >= 0.9 | 高度相似 | 直接采用参考值 |
| 0.7 - 0.9 | 中等相似 | 作为AI纠错的强参考 |
| 0.5 - 0.7 | 低相似度 | 作为弱参考 |
| < 0.5 | 不相似 | 不采用 |

---

## 7. DNA编解码模块 (`dna_codec.py`)

### 7.1 类：DNACodec

**职责**：封装 C++ 编解码器的 subprocess 调用。

### 7.2 对外接口

| 方法签名 | 返回值 | 说明 | 异常 |
|---------|--------|------|------|
| `generate_key(identity_info) -> str` | str (静态) | 生成16字符密钥 | ValueError |
| `encode(plaintext, key) -> EncodeResult` | EncodeResult | DNA编码 | RuntimeError, TimeoutError |
| `decode(dna_sequence, key) -> DecodeResult` | DecodeResult | DNA解码 | RuntimeError, TimeoutError |
| `validate_dna_sequence(sequence) -> tuple[bool, str]` | tuple (静态) | 验证序列合法性 | - |

### 7.3 密钥生成算法

```python
@staticmethod
def generate_key(identity_info: dict) -> str:
    """
    基于患者身份信息生成加密密钥
    
    Args:
        identity_info: 至少包含 {"name": str, "birth_date": str}
    
    Returns:
        16字符密钥字符串
    
    算法：
        1. 拼接 name + birth_date
        2. 计算SHA-256哈希
        3. 取前16个十六进制字符作为密钥
    """
    import hashlib
    raw = f"{identity_info['name']}{identity_info['birth_date']}"
    hash_hex = hashlib.sha256(raw.encode()).hexdigest()
    return hash_hex[:16]
```

### 7.4 编码调用流程

```
plaintext (英文病症字符串)
    │
    ▼
调用 DNA_encoder.exe --input <plaintext> --key <key>
    │
    ▼
解析标准输出：
    ├── dna_sequence: "XCGYATCG..."
    ├── cg_content: 0.52
    ├── thermal_stability: 1.28
    ├── padded_zeros: 1
    └── sequence_length: 128
    │
    ▼
返回 EncodeResult(status=SUCCESS, ...)
```

### 7.5 解码调用流程

```
dna_sequence ("XCGYATCG...")
    │
    ▼
调用 DNA_decoder.exe --input <dna_sequence> --key <key>
    │
    ▼
解析标准输出：
    └── original_text: "PKU:negative;CH:negative;..."
    │
    ▼
返回 DecodeResult(status=SUCCESS, ...)
```

### 7.6 C++程序调用规范

| 参数 | 说明 |
|------|------|
| 编码器路径 | `DNA_code/DNA_code/DNA_encoder.exe`（或config配置） |
| 解码器路径 | `DNA_code/DNA_code/DNA_decoder.exe`（或config配置） |
| 调用方式 | subprocess.run()，捕获stdout/stderr |
| 超时时间 | 默认60秒（可配置） |
| 输入方式 | 命令行参数或标准输入 |
| 输出方式 | 标准输出（JSON格式或固定格式） |

### 7.7 数据结构

**EncodeResult**：
```python
@dataclass
class EncodeResult:
    status: CodecStatus          # 编码状态
    dna_sequence: str = ""       # DNA序列
    cg_content: float = 0.0      # GC含量 (0-1)
    thermal_stability: float = 0.0  # 热稳定性
    padded_zeros: int = 0        # 填充零位数
    sequence_length: int = 0     # 序列长度
    ciphertext: str = ""         # XOR加密中间结果
    error_message: str = ""      # 错误信息
```

**DecodeResult**：
```python
@dataclass
class DecodeResult:
    status: CodecStatus          # 解码状态
    original_text: str = ""      # 解码后文本
    error_message: str = ""      # 错误信息
```

**CodecStatus 枚举**：
```python
class CodecStatus(Enum):
    SUCCESS = "success"
    ENCODER_ERROR = "encoder_error"
    DECODER_ERROR = "decoder_error"
    TIMEOUT = "timeout"
    INVALID_INPUT = "invalid_input"
```

### 7.8 DNA序列校验

```python
@staticmethod
def validate_dna_sequence(sequence: str) -> tuple[bool, str]:
    """
    验证DNA序列合法性
    
    Returns:
        (是否合法, 原因说明)
    
    校验规则：
        1. 只允许 A/T/C/G/X/Y 字符
        2. 长度 > 0
        3. X/Y必须成对出现（可选）
    """
    valid_chars = set("ATCGXY")
    if not sequence:
        return False, "序列为空"
    if any(c not in valid_chars for c in sequence.upper()):
        return False, "包含非法字符"
    return True, "序列合法"
```

---

## 8. 智能纠错模块 (`error_corrector.py`)

### 8.1 类：ErrorCorrector

**职责**：编排完整的纠错流程，协调 data_store 和 ollama_api。

### 8.2 对外接口

| 方法签名 | 返回值 | 说明 |
|---------|--------|------|
| `correct(decoded_text: str, record_id: str = None) -> dict` | dict | 执行完整纠错流程 |
| `analyze_damage(dna_sequence: str, original: str) -> dict` | dict | 分析数据损坏程度 |
| `generate_report(correction_result: dict) -> str` | str | 生成纠错报告 |

### 8.3 纠错流程

```
解码后的文本 (decoded_text)
    │
    ▼
Step 1: 相似度检索
    │   调用 data_store.find_similar_records(decoded_text)
    │   获取参考文本列表
    │
    ▼
Step 2: 损坏程度分析
    │   计算 expected vs actual 的差异
    │   统计位翻转率、缺失率
    │
    ▼
Step 3: AI纠错推理
    │   调用 ollama_api.correct_errors(
    │       corrupted_text=decoded_text,
    │       reference_texts=参考列表
    │   )
    │
    ▼
Step 4: 结果整合
    │   合并纠错结果
    │   计算最终置信度
    │
    ▼
返回: {
    "original_text": "原始解码文本",
    "corrected_text": "纠错后文本",
    "confidence": 0.95,
    "error_rate": 0.02,
    "corrections": [...],
    "references_used": 3
}
```

### 8.4 损坏程度分析

```python
def analyze_damage(self, dna_sequence: str, original: str) -> dict:
    """
    分析DNA序列/文本的损坏程度
    
    Returns:
        {
            "total_length": 128,
            "error_count": 3,
            "error_rate": 0.023,
            "error_types": {
                "substitution": 2,   # 替换错误
                "insertion": 0,      # 插入错误
                "deletion": 1        # 删除错误
            },
            "damage_level": "low"   # low/medium/high/critical
        }
    """
    pass
```

---

## 9. 交付物清单

### 第一阶段交付

#### core/ 纯逻辑层

- [ ] `field_extractor.py` - 字段常量 + 验证方法
- [ ] `data_classifier.py` - DataClassifier 类
- [ ] `pinyin_utils.py` - 拼音转换工具
- [ ] `similarity.py` - SimilarityCalculator 类
- [ ] `tests/test_core/` - 全部单元测试

#### dna_codec.py

- [ ] DNACodec 类完整实现
- [ ] 密钥生成算法
- [ ] C++编码器封装
- [ ] C++解码器封装
- [ ] DNA序列校验
- [ ] 错误处理和超时
- [ ] tests/test_dna_codec.py

#### error_corrector.py

- [ ] ErrorCorrector 类完整实现
- [ ] 纠错流程编排
- [ ] 损坏程度分析
- [ ] 纠错报告生成

#### 配置与入口

- [ ] `config.py` - 全局配置
- [ ] `main.py` - 应用入口（极简启动器）
- [ ] 项目骨架（目录结构、__init__.py）

### 测试覆盖要求

| 模块 | 测试项 |
|------|--------|
| field_extractor | 字段分类正确性、常量完整性 |
| data_classifier | 正常数据、缺省字段、未知字段 |
| pinyin_utils | 常用汉字、特殊字符、空字符串 |
| similarity | 完全相同、完全不同、部分相似 |
| dna_codec | 正常编解码、空输入、非法序列、超时 |
| error_corrector | 有/无参考文本、不同损坏程度 |

---

## 10. 注意事项

1. **core/ 纯逻辑**：不引入任何外部依赖（除pypinyin可选），保证可移植性
2. **C++调用**：注意子进程生命周期管理，避免僵尸进程
3. **密钥安全**：generate_key 产生的密钥只在内存中使用，不落盘明文
4. **编码输入**：C++编码器只接受英文字符，中文必须先转拼音
5. **纠错是增强功能**：即使纠错失败，也应返回原始解码结果
6. **性能考虑**：相似度计算在大数据量时可能较慢，考虑加缓存
