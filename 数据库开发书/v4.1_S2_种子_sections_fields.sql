-- v4.1 重塑 · S2 种子脚本：schema_meta + sections（8 表头）+ fields（16 空全枚举）
-- 来源：从 medical_archive_v4_样例.db（v4.1 定稿库）导出，与验收脚本 21 项口径一致
-- 版本：v4.1-S2　生成日期：2026-11-18　（旧版 v4.0-S2 已移入 _历史/，勿混用）
-- 用法：建库后执行本脚本。幂等（INSERT OR IGNORE），可重复执行。
-- 注意：options 由 S3/S4 从 ICD-10 派生 + ICD-9-CM3 + WS/T 值域灌入，不在本脚本范围。

PRAGMA foreign_keys = OFF;
BEGIN TRANSACTION;

-- ==== schema_meta ====
INSERT OR IGNORE INTO schema_meta (version, applied_at) VALUES ('v4.1', '2026-11-17T08:41:38');

-- ==== sections ====
INSERT OR IGNORE INTO sections (id, section_key, name_cn, name_en, parent_id, level, sort_order, note) VALUES (1, 'inscription', '铭文部分：', 'Inscription', NULL, 1, 1, '姓名/性别/民族/身份证号/常住地址/档案编号/建档日期，仅用于密钥派生，不建字段与枚举');
INSERT OR IGNORE INTO sections (id, section_key, name_cn, name_en, parent_id, level, sort_order, note) VALUES (2, 'storage', '存储部分：', 'Storage', NULL, 1, 2, '其下六个二级标题为挂载点，空的枚举项在此展开');
INSERT OR IGNORE INTO sections (id, section_key, name_cn, name_en, parent_id, level, sort_order, note) VALUES (3, 'past_and_family_history', '一、既往史与家族史', 'Past and Family History', 2, 2, 3, '对应手绘稿区块 1；疾病词条来源 ICD-10，手术词条来源 ICD-9-CM3 3.0，高危因素来源 WS/T 364.5');
INSERT OR IGNORE INTO sections (id, section_key, name_cn, name_en, parent_id, level, sort_order, note) VALUES (4, 'allergy_history', '二、过敏史', 'Allergy History', 2, 2, 4, '对应手绘稿区块 2；药物过敏挂 Z88，致敏原物质无国标，自建院内字典');
INSERT OR IGNORE INTO sections (id, section_key, name_cn, name_en, parent_id, level, sort_order, note) VALUES (5, 'personal_lifestyle', '三、个人生活史', 'Personal Lifestyle', 2, 2, 5, '对应手绘稿区块 3；吸烟/饮酒值域来源 WS/T 364.5');
INSERT OR IGNORE INTO sections (id, section_key, name_cn, name_en, parent_id, level, sort_order, note) VALUES (6, 'disease_classification', '四、疾病分类', 'Disease Classification', 2, 2, 6, '对应手绘稿区块「疾病」；选项由 icd_codes.chapter_code 派生 22 章');
INSERT OR IGNORE INTO sections (id, section_key, name_cn, name_en, parent_id, level, sort_order, note) VALUES (7, 'symptoms', '五、症状表现', 'Symptoms', 2, 2, 7, '对应手绘稿区块「症状表现·伴随症状」；词条来源 ICD-10 第 XVIII 章 + 自建常见症状');
INSERT OR IGNORE INTO sections (id, section_key, name_cn, name_en, parent_id, level, sort_order, note) VALUES (8, 'physical_examination', '六、体格检查', 'Physical Examination', 2, 2, 8, '对应手绘稿区块「体格检查异常」；词条来源 ICD-10 第 XVIII 章体征 + 自建');

