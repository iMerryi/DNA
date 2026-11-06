# DNA 医疗档案系统 · UI 接口模块软件设计书

| 项目   | 内容                                    |
| ---- | ------------------------------------- |
| 模块名称 | 用户界面接口模块（`src/ui_interface.py`）       |
| 所属项目 | DNA 医疗冷归档存储系统                         |
| 文档版本 | v1.0                                  |
| 编写日期 | 2026-10-25                            |
| 适用范围 | 登录鉴权、界面导航、档案表单交互、AI 识别进度展示、冷归档测试字符串输出 |

---

## 1. 模块概述

### 1.1 功能定位

本模块是 DNA 医疗冷归档存储系统的**人机交互接口层（UI 层）**，基于 Flet 桌面 GUI 框架实现，承载系统全部用户交互：

1. **登录鉴权界面**：提供"账号登录（admin/123456）/ 游客模式"双入口，通过全局标记 `is_visitor` 区分权限；
2. **界面导航**：开场画面（Splash）→ 主界面（加密/解密双卡片）→ 档案填写表单的页面路由；
3. **档案采集表单**：三大板块（基本信息、个人基础信息、新生儿疾病筛查）共 30+ 字段的录入、校验与状态管理；
4. **AI 识别交互**：文档导入（拖拽/点选/粘贴路径三入径）、后台线程识别进度展示（悬浮进度卡片）、结果回填表单；
5. **冷归档数据分类展示**：将档案数据按"物理存储 / 反复存储 / 病症记录"三类分类，可视化确认并输出供下游 C++ 加密/纠错程序使用的测试字符串。

### 1.2 设计要点

- **单文件闭包式架构**：无自定义类，全部通过模块级函数 + 函数内闭包组织，`run_app_logic` 是核心作用域容器，内部约 20 个闭包函数共享 `form_data`（表单数据字典）、`field_controls`（控件注册表）、`picker_callback`（文件选择器单例回调）三个可变状态；
- **权限模型**：全局布尔 `is_visitor`，游客可浏览、可识别，但禁止保存档案（`save_all_data` 前置拦截）；
- **并发模型**：AI 识别运行于守护线程，UI 通过 `page.update()` 从工作线程刷新（依赖 Flet 跨线程行为）；取消采用 `threading.Event` 检查点机制；
- **降级策略**：疾病术语库缺失时界面显示红色警告但功能降级可用，不阻断主流程；
- **向后兼容**：混用 Flet 旧 API（`page.dialog = dlg`）与新 API（`page.open/close`），兼容旧版 Flet。

### 1.3 界面导航结构

```
main(page) ──► login_select_page（登录选择）
                 │
                 ▼
           run_app_logic
                 │
      ┌──────────┴──────────┐
   开场画面 Splash      （点击任意位置）
      └──────────► enter_main 主界面
                        │
        ┌───────────────┴───────────────┐
   加密卡片                          解密卡片
   ├─ 📝 在线填写 → show_online_form  ├─ 📄 读取加密文件（占位）
   ├─ 📄 输入文档 → open_doc_dialog   ├─ 📝 解密为文档（占位）
   └─ 🖼️ 输入图片 → show_upload_dialog└─ 🖼️ 解密为图片（占位）

show_online_form 内：
   💾 保存数据  📄 从文档导入（二次识别）  ✅ 确认并测试  ↩️ 返回主界面
```

> 注：解密卡片三个入口当前仅弹窗占位，未接入解密逻辑，属预留接口。

---

## 2. 接口说明

### 2.1 对外接口（程序入口）

| 接口   | 签名                                               | 说明                |
| ---- | ------------------------------------------------ | ----------------- |
| 应用入口 | `main(page: ft.Page) → None`                     | Flet 框架回调，渲染登录选择页 |
| 独立运行 | `if __name__ == "__main__": ft.app(target=main)` | 启动桌面窗口            |
| 被复用  | 其他模块可直接 `from ui_interface import main` 挂载此 UI   |                   |

### 2.2 模块级接口

