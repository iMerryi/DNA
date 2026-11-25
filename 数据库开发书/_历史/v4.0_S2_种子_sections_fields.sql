-- =====================================================================
-- v4.0 重塑 · S2 种子脚本：sections（14 条表头）+ fields（42 个空）
-- 依据：《10.17 医疗信息框架》14 个表头、43 处「· xxx：」，其中
--       「按病症词典分类」与「按系统分类」合并为一个空 → 42 条
-- 目标库：SQLite 3（medical_archive.db）；幂等，可重复执行
-- 版本：v4.0-S2　生成日期：2026-11-11
-- =====================================================================

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------
-- 表1　sections 表头
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sections (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    section_key TEXT    NOT NULL UNIQUE,
    name_cn     TEXT    NOT NULL,
    name_en     TEXT    NOT NULL,
    parent_id   INTEGER REFERENCES sections(id) ON DELETE RESTRICT,
    level       INTEGER NOT NULL CHECK (level IN (1, 2, 3)),
    sort_order  INTEGER NOT NULL,
    note        TEXT    NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_sections_parent ON sections(parent_id);
CREATE INDEX IF NOT EXISTS idx_sections_sort   ON sections(level, sort_order);

-- ---------------------------------------------------------------------
-- 表2　fields 空定义
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fields (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    field_key      TEXT    NOT NULL UNIQUE,
    name_cn        TEXT    NOT NULL,
    name_en        TEXT    NOT NULL,
    section_id     INTEGER NOT NULL REFERENCES sections(id) ON DELETE RESTRICT,
    value_type     TEXT    NOT NULL CHECK (value_type IN
                       ('multi_enum', 'enum', 'text', 'date', 'number', 'number_group')),
    is_multi       INTEGER NOT NULL DEFAULT 0 CHECK (is_multi IN (0, 1)),
    is_required    INTEGER NOT NULL DEFAULT 1 CHECK (is_required IN (0, 1)),
    derive_from    TEXT    NOT NULL DEFAULT '',
    unit_cn        TEXT    NOT NULL DEFAULT '',
    unit_en        TEXT    NOT NULL DEFAULT '',
    sort_order     INTEGER NOT NULL,
    note           TEXT    NOT NULL DEFAULT '',
    UNIQUE (section_id, sort_order)
);

CREATE INDEX IF NOT EXISTS idx_fields_section ON fields(section_id);
CREATE INDEX IF NOT EXISTS idx_fields_vtype   ON fields(value_type);

-- ---------------------------------------------------------------------
-- 1) 14 个表头：先顶级，再二级，再三級，保证 parent_id 可解析
-- ---------------------------------------------------------------------
INSERT INTO sections (section_key, name_cn, name_en, parent_id, level, sort_order, note) VALUES
  ('inscription', '铭文部分：', 'Inscription', NULL, 1, 1,
   '姓名/性别/民族/身份证号/常住地址/档案编号/建档日期，仅用于密钥派生，不建字段与枚举'),
  ('storage',     '存储部分：', 'Storage',     NULL, 1, 2,
   '其下三级标题为挂载点，空的枚举项在此展开')
ON CONFLICT(section_key) DO UPDATE SET
  name_cn = excluded.name_cn, name_en = excluded.name_en,
  level = excluded.level, sort_order = excluded.sort_order, note = excluded.note;

INSERT INTO sections (section_key, name_cn, name_en, parent_id, level, sort_order, note)
SELECT 'patient_background', '一、患者基础与背景信息类（不可或缺）',
       'Patient Background Information (Essential)',
       (SELECT id FROM sections WHERE section_key = 'storage'), 2, 3, ''
UNION ALL
SELECT 'clinical_history', '二、临床主诉与现病史类（症状的延伸）',
       'Clinical Presentation and History of Present Illness',
       (SELECT id FROM sections WHERE section_key = 'storage'), 2, 4, ''
UNION ALL
SELECT 'followup', '三、随访记录类（动态追踪）',
       'Follow-up Records (Dynamic Tracking)',
       (SELECT id FROM sections WHERE section_key = 'storage'), 2, 5, ''
ON CONFLICT(section_key) DO UPDATE SET
  name_cn = excluded.name_cn, name_en = excluded.name_en,
  parent_id = excluded.parent_id, level = excluded.level,
  sort_order = excluded.sort_order, note = excluded.note;

INSERT INTO sections (section_key, name_cn, name_en, parent_id, level, sort_order, note)
SELECT 'past_and_family_history', '1.既往史/家族史：', 'Past Medical and Family History',
       (SELECT id FROM sections WHERE section_key = 'patient_background'), 3, 6,
       '不仅是高危因素，还包括既往患病史、手术史、外伤史、输血史、预防接种史'
