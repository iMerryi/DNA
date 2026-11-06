# 用户账号与使用历史模块设计书

> 模块：账号体系 + 操作留痕
> 版本：v1.0（设计稿，待评审）
> 依赖：`database_v2_design.md` v2.1（数据模型主体）
> 定位：本文件只讲**要做什么、放在哪一层、接口长什么样**，不含 DDL 与实现代码
> 状态：**待确认**（§9 有两个待拍板项）

---

## 1. 要解决的问题

当前注册功能是个空壳：

| 现状 | 后果 |
|---|---|
| 账号存在 `data/users.json`，由 `ui_interface.py` 自己读写 | 账号数据在数据库之外，与档案彻底脱节；换机器/清库即丢 |
| 密码明文存储 | 任何人打开 json 就能看到全部密码 |
| 档案没有归属人 | 谁都能看到所有人的档案，无法区分"我的档案" |
| 没有任何操作记录 | 查不出"谁在什么时候保存/编码/删除了哪条档案" |

**目标：账号进库、档案有主、关键操作可追溯。**

---

## 2. 职责边界（谁写哪一段）

| 内容 | 归属层 | 落点 | 责任模块 |
|---|---|---|---|
| 表结构、密码处理、登录校验、日志写入与查询 | 数据层 | `data_store.py` | 数据库同学 |
| 登录/注册弹窗、提示语、持有"当前登录用户" | 界面层 | `ui_interface.py` | 前端同学 |
| 把"当前用户"传入保存/查询链路 | 集成层 | `main.py` | 集成负责人（PM） |

**硬约束（三条）**

1. `ui_interface.py` **不得**出现 `sqlite3`、不得读写 `users.json`；账号相关只允许调用 `DataStore` 方法。
2. 密码**不得**明文落盘，任何位置（json、日志、界面提示）都不出现明文。
3. 游客不建账号、不写库；游客能做什么由 §5 权限表定义。

---

## 3. 数据模型（新增部分）

沿用 `database_v2_design.md` 的表结构，本模块新增 2 张表、1 个字段：

### 3.1 表 `users`（账号）

| 字段 | 说明 |
|---|---|
| id | 自增主键 |
| username | 登录名，**唯一**，大小写不敏感（存小写规范值） |
| password_hash | 密码哈希串，格式 `sha256$<salt>$<hex>` |
| display_name | 显示名，可为空，缺省等于 username |
| role | 角色：`user`（普通）/ `admin`（管理员） |
| is_active | 是否启用，0 = 停用（沿用账号但拒绝登录） |
| created_at | 注册时间 |
| last_login_at | 最近登录时间，可为空 |

> 不存"游客"账号。游客是运行态，不落库。

### 3.2 表 `user_activity_log`（使用历史）

| 字段 | 说明 |
|---|---|
| id | 自增主键 |
| user_id | 关联 `users.id`；游客操作可为 NULL |
| action | 动作枚举，见 §4 |
| target_record_id | 关联的档案号，可空 |
| detail | 补充说明（如错误原因、导出格式），可空 |
| created_at | 发生时间 |

**动作枚举（action）**

`register` / `login` / `logout` / `create_record` / `update_record` / `delete_record` / `encode_dna` / `decode_dna` / `export_report` / `ai_extract`

> 枚举固定，不在业务代码里临时造新值；新增动作需改本表。

### 3.3 `archive_records` 新增字段

| 字段 | 说明 |
|---|---|
| owner_id | 档案归属人，关联 `users.id` |

- 新建档案时写入当前登录用户。
- **历史数据与游客创建的档案为 NULL**，表示"无主/历史数据"，仅 `admin` 可完整查看。
- 不做外键级联删除；用户停用后其档案仍保留。

### 3.4 结构版本

新增以上内容后，库结构版本从 v2.1 升到 **v2.2**，记录在 `schema_meta`。`init_database()` 按版本号判断是否需要建表/加列，不需要重建库。

---

## 4. 接口契约（`DataStore` 新增方法）

> 所有方法由 `data_store.py` 提供，界面层只调用、不实现。

### 4.1 账号

| 方法 | 输入 | 输出 | 说明 |
|---|---|---|---|
| `create_user` | username, password, role="user", display_name=None | `(success: bool, message: str)` | 重名、空值、长度不合规返回 `False` 并给中文原因 |
| `verify_user` | username, password | `dict \| None` | 成功返回 `{id, username, display_name, role}`；失败返回 `None`，不区分"用户不存在/密码错误" |
| `get_user` | user_id 或 username | `dict \| None` | 管理端查询用 |
| `set_user_active` | user_id, active: bool | `bool` | 停用/启用账号 |
| `touch_last_login` | user_id | `None` | 登录成功时更新 `last_login_at` |

**密码规则**

- 哈希算法：`sha256(salt + password)`，salt 为随机 16 字节，随哈希串一起存。
- 密码最小长度 6，不允许纯空格；不强制复杂度（本地工具，避免过度设计）。
- 校验时必须走"用存储串里的 salt 重新计算再比对"，禁止明文比较。
- 明确边界：**这是本地单机应用的弱认证**，用于区分数据归属，不承担对抗性安全职责。

### 4.2 使用历史

| 方法 | 输入 | 输出 | 说明 |
|---|---|---|---|
| `log_activity` | user_id, action, target_record_id=None, detail=None | `None` | 写日志失败不得阻断主流程（内部捕获异常） |
| `list_activity` | user_id=None, action=None, limit=50, offset=0 | `(list, total)` | `user_id=None` 表示全部（仅 admin 使用） |

### 4.3 与档案相关的既有方法调整

