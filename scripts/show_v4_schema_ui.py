# -*- coding: utf-8 -*-
"""
v4.0 数据库表头/空结构可视化工具
依据：docs/modules/ 或 数据库开发书/00_数据库开发书_最终版_v4.0.md
作用：只读展示 14 个 sections 与 42 个 fields 的层级关系，方便人类理解数据库设计。
"""
import tkinter as tk
from tkinter import ttk

# ==================== 数据：14 个 sections ====================
SECTIONS = [
    {"sort": 1,  "level": 1, "parent": None,                   "key": "inscription",            "name": "铭文部分："},
    {"sort": 2,  "level": 1, "parent": None,                   "key": "storage",                "name": "存储部分："},
    {"sort": 3,  "level": 2, "parent": "storage",              "key": "patient_background",     "name": "一、患者基础与背景信息类（不可或缺）"},
    {"sort": 4,  "level": 2, "parent": "storage",              "key": "clinical_history",       "name": "二、临床主诉与现病史类（症状的延伸）"},
    {"sort": 5,  "level": 2, "parent": "storage",              "key": "followup",               "name": "三、随访记录类（动态追踪）"},
    {"sort": 6,  "level": 3, "parent": "patient_background",   "key": "past_and_family_history","name": "1.既往史/家族史："},
    {"sort": 7,  "level": 3, "parent": "patient_background",   "key": "allergy_history",        "name": "2.过敏史："},
    {"sort": 8,  "level": 3, "parent": "patient_background",   "key": "personal_lifestyle",     "name": "3.个人生活史："},
    {"sort": 9,  "level": 3, "parent": "patient_background",   "key": "reproductive_history",   "name": "4.婚育史/月经史："},
    {"sort": 10, "level": 3, "parent": "patient_background",   "key": "birth_and_family",       "name": "5.出生史与家庭信息："},
    {"sort": 11, "level": 3, "parent": "clinical_history",     "key": "disease_classification", "name": "1.疾病分类："},
    {"sort": 12, "level": 3, "parent": "clinical_history",     "key": "symptoms",               "name": "2.症状表现："},
    {"sort": 13, "level": 3, "parent": "clinical_history",     "key": "physical_examination",   "name": "3.体格检查（体征）："},
    {"sort": 14, "level": 3, "parent": "followup",             "key": "followup_record",        "name": "1.随访记录："},
]

