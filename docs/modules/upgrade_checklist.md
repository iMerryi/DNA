# DNA 项目升级清单（版本现状与待办）

> 生成时间：2026-11-07
> 当前代码数据库版本：**v3.0**
> 当前唯一设计依据：**database_master_design.md v3.0**

---

## 一、当前版本现状

### 1.1 代码模块状态

| 模块 | 文件 | 版本 | 状态 | 说明 |
|------|------|------|------|------|
| 主入口 | `src/main.py` | 无 | 可用 | 能启动应用，已接入 v3.0 DataStore |
| 前端界面 | `src/ui_interface.py` | 无 | 需升级 | 登录页已可用，但保存逻辑仍写 JSON，未接 v3.0 DataStore |
| 数据库 | `src/data_store.py` | **v3.0** | 最新可用 | 9 张表已按 v3.0 主设计书实现 |
| AI 提取 | `src/ollama_api.py` | 无 | 需升级 | 返回格式仍是旧版（物理/反复/病症三层），未对接 v3.0 字段 key |
| 字段字典 | `src/core/field_extractor.py` | 无 | 可用 | 最小版本 |
| 数据分类 | `src/core/data_classifier.py` | 无 | 需升级 | 只做了 AI 结果 → 表单拍平，未做表单 → v3.0 entries |
| 拼音工具 | `src/core/pinyin_utils.py` | 无 | 可用 | 工具函数 |
| DNA 编解码 | `src/dna_codec.py` | 不存在 | 未开始 | 核心模块缺失 |
| 纠错模块 | `src/error_corrector.py` | 不存在 | 未开始 | 核心模块缺失 |

### 1.2 设计文档状态

| 文档 | 版本 | 状态 | 处理建议 |
|------|------|------|----------|
| `database_master_design.md` | **v3.0** | 最新唯一依据 | 保留在 `docs/modules/` 根目录 |
| `医疗档案数据库主设计书_v3.0.docx` | v3.0 | Word 版 | 保留，用于打印/评审 |
| `medical_archive_database_design2.md` | v2.1 | 已合并到 v3.0 | **归档** |
| `user_account_module_design1.md` | v1.0 | 已合并到 v3.0 | **归档** |
| `database_v2_design.md` | v2.1 | 被 v3.0 取代 | **归档** |
| `database.md` | v1 | 已过时 | **归档** |
| `database_design.md` | v1 | 已过时 | **归档** |
| `ui_interface.md` | 未知 | 可能已过时 | 需检查内容后决定是否归档 |
| `frontend.md` | 未知 | 可能已过时 | 需检查内容后决定是否归档 |
| `algorithm.md` | 未知 | 可能仍有效 | 需检查是否与 v3.0 兼容 |
| `ollama_ai.md` / `ollama_api.md` | 未知 | 可能已过时 | 需检查是否与 v3.0 兼容 |

### 1.3 脚本/工具状态

| 文件 | 状态 | 处理建议 |
|------|------|----------|
| `scripts/gen_field_seed.py` | 基于 v2.1，已不适用 | **删除** 或重写为 v3.0 格式 |
| `data/seed/` 目录 | 可能不存在或为空 | 如需 236 条病症词典，需补充种子文件 |

---

## 二、需要升级的内容（按优先级排序）

### P0：文档版本统一（必须先做，否则队友不知道该看哪份）

- [ ] 将 `medical_archive_database_design2.md`、`user_account_module_design1.md`、`database_v2_design.md`、`database.md`、`database_design.md` 移入 `docs/modules/archive/`
- [ ] 在 `database_master_design.md` 顶部明确标注："本文档是唯一施工依据，其他版本已归档"
- [ ] 删除 `scripts/gen_field_seed.py` 或重写为 v3.0 版本

### P1：前端接入 v3.0 数据库（当前最大卡点）

- [ ] `ui_interface.py` 删除所有直接读写 JSON 的代码
- [ ] `ui_interface.py` 删除裸 `sqlite3` 查询（如还有）
- [ ] 表单字段从硬编码改为从 `data_store.list_field_definitions()` 动态读取
- [ ] 点"保存数据"时调用 `data_store.save_record()`，传入 `ArchiveRecord`
- [ ] 保存时带上当前登录用户的 `owner_id`
- [ ] 游客登录时禁用"保存"按钮或给出提示