| 编号   | 接口                                                                | 输入            | 输出                            | 说明                    |
| ---- | ----------------------------------------------------------------- | ------------- | ----------------------------- | --------------------- |
| I-01 | `search_disease_terms(search_text, limit=5)`                      | 搜索文本，条数上限     | `list[tuple(id, 中文, 英文, 类别)]` | 疾病术语模糊检索              |
| I-02 | `get_disease_by_chinese(chinese_name)`                            | 中文病名          | 英文名（无匹配返回原文）                  | 中文→英文精确映射             |
| I-03 | `to_pinyin_string(text)`                                          | 中文文本          | `_` 连接拼音串                     | 反复存储编码                |
| I-04 | `extract_text_from_file(path)`                                    | 文件路径          | 纯文本                           | txt/docx/pdf 分派解析     |
| I-05 | `ask_ollama(text, on_progress=None, model="qwen2.5:7b-instruct")` | 文档文本、进度回调、模型名 | `dict`                        | 流式调用本地 Ollama 提取结构化字段 |
| I-06 | `login_select_page(page)`                                         | ft.Page       | None                          | 登录页渲染与鉴权              |
| I-07 | `run_app_logic(page)`                                             | ft.Page       | None                          | 主业务全部界面逻辑             |

### 2.3 外部依赖接口

| 外部系统         | 接口                                                                                    | 协议/方式                                 |
| ------------ | ------------------------------------------------------------------------------------- | ------------------------------------- |
| Ollama 本地大模型 | `POST http://localhost:11434/api/chat`                                                | HTTP JSON，`stream: true`，timeout=300s |
| 疾病术语库        | SQLite `medical_terms.db`，表 `disease_terms(id, chinese_name, english_name, category)` | sqlite3 只读                            |
| 档案文档         | 本地 .txt / .docx / .pdf                                                                | 文件系统读取                                |
| 档案输出         | `儿童健康档案_{姓名}_{YYYYmmdd_HHMMSS}.json`                                                  | UTF-8 文件写入                            |
| 终端 stdout    | `print` 输出两类测试字符串                                                                     | 标准输出（供 C++ 程序人工转交）                    |

### 2.4 事件/回调接口

| 回调                                | 签名                       | 触发时机                                       |
| --------------------------------- | ------------------------ | ------------------------------------------ |
| `on_progress(n)`                  | n：累计生成字符数                | Ollama 流式输出每次收到新内容                         |
| `on_success(data)`                | data：AI 字段 dict          | 表单内二次导入识别成功                                |
| `on_picker_result(e)`             | ft.FilePickerResultEvent | 文件选择器返回（`picker_callback["fn"]` 单例分发，用后即清） |
| `on_change / on_blur / on_accept` | ft 事件对象                  | 输入框变更/失焦、拖拽区接收                             |

---

## 3. 类/函数说明

> 无自定义类；UI 状态由 `run_app_logic` 及 `show_online_form` 作用域内的闭包共享。

### 3.1 数据层函数

#### `search_disease_terms(search_text: str, limit: int = 5) -> list[tuple]`

- 中文/英文名 `LIKE %text%` 模糊查询，按 `category, chinese_name` 排序，返回至多 limit 条。
- **降级**：库文件不存在返回 `[]`；每次调用独立建连，无共享连接，天然线程安全。

#### `get_disease_by_chinese(chinese_name: str) -> str`

- 精确匹配中文病名英文标准名；库缺失或无匹配返回原文，保证字段值不丢失。

### 3.2 工具函数

#### `to_pinyin_string(text: str) -> str`

- pypinyin 普通注音逐字转写，`_` 拼接（如 `体温_37.5` → `ti_wen_37.5`）；空串入参返回 `""`。

### 3.3 文档解析与 AI 函数

#### `extract_text_from_file(path: str) -> str`

| 扩展名     | 解析器               | 规则                             |
| ------- | ----------------- | ------------------------------ |
| `.txt`  | 内置 open           | UTF-8，`errors="ignore"`        |
| `.docx` | python-docx（延迟导入） | 非空段落 `\n` 连接                   |
| `.pdf`  | pdfplumber（延迟导入）  | 逐页 `extract_text()`，空页 `""` 兜底 |
| 其他      | —                 | 抛 `ValueError`                 |

#### `ask_ollama(text: str, on_progress=None, model: str) -> dict`

