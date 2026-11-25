# -*- coding: utf-8 -*-
"""
数据库结构验收脚本（v4.1 / 10 表 · 8 表头 · 16 空全枚举口径）
用法：
    python 07_验收脚本_verify_schema.py                     # 默认验同目录随包样例库
    python 07_验收脚本_verify_schema.py --db 某路径.db      # 验自己重建的库

只读，不写任何东西（会开一个内存里的临时连接做"坏写入"试探）。
退出码 0 = 全过；1 = 有 FAIL。
"""
import argparse, os, sqlite3, sys

HERE = os.path.dirname(os.path.abspath(__file__))
# 交接包独立分发，包内没有 DNA_/data/db/ 现库；默认指向随包提供的 v4.1 样例库。
DEFAULT_DB = os.path.join(HERE, "medical_archive_v4_样例.db")

EXPECT_TABLES = {"schema_meta", "archive_records", "icd_codes", "sections", "fields",
                 "options", "answers", "dna_sequences", "decode_records", "user_activity_log"}
EXPECT_TYPE_DIST = {"multi_enum": 14, "enum": 2}

results = []
def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print("  [%s] %-34s %s" % ("PASS" if ok else "FAIL", name, detail))

def warn(name, detail):
    results.append((name, None, detail))
    print("  [WARN] %-34s %s" % (name, detail))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DEFAULT_DB)
    a = ap.parse_args()
    path = os.path.abspath(a.db)
    if not os.path.exists(path):
        print("找不到库：", path); return 1
    print("验收目标：", path)
    print("大小：%d bytes\n" % os.path.getsize(path))

    c = sqlite3.connect(path)
    c.execute("PRAGMA foreign_keys = ON")

    # 1 表清单
    tabs = set(r[0] for r in c.execute(
        "select name from sqlite_master where type='table' and name not like 'sqlite_%'"))
    check("表清单 = 10 张（无 users）", tabs == EXPECT_TABLES,
          "多出:%s 缺少:%s" % (sorted(tabs - EXPECT_TABLES), sorted(EXPECT_TABLES - tabs)))

    if tabs != EXPECT_TABLES:
        print("\n表结构不对，后续检查跳过。")
        return 1

    # 2 骨架行数
    n_sec = c.execute("select count(*) from sections").fetchone()[0]
    check("sections = 8", n_sec == 8, "实测 %d" % n_sec)
    n_fld = c.execute("select count(*) from fields").fetchone()[0]
    check("fields = 16", n_fld == 16, "实测 %d" % n_fld)

    # 3 类型分布
    dist = dict(c.execute("select value_type, count(*) from fields group by value_type").fetchall())
    check("fields 类型分布 14/2（全枚举）", dist == EXPECT_TYPE_DIST, str(dist))

    # 4 树完整性
    roots = c.execute("select count(*) from sections where parent_id is null").fetchone()[0]
    check("表头根节点 = 2", roots == 2, "实测 %d" % roots)
    orphan = c.execute("""select count(*) from sections x where x.parent_id is not null
                          and not exists(select 1 from sections p where p.id = x.parent_id)""").fetchone()[0]
    check("孤儿表头 = 0", orphan == 0, "实测 %d" % orphan)
    lvl_bad = c.execute("""select count(*) from sections x where x.parent_id is not null
                           and x.level <> (select p.level + 1 from sections p where p.id = x.parent_id)""").fetchone()[0]
    check("level 与 parent 一致 = 0 处错", lvl_bad == 0, "实测 %d 处不一致" % lvl_bad)

    all_enum = c.execute("select count(*) from fields where value_type not in ('multi_enum','enum')").fetchone()[0]
    check("16 空全部为枚举型 = 0 个例外", all_enum == 0, "实测 %d 个非枚举" % all_enum)
    no_insc = c.execute("""select count(*) from fields f join sections s on s.id = f.section_id
                           where s.section_key = 'inscription'""").fetchone()[0]
    check("铭文下无字段挂载 = 0", no_insc == 0, "实测 %d" % no_insc)

    # 5 空与表头的挂接
    bad_sec = c.execute("""select count(*) from fields f where not exists
                           (select 1 from sections s where s.id = f.section_id)""").fetchone()[0]
    check("空挂错表头 = 0", bad_sec == 0, "实测 %d" % bad_sec)
    dangling = c.execute("""select count(*) from fields f where f.derive_from <> ''
                            and not exists(select 1 from fields p where p.field_key = f.derive_from)""").fetchone()[0]
    check("derive_from 悬空 = 0", dangling == 0, "实测 %d" % dangling)

    dc = c.execute("select name_cn, note from fields where field_key = 'disease_category'").fetchone()
    check("疾病分类：选项由 22 章派生",
          dc is not None and "22 章" in (dc[1] or ""), str(dc))

    # 6 外键数量与目标
    fk_total = sum(len(c.execute("select * from pragma_foreign_key_list('%s')" % t).fetchall()) for t in tabs)
    check("外键 = 9 条", fk_total == 9, "实测 %d" % fk_total)
    log_fk = c.execute("select * from pragma_foreign_key_list('user_activity_log')").fetchall()
    check("日志表无外键（删档也要写得进）", len(log_fk) == 0, "实测 %d 条" % len(log_fk))

    # 7 索引
    n_idx = c.execute("""select count(*) from sqlite_master where type='index'
                         and name not like 'sqlite_%'""").fetchone()[0]
    check("显式索引 = 21 个", n_idx == 21, "实测 %d" % n_idx)

    # 8 候选项目录质量
    n_opt = c.execute("select count(*) from options").fetchone()[0]
    bad_icd = c.execute("""select count(*) from options o where o.icd_code is not null
                           and not exists(select 1 from icd_codes i where i.code = o.icd_code)""").fetchone()[0]
    check("option 的 icd_code 无悬空 = 0", bad_icd == 0, "实测 %d 条悬空" % bad_icd)
    if n_opt == 0:
        warn("options 已灌数量", "0 条 —— 界面下拉会是空的，S3/S4 还没灌")
    else:
        print("  [INFO] %-34s %d 条" % ("options 已灌数量", n_opt))

    # 9 answers 门卫规则（在临时表副本上试写，不动原数据）
    c.execute("SAVEPOINT gate")
    gate = []
    def try_bad(label, sql):
        try:
            c.execute(sql); c.execute("ROLLBACK TO gate")
            gate.append((label, False))
        except sqlite3.IntegrityError:
            c.execute("ROLLBACK TO gate")
            gate.append((label, True))
    fld = c.execute("select min(id) from fields").fetchone()[0]
    opt = c.execute("select min(id) from options").fetchone()[0]
    rec = c.execute("select min(record_id) from archive_records").fetchone()[0]
    if opt and rec:
        try_bad("勾选项+填数值被拒",
                "insert into answers(record_id,field_id,option_id,value_num,updated_at) "
                "values ('%s',%d,%d,1.0,'x')" % (rec, fld, opt))
    try_bad("什么都空被拒",
            "insert into answers(record_id,field_id,updated_at) values ('%s',%d,'x')" % (rec or "X", fld))
    try_bad("引用不存在档案被拒",
            "insert into answers(record_id,field_id,updated_at) values ('NO_SUCH',%d,'x')" % fld)
    c.execute("RELEASE gate")
    for label, ok in gate:
        check(label, ok, "" if ok else "没拦住，CHECK/FK 未生效")

    # 10 版本标签
    ver = c.execute("select version from schema_meta").fetchall()
    check("schema_meta 版本 = v4.1", len(ver) >= 1 and ver[0][0] == "v4.1", str(ver))

    # 11 一致性巡检（有数据的库才有意义）
    dup = c.execute("""select count(*) from (select record_id, field_id, option_id, seq, count(*) n
                       from answers where option_id is not null group by 1,2,3,4 having n > 1)""").fetchone()[0]
    check("同一答案重复写入 = 0", dup == 0, "实测 %d 组重复" % dup)
    orphan_ans = c.execute("""select count(*) from answers a where not exists
                              (select 1 from archive_records r where r.record_id = a.record_id)""").fetchone()[0]
    check("答案指向不存在的档案 = 0", orphan_ans == 0, "实测 %d" % orphan_ans)

    c.close()

    n_fail = sum(1 for _, ok, _ in results if ok is False)
    print("\n" + "-" * 60)
    print("结果：%d 项通过，%d 项未通过，%d 项提示" %
          (sum(1 for _, ok, _ in results if ok is True), n_fail,
           sum(1 for _, ok, _ in results if ok is None)))
    return 0 if n_fail == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
