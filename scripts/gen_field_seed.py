#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
从 docs/modules/database_v2_design.md §5 生成字段字典种子 SQL。

用法：
    python scripts/gen_field_seed.py

输出：
    data/seed/seed_field_definitions.sql

设计原则：文档是唯一真源。要加字段，改文档 §5 的表格，然后重跑本脚本。
不要手工编辑生成的 SQL 文件。
"""
import io
import os
import re

DOC = "docs/modules/database_v2_design.md"
OUT = "data/seed/seed_field_definitions.sql"

SECTION_MAP = {
    "5.1": "identity",
    "5.2": "birth",
    "5.3": "history",
    "5.4": "allergy",
    "5.5": "lifestyle",
    "5.6": "reproductive",
    "5.7": "complaint",
    "5.8": "exam",
    "5.9": "followup",
}

# 标签里的括号内容默认不当单位用，这里显式覆盖
UNIT_OVERRIDE = {
    "apgar_1min": "",      # 标签「Apgar评分(1分钟)」——括号里是时间点不是单位
    "apgar_5min": "",
}


def parse_type(raw_type: str, label_cn: str):
    """'text, multi' / 'number（℃）' / 'enum: male/female/unknown' → (value_type, is_multi, unit)"""
    t = raw_type.strip()
    is_multi = 1 if "multi" in t else 0
    low = t.lower()

    if low.startswith("enum"):
        value_type = "enum"
    elif low.startswith("number"):
        value_type = "number"
    elif low.startswith("date"):
        value_type = "date"
    elif low.startswith("bool"):
        value_type = "bool"
    else:
        value_type = "text"

    unit = ""
    m = re.search(r"[（(]([^）)]+)[）)]", t)
    if m and "如" not in m.group(1):
        unit = m.group(1).strip()
    # 单位写在标签里，如「出生体重(g)」
    if not unit and value_type == "number":
        m2 = re.search(r"[（(]([^）)]+)[）)]", label_cn)
        if m2:
            unit = m2.group(1).strip()
    return value_type, is_multi, unit


def main() -> None:
    doc = io.open(DOC, encoding="utf-8").read()
    body = doc[doc.index("### 5.1"):doc.index("### 5.10")]

    parts = re.split(r"\n### (5\.\d) ", body)
    chunks = {"5.1": parts[0]}
    for i in range(1, len(parts), 2):
        chunks[parts[i]] = parts[i + 1]

    rows = []
    for num, section in SECTION_MAP.items():
        order = 0
        for line in chunks.get(num, "").split("\n"):
            if not line.startswith("| "):
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 4:
                continue
            field_key = cells[0]
            if not re.fullmatch(r"[a-z][a-z0-9_]*", field_key) or field_key == "field_key":
                continue
            label_cn, label_en = cells[1], cells[2]
            # §5.1 是 5 列（多了「物理列」），其余是 4 列
            raw_type = cells[4] if len(cells) >= 5 else cells[3]
            value_type, is_multi, unit = parse_type(raw_type, label_cn)
            unit = UNIT_OVERRIDE.get(field_key, unit)
            order += 10
            rows.append((section, field_key, label_cn, label_en,
                         value_type, is_multi, unit, order))

    seen, unique_rows = set(), []
    for r in rows:
        if r[1] in seen:
            print("⚠️  跳过重复 field_key:", r[1])
            continue
        seen.add(r[1])
        unique_rows.append(r)

    def esc(s: str) -> str:
        return s.replace("'", "''")

    lines = [
        "-- 字段字典种子数据（v2.1，共 %d 条）" % len(unique_rows),
        "-- 由 scripts/gen_field_seed.py 从 docs/modules/database_v2_design.md §5 自动生成",
        "-- 不要手工编辑本文件；改字段请改文档后重跑脚本",
        "-- 用法：sqlite3 data/db/medical_archive.db < data/seed/seed_field_definitions.sql",
        "--       或由 DataStore.init_field_definitions() 读取执行",
        "",
        "BEGIN TRANSACTION;",
        "",
    ]
    for section, fk, cn, en, vt, multi, unit, order in unique_rows:
        lines.append(
            "INSERT INTO field_definitions "
            "(field_key, section, label_cn, label_en, value_type, is_multi, is_active, "
            "unit_cn, unit_en, sort_order, is_legacy)\n"
            "VALUES ('%s', '%s', '%s', '%s', '%s', %d, 1, '%s', '%s', %d, 0)\n"
            "ON CONFLICT(field_key) DO UPDATE SET "
            "section=excluded.section, label_cn=excluded.label_cn, label_en=excluded.label_en, "
            "value_type=excluded.value_type, is_multi=excluded.is_multi, "
            "unit_cn=excluded.unit_cn, unit_en=excluded.unit_en, sort_order=excluded.sort_order;"
            % (esc(fk), section, esc(cn), esc(en), vt, multi, esc(unit), esc(unit), order)
        )
    lines += ["", "COMMIT;"]

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    io.open(OUT, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("✅ 生成 %d 条字段定义 → %s" % (len(unique_rows), OUT))


if __name__ == "__main__":
    main()