- **Prompt 约束**（影响下游 DNA 编码正确性的关键）：System 要求输出严格 JSON、无 markdown 围栏；明确写"无/正常/未检出"的字段**原样填入**，仅完全未提及的字段留空字符串；
- 参数：`format="json"`、`temperature=0.1`、`stream=True`；
- 进度：每收到内容以累计字符数回调 `on_progress`；
- 清洗：取首个 `{` 至末个 `}` 子串 `json.loads`；无花括号抛 `ValueError("AI 输出不是 JSON")`。

### 3.4 字段常量（数据字典）

| 常量                             | 用途          | 内容                                                   |
| ------------------------------ | ----------- | ---------------------------------------------------- |
| `PHYSICAL_FIELDS`（23 项）        | 物理存储类       | 档案编号、姓名、性别、出生日期、证件号码、地址、血型、父母信息、出生孕周/体重/身长、Apgar 评分等 |
| `DISEASE_FIELDS`（7 项）          | 病症记录类（需标准化） | 苯丙酮尿症、先天性甲减、听力筛查、过敏史、先天异常、既往住院史、家族遗传病史               |
| `REPEATED_FIELDS`（3 项）         | 反复存储类       | 随访日期、当前体重、体温                                         |
| `DB_PATH = "medical_terms.db"` | 术语库路径       | 相对路径，随工作目录变化                                         |
| `is_visitor = False`           | 全局游客标记      | 登录成功置 `False`，游客置 `True`                             |

### 3.5 UI 层函数

#### 模块级：`login_select_page(page)`

渲染登录选择页；内部闭包：

- `normal_login_click`：弹出账号/密码对话框；
- `verify_login(dlg, page, username, password)`：硬编码校验 `admin/123456`，成功置 `is_visitor=False` 进入业务，失败红色 SnackBar；
- `visitor_click`：置 `is_visitor=True` 直接进入业务。

#### `run_app_logic(page)` 作用域内的闭包

| 函数                                                  | 职责                                                                          |
| --------------------------------------------------- | --------------------------------------------------------------------------- |
| `on_picker_result(e)`                               | 文件选择器回调单例分发，取出即清空                                                           |
| `show_dialog(page, title, button_texts)`            | 通用多按钮弹窗                                                                     |
| `close_dlg(page, dlg, action)`                      | 关闭弹窗并按按钮文本路由到填写/文档/图片入口                                                     |
| `show_upload_dialog(page)`                          | 图片上传对话框（jpg/jpeg/png 选择 + 预览；OCR 未接入，占位）                                    |
| `open_doc_dialog(page, on_success=None)`            | 文档导入对话框：拖拽 DragTarget / 点选 FilePicker / 粘贴路径三入径，统一经 `handle_path` 剥引号、校验存在性 |
| `start_ai_recognition(page, path, on_success=None)` | AI 识别总控：守护线程 + 悬浮进度卡片 + 取消机制（详见 §4.2）                                       |
| `set_progress(pct, status)`                         | 线程安全地刷新进度条（取消后短路）                                                           |

#### `show_online_form(page, prefill=None)` 作用域内的闭包

| 函数                                     | 职责                                                                                    |
| -------------------------------------- | ------------------------------------------------------------------------------------- |
| `save_field(name, value)`              | 写入 `form_data[name]`                                                                  |
| `register_field(name, ctrl)`           | 注册控件到 `field_controls`（AI 回填的依据）                                                      |
| `create_searchable_disease_field(...)` | 病症搜索组件工厂：输入即触发 `search_disease_terms` 渲染候选项；失焦时按 §4.3 规则标准化归档；未收录输入记入 `manual_inputs` |
| `fill_form_from_data(data)`            | AI 数据回填：TextField 直接赋值；RadioGroup 仅命中既有选项才赋值；病症字段补 `_中文/_英文/_来源` 三键                   |
| `import_doc_in_form()`                 | 表单内二次识别，成功回调 `on_success` → 回填 + 绿色提示                                                 |
| `save_all_data(e)`                     | 游客拦截 → 姓名必填校验 → 写 JSON 文件                                                             |
| `confirm_and_test(e)`                  | 三类数据分类汇总 + 生成冷归档测试字符串（详见 §4.4）                                                        |

---

## 4. 算法流程

### 4.1 登录鉴权流程

```
启动 → login_select_page
  ├─ 账号登录 → 弹窗输入 → verify_login
  │     ├─ "admin"/"123456" → is_visitor=False → run_app_logic
  │     └─ 否则 → 红色 SnackBar "账号或密码错误"
  └─ 游客模式 → is_visitor=True → run_app_logic
```