# ==================== 数据：42 个 fields ====================
FIELDS = [
    {"#": 1,  "key": "past_medical_history",  "name": "既往患病史",         "type": "multi_enum",   "required": 1, "section": "past_and_family_history"},
    {"#": 2,  "key": "surgery_history",       "name": "手术史",             "type": "multi_enum",   "required": 1, "section": "past_and_family_history"},
    {"#": 3,  "key": "trauma_history",        "name": "外伤史",             "type": "multi_enum",   "required": 1, "section": "past_and_family_history"},
    {"#": 4,  "key": "transfusion_history",   "name": "输血史",             "type": "enum",         "required": 1, "section": "past_and_family_history"},
    {"#": 5,  "key": "vaccination_history",   "name": "预防接种史",         "type": "enum",         "required": 1, "section": "past_and_family_history"},
    {"#": 6,  "key": "family_history",        "name": "家族史",             "type": "multi_enum",   "required": 1, "section": "past_and_family_history"},
    {"#": 7,  "key": "high_risk_factor",      "name": "高危因素",           "type": "multi_enum",   "required": 1, "section": "past_and_family_history"},
    {"#": 8,  "key": "allergy_source",        "name": "过敏原",             "type": "multi_enum",   "required": 1, "section": "allergy_history"},
    {"#": 9,  "key": "allergy_reaction",      "name": "过敏反应",           "type": "multi_enum",   "required": 1, "section": "allergy_history"},
    {"#": 10, "key": "drug_allergy",          "name": "药物过敏史",         "type": "multi_enum",   "required": 1, "section": "allergy_history"},
    {"#": 11, "key": "smoking_history",       "name": "吸烟史",             "type": "enum",         "required": 1, "section": "personal_lifestyle"},
    {"#": 12, "key": "alcohol_history",       "name": "饮酒史",             "type": "enum",         "required": 1, "section": "personal_lifestyle"},
    {"#": 13, "key": "diet_habit",            "name": "饮食情况",           "type": "multi_enum",   "required": 1, "section": "personal_lifestyle"},
    {"#": 14, "key": "sleep_habit",           "name": "作息情况",           "type": "multi_enum",   "required": 1, "section": "personal_lifestyle"},
    {"#": 15, "key": "marriage_history",      "name": "婚育史",             "type": "multi_enum",   "required": 0, "section": "reproductive_history"},
    {"#": 16, "key": "menstrual_history",     "name": "月经史",             "type": "multi_enum",   "required": 0, "section": "reproductive_history"},
    {"#": 17, "key": "birth_date",            "name": "出生日期",           "type": "date",         "required": 1, "section": "birth_and_family"},
    {"#": 18, "key": "abo_blood_type",        "name": "ABO 血型",           "type": "enum",         "required": 0, "section": "birth_and_family"},
    {"#": 19, "key": "rh_blood_type",         "name": "Rh 血型",            "type": "enum",         "required": 0, "section": "birth_and_family"},
    {"#": 20, "key": "delivery_org",          "name": "建档机构 / 分娩机构", "type": "text",         "required": 0, "section": "birth_and_family"},
    {"#": 21, "key": "parent_name",           "name": "父亲姓名 / 母亲姓名", "type": "text",         "required": 0, "section": "birth_and_family"},
    {"#": 22, "key": "parent_phone",          "name": "父亲电话 / 母亲电话 / 联系电话", "type": "text", "required": 0, "section": "birth_and_family"},
    {"#": 23, "key": "hukou_address",         "name": "户籍地址",           "type": "text",         "required": 0, "section": "birth_and_family"},
    {"#": 24, "key": "disease_category",      "name": "疾病分类",           "type": "multi_enum",   "required": 1, "section": "disease_classification"},
    {"#": 25, "key": "disease_result",        "name": "病症结果",           "type": "multi_enum",   "required": 1, "section": "disease_classification"},
    {"#": 26, "key": "chief_complaint",       "name": "主诉",               "type": "multi_enum",   "required": 1, "section": "symptoms"},
    {"#": 27, "key": "symptom_onset",         "name": "起病时间",           "type": "date",         "required": 1, "section": "symptoms"},
    {"#": 28, "key": "symptom_severity",      "name": "缓急程度",           "type": "enum",         "required": 0, "section": "symptoms"},
    {"#": 29, "key": "symptom_duration",      "name": "持续时间",           "type": "text",         "required": 0, "section": "symptoms"},
    {"#": 30, "key": "accompanying_symptom",  "name": "伴随症状",           "type": "multi_enum",   "required": 0, "section": "symptoms"},
    {"#": 31, "key": "mental_state",          "name": "精神状态",           "type": "enum",         "required": 0, "section": "symptoms"},
    {"#": 32, "key": "appetite",              "name": "食欲",               "type": "enum",         "required": 0, "section": "symptoms"},
    {"#": 33, "key": "sleep_status",          "name": "睡眠",               "type": "enum",         "required": 0, "section": "symptoms"},
    {"#": 34, "key": "bowel_bladder",         "name": "大小便",             "type": "multi_enum",   "required": 0, "section": "symptoms"},
    {"#": 35, "key": "vital_signs",           "name": "生命体征",           "type": "number_group", "required": 0, "section": "physical_examination"},
    {"#": 36, "key": "special_exam",          "name": "专科查体",           "type": "multi_enum",   "required": 0, "section": "physical_examination"},
    {"#": 37, "key": "positive_signs",        "name": "阳性体征",           "type": "multi_enum",   "required": 0, "section": "physical_examination"},
    {"#": 38, "key": "negative_signs",        "name": "阴性体征",           "type": "multi_enum",   "required": 0, "section": "physical_examination"},
    {"#": 39, "key": "followup_date",         "name": "随访日期",           "type": "date",         "required": 1, "section": "followup_record"},
    {"#": 40, "key": "current_weight",        "name": "当前体重",           "type": "number",       "required": 0, "section": "followup_record"},
    {"#": 41, "key": "current_temperature",   "name": "当前体温",           "type": "number",       "required": 0, "section": "followup_record"},
    {"#": 42, "key": "followup_note",         "name": "随访备注",           "type": "text",         "required": 0, "section": "followup_record"},
]

TYPE_LABEL = {
    "multi_enum": "多选",
    "enum": "单选",
    "text": "文本",
    "date": "日期",
    "number": "数值",
    "number_group": "数值组",
}