-- ==== fields ====
INSERT OR IGNORE INTO fields (id, field_key, name_cn, name_en, section_id, value_type, is_multi, is_required, derive_from, unit_cn, unit_en, sort_order, note) VALUES (1, 'past_medical_history', '既往患病史', 'Past Medical History', 3, 'multi_enum', 1, 1, '', '', '', 1, '词条来源：ICD-10 常见病（约 150 条）');
INSERT OR IGNORE INTO fields (id, field_key, name_cn, name_en, section_id, value_type, is_multi, is_required, derive_from, unit_cn, unit_en, sort_order, note) VALUES (2, 'surgery_history', '手术史', 'Surgical History', 3, 'multi_enum', 1, 1, '', '', '', 2, '词条来源：手术操作分类代码国家临床版 3.0（ICD-9-CM3，14,518 条中筛常见手术）');
INSERT OR IGNORE INTO fields (id, field_key, name_cn, name_en, section_id, value_type, is_multi, is_required, derive_from, unit_cn, unit_en, sort_order, note) VALUES (3, 'trauma_history', '外伤史', 'Trauma History', 3, 'multi_enum', 1, 1, '', '', '', 3, '词条来源：ICD-10 第 XIX 章（S/T 损伤中毒）常见损伤');
INSERT OR IGNORE INTO fields (id, field_key, name_cn, name_en, section_id, value_type, is_multi, is_required, derive_from, unit_cn, unit_en, sort_order, note) VALUES (4, 'family_history', '家族史', 'Family History', 3, 'multi_enum', 1, 1, '', '', '', 4, '复用既往患病史的疾病项，option_key 加 family__ 前缀，共用同一 icd_code');
INSERT OR IGNORE INTO fields (id, field_key, name_cn, name_en, section_id, value_type, is_multi, is_required, derive_from, unit_cn, unit_en, sort_order, note) VALUES (5, 'high_risk_factor', '高危因素', 'High-Risk Factor', 3, 'multi_enum', 1, 1, '', '', '', 5, '词条来源：WS/T 364.5-2023 健康危险因素值域代码（option_key 加 wst_ 前缀）');
INSERT OR IGNORE INTO fields (id, field_key, name_cn, name_en, section_id, value_type, is_multi, is_required, derive_from, unit_cn, unit_en, sort_order, note) VALUES (6, 'allergy_source', '过敏原', 'Allergen', 4, 'multi_enum', 1, 1, '', '', '', 1, '致敏原物质国内无国标，自建院内字典（约 20 条）；过敏诊断走 ICD-10');
INSERT OR IGNORE INTO fields (id, field_key, name_cn, name_en, section_id, value_type, is_multi, is_required, derive_from, unit_cn, unit_en, sort_order, note) VALUES (7, 'allergy_reaction', '过敏反应', 'Allergic Reaction', 4, 'multi_enum', 1, 1, '', '', '', 2, '过敏性鼻炎 J30、哮喘 J45、荨麻疹 L50 等挂 ICD-10，其余自建');
INSERT OR IGNORE INTO fields (id, field_key, name_cn, name_en, section_id, value_type, is_multi, is_required, derive_from, unit_cn, unit_en, sort_order, note) VALUES (8, 'drug_allergy', '药物过敏史', 'Drug Allergy History', 4, 'multi_enum', 1, 1, '', '', '', 3, '词条来源：ICD-10 第 XXI 章 Z88.0–Z88.9（9 类药物过敏）');
INSERT OR IGNORE INTO fields (id, field_key, name_cn, name_en, section_id, value_type, is_multi, is_required, derive_from, unit_cn, unit_en, sort_order, note) VALUES (9, 'smoking_history', '吸烟史', 'Smoking History', 5, 'enum', 0, 1, '', '', '', 1, '值域来源：WS/T 364.5-2023 吸烟状态代码');
INSERT OR IGNORE INTO fields (id, field_key, name_cn, name_en, section_id, value_type, is_multi, is_required, derive_from, unit_cn, unit_en, sort_order, note) VALUES (10, 'alcohol_history', '饮酒史', 'Alcohol History', 5, 'enum', 0, 1, '', '', '', 2, '值域来源：WS/T 364.5-2023 饮酒频率代码');
INSERT OR IGNORE INTO fields (id, field_key, name_cn, name_en, section_id, value_type, is_multi, is_required, derive_from, unit_cn, unit_en, sort_order, note) VALUES (11, 'diet_habit', '饮食情况', 'Dietary Habit', 5, 'multi_enum', 1, 1, '', '', '', 3, '自建固定词条（哺乳方式、辅食、挑食等）');
INSERT OR IGNORE INTO fields (id, field_key, name_cn, name_en, section_id, value_type, is_multi, is_required, derive_from, unit_cn, unit_en, sort_order, note) VALUES (12, 'sleep_habit', '作息情况', 'Sleep Pattern', 5, 'multi_enum', 1, 1, '', '', '', 4, '自建固定词条（规律/不规律、午睡、入睡时间等）');
INSERT OR IGNORE INTO fields (id, field_key, name_cn, name_en, section_id, value_type, is_multi, is_required, derive_from, unit_cn, unit_en, sort_order, note) VALUES (13, 'disease_category', '疾病分类', 'Disease Classification', 6, 'multi_enum', 1, 1, '', '', '', 1, '选项由 icd_codes.chapter_code 派生 ICD 22 章，source=derived');
INSERT OR IGNORE INTO fields (id, field_key, name_cn, name_en, section_id, value_type, is_multi, is_required, derive_from, unit_cn, unit_en, sort_order, note) VALUES (14, 'chief_complaint', '症状表现（主诉）', 'Chief Complaint', 7, 'multi_enum', 1, 1, '', '', '', 1, '词条来源：ICD-10 第 XVIII 章（877 条症状体征）+ 自建常见症状');
INSERT OR IGNORE INTO fields (id, field_key, name_cn, name_en, section_id, value_type, is_multi, is_required, derive_from, unit_cn, unit_en, sort_order, note) VALUES (15, 'accompanying_symptom', '伴随症状', 'Accompanying Symptom', 7, 'multi_enum', 1, 0, '', '', '', 2, '复用症状表现的词条集合，option_key 加 history__ 前缀');
INSERT OR IGNORE INTO fields (id, field_key, name_cn, name_en, section_id, value_type, is_multi, is_required, derive_from, unit_cn, unit_en, sort_order, note) VALUES (16, 'positive_signs', '体格检查异常（阳性体征）', 'Positive Signs', 8, 'multi_enum', 1, 0, '', '', '', 1, '词条来源：ICD-10 第 XVIII 章体征类 + 自建；手绘稿标题「体格检查异常」');

COMMIT;

PRAGMA foreign_keys = ON;