> ⚠️ 当前为明文硬编码弱凭据，仅适用于演示环境，正式版需接入数据库鉴权 + 密码哈希。

### 4.2 AI 识别进度算法（`start_ai_recognition` worker 线程）

进度映射（分段）：

| 阶段      | 进度区间     | 机制                                           |
| ------- | -------- | -------------------------------------------- |
| 文档读取    | 0 → 5%   | `set_progress(5)`                            |
| 连接本地 AI | 5 → 12%  | 固定点                                          |
| AI 思考等待 | 12 → 20% | 缓升线程每 0.8s +1%（`stop_creep` 可终止）             |
| AI 流式生成 | 20 → 90% | `pct = min(90, 20 + int(已生成字符数 / 900 * 70))` |
| 完成整理    | 100%     | 固定点                                          |

```
worker 线程:
  extract_text_from_file → 文本为空抛 ValueError
  启动缓升线程（12%→20%）
  ask_ollama(text, on_tokens)  ← 流式回调映射进度
  finally: stop_creep.set(); creep_thread.join(1)  强制终止缓升线程
  成功 → result=("ok", data)；异常 → result=("error", msg)
finally:
  隐藏并移除进度卡片
  已取消 → 蓝色 SnackBar
  ok    → on_success(data) 或 show_online_form(prefill=data)
  error → 红色 SnackBar
```

取消机制：`cancel_event = threading.Event` 在各阶段检查点短路；`set_progress` 与 `on_tokens` 均先查事件再刷新 UI。

### 4.3 病症标准化算法（`create_searchable_disease_field` / `on_blur`）

每个病症字段维护三元组溯源结构：

```
{字段}_中文 : 用户确认的中文值
{字段}_英文 : 数据库英文标准名（查无则等于中文）
{字段}_来源 : "数据库标准词条" | "手动输入"
```

判定优先级：

1. **下拉点选** → 词条中文/英文，来源=数据库标准词条；
2. **失焦精确查询** → 命中=标准词条；未命中=手动输入，且 `manual_inputs[字段]` 记录 `{中文内容, 录入时间, 字段标签, 备注:"需后续标准化处理"}`；
3. **AI 回填** → `fill_form_from_data` 对空缺的病症字段做同样兜底映射。

设计意图：进入 DNA 编码环节的病症文本优先为受控英文词表，未受控输入显式标注待标准化，满足医疗数据可溯源要求。

### 4.4 冷归档测试字符串生成算法（`confirm_and_test`）

| 类别      | 取数                      | 编码方式                                                                   | 输出位置               |
| ------- | ----------------------- | ---------------------------------------------------------------------- | ------------------ |
| 1. 物理存储 | PHYSICAL_FIELDS 非空值     | JSON 原文                                                                | 确认弹窗 Card          |
| 2. 反复存储 | REPEATED_FIELDS 非空值     | `to_pinyin_string(f"{字段}_{值}")` → **重复 3 遍入池 → random.shuffle → 空格连接** | 终端 print + 弹窗 Card |
| 3. 病症记录 | 各 DISEASE_FIELD 的 `_英文` | 按 DISEASE_FIELDS 定义顺序 `"\|"` 连接                                        | 终端 print + 弹窗 Card |

**冗余打乱算法用途**：DNA 存储中同一随访信息写入多条寡核苷酸链以提高容错率；重复 3 遍 + 随机洗牌使冗余片段分散，为下游 C++ 加密/纠错（如 RS 码）提供分布更均匀的输入。

```
pool = []
for 字段 in REPEATED_FIELDS:
    s = to_pinyin_string(f"{字段}_{值}")
    pool += [s, s, s]
random.shuffle(pool)
repeated_string = " ".join(pool)
```

### 4.5 保存流程（`save_all_data`）

```
游客？ → 橙色提示，return
姓名为空？ → 橙色提示，return
写 儿童健康档案_{姓名}_{YYYYmmdd_HHMMSS}.json（UTF-8, indent=2）
  成功 → 绿色 SnackBar 含文件名
  异常 → 红色 SnackBar 含错误信息
```

---

## 5. 依赖

### 5.1 第三方库

