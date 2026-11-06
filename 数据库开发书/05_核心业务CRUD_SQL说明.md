# 核心业务 CRUD SQL 说明

> 对应 `DataStore` 接口的内部 SQL 实现。每条给出：业务场景 → SQL → 说明。
> 约定：所有写操作在事务内完成；所有连接执行 `PRAGMA foreign_keys = ON`。

---

## 1. 保存档案（`save_record`）—— 单事务三段写入

**场景**：前端点"保存"，一条档案 = 身份列 1 行 + 内容条目 N 行 + 病症结果 M 行。

```sql
BEGIN TRANSACTION;

-- ① 身份列：存在则更新，不存在则插入（record_id 由应用层生成）
INSERT INTO archive_records
    (record_id, archive_number, name, gender, nation, id_number,
     residence_address, create_date, source, created_at, updated_at)
VALUES
    (:record_id, :archive_number, :name, :gender, :nation, :id_number,
     :residence_address, :create_date, :source,
     datetime('now','localtime'), datetime('now','localtime'))
ON CONFLICT(record_id) DO UPDATE SET
    archive_number = excluded.archive_number,
    name           = excluded.name,
    gender         = excluded.gender,
    nation         = excluded.nation,
    id_number      = excluded.id_number,
    residence_address = excluded.residence_address,
    create_date    = excluded.create_date,
    updated_at     = datetime('now','localtime');

-- ② 内容条目：先清后插（整条替换语义，"写入即覆盖"）
DELETE FROM record_entries WHERE record_id = :record_id;

INSERT INTO record_entries
    (record_id, field_key, seq, value_cn, value_en, value_num, updated_at)
VALUES
    (:record_id, :field_key, :seq, :value_cn, :value_en, :value_num,
     datetime('now','localtime'));
-- ↑ 应用层循环执行 N 次（executemany）

-- ③ 病症结果：同上，先清后插
DELETE FROM record_diseases WHERE record_id = :record_id;

INSERT INTO record_diseases
    (record_id, disease_term_id, result_cn, result_en, seq, checked_at, updated_at)
VALUES
    (:record_id, :term_id, :result_cn, :result_en, :seq, :checked_at,
     datetime('now','localtime'));

COMMIT;
-- 任一步失败 → ROLLBACK，保证档案不会出现"半条"
```

**说明**：
- `record_id` 已存在时走 `ON CONFLICT ... DO UPDATE`（不用 `INSERT OR REPLACE`，避免自增主键漂移）；
- 条目"先清后插"即条目层物理覆盖（R7），不需要处理软删行复活；
- 写入前应用层按 R1 校验 `field_key` 已登记、按 R4 同步 `value_num`，未登记抛 `FieldKeyNotRegisteredError`。

---

## 2. 加载档案（`load_record`）—— 三段组装

```sql
-- ① 身份
SELECT * FROM archive_records
WHERE record_id = :record_id AND is_deleted = 0;

-- ② 内容条目（按分组与表单顺序排列）
SELECT e.field_key, e.seq, e.value_cn, e.value_en, e.value_num,
       d.section, d.label_cn, d.value_type, d.is_multi, d.unit_cn
FROM record_entries e
JOIN field_definitions d ON d.field_key = e.field_key
WHERE e.record_id = :record_id
ORDER BY d.section, d.sort_order, e.seq;

-- ③ 病症结果
SELECT t.term_key, t.chinese_name, t.english_name,
       r.result_cn, r.result_en, r.seq, r.checked_at
FROM record_diseases r
JOIN disease_terms t ON t.id = r.disease_term_id
WHERE r.record_id = :record_id
ORDER BY t.term_key, r.seq;
```

**说明**：三查询在应用层组装回 `ArchiveRecord` 对象；`JOIN` 字典带出 `label_cn`，界面直接显示中文标签。

---

## 3. 档案列表（`list_records`）—— 分页 + 关键词过滤

