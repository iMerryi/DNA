# AI交互模块开发文档

## 模块概述

| 属性 | 内容 |
|------|------|
| **模块名称** | ollama_api.py |
| **模块全称** | Ollama Application Programming Interface |
| **负责角色** | AI工程师（同学C） |
| **技术栈** | Ollama + Qwen2.5 + urllib |
| **依赖模块** | 无（仅依赖Ollama外部服务） |
| **代码位置** | `modules/ollama_api.py` |
| **外部依赖** | Ollama 本地服务 (http://localhost:11434) |

---

## 1. 模块职责

| 编号 | 职责描述 | 优先级 |
|------|---------|--------|
| AI-01 | 连接本地Ollama服务 | P0 |
| AI-02 | 调用指定模型执行文档字段提取 | P0 |
| AI-03 | 流式返回AI生成内容，支持进度回调 | P0 |
| AI-04 | 封装统一接口，方便后续替换模型 | P0 |
| AI-05 | 支持智能纠错推理（解码后） | P1 |
| AI-06 | 支持OCR图片文字识别（预留） | P2 |

---

## 2. Ollama 服务配置

### 2.1 连接参数

| 参数 | 默认值 | 来源 |
|------|--------|------|
| base_url | `http://localhost:11434` | config.py |
| model_name | `qwen2.5:7b-instruct` | config.py |
| timeout | 300秒 | 构造函数参数 |
| max_retries | 2次 | 构造函数参数 |

### 2.2 支持的模型

| ModelType | 模型名称 | 用途 |
|-----------|---------|------|
| FIELD_EXTRACTOR | qwen2.5:7b-instruct | 文档字段提取（主力模型） |
| ERROR_CORRECTOR | qwen2.5:14b-instruct | 智能纠错（更大模型） |
| GENERAL_CHAT | qwen2.5:7b-chat | 通用对话（预留） |
| CUSTOM | 自定义 | 用户指定 |

---

## 3. 对外接口（需实现的公共方法）

> 详细签名见 `api_contract.md` 第5节。

### 3.1 方法总览

| 方法 | 用途 | 返回类型 | 是否异步 |
|------|------|---------|---------|
| `test_connection()` | 测试服务可用性 | tuple[bool, str] | 同步 |
| `extract_fields()` | 文档字段提取 | AIResponse | 同步（内部流式） |
| `correct_errors()` | AI辅助纠错 | AIResponse | 同步（内部流式） |
| `chat()` | 通用对话 | AIResponse | 同步 |

---

## 4. 核心功能详细设计

### 4.1 服务连接测试

**方法**：`test_connection() -> tuple[bool, str]`

**实现逻辑**：
1. 向 `/api/tags` 发送GET请求
2. 检查HTTP状态码和响应内容
3. 验证配置的模型是否已安装
4. 返回 (是否可用, 状态消息)

**返回示例**：
```python
(True, "Ollama服务正常，模型 qwen2.5:7b-instruct 已就绪")
(False, "无法连接Ollama服务，请确认服务已启动")
```

---

### 4.2 文档字段提取 ⭐ 核心功能

**方法**：`extract_fields(document_text, on_progress, fields_hint) -> AIResponse`

#### 4.2.1 输入参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| document_text | str | 是 | 原始文档文本（来自文件解析或手动输入） |
| on_progress | Callable | 否 | 进度回调 `fn(percent: int, message: str)` |
| fields_hint | list | 否 | 字段提示列表（可选，帮助AI理解预期字段） |

#### 4.2.2 输出结构（AIResponse.data）

```python
{
    "物理存储": {
        "档案编号": "ARCHIVE_20261013_001",
        "姓名": "张三",
        "性别": "男",
        "出生日期": "2026-01-15",
        # ... 其他20个物理字段
    },
    "反复存储": [
        {
            "随访日期": "2026-10-01",
            "当前体重": "4.5kg",
            "体温": "36.8℃"
        }
        ],
    "病症记录": {
        "苯丙酮尿症": "阴性",
        "先天性甲状腺功能减低症": "阴性",
        "听力筛查": "通过",
        "过敏史": "无",
        "先天异常": "无",
        "既往住院史": "无",
        "家族遗传病史": "无"
    }
}
```

#### 4.2.3 System Prompt 设计要点

Prompt 必须包含以下指令：

1. **角色定义**：你是一个专业的医疗档案信息提取助手
2. **输出格式**：严格的JSON格式，包含三个顶层key
3. **字段映射**：明确列出33个目标字段名
4. **取值约束**：
   - 性别：只能是"男"或"女"
   - 血型：A/B/AB/O
   - 病症结果：阴性/阳性/疑似/通过/未通过/自由文本
5. **缺失处理**：字段值缺失时填空字符串，不要编造
6. **置信度**：对不确定的字段标注置信度（可选）

#### 4.2.4 进度回调时机

| 百分比 | 阶段 | message |
|--------|------|---------|
| 0% | 开始 | "正在连接AI服务..." |
| 10% | 发送请求 | "发送文档给AI分析..." |
| 30% | 流式接收 | "AI正在识别字段..." |
| 60% | 流式接收 | "AI正在整理数据..." |
| 90% | 解析响应 | "正在解析AI返回结果..." |
| 100% | 完成 | "字段提取完成" |

---

### 4.3 智能纠错 ⭐ 重要功能

**方法**：`correct_errors(corrupted_text, reference_texts, on_progress) -> AIResponse`

#### 4.3.1 使用场景

DNA解码后，可能因序列损坏导致文本错误。此方法结合：
- **参考文本**：从数据库查到的相似档案记录
- **AI推理**：基于上下文推断正确的字符

#### 4.3.2 输入参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| corrupted_text | str | 是 | 可能包含错误的解码文本 |
| reference_texts | list[str] | 是 | 参考文本列表（来自相似度查询） |
| on_progress | Callable | 否 | 进度回调 |

#### 4.3.3 输出结构（AIResponse.data）

```python
{
    "corrected_text": "纠错后的完整文本",
    "corrections": [
        {
            "position": 25,
            "original": "A",
            "corrected": "T",
            "reason": "根据上下文和参考记录，此处应为T"
        }
    ],
    "confidence": 0.95
}
```

#### 4.3.4 System Prompt 设计要点

1. **角色定义**：你是DNA解码文本纠错专家
2. **输入**：损坏文本 + 多个参考文本
3. **任务**：识别并修复错误字符
4. **输出**：纠错后文本 + 修正详情 + 置信度
5. **原则**：
   - 优先参考已知正确数据
   - 不确定时保留原文并标注
   - 给出每处修改的理由

---

### 4.4 通用对话（预留）

**方法**：`chat(prompt, system_prompt, temperature) -> AIResponse`

用于未来扩展，如：
- 用户咨询操作指南
- 自然语言查询档案
- 其他AI交互场景

---

## 5. AIResponse 数据类

```python
@dataclass
class AIResponse:
    success: bool                  # 是否成功
    data: Optional[Any] = None    # 响应数据（结构视方法而异）
    error_message: str = ""       # 错误信息
    tokens_used: int = 0          # 消耗的token数
    duration_seconds: float = 0.0 # 耗时（秒）
```

**各方法的 data 结构差异**：

| 方法 | data 类型 | 结构 |
|------|----------|------|
| extract_fields | dict | `{物理存储: {}, 反复存储: [], 病症记录: {}}` |
| correct_errors | dict | `{corrected_text, corrections[], confidence}` |
| chat | str | 纯文本回复 |

---

## 6. 错误处理

### 6.1 异常类型

| 异常 | 触发条件 | 处理方式 |
|------|---------|---------|
| ConnectionError | Ollama服务未启动 | 返回 AIResponse(success=False) + 友好提示 |
| TimeoutError | 请求超时（>300s） | 返回超时错误，建议用户检查文档长度 |
| ValueError | 模型不存在 | 提示用户安装指定模型 |
| urllib.error.URLError | 网络问题 | 返回网络错误提示 |

### 6.2 重试机制

- 默认最大重试次数：2次
- 重试间隔：指数退避（1s, 2s, 4s...）
- 仅对网络超时和连接错误重试
- 参数错误、模型不存在不重试

---

## 7. Ollama API 调用细节

### 7.1 字段提取API调用

```python
# HTTP POST http://localhost:11434/api/generate
# 使用 stream=True 流式接收

request_body = {
    "model": "qwen2.5:7b-instruct",
    "prompt": "{user_prompt}",
    "system": "{system_prompt}",
    "stream": True,
    "options": {
        "temperature": 0.3,      # 低温度，提高确定性
        "num_predict": 4096      # 最大输出token数
    }
}
```

### 7.2 流式处理伪代码

```python
def _stream_request(self, request_body, on_progress):
    url = f"{self.base_url}/api/generate"
    req = urllib.request.Request(url, data=json.dumps(request_body).encode(), method='POST')
    
    with urllib.request.urlopen(req, timeout=self.timeout) as response:
        full_response = ""
        for line in response:
            chunk = json.loads(line)
            full_response += chunk.get("response", "")
            
            # 计算进度（估算）
            if on_progress and chunk.get("done"):
                on_progress(100, "完成")
    
    return json.loads(full_response)
```

---

## 8. 交付物清单

### 第一阶段交付

- [ ] `OllamaClient` 类完整实现
- [ ] `test_connection()` 服务检测
- [ ] `extract_fields()` 字段提取（含完整Prompt工程）
- [ ] `correct_errors()` 智能纠错（含完整Prompt工程）
- [ ] `chat()` 通用对话（基础实现）
- [ ] 流式调用与进度回调
- [ ] 错误处理与重试机制
- [ ] 单元测试 `tests/test_ollama_api.py`

### Prompt工程交付

- [ ] 字段提取 System Prompt（优化版）
- [ ] 智能纠错 System Prompt（优化版）
- [ ] Few-shot 示例（可选，提升准确率）

### 测试覆盖要求

| 测试项 | 要求 |
|--------|------|
| 连接测试 | 服务正常/异常两种场景 |
| 字段提取 | 标准文档、模糊文档、空文档、超长文档 |
| 纠错功能 | 有/无参考文本、不同程度损坏 |
| 进度回调 | 验证回调次数和百分比值 |
| 超时处理 | 模拟超时场景 |
| 重试机制 | 验证重试次数和间隔 |

---

## 9. 注意事项

1. **独立模块**：不依赖其他业务模块，可独立开发和测试
2. **本地部署**：Ollama必须在本地运行，确保隐私
3. **Prompt是核心**：字段提取质量高度依赖Prompt设计，需要反复调优
4. **流式体验**：即使内部是同步调用，也要通过回调让UI感知进度
5. **模型兼容**：接口设计要方便未来替换为其他模型（如本地部署的其他LLM）
6. **Token限制**：注意文档长度，超长文档需截断或分片处理
7. **温度设置**：字段提取用低temperature(0.3)，创意任务可用高temperature