| 库             | 用途                                                  | 导入时机        |
| ------------- | --------------------------------------------------- | ----------- |
| `flet`        | 桌面 GUI（需支持 `page.open/close`、FilePicker、DragTarget） | 顶层          |
| `pypinyin`    | 汉字转拼音                                               | 顶层          |
| `python-docx` | DOCX 提取                                             | **函数内延迟导入** |
| `pdfplumber`  | PDF 提取                                              | **函数内延迟导入** |

### 5.2 标准库

`sqlite3`、`json`、`os`、`random`、`threading`、`time`、`urllib.request`、`datetime`

### 5.3 外部服务与数据

| 依赖                     | 要求                                                         | 缺失影响                          |
| ---------------------- | ---------------------------------------------------------- | ----------------------------- |
| Ollama                 | `localhost:11434`，已装 `qwen2.5:7b-instruct`                 | AI 识别失败（SnackBar 报错），手动填写不受影响 |
| 术语库 `medical_terms.db` | 表 `disease_terms`                                          | 搜索为空/翻译原样返回；表单顶部红色初始化警告；功能降级  |
| 封面图 `cover.jpg`        | **硬编码** `C:/Users/HONOR/Desktop/DNA_new_version/cover.jpg` | 换机部署开场画面缺图                    |

> 建议固化 `requirements.txt`：`flet`、`pypinyin`、`python-docx`、`pdfplumber`。

---

## 6. 异常处理

### 6.1 策略

**UI 层兜底 + SnackBar 提示**：worker 线程内统一 `try/except Exception`，任何单点失败转化为用户可见提示，不导致应用崩溃。

### 6.2 异常场景清单


| 场景 | 触发点 | 处理方式 | 用户感知 |
|------|--------|----------|----------|
| 术语库不存在 | `search_disease_terms` / `get_disease_by_chinese` | 静默降级：返回空/原文 | 表单顶部红色初始化警告 |
| 不支持的文件类型 | `extract_text_from_file` | 抛 `ValueError` | SnackBar"仅支持 txt/docx/pdf" |
| 文档无可提取文本 | worker 线程 | 抛 `ValueError` | SnackBar"识别失败" |
| Ollama 未启动/超时 | `urlopen`（timeout=300s） | worker 捕获 `URLError` | SnackBar"识别失败: …" |
| AI 输出非 JSON | 花括号定位失败 | 抛 `ValueError` | SnackBar"识别失败" |
| 文件不存在 | `handle_path` 前置校验 | 不发请求 | 状态文本"❌ 文件不存在" |
| 保存失败（磁盘/权限/非法文件名） | `save_all_data` | `try/except` | SnackBar"❌ 保存失败" |
| 用户中途取消 | 取消按钮 → `cancel_event` | 检查点短路 + `finally` 清理卡片 | 蓝色 SnackBar"🛑 用户已取消识别" |
| 登录凭据错误 | `verify_login` | 拒绝进入 | 红色 SnackBar"账号或密码错误" |
| 游客尝试保存 | `save_all_data` 前置拦截 | 直接 return | 橙色 SnackBar"游客模式禁止保存" |
| AI 回填字段非预期值 | `fill_form_from_data` RadioGroup 分支 | 值不在选项中则跳过赋值 | 字段留空，无提示（可改进） |

### 6.3 已知薄弱点（建议加固）

1. `save_all_data` 文件名直接拼接用户输入的姓名，未过滤 `/\:*?"<>|` 等非法字符；
2. 未限制导入文件大小，超大 PDF 可能拖垮 AI 识别；
3. worker 线程直接调用 `page.update()` 依赖 Flet 跨线程行为，存在竞态风险；
4. SQLite 操作未捕获 `sqlite3.Error`（库损坏/表结构不符时直接抛出）；
5. 混用新旧 Flet Dialog API，升级 Flet 后 `page.dialog = dlg` 可能失效。

---

## 7. 测试要点

### 7.1 单元测试