UNION ALL
SELECT 'allergy_history', '2.过敏史：', 'Allergy History',
       (SELECT id FROM sections WHERE section_key = 'patient_background'), 3, 7,
       '花粉、青霉素……'
UNION ALL
SELECT 'personal_lifestyle', '3.个人生活史：', 'Personal Lifestyle',
       (SELECT id FROM sections WHERE section_key = 'patient_background'), 3, 8,
       '吸烟饮酒史的具体量化、饮食作息等诱因'
UNION ALL
SELECT 'reproductive_history', '4.婚育史/月经史：', 'Marital, Reproductive and Menstrual History',
       (SELECT id FROM sections WHERE section_key = 'patient_background'), 3, 9,
       '女性患者必备'
UNION ALL
SELECT 'birth_and_family', '5.出生史与家庭信息：', 'Birth History and Family Information',
       (SELECT id FROM sections WHERE section_key = 'patient_background'), 3, 10,
       '胎龄、出生体重、出生身长、Apgar 评分为实测数值，不设候选词条'
UNION ALL
SELECT 'disease_classification', '1.疾病分类：', 'Disease Classification',
       (SELECT id FROM sections WHERE section_key = 'clinical_history'), 3, 11,
       '原文档两行（按病症词典分类 8 项 / 按系统分类 10 项）合并为一个空，选项为 ICD 22 章'
UNION ALL
SELECT 'symptoms', '2.症状表现：', 'Symptom Manifestation',
       (SELECT id FROM sections WHERE section_key = 'clinical_history'), 3, 12,
       '患者最主要症状如精神/食欲/睡眠/大小便等、起病时间、缓急、伴随症状、持续时间等'
UNION ALL
SELECT 'physical_examination', '3.体格检查（体征）：', 'Physical Examination (Signs)',
       (SELECT id FROM sections WHERE section_key = 'clinical_history'), 3, 13,
       '生命体征如体温、脉搏、呼吸、血压；专科查体如心肺听诊、腹部触诊等阳/阴性体征'
UNION ALL
SELECT 'followup_record', '1.随访记录：', 'Follow-up Record',
       (SELECT id FROM sections WHERE section_key = 'followup'), 3, 14, ''
ON CONFLICT(section_key) DO UPDATE SET
  name_cn = excluded.name_cn, name_en = excluded.name_en,
  parent_id = excluded.parent_id, level = excluded.level,
  sort_order = excluded.sort_order, note = excluded.note;

-- ---------------------------------------------------------------------
-- 2) 42 个空
--    排序号 = 文档中的先后；UNIQUE(section_id, sort_order) 保证不串位
-- ---------------------------------------------------------------------
INSERT INTO fields (field_key, name_cn, name_en, section_id, value_type, is_multi,
                    is_required, derive_from, unit_cn, unit_en, sort_order, note)
SELECT v.field_key, v.name_cn, v.name_en,
       (SELECT id FROM sections WHERE section_key = v.section_key),
       v.value_type, v.is_multi, v.is_required, v.derive_from,
       v.unit_cn, v.unit_en, v.sort_order, v.note