```sql
-- 总数（先查，用于分页控件）
SELECT COUNT(*) AS total
FROM archive_records
WHERE is_deleted = 0
  AND ( :keyword IS NULL
        OR name LIKE '%' || :keyword || '%'
        OR archive_number LIKE '%' || :keyword || '%'
        OR id_number LIKE '%' || :keyword || '%' );

-- 当前页（只取身份列，不 JOIN 条目表，避免 N+1）
SELECT record_id, archive_number, name, gender, nation,
       id_number, residence_address, create_date, source,
       created_at, updated_at
FROM archive_records
WHERE is_deleted = 0
  AND ( :keyword IS NULL
        OR name LIKE '%' || :keyword || '%'
        OR archive_number LIKE '%' || :keyword || '%'
        OR id_number LIKE '%' || :keyword || '%' )
ORDER BY created_at DESC
LIMIT :limit OFFSET :offset;
```

**说明**：返回 `(items, total)` 元组；keyword 只匹配身份三列，不扫键值表——这是身份字段保留物理列的直接收益。

---

## 4. 局部更新内容（`upsert_entries`）—— 不重建整条记录

**场景**：随访后只补录几项，不影响其它字段。

```sql
-- 逐条 upsert（应用层循环）
INSERT INTO record_entries
    (record_id, field_key, seq, value_cn, value_en, value_num, updated_at)
VALUES
    (:record_id, :field_key, :seq, :value_cn, :value_en, :value_num,
     datetime('now','localtime'))
ON CONFLICT(record_id, field_key, seq) DO UPDATE SET
    value_cn   = excluded.value_cn,
    value_en   = excluded.value_en,
    value_num  = excluded.value_num,
    updated_at = datetime('now','localtime');
```

**说明**：唯一约束 `(record_id, field_key, seq)` 就是 upsert 的冲突目标；未出现在本次 entries 里的字段保持原值。

---

## 5. 删除条目 / 删除档案

```sql
-- 删除单条内容（如删掉第 2 次随访的体重）：物理删除
DELETE FROM record_entries
WHERE record_id = :record_id AND field_key = :field_key AND seq = :seq;

-- 删除档案：软删除（医疗数据保留审计）
UPDATE archive_records
SET is_deleted = 1, updated_at = datetime('now','localtime')
WHERE record_id = :record_id AND is_deleted = 0;

-- 彻底删除档案（仅销毁/迁移场景）：必须按依赖顺序，否则被外键拒绝
-- ① 先清解码记录
DELETE FROM decode_records
WHERE dna_record_id IN (SELECT id FROM dna_sequences WHERE record_id = :record_id);

-- ② 再清 DNA 序列（该外键未设 CASCADE，会阻止直接删档案）
DELETE FROM dna_sequences WHERE record_id = :record_id;

-- ③ 最后删档案：record_entries / record_diseases 由 CASCADE 自动清理
DELETE FROM archive_records WHERE record_id = :record_id;
```

**说明**：
- 日常删除一律走软删除（`is_deleted=1`），物理删除只用于数据销毁或迁移；
- `record_entries`/`record_diseases` 对档案是 `ON DELETE CASCADE`；`dna_sequences` 未设 CASCADE，因此上一步漏做时 `DELETE archive_records` 会直接抛外键错误（不是产生孤儿行），这是刻意保留的审计保护。

---

## 6. 随访记录组装 —— 多值字段按 seq 对齐

**场景**：随访日期/体重/体温/备注四件套各是多值字段，按次数组装。

```sql
SELECT field_key, seq, value_cn, value_num
FROM record_entries
WHERE record_id = :record_id
  AND field_key IN ('followup_date','current_weight',
                    'current_temperature','followup_note')
ORDER BY seq, field_key;
```

应用层按 `seq` 分组：`seq=1` 的四行 → 第 1 次随访；`seq=2` → 第 2 次。不再使用 JSON 数组。

---

## 7. 病症结果写入与检索