| 用例组 | 对象 | 关键用例 |
|--------|------|----------|
| UT-01 术语检索 | `search_disease_terms` | 中文/英文/部分匹配命中；limit 截断；库缺失返回 `[]`；`%`/`_` 通配符注入行为 |
| UT-02 中文翻译 | `get_disease_by_chinese` | 精确命中；无匹配返回原文；库缺失返回原文 |
| UT-03 拼音 | `to_pinyin_string` | 纯中文；中英数字混合；空串；多音字一致性 |
| UT-04 文档提取 | `extract_text_from_file` | 三格式正常样例；空 txt；损坏 pdf；.jpg/.doc 抛 `ValueError`；路径含空格 |
| UT-05 JSON 清洗 | `ask_ollama` 解析（mock HTTP） | 纯 JSON；带 markdown 围栏；无花括号抛异常；前后夹杂说明文字截取正确 |

### 7.2 集成测试（需本地 Ollama）

| 用例 | 步骤 | 预期 |
|------|------|------|
| IT-01 全链路识别 | 导入含"青霉素过敏、体温 37.5℃"的 docx | 表单自动回填；病症字段生成三元组；进度卡片 0→100% 后消失 |
| IT-02 "无"字段保留 | 文档明确写"既往住院史：无" | 字段值="无"而非空串（核心 Prompt 约束） |
| IT-03 取消识别 | 识别中点取消 | 卡片消失，蓝色提示，无残留 UI 更新 |
| IT-04 表单内二次导入 | 填写中途"从文档导入" | 仅覆盖非空字段，不破坏已填内容 |
| IT-05 RadioGroup 回填 | AI 返回性别="未知" | 不赋值、不报错 |
| IT-06 拖拽导入 | 拖拽 pdf 至 DragTarget | 剥引号后正常进入识别 |

### 7.3 业务规则测试

| 用例 | 验证点 |
|------|--------|
| BT-01 游客权限 | 游客保存 → 橙色提示，且工作目录**不产生** JSON 文件 |
| BT-02 姓名必填 | 空姓名保存 → 拦截 |
| BT-03 保存命名 | 文件名 `儿童健康档案_{姓名}_{YYYYmmdd_HHMMSS}.json`，UTF-8 中文可读、含三元组键 |
| BT-04 冗余字符串 | 3 个随访字段 → 池内 9 片段，每片段恰出现 3 次；多次生成顺序不同（shuffle 生效） |
| BT-05 病症串顺序 | 英文串按 DISEASE_FIELDS 定义顺序 `|` 连接，与 UI 填写顺序无关 |
| BT-06 手动输入溯源 | 手输未收录病症 → `manual_inputs` 含录入时间与"需后续标准化处理"备注 |

### 7.4 UI/异常路径测试

- 库文件缺失启动 → 红色警告可见，其余功能可用（降级验证）；
- Ollama 停止时识别 → 红色 SnackBar，应用不崩溃；
- 粘贴带引号路径 `"C:/x/y.txt"` → 正常识别；
- 拖拽不存在路径 → 状态文本报错；
- 快速连续点击"确认并测试" → 无弹窗叠加错乱；
- 开场画面点击任意位置 → 正确进入主界面；表单"返回"按钮 → 回到主界面。

### 7.5 兼容性/部署测试

- 从不同工作目录启动，验证 `DB_PATH` 相对路径行为一致或降级正常；
- 非 HONOR 机器上 `cover.jpg` 硬编码路径的开场画面表现；
- Flet 版本回归：新旧 Dialog API 混用是否告警/失效；
- Windows 终端输出中文/emoji（GBK 控制台）是否乱码——影响测试字符串的可读转交。

---

## 8. 附：改进建议（供下一版设计参考）

1. **鉴权安全化**：凭据入库 + 哈希校验，支持多用户角色；
2. **路径/资源配置化**：`DB_PATH`、`cover.jpg` 移入配置文件；
3. **拆分模块**：拆为 `db.py / nlp.py / ui_login.py / ui_form.py`，用会话对象替代全局 `is_visitor`；
4. **UI 线程安全**：工作线程刷新改用 `page.run_thread`/`page.call_from_thread` 等 Flet 官方机制；
5. **文件名清洗**：保存前过滤非法字符并截断长度；
6. **图片 OCR 接入**：补齐"输入图片"入口（当前为占位）；
7. **测试字符串落地**：`confirm_and_test` 结果目前仅 print 终端，建议写入临时文件或剪贴板，规避 Windows GBK 控制台编码问题；
8. **统一 Dialog API**：全部迁移至 `page.open()/page.close()`，去掉旧式 `page.dialog` 赋值。

---

*文档结束*