FROM (
  -- 1.既往史/家族史 -------------------------------------------------
  SELECT 'past_medical_history' AS field_key, '既往患病史' AS name_cn,
         'Past Medical History' AS name_en, 'past_and_family_history' AS section_key,
         'multi_enum' AS value_type, 1 AS is_multi, 1 AS is_required, '' AS derive_from,
         '' AS unit_cn, '' AS unit_en, 1 AS sort_order, '' AS note
  UNION ALL SELECT 'surgery_history', '手术史', 'Surgical History', 'past_and_family_history',
         'multi_enum', 1, 1, '', '', '', 2, 'ICD 手术操作码不在本码表内，词条自建'
  UNION ALL SELECT 'trauma_history', '外伤史', 'Trauma History', 'past_and_family_history',
         'multi_enum', 1, 1, '', '', '', 3, '自建 + ICD 第 XIX 章（S/T 损伤中毒）'
  UNION ALL SELECT 'transfusion_history', '输血史', 'Transfusion History', 'past_and_family_history',
         'enum', 0, 1, '', '', '', 4, '无 / 不详；有输血者登记血型与血液成分'
  UNION ALL SELECT 'vaccination_history', '预防接种史', 'Vaccination History', 'past_and_family_history',
         'enum', 0, 1, '', '', '', 5, '按国家免疫规划接种 / 有漏种 / 不详'
  UNION ALL SELECT 'family_history', '家族史', 'Family History', 'past_and_family_history',
         'multi_enum', 1, 1, '', '', '', 6, '疾病项与既往患病史同码不同键，前缀 family__'
  UNION ALL SELECT 'high_risk_factor', '高危因素', 'High-Risk Factor', 'past_and_family_history',
         'multi_enum', 1, 1, '', '', '', 7, '新生儿与妊娠相关，ICD 无对应分类，自建'
  -- 2.过敏史 --------------------------------------------------------
  UNION ALL SELECT 'allergy_source', '过敏原', 'Allergen', 'allergy_history',
         'multi_enum', 1, 1, '', '', '', 1, 'ICD 无过敏原分类，自建；可挂 Z88'
  UNION ALL SELECT 'allergy_reaction', '过敏反应', 'Allergic Reaction', 'allergy_history',
         'multi_enum', 1, 1, '', '', '', 2, '过敏性鼻炎/哮喘/荨麻疹等可挂 ICD 诊断'
  UNION ALL SELECT 'drug_allergy', '药物过敏史', 'Drug Allergy History', 'allergy_history',
         'multi_enum', 1, 1, '', '', '', 3, '可挂 Z88.0–Z88.9'
  -- 3.个人生活史 ----------------------------------------------------
  UNION ALL SELECT 'smoking_history', '吸烟史', 'Smoking History', 'personal_lifestyle',
         'enum', 0, 1, '', '', '', 1, ''
  UNION ALL SELECT 'alcohol_history', '饮酒史', 'Alcohol History', 'personal_lifestyle',
         'enum', 0, 1, '', '', '', 2, ''
  UNION ALL SELECT 'diet_habit', '饮食情况', 'Dietary Habit', 'personal_lifestyle',
         'multi_enum', 1, 1, '', '', '', 3, ''
  UNION ALL SELECT 'sleep_habit', '作息情况', 'Sleep Pattern', 'personal_lifestyle',
         'multi_enum', 1, 1, '', '', '', 4, ''
  -- 4.婚育史/月经史 -------------------------------------------------
  UNION ALL SELECT 'marriage_history', '婚育史', 'Marital and Childbearing History', 'reproductive_history',
         'multi_enum', 1, 0, '', '', '', 1, '男性患者留空'
  UNION ALL SELECT 'menstrual_history', '月经史', 'Menstrual History', 'reproductive_history',
         'multi_enum', 1, 0, '', '', '', 2, '男性患者与绝经后按实际情况留空'
  -- 5.出生史与家庭信息 ----------------------------------------------
  UNION ALL SELECT 'birth_date', '出生日期', 'Date of Birth', 'birth_and_family',
         'date', 0, 1, '', '', '', 1, '按出生医学证明登记'
  UNION ALL SELECT 'abo_blood_type', 'ABO 血型', 'ABO Blood Group', 'birth_and_family',
         'enum', 0, 0, '', '', '', 2, ''
  UNION ALL SELECT 'rh_blood_type', 'Rh 血型', 'Rh Blood Group', 'birth_and_family',
         'enum', 0, 0, '', '', '', 3, ''
  UNION ALL SELECT 'delivery_org', '建档机构 / 分娩机构', 'Registration / Delivery Institution', 'birth_and_family',
         'text', 0, 0, '', '', '', 4, '按机构全称登记'
  UNION ALL SELECT 'parent_name', '父亲姓名 / 母亲姓名', 'Parent Name', 'birth_and_family',
         'text', 0, 0, '', '', '', 5, '按身份证登记'
  UNION ALL SELECT 'parent_phone', '父亲电话 / 母亲电话 / 联系电话', 'Parent / Contact Phone', 'birth_and_family',
         'text', 0, 0, '', '', '', 6, '按可接通号码登记'
  UNION ALL SELECT 'hukou_address', '户籍地址', 'Registered Residence Address', 'birth_and_family',
         'text', 0, 0, '', '', '', 7, '按户口簿登记'
  -- 1.疾病分类（合并） ----------------------------------------------
  UNION ALL SELECT 'disease_category', '疾病分类', 'Disease Classification', 'disease_classification',
         'multi_enum', 1, 1, '', '', '', 1, '选项由 icd_codes.chapter_code 派生 22 章'
  UNION ALL SELECT 'disease_result', '病症结果', 'Disease Result', 'disease_classification',
         'multi_enum', 1, 1, '', '', '', 2, '阴性 / 阳性 / 未查'
  -- 2.症状表现 ------------------------------------------------------
  UNION ALL SELECT 'chief_complaint', '主诉', 'Chief Complaint', 'symptoms',
         'multi_enum', 1, 1, '', '', '', 1, 'ICD 第 XVIII 章症状项 + 自建常见症状'
  UNION ALL SELECT 'symptom_onset', '起病时间', 'Onset Date', 'symptoms',
         'date', 0, 1, '', '', '', 2, '按起病当日登记'
  UNION ALL SELECT 'symptom_severity', '缓急程度', 'Onset Severity', 'symptoms',
         'enum', 0, 0, '', '', '', 3, '急性 / 慢性 / 反复发作'
  UNION ALL SELECT 'symptom_duration', '持续时间', 'Duration', 'symptoms',
         'text', 0, 0, '', '', '', 4, '按起病时间与就诊时间的间隔登记，如「3 天」'
  UNION ALL SELECT 'accompanying_symptom', '伴随症状', 'Accompanying Symptom', 'symptoms',
         'multi_enum', 1, 0, '', '', '', 5, '复用主诉的症状项，前缀 history__'
  UNION ALL SELECT 'mental_state', '精神状态', 'Mental State', 'symptoms',
         'enum', 0, 0, '', '', '', 6, ''
  UNION ALL SELECT 'appetite', '食欲', 'Appetite', 'symptoms',
         'enum', 0, 0, '', '', '', 7, ''
  UNION ALL SELECT 'sleep_status', '睡眠', 'Sleep Status', 'symptoms',
         'enum', 0, 0, '', '', '', 8, ''
  UNION ALL SELECT 'bowel_bladder', '大小便', 'Bowel and Bladder', 'symptoms',
         'multi_enum', 1, 0, '', '', '', 9, ''
  -- 3.体格检查（体征） ----------------------------------------------
  UNION ALL SELECT 'vital_signs', '生命体征', 'Vital Signs', 'physical_examination',
         'number_group', 0, 0, '', '', '', 1, '体温 ℃ / 脉搏 次·min⁻¹ / 呼吸 次·min⁻¹ / 血压 mmHg，按实测值登记'
  UNION ALL SELECT 'special_exam', '专科查体', 'Specialist Examination', 'physical_examination',
         'multi_enum', 1, 0, '', '', '', 2, '查体部位与项目，自建'
  UNION ALL SELECT 'positive_signs', '阳性体征', 'Positive Signs', 'physical_examination',
         'multi_enum', 1, 0, '', '', '', 3, 'ICD 第 XVIII 章体征 + 自建'
  UNION ALL SELECT 'negative_signs', '阴性体征', 'Negative Signs', 'physical_examination',
         'multi_enum', 1, 0, 'positive_signs', '', '', 4,
         '由阳性体征取反派生；无异常时留空，不人工维护第二套词条'
  -- 1.随访记录 ------------------------------------------------------
  UNION ALL SELECT 'followup_date', '随访日期', 'Follow-up Date', 'followup_record',
         'date', 0, 1, '', '', '', 1, '多次随访按时间顺序编号'
  UNION ALL SELECT 'current_weight', '当前体重', 'Current Weight', 'followup_record',
         'number', 0, 0, '', 'kg', 'kg', 2, '按每次随访实测值登记'
  UNION ALL SELECT 'current_temperature', '当前体温', 'Current Temperature', 'followup_record',
         'number', 0, 0, '', '℃', '°C', 3, '按每次随访实测值登记'
  UNION ALL SELECT 'followup_note', '随访备注', 'Follow-up Note', 'followup_record',
         'text', 0, 0, '', '', '', 4, '记录本次随访的病情变化与处置'
) AS v
WHERE NOT EXISTS (SELECT 1 FROM fields f WHERE f.field_key = v.field_key);