```sql
-- 写入（先按中文名查词条 id，词条必须在词典内）
SELECT id, term_key FROM disease_terms
WHERE chinese_name = :chinese_name AND is_active = 1;

INSERT INTO record_diseases
    (record_id, disease_term_id, result_cn, result_en, seq, checked_at, updated_at)
VALUES
    (:record_id, :term_id, :result_cn, :result_en, :seq, :checked_at,
     datetime('now','localtime'))
ON CONFLICT(record_id, disease_term_id, seq) DO UPDATE SET
    result_cn = excluded.result_cn,
    result_en = excluded.result_en,
    checked_at = excluded.checked_at,
    updated_at = datetime('now','localtime');

-- 病症搜索（前端联想输入框）
SELECT id, term_key, chinese_name, english_name, category
FROM disease_terms
WHERE is_active = 1
  AND (chinese_name LIKE :kw OR english_name LIKE :kw)
ORDER BY chinese_name
LIMIT :limit;
```

---

## 8. DNA 序列：保存 / 取有效版本

```sql
-- 保存编码结果（新编码会使旧版本失效：同一事务两步）
UPDATE dna_sequences SET is_valid = 0
WHERE record_id = :record_id AND is_valid = 1;

INSERT INTO dna_sequences
    (record_id, dna_sequence, key_hash, cg_content, thermal_stability,
     padded_zeros, sequence_length, original_text, encoded_at,
     is_valid, payload_version, payload_mode)
VALUES
    (:record_id, :dna_sequence, :key_hash, :cg_content, :thermal_stability,
     :padded_zeros, :sequence_length, :original_text,
     datetime('now','localtime'), 1, 'v2', 'bilingual');

-- 取当前有效序列
SELECT * FROM dna_sequences
WHERE record_id = :record_id AND is_valid = 1
ORDER BY encoded_at DESC LIMIT 1;

-- 按序列反查（解码入口）
SELECT * FROM dna_sequences WHERE dna_sequence = :sequence;
```

---

## 9. DNA 载荷导出（编码输入的 SQL 部分）

**场景**：把一条档案拼成编码载荷 `{"v":"v2","record_id":...,"fields":{...},"diseases":[...]}`。

```sql
-- fields 部分：每个字段取 value_en（空则回退 value_cn）
SELECT e.field_key, e.seq,
       CASE WHEN e.value_en != '' THEN e.value_en ELSE e.value_cn END AS payload_value
FROM record_entries e
WHERE e.record_id = :record_id
ORDER BY e.field_key, e.seq;

-- diseases 部分：用不可变 term_key，不用可改的 english_name
SELECT t.term_key, r.result_en
FROM record_diseases r
JOIN disease_terms t ON t.id = r.disease_term_id
WHERE r.record_id = :record_id;
```

应用层将 fields 组装为字典（多值字段为有序数组，顺序由 seq 决定），再 `json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))` 得到纯 ASCII 载荷。

---

## 10. 解码回填校验

```sql
-- 字典里不存在的 field_key / term_key → 记纠错日志，不静默丢弃
SELECT field_key FROM field_definitions WHERE field_key = :key;

SELECT id, term_key FROM disease_terms WHERE term_key = :key;
```

---

## 11. 统计（`get_statistics`）

```sql
SELECT
    (SELECT COUNT(*) FROM archive_records WHERE is_deleted = 0)              AS archive_count,
    (SELECT COUNT(*) FROM record_entries e
       JOIN archive_records a ON a.record_id = e.record_id
      WHERE a.is_deleted = 0)                                                 AS entry_count,
    (SELECT COUNT(*) FROM disease_terms WHERE is_active = 1)                  AS term_count,
    (SELECT COUNT(*) FROM dna_sequences WHERE is_valid = 1)                   AS valid_dna_count,
    (SELECT COUNT(*) FROM decode_records)                                     AS decode_count;
```

**说明**：`entry_count` 必须与 `archive_count` 同口径（排除软删档案），否则列表显示 N 条档案、统计却报出更多条目，数字对不上。

---

## 12. 备份与恢复

