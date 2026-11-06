# 数据库开发书

> DNA 医疗档案系统 · iCAN 参赛数据库材料
> 数据库：SQLite（`data/db/medical_archive.db`）　|　结构版本：v2.1

## 目录（建议阅读/提交顺序）

| # | 文件 | 内容 |
|---|------|------|
| 1 | [01_数据字典.md](01_数据字典.md) | 60 个字段的规范数据字典：分组、中英文标签、类型、枚举值、多值规则、双语边界 |
| 2 | [02_ER图.md](02_ER图.md) | 8 张实体的 E-R 图（Mermaid 可渲染版 + 文本版）与 6 组联系的文字说明 |
| 3 | [03_数据表设计说明.md](03_数据表设计说明.md) | 每张表的用途、字段、主键、外键、约束、索引及索引设计说明 |
| 4 | [04_建表脚本.sql](04_建表脚本.sql) | 可直接执行的建表脚本（8 表 + 迁移暂存表 + 13 索引 + 版本写入） |
| 5 | [05_核心业务CRUD_SQL说明.md](05_核心业务CRUD_SQL说明.md) | 保存/加载/分页/局部更新/随访组装/DNA 载荷导出等 12 类核心 SQL |
| 6 | [06_数据安全说明.md](06_数据安全说明.md) | 存储安全、访问控制、写入防护、软删除审计、备份恢复、隐私合规、安全 Checklist |

## 一致性声明

六份材料基于现行设计文档 `DNA_/docs/modules/database_v2_design.md` v2.1，并在本轮加固中补充了数据库级约束（设计文档 §4 待同步同一版本）：

- 字段字典 60 条与种子文件 `data/seed/seed_field_definitions.sql` 同源（由 `scripts/gen_field_seed.py` 自动生成）；
- 建表脚本已实际在 SQLite 中验证通过（8 表 + 13 索引 + schema_meta 写入 v2.1），可重复执行；
- 相对设计文档新增：`schema_meta` 主键、`seq NOT NULL`、17 个 `CHECK` 约束、索引 `IF NOT EXISTS`；
- CRUD SQL 与 `api_contract.md` v2.1 的 DataStore 接口一一对应。

## 实现状态

- 建表脚本、字段字典种子可直接执行并通过自检（`foreign_key_check` 无输出、`integrity_check = ok`）；
- 现行 `src/data_store.py` 与 `data/db/medical_archive.db` 仍为 v1（5 张表），v2.1 数据层代码与 v1→v2 迁移尚未落地，需要另行实施；
- 病症词典 236 条种子（`data/seed/seed_disease_terms.sql`）尚未产出。

## 配套材料（不在本目录）

- 字段字典种子：`DNA_/data/seed/seed_field_definitions.sql`
- 种子生成脚本：`DNA_/scripts/gen_field_seed.py`
- 设计依据：`DNA_/docs/modules/database_v2_design.md`
- 接口契约：`DNA_/docs/main/api_contract.md`