| 方法 | 调整 |
|---|---|
| `save_record` | 签名不变，但写入时带 `owner_id`（由界面层传入当前用户；游客传 `None`） |
| `list_records` | 增加 `owner_id` 过滤参数；`admin` 传 `None` 看全部，普通用户传自己的 id |
| `delete_record` | 记录一条 `delete_record` 日志 |

> 原则：**签名只加可选参数，不改已有必填参数**，避免前端所有调用点返工。

---

## 5. 权限规则

| 能力 | 游客 | 普通用户 | 管理员 |
|---|---|---|---|
| 填写/导入/编辑档案 | ✅（仅在内存，可导出） | ✅ | ✅ |
| 档案落库 | ❌（提示"请登录后保存"） | ✅ 仅自己的 | ✅ 全部 |
| 查看档案列表 | 仅本次会话内的临时数据 | 仅自己 `owner_id` 的 | 全部（含 `owner_id` 为 NULL 的历史数据） |
| 编解码 DNA | ✅ | ✅ | ✅ |
| 查看使用历史 | ❌ | 仅自己的 | 全部 |
| 账号管理（停用/改角色） | ❌ | ❌ | ✅ |

**说明**：游客"不能落库"是刻意的——否则无主档案会污染 `owner_id` 语义，且无法追溯。

---

## 6. 主要流程

### 6.1 注册

界面弹窗 → 本地格式校验（非空、两次密码一致）→ `create_user()` →
成功：提示"注册成功，请登录"；失败：展示 `message`。
**注册不自动登录**（避免"刚注册就进主界面"导致权限状态含糊）。

### 6.2 账号登录

弹窗 → `verify_user()` → 成功：`touch_last_login()` + `log_activity(login)` +
界面记录 `current_user` → 进入主界面；失败：统一提示"账号或密码错误"。

### 6.3 游客登录

不调用数据库，界面记录 `current_user = None` + `is_visitor = True` → 进入主界面。
保存按钮改为提示"游客模式不可保存，请登录后使用"。

### 6.4 保存档案（串联）

界面收集表单 → `save_record(record, owner_id=current_user.id)` →
成功后 `log_activity(create_record, record_id)`。游客调用直接短路，不写库。

### 6.5 退出登录

`log_activity(logout)` → 清空 `current_user` → 回到登录页。

---

## 7. 边界与异常

| 场景 | 处理 |
|---|---|
| 用户名重复（含大小写差异） | 统一转小写后判重，返回"该账号已存在" |
| 用户名/密码为空或纯空格 | 前端拦截 + 数据层二次校验 |
| 密码哈希串损坏 | `verify_user` 返回 `None`，不抛异常 |
| 账号被停用 | 登录失败，提示"账号已停用" |
| 游客点击保存 | 前端拦截，给中文提示，不发数据库请求 |
| 日志写入失败 | 吞掉异常并打印，**不影响保存/登录结果** |
| 库结构为 v2.1（无新表） | `init_database()` 自动升级到 v2.2，不要求用户删库 |
| 历史档案 `owner_id` 为 NULL | 普通用户不可见；admin 可见并标注"历史数据" |

---

## 8. 迁移

1. 现有 `data/users.json`（明文账号）在首次启动时导入 `users` 表，导入后**重命名**为 `users.json.migrated` 保留一份，不再读写。
2. 已存在的 `archive_records` 全部 `owner_id = NULL`，视为历史数据。
3. `data/users.json` 从 `.gitignore` 覆盖范围内可清理，不再作为数据源。

---

## 9. 待确认（需要你拍板）

1. **游客的操作是否留痕？**
   - A：完全不记（推荐，日志无噪音）
   - B：记 `user_id = NULL` 的 `login/encode/decode`，仅用于统计
2. **普通用户能否看到"历史数据"（`owner_id` 为 NULL 的档案）？**
   - A：不能，只有 admin 能看（推荐，语义清晰）
   - B：能，但只读

---

## 10. 验收标准

| # | 用例 | 期望 |
|---|---|---|
| T1 | 注册新账号 | `users` 表新增 1 行；`users.json` 不再产生 |
| T2 | 重复注册同名（含大小写差异） | 被拒，提示"该账号已存在" |
| T3 | 用正确密码登录 | 进入主界面；`last_login_at` 更新；`user_activity_log` 有 `login` |
| T4 | 用错误密码登录 | 停留在登录页，提示统一，无异常栈 |
| T5 | 游客登录后点保存 | 提示"游客模式不可保存"，`archive_records` 无新增 |
| T6 | 普通用户保存档案 | 新增行 `owner_id` = 该用户；日志有 `create_record` |
| T7 | 普通用户查看列表 | 只出现自己 `owner_id` 的档案 |
| T8 | 从 v2.1 库启动 | 自动补建 2 张表 + `owner_id` 列，既有档案 `owner_id` 为 NULL |
| T9 | 打开 `data/users.json`（若残留） | 不含任何明文密码 |

---

## 11. 实施顺序

| 阶段 | 内容 | 责任 |
|---|---|---|
| P1 | `data_store.py`：建 `users`/`user_activity_log`、加 `owner_id`、结构版本升 v2.2 | 数据库同学 |
| P2 | `data_store.py`：`create_user`/`verify_user`/`log_activity`/`list_activity` | 数据库同学 |
| P3 | `data_store.py`：`save_record` 写 `owner_id`、`list_records` 加过滤、`delete_record` 记日志 | 数据库同学 |
| P4 | 迁移：导入 `users.json` → `users` 表 | 数据库同学 |
| P5 | `ui_interface.py`：删 `_load_users/_save_users`，改调 `DataStore`；保存前判游客 | 前端同学 |
| P6 | `main.py`：确保 `DataStore` 单例贯穿 UI 与保存链路 | 集成负责人 |

> P1–P3 完成即可先用脚本验证 T1–T8，不必等 UI。