TYPE_COLOR = {
    "multi_enum": "#E3F2FD",   # 浅蓝
    "enum": "#E8F5E9",         # 浅绿
    "text": "#FFF3E0",         # 浅橙
    "date": "#F3E5F5",         # 浅紫
    "number": "#E0F7FA",       # 浅青
    "number_group": "#FFFDE7", # 浅黄
}


class SchemaViewer(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("DNA v4.0 数据库表头/空结构可视化")
        self.geometry("1100x700")
        self._build_ui()
        self._populate_tree()
        self._update_stats()

    def _build_ui(self):
        # 顶部统计
        self.stats_var = tk.StringVar()
        tk.Label(
            self, textvariable=self.stats_var,
            font=("Microsoft YaHei", 12, "bold"),
            bg="#FAFAFA", anchor="w", padx=10, pady=8
        ).pack(fill="x")

        # 主区域：左右分栏
        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill="both", expand=True, padx=8, pady=4)

        # 左侧树
        left = tk.Frame(paned)
        paned.add(left, weight=3)

        tk.Label(left, text="层级结构（点击节点看详情）", font=("Microsoft YaHei", 10, "bold")).pack(anchor="w", pady=(0, 4))

        tree_frame = tk.Frame(left)
        tree_frame.pack(fill="both", expand=True)

        cols = ("name", "key", "type", "required")
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="tree headings", selectmode="browse")
        self.tree.heading("#0", text="层级")
        self.tree.heading("name", text="名称")
        self.tree.heading("key", text="key")
        self.tree.heading("type", text="类型")
        self.tree.heading("required", text="必填")

        self.tree.column("#0", width=120, minwidth=80)
        self.tree.column("name", width=260, minwidth=120)
        self.tree.column("key", width=180, minwidth=100)
        self.tree.column("type", width=80, minwidth=60)
        self.tree.column("required", width=50, minwidth=40)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        # 右侧详情
        right = tk.Frame(paned, padx=10, pady=10)
        paned.add(right, weight=2)

        tk.Label(right, text="节点详情", font=("Microsoft YaHei", 12, "bold")).pack(anchor="w", pady=(0, 8))
        self.detail = tk.Text(right, wrap="word", font=("Microsoft YaHei", 10), padx=8, pady=8, state="disabled")
        self.detail.pack(fill="both", expand=True)

        # 底部图例
        legend = tk.Frame(self, bg="#FAFAFA", pady=6)
        legend.pack(fill="x", side="bottom")
        tk.Label(legend, text="字段类型图例：", bg="#FAFAFA", font=("Microsoft YaHei", 9, "bold")).pack(side="left", padx=(10, 4))
        for t, label in TYPE_LABEL.items():
            lbl = tk.Label(legend, text=label, bg=TYPE_COLOR[t], relief="solid", borderwidth=1, padx=8, font=("Microsoft YaHei", 9))
            lbl.pack(side="left", padx=4)
        tk.Label(legend, text="|", bg="#FAFAFA", fg="#999", font=("Microsoft YaHei", 9)).pack(side="left", padx=6)
        tk.Label(legend, text="⭕ 来自 options 枚举表", bg="#FAFAFA", font=("Microsoft YaHei", 9)).pack(side="left", padx=4)
        tk.Label(legend, text="🔷 直接填写值（不查 options）", bg="#FAFAFA", font=("Microsoft YaHei", 9)).pack(side="left", padx=4)

    def _populate_tree(self):
        section_by_key = {s["key"]: s for s in SECTIONS}
        node_map = {}

        # 按 sort 排，保证父节点先出现
        for sec in sorted(SECTIONS, key=lambda x: x["sort"]):
            parent_iid = node_map.get(sec["parent"], "")
            level_tag = f"level{sec['level']}"
            text = "  " * (sec["level"] - 1) + f"L{sec['level']}"
            iid = self.tree.insert(
                parent_iid, "end",
                text=text,
                values=(sec["name"], sec["key"], "", ""),
                tags=(level_tag,)
            )
            node_map[sec["key"]] = iid

        # 插字段：枚举型加 ⭕，值型加 🔷
        for fld in FIELDS:
            parent_iid = node_map.get(fld["section"], "")
            tag = f"type_{fld['type']}"
            icon = "⭕" if fld["type"] in ("multi_enum", "enum") else "🔷"
            display_name = f"{icon} {fld['name']}"
            self.tree.insert(
                parent_iid, "end",
                text="    ├─",
                values=(display_name, fld["key"], TYPE_LABEL.get(fld["type"], fld["type"]), "是" if fld["required"] else ""),
                tags=(tag, fld["type"])
            )

        # 样式
        self.tree.tag_configure("level1", font=("Microsoft YaHei", 10, "bold"), foreground="#1A237E")
        self.tree.tag_configure("level2", font=("Microsoft YaHei", 9, "bold"), foreground="#283593")
        self.tree.tag_configure("level3", font=("Microsoft YaHei", 9), foreground="#37474F")
        for t, color in TYPE_COLOR.items():
            self.tree.tag_configure(f"type_{t}", background=color)

    def _update_stats(self):
        type_counts = {}
        for f in FIELDS:
            type_counts[f["type"]] = type_counts.get(f["type"], 0) + 1
        type_text = " / ".join(f"{TYPE_LABEL[k]}:{v}" for k, v in type_counts.items())
        required = sum(1 for f in FIELDS if f["required"])
        stats = (
            f"Sections: {len(SECTIONS)} 个  |  Fields: {len(FIELDS)} 个  "
            f"| 必填: {required} 个  | 选填: {len(FIELDS)-required} 个  | 类型分布: {type_text}"
        )
        self.stats_var.set(stats)

    def _on_select(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        values = self.tree.item(sel[0], "values")
        name, key, typ, required = values

        self.detail.config(state="normal")
        self.detail.delete("1.0", "end")

        # 判断是 section 还是 field
        is_field = any(f["key"] == key for f in FIELDS)

        if is_field:
            fld = next(f for f in FIELDS if f["key"] == key)
            sec = next((s for s in SECTIONS if s["key"] == fld["section"]), None)
            self.detail.insert("end", f"字段序号: {fld['#']}\n")
            self.detail.insert("end", f"字段 key: {fld['key']}\n")
            self.detail.insert("end", f"中文名: {fld['name']}\n")
            self.detail.insert("end", f"字段类型: {TYPE_LABEL.get(fld['type'], fld['type'])} ({fld['type']})\n")
            self.detail.insert("end", f"是否必填: {'是' if fld['required'] else '否'}\n")
            self.detail.insert("end", f"归属表头: {sec['name'] if sec else '未知'} ({sec['key'] if sec else ''})\n")
            self.detail.insert("end", "\n说明:\n")
            if fld["type"] in ("multi_enum", "enum"):
                self.detail.insert("end", "• 该字段使用 options 枚举表作为下拉/多选来源。\n")
                if fld["type"] == "multi_enum":
                    self.detail.insert("end", "• 可多选，answers 表中以多行记录存储。\n")
                else:
                    self.detail.insert("end", "• 只能单选，answers 表中一行记录。\n")
            else:
                self.detail.insert("end", "• 【值型字段】不查 options 枚举表，用户直接填写。\n")
                if fld["type"] == "number_group":
                    self.detail.insert("end", "• 数值组（如体温、血压等多指标组合），写入 answers.value_num/值列。\n")
                elif fld["type"] == "date":
                    self.detail.insert("end", "• 日期型，写入 answers.value_date。\n")
                elif fld["type"] == "number":
                    self.detail.insert("end", "• 数值型，写入 answers.value_num。\n")
                elif fld["type"] == "text":
                    self.detail.insert("end", "• 开放文本，写入 answers.value_text。\n")
        else:
            sec = next((s for s in SECTIONS if s["key"] == key), None)
            if sec:
                child_count = sum(1 for f in FIELDS if f["section"] == sec["key"])
                self.detail.insert("end", f"表头 key: {sec['key']}\n")
                self.detail.insert("end", f"中文名: {sec['name']}\n")
                self.detail.insert("end", f"层级: L{sec['level']}\n")
                self.detail.insert("end", f"排序: {sec['sort']}\n")
                self.detail.insert("end", f"父节点: {sec['parent'] if sec['parent'] else '无（顶层）'}\n")
                self.detail.insert("end", f"下属字段数: {child_count}\n")
                if child_count == 0:
                    self.detail.insert("end", "\n说明: 该表头下不挂字段（如 inscription 铭文部分）。\n")

        self.detail.config(state="disabled")


if __name__ == "__main__":
    app = SchemaViewer()
    app.mainloop()