```sql
-- 备份（SQLite 在线备份 API，或直接文件拷贝）
VACUUM INTO :backup_path;    -- 生成紧凑的一致性快照，不锁写

-- 恢复 = 用备份文件替换当前库文件；恢复后执行：
PRAGMA integrity_check;      -- 期望返回 ok
SELECT * FROM schema_meta;   -- 核对结构版本
```

---

## 13. 账号与操作日志（v3.0 新增）

**场景**：注册、登录校验、归属过滤、写审计日志。

### 13.1 注册与登录

```sql
-- 注册：先转小写再判重（SQLite 的 UNIQUE 不区分大小写，必须应用层先 normalize）
INSERT INTO users (username, password_hash, display_name, role, created_at)
VALUES (:username_lower, :password_hash, :display_name, :role, datetime('now', 'localtime'));
-- username 撞 UNIQUE → 捕获 IntegrityError 返回 "用户名已存在"

-- 登录校验：一次查出，比对哈希；不区分"用户不存在"与"密码错误"
SELECT id, username, display_name, role, is_active, password_hash
FROM users
WHERE username = :username_lower;
-- Python 侧: is_active=0 拒绝；pbkdf2 校验通过后：
UPDATE users SET last_login_at = datetime('now', 'localtime') WHERE id = :user_id;
```

**密码哈希（应用层，不是 SQL）**：

```python
import hashlib, os, secrets

def hash_password(plain: str) -> str:
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac('sha256', plain.encode(), salt.encode(), 200_000)
    return f"pbkdf2$200000${salt}${h.hex()}"

def verify_password(plain: str, stored: str) -> bool:
    _, iters, salt, hexhash = stored.split('$')
    h = hashlib.pbkdf2_hmac('sha256', plain.encode(), salt.encode(), int(iters))
    return secrets.compare_digest(h.hex(), hexhash)   # 常量时间比较，防时序侧信道
```

### 13.2 档案归属过滤（`list_records` 的 v3.0 语义）

```sql
-- owner_id 为 NULL：看全部（admin / 单用户模式）
-- owner_id 给定：只看自己的（普通用户默认视图）
SELECT a.*, COUNT(e.id) AS entry_count
FROM archive_records a
LEFT JOIN record_entries e ON e.record_id = a.record_id
WHERE a.is_deleted = 0
  AND (:owner_id IS NULL OR a.owner_id = :owner_id)
  AND (:keyword IS NULL OR a.name LIKE '%' || :keyword || '%')
GROUP BY a.record_id
ORDER BY a.created_at DESC
LIMIT :limit OFFSET :offset;

SELECT COUNT(*) FROM archive_records
WHERE is_deleted = 0
  AND (:owner_id IS NULL OR owner_id = :owner_id)
  AND (:keyword IS NULL OR name LIKE '%' || :keyword || '%');
```

### 13.3 写操作日志（`log_activity`）

```sql
INSERT INTO user_activity_log (user_id, action, target_record_id, detail, created_at)
VALUES (:user_id, :action, :target_record_id, :detail, datetime('now', 'localtime'));
```

**要点**：

- `action` 只允许十枚举，CHECK 约束兜底；
- **调用侧用 try/except 包住**：日志失败不能让保存档案失败；同一连接 + WAL 模式，避免 `database is locked` 导致日志被静默丢弃；
- 查询历史（`list_activity`）：

```sql
SELECT l.*, u.username
FROM user_activity_log l
LEFT JOIN users u ON u.id = l.user_id
WHERE (:user_id IS NULL OR l.user_id = :user_id)
  AND (:action  IS NULL OR l.action = :action)
ORDER BY l.created_at DESC, l.id DESC
LIMIT :limit OFFSET :offset;
```

### 13.4 归属校验的边界（如实说明）

`save_record` / `list_records` 带归属参数，但 `load_record` / `update_record` / `delete_record` **不校验归属**——知道 `record_id` 就能读写。这是单机应用的取舍：账号解决"数据是谁的"，不解决"防别人偷看"。答辩口径：**数据归属区分，不是权限控制**。