### P2：登录/注册模块走数据库

- [ ] 删除 `data/users.json` 相关代码
- [ ] 注册调用 `data_store.create_user()`
- [ ] 登录调用 `data_store.verify_user()`
- [ ] 登录成功后保存当前用户对象（`id`、`username`、`role`）
- [ ] 登录/注册/退出时记录 `user_activity_log`

### P3：AI 模块对接 v3.0 字段 key

- [ ] `ollama_api.py` 的 `extract_fields()` 返回 v3.0 格式：`{field_key: value_cn}`
- [ ] 文档识别结果通过 `data_classifier.py` 转成 `ArchiveRecord.entries`
- [ ] 删除 UI 里混入的旧版 `ask_ollama()` 逻辑（如还有残留）

### P4：DNA 编解码模块（核心功能）

- [ ] 实现 `src/dna_codec.py`：
  - `encode(payload: dict, key: str) -> str`：把规范 payload 转成 DNA 序列
  - `decode(dna_sequence: str, key: str) -> dict`：把 DNA 序列还原成 payload
- [ ] 编码载荷格式按 v3.0 设计书 §7.2：`json.dumps(payload, ensure_ascii=True, sort_keys=True)`
- [ ] 实现 `src/error_corrector.py`：解码失败时尝试纠错
- [ ] 前端"确认并测试"按钮调用 `dna_codec.encode()`
- [ ] 前端"解密 DNA"按钮调用 `dna_codec.decode()`

### P5：解码回填界面

- [ ] 输入 DNA 序列 → 解码 → 展示中文结果
- [ ] 可选择"导入到表单"继续编辑
- [ ] 记录解码历史到 `decode_records`

### P6：病症词典补全

- [ ] 整理 236 条病症数据
- [ ] 放入 `docs/seed/disease_terms.csv`（避免被 `.gitignore` 忽略）
- [ ] `data_store.py` 启动时自动加载

### P7：权限与历史查看

- [ ] 普通用户只查看自己的档案
- [ ] 管理员可查看全部档案
- [ ] 增加"我的历史"页面，展示 `user_activity_log`

---

## 三、版本号管理规则（以后不乱的约定）

| 改动类型 | 版本号变化 | 需要更新的地方 |
|----------|-----------|----------------|
| 改表结构（加减表、列、约束） | v3.0 → v3.1 | `data_store.py` 中 `SCHEMA_VERSION` + 迁移逻辑 + `database_master_design.md` |
| 改字段字典 | 不升版本号 | `data_store.py` 中 `FIELD_DEFINITIONS` + `database_master_design.md` §5 |
| 改接口契约 | 不升版本号 | `database_master_design.md` §8 + 调用方代码 |
| 纯业务逻辑改动 | 不升版本号 | 对应代码文件 |

---

## 四、建议执行顺序

```
第 1 步：文档归档（P0）
第 2 步：前端改保存逻辑（P1）
第 3 步：前端改登录注册（P2）
第 4 步：AI 模块对接（P3）
第 5 步：DNA 编解码（P4）
第 6 步：解码回填界面（P5）
第 7 步：补全病症词典（P6）
第 8 步：权限与历史（P7）
```

---

## 五、当前最大的三个风险

1. **多份设计文档并存**：队友可能继续按 v2.1 或 v1 开发，导致数据结构再次分裂。
2. **前端没接数据库**："保存"按钮现在不写库，项目主链路仍不通。
3. **DNA 编解码缺失**：这是项目核心卖点，目前还没有实现。

---

## 六、立即可以验证的三件事

1. 运行 `python src/main.py`，确认应用能启动，三个登录入口可用
2. 用数据库工具打开 `data/db/medical_archive.db`，确认 9 张表已创建
3. 在前端"在线填写"后点"保存"，确认数据已写入 `archive_records` 和 `record_entries`（当前可能还没有写入）