-- ---------------------------------------------------------------------
-- 3) 自检（执行后应输出：14 / 42 / 43 / 0 差异）
-- ---------------------------------------------------------------------
SELECT '--- S2 自检 ---' AS check_point;
SELECT '表头条数' AS item, COUNT(*) AS actual, 14 AS expected FROM sections
UNION ALL SELECT '空条数',  COUNT(*), 42 FROM fields
UNION ALL SELECT '文档原文空数', 43, 43
UNION ALL SELECT '归属缺失的空', COUNT(*), 0 FROM fields f
        LEFT JOIN sections s ON s.id = f.section_id WHERE s.id IS NULL
UNION ALL SELECT 'parent 悬空的表头', COUNT(*), 0 FROM sections c
        WHERE c.parent_id IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM sections p WHERE p.id = c.parent_id)
UNION ALL SELECT 'derive_from 指向不存在的空', COUNT(*), 0 FROM fields f
        WHERE f.derive_from <> ''
          AND NOT EXISTS (SELECT 1 FROM fields p WHERE p.field_key = f.derive_from);

SELECT '--- 各表头下的空 ---' AS check_point;
SELECT s.sort_order AS 序, s.name_cn AS 表头, f.sort_order AS 内序,
       f.name_cn AS 空, f.value_type AS 类型, f.is_required AS 必填
FROM fields f JOIN sections s ON s.id = f.section_id
ORDER BY s.sort_order, f.sort_order;
