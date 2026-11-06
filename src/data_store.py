"""
DataStore 数据持久层 v3.0
依据：docs/modules/database_master_design.md（医疗档案数据库主设计书 v3.0）
- 9 张表：schema_meta / users / archive_records / field_definitions /
  record_entries / record_diseases / disease_terms / dna_sequences /
  decode_records / user_activity_log
- 内容键值化：record_entries 一行一个字段取值，中英双值
- 档案归属：archive_records.owner_id -> users.id
"""
import sqlite3
import os
import json
import uuid
import shutil
import hashlib
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple

import docx
import pdfplumber
from fuzzywuzzy import fuzz

SCHEMA_VERSION = "v3.0"

# ==========================================
# 1. 异常定义（设计书 §8.9）
# ==========================================
class DataStoreError(Exception):
    pass

class FieldKeyNotRegisteredError(DataStoreError):
    """field_key 未登记或已停用（R1）"""

class DuplicateSeqError(DataStoreError):
    """同一 field_key 下 seq 重复（R5）"""

class RecordNotFoundError(DataStoreError):
    pass

class GuestWriteForbiddenError(DataStoreError):
    """游客尝试落库（R8）"""

# ==========================================
# 2. 数据类
# ==========================================
@dataclass
class DiseaseTerm:
    id: int
    term_key: str
    chinese_name: str
    english_name: str
    category: str
    is_active: int = 1
    updated_at: str = ""

@dataclass
class FieldDefinition:
    id: int
    field_key: str
    section: str
    label_cn: str
    label_en: str
    value_type: str = "text"
    is_multi: int = 0
    is_active: int = 1
    unit_cn: str = ""
    unit_en: str = ""
    sort_order: int = 0
    is_legacy: int = 0

@dataclass
class ArchiveRecord:
    """完整档案：身份（物理列）+ 内容（键值）+ 病症结果"""
    id: Optional[int] = None
    record_id: str = ""
    owner_id: Optional[int] = None
    # 身份铭文（§5.1，7 个物理列）
    archive_number: str = ""
    name: str = ""
    gender: str = ""            # male / female / unknown
    nation: str = ""
    id_number: str = ""
    residence_address: str = ""
    create_date: str = ""       # 建档日期（业务日期）
    # 元数据
    source: str = "manual"
    created_at: str = ""
    updated_at: str = ""
    is_deleted: int = 0
    # 内容键值：[{field_key, seq, value_cn, value_en, value_num}]
    entries: List[Dict[str, Any]] = field(default_factory=list)
    # 病症结果：[{term_key, result_cn, result_en, seq, checked_at}]
    diseases: List[Dict[str, Any]] = field(default_factory=list)

@dataclass
class DNASequenceRecord:
    id: Optional[int] = None
    record_id: str = ""
    dna_sequence: str = ""
    key_hash: str = ""
    cg_content: float = 0.0
    thermal_stability: float = 0.0
    padded_zeros: int = 0
    sequence_length: int = 0
    original_text: str = ""
    encoded_at: str = ""
    is_valid: bool = True
    payload_version: str = "v3"
    payload_mode: str = "bilingual"

@dataclass
class DecodeRecord:
    id: Optional[int] = None
    dna_record_id: int = 0
    decoded_text: str = ""
    corrected_text: str = ""
    confidence: float = 0.0
    error_rate: float = 0.0
    correction_log: str = "{}"
    decoded_at: str = ""

# ==========================================
# 3. 字段字典种子（设计书 §5，60 个）
# (field_key, section, 中文, 英文, 类型, 多值, 单位cn, 单位en)
# ==========================================
FIELD_DEFINITIONS: List[Tuple] = [
    # --- birth 出生史与家庭信息（16）---
    ("birth_date",         "birth", "出生日期",          "date of birth",              "date",   0, "", ""),
    ("organization",       "birth", "建档机构",          "registering organization",   "text",   0, "", ""),
    ("abo_blood_type",     "birth", "ABO血型",           "ABO blood type",             "enum",   0, "", ""),
    ("rh_blood_type",      "birth", "Rh血型",            "Rh blood type",              "enum",   0, "", ""),
    ("father_name",        "birth", "父亲姓名",          "father's name",              "text",   0, "", ""),
    ("father_phone",       "birth", "父亲电话",          "father's phone",             "text",   0, "", ""),
    ("mother_name",        "birth", "母亲姓名",          "mother's name",              "text",   0, "", ""),
    ("mother_phone",       "birth", "母亲电话",          "mother's phone",             "text",   0, "", ""),
    ("gestational_weeks",  "birth", "胎龄（周）",        "gestational age (weeks)",    "number", 0, "周", "weeks"),
    ("birth_weight",       "birth", "出生体重",          "birth weight",               "number", 0, "g", "g"),
    ("birth_length",       "birth", "出生身长",          "birth length",               "number", 0, "cm", "cm"),
    ("delivery_org",       "birth", "分娩机构",          "delivery institution",       "text",   0, "", ""),
    ("apgar_1min",         "birth", "Apgar评分(1分钟)",  "Apgar score (1 min)",        "number", 0, "", ""),
    ("apgar_5min",         "birth", "Apgar评分(5分钟)",  "Apgar score (5 min)",        "number", 0, "", ""),
    ("contact_phone",      "birth", "联系电话",          "contact phone",              "text",   0, "", ""),
    ("hukou_address",      "birth", "户籍地址",          "registered residence",       "text",   0, "", ""),
    # --- history 既往史/家族史（7）---
    ("past_medical_history", "history", "既往患病史", "past medical history", "text", 0, "", ""),
    ("surgery_history",      "history", "手术史",     "surgical history",     "text", 0, "", ""),
    ("trauma_history",       "history", "外伤史",     "trauma history",       "text", 0, "", ""),
    ("transfusion_history",  "history", "输血史",     "transfusion history",  "text", 0, "", ""),
    ("vaccination_history",  "history", "预防接种史", "vaccination history",  "text", 0, "", ""),
    ("family_history",       "history", "家族史",     "family history",       "text", 0, "", ""),
    ("high_risk_factor",     "history", "高危因素",   "high-risk factor",     "text", 1, "", ""),
    # --- allergy 过敏史（3）---
    ("allergy_source",   "allergy", "过敏原",     "allergen",              "text", 1, "", ""),
    ("allergy_reaction", "allergy", "过敏反应",   "allergic reaction",     "text", 1, "", ""),
    ("drug_allergy",     "allergy", "药物过敏史", "drug allergy history",  "text", 0, "", ""),
    # --- lifestyle 个人生活史（4）---
    ("smoking_history", "lifestyle", "吸烟史（量化）", "smoking history (quantified)", "text", 0, "", ""),
    ("alcohol_history", "lifestyle", "饮酒史（量化）", "alcohol history (quantified)", "text", 0, "", ""),
    ("diet_habit",      "lifestyle", "饮食情况",       "diet habit",                   "text", 0, "", ""),
    ("sleep_habit",     "lifestyle", "作息情况",       "sleep pattern",                "text", 0, "", ""),
    # --- reproductive 婚育史/月经史（2）---
    ("marriage_history",  "reproductive", "婚育史", "marriage and childbearing history", "text", 0, "", ""),
    ("menstrual_history", "reproductive", "月经史", "menstrual history",                 "text", 0, "", ""),
    # --- complaint 临床主诉与现病史（10）---
    ("disease_category",      "complaint", "疾病分类", "disease category",      "text",   0, "", ""),
    ("chief_complaint",       "complaint", "主诉",     "chief complaint",       "text",   0, "", ""),
    ("symptom_onset",         "complaint", "起病时间", "onset time",            "date",   0, "", ""),
    ("symptom_severity",      "complaint", "缓急程度", "severity",              "enum",   0, "", ""),
    ("symptom_duration",      "complaint", "持续时间", "duration",              "text",   0, "", ""),
    ("accompanying_symptoms", "complaint", "伴随症状", "accompanying symptoms", "text",   1, "", ""),
    ("mental_state",          "complaint", "精神状态", "mental state",          "text",   0, "", ""),
    ("appetite",              "complaint", "食欲",     "appetite",              "text",   0, "", ""),
    ("sleep_quality",         "complaint", "睡眠",     "sleep quality",         "text",   0, "", ""),
    ("bowel_urine",           "complaint", "大小便",   "bowel and urine",      "text",   0, "", ""),
    # --- exam 体格检查（7）---
    ("temperature",     "exam", "体温",     "temperature",           "number", 0, "℃", "°C"),
    ("pulse",           "exam", "脉搏",     "pulse",                 "number", 0, "次/分", "bpm"),
    ("respiration",     "exam", "呼吸",     "respiration",           "number", 0, "次/分", "rpm"),
    ("blood_pressure",  "exam", "血压",     "blood pressure",        "text",   0, "mmHg", "mmHg"),
    ("specialty_exam",  "exam", "专科查体", "specialty examination", "text",   0, "", ""),
    ("positive_signs",  "exam", "阳性体征", "positive signs",        "text",   1, "", ""),
    ("negative_signs",  "exam", "阴性体征", "negative signs",        "text",   1, "", ""),
    # --- followup 随访（4，共用 seq）---
    ("followup_date",        "followup", "随访日期", "follow-up date",       "date",   1, "", ""),
    ("current_weight",       "followup", "当前体重", "current weight",       "number", 1, "kg", "kg"),
    ("current_temperature",  "followup", "当前体温", "current temperature",  "number", 1, "℃", "°C"),
    ("followup_note",        "followup", "随访备注", "follow-up note",       "text",   1, "", ""),
]

# 默认病症词条（term_key 不可变）；236 条完整词典放 docs/seed/disease_terms.csv 后自动加载
DEFAULT_DISEASE_TERMS: List[Tuple[str, str, str, str]] = [
    ("phenylketonuria", "苯丙酮尿症", "Phenylketonuria", "genetic_metabolic"),
    ("congenital_hypothyroidism", "先天性甲状腺功能减低症", "Congenital Hypothyroidism", "endocrine"),
    ("hearing_screening", "听力筛查", "Hearing Screening", "screening"),
]

# 病症结果中英文映射（R3）
_DISEASE_RESULT_CN2EN = {"阴性": "negative", "阳性": "positive", "未查": "not_tested"}
_DISEASE_RESULT_EN2CN = {v: k for k, v in _DISEASE_RESULT_CN2EN.items()}


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _hash_password(password: str, salt_hex: str) -> str:
    """密码哈希，格式 sha256$<salt_hex>$<hash_hex>（设计书 §8.2）"""
    h = hashlib.sha256(bytes.fromhex(salt_hex) + password.encode("utf-8")).hexdigest()
    return f"sha256${salt_hex}${h}"


# ==========================================
# 4. DataStore 核心类
# ==========================================
class DataStore:
    # ---------- 4.1 初始化 ----------
    def __init__(self, db_path: Optional[str] = None, data_dir: Optional[str] = None):
        self.data_dir = data_dir or "data"
        self.db_path = db_path or os.path.join(self.data_dir, "db", "medical_archive.db")
        for d in (os.path.dirname(self.db_path),
                  os.path.join(self.data_dir, "uploads"),
                  os.path.join(self.data_dir, "exports", "json"),
                  os.path.join(self.data_dir, "exports", "docx"),
                  os.path.join(self.data_dir, "backups"),
                  os.path.join(self.data_dir, "logs")):
            os.makedirs(d, exist_ok=True)
        self.conn: Optional[sqlite3.Connection] = None
        self._field_def_cache: Dict[str, sqlite3.Row] = {}

    def get_connection(self) -> sqlite3.Connection:
        """外键是连接级设置，每个连接都必须打开（设计书 §4.1）"""
        if self.conn is None:
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA foreign_keys = ON;")
        return self.conn

    def close(self) -> None:
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    # ---------- 4.2 建库与迁移 ----------
    def init_database(self) -> None:
        """建表 + 索引 + schema_meta；自动处理旧版结构迁移（§10.1）"""
        conn = self.get_connection()
        cur = conn.cursor()

        # --- 旧版 disease_terms（无 term_key）：重建表保留数据 ---
        if self._table_exists("disease_terms") and not self._column_exists("disease_terms", "term_key"):
            cols = [r["name"] for r in conn.execute("PRAGMA table_info(disease_terms)")]
            if "chinese_name" in cols:
                cur.execute("ALTER TABLE disease_terms RENAME TO disease_terms_v1")
                self._create_disease_terms(cur)
                for row in conn.execute("SELECT * FROM disease_terms_v1").fetchall():
                    term_key = self._slug(row["english_name"]) or self._slug(row["chinese_name"])
                    cur.execute(
                        "INSERT OR IGNORE INTO disease_terms (term_key, chinese_name, english_name, category, updated_at) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (term_key, row["chinese_name"], row["english_name"],
                         row["category"] if "category" in row.keys() else "general", _now()))
                cur.execute("DROP TABLE disease_terms_v1")
                print("[迁移] disease_terms 已升级为含 term_key 结构")

        # --- 旧版 archive_records（含 v1 的 phone 列）：空表直接重建，非空报错 ---
        if self._table_exists("archive_records") and self._column_exists("archive_records", "phone"):
            cnt = conn.execute("SELECT COUNT(*) FROM archive_records").fetchone()[0]
            if cnt == 0:
                cur.execute("DROP TABLE archive_records")
                print("[迁移] 旧的 v1 archive_records（空表）已移除，按 v3.0 重建")
            else:
                raise DataStoreError(
                    "检测到 v1 版 archive_records 且含数据，请先执行 v1 迁移流程（设计书 §10.3）")

        # --- 建全部表 ---
        cur.execute("""CREATE TABLE IF NOT EXISTS schema_meta (
            version TEXT NOT NULL, applied_at TEXT NOT NULL);""")

        cur.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            display_name TEXT DEFAULT '',
            role TEXT DEFAULT 'user',
            is_active INTEGER DEFAULT 1,
            created_at TEXT NOT NULL,
            last_login_at TEXT DEFAULT '');""")

        cur.execute("""CREATE TABLE IF NOT EXISTS archive_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_id TEXT NOT NULL UNIQUE,
            owner_id INTEGER,
            archive_number TEXT DEFAULT '',
            name TEXT NOT NULL,
            gender TEXT DEFAULT '',
            nation TEXT DEFAULT '',
            id_number TEXT DEFAULT '',
            residence_address TEXT DEFAULT '',
            create_date TEXT DEFAULT '',
            source TEXT DEFAULT 'manual',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            is_deleted INTEGER DEFAULT 0,
            FOREIGN KEY (owner_id) REFERENCES users(id));""")

        cur.execute("""CREATE TABLE IF NOT EXISTS field_definitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            field_key TEXT NOT NULL UNIQUE,
            section TEXT NOT NULL,
            label_cn TEXT NOT NULL,
            label_en TEXT NOT NULL,
            value_type TEXT DEFAULT 'text',
            is_multi INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            unit_cn TEXT DEFAULT '',
            unit_en TEXT DEFAULT '',
            sort_order INTEGER DEFAULT 0,
            is_legacy INTEGER DEFAULT 0);""")

        self._create_disease_terms(cur)

        cur.execute("""CREATE TABLE IF NOT EXISTS record_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_id TEXT NOT NULL,
            field_key TEXT NOT NULL,
            seq INTEGER DEFAULT 0,
            value_cn TEXT DEFAULT '',
            value_en TEXT DEFAULT '',
            value_num REAL,
            updated_at TEXT NOT NULL,
            UNIQUE (record_id, field_key, seq),
            FOREIGN KEY (record_id) REFERENCES archive_records(record_id) ON DELETE CASCADE,
            FOREIGN KEY (field_key) REFERENCES field_definitions(field_key));""")

        cur.execute("""CREATE TABLE IF NOT EXISTS record_diseases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_id TEXT NOT NULL,
            disease_term_id INTEGER NOT NULL,
            result_cn TEXT DEFAULT '',
            result_en TEXT DEFAULT '',
            seq INTEGER DEFAULT 0,
            checked_at TEXT DEFAULT '',
            updated_at TEXT NOT NULL,
            UNIQUE (record_id, disease_term_id, seq),
            FOREIGN KEY (record_id) REFERENCES archive_records(record_id) ON DELETE CASCADE,
            FOREIGN KEY (disease_term_id) REFERENCES disease_terms(id));""")

        cur.execute("""CREATE TABLE IF NOT EXISTS dna_sequences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_id TEXT NOT NULL,
            dna_sequence TEXT NOT NULL,
            key_hash TEXT NOT NULL,
            cg_content REAL DEFAULT 0,
            thermal_stability REAL DEFAULT 0,
            padded_zeros INTEGER DEFAULT 0,
            sequence_length INTEGER DEFAULT 0,
            original_text TEXT DEFAULT '',
            encoded_at TEXT NOT NULL,
            is_valid INTEGER DEFAULT 1,
            payload_version TEXT DEFAULT 'v3',
            payload_mode TEXT DEFAULT 'bilingual',
            FOREIGN KEY (record_id) REFERENCES archive_records(record_id));""")

        cur.execute("""CREATE TABLE IF NOT EXISTS decode_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dna_record_id INTEGER NOT NULL,
            decoded_text TEXT NOT NULL,
            corrected_text TEXT DEFAULT '',
            confidence REAL DEFAULT 0,
            error_rate REAL DEFAULT 0,
            correction_log TEXT DEFAULT '{}',
            decoded_at TEXT NOT NULL,
            FOREIGN KEY (dna_record_id) REFERENCES dna_sequences(id));""")

        cur.execute("""CREATE TABLE IF NOT EXISTS user_activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT NOT NULL,
            target_record_id TEXT DEFAULT '',
            detail TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id));""")

        # --- 索引（设计书 §4，不为 value_cn/value_en 建索引）---
        for sql in (
            "CREATE INDEX IF NOT EXISTS idx_archive_name ON archive_records(name);",
            "CREATE INDEX IF NOT EXISTS idx_archive_owner ON archive_records(owner_id, created_at);",
            "CREATE INDEX IF NOT EXISTS idx_archive_created ON archive_records(created_at);",
            "CREATE INDEX IF NOT EXISTS idx_archive_deleted ON archive_records(is_deleted, created_at);",
            "CREATE INDEX IF NOT EXISTS idx_entries_record ON record_entries(record_id);",
            "CREATE INDEX IF NOT EXISTS idx_entries_field ON record_entries(field_key);",
            "CREATE INDEX IF NOT EXISTS idx_entries_num ON record_entries(field_key, value_num);",
            "CREATE INDEX IF NOT EXISTS idx_def_section ON field_definitions(section, sort_order);",
            "CREATE INDEX IF NOT EXISTS idx_def_active ON field_definitions(is_active);",
            "CREATE INDEX IF NOT EXISTS idx_disease_result ON record_diseases(record_id, disease_term_id);",
            "CREATE INDEX IF NOT EXISTS idx_disease_term ON record_diseases(disease_term_id);",
            "CREATE INDEX IF NOT EXISTS idx_dna_record ON dna_sequences(record_id, is_valid);",
            "CREATE INDEX IF NOT EXISTS idx_dna_sequence ON dna_sequences(dna_sequence);",
            "CREATE INDEX IF NOT EXISTS idx_decode_dna ON decode_records(dna_record_id);",
            "CREATE INDEX IF NOT EXISTS idx_activity_user ON user_activity_log(user_id, created_at);",
        ):
            cur.execute(sql)

        # --- 版本登记 ---
        row = cur.execute("SELECT version FROM schema_meta ORDER BY rowid DESC LIMIT 1").fetchone()
        if row is None:
            cur.execute("INSERT INTO schema_meta (version, applied_at) VALUES (?, ?)",
                        (SCHEMA_VERSION, _now()))
        conn.commit()

        # --- users.json 迁移（§10.2）---
        self._migrate_users_json()

    @staticmethod
    def _create_disease_terms(cur: sqlite3.Cursor) -> None:
        cur.execute("""CREATE TABLE IF NOT EXISTS disease_terms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            term_key TEXT NOT NULL UNIQUE,
            chinese_name TEXT NOT NULL UNIQUE,
            english_name TEXT NOT NULL,
            category TEXT DEFAULT 'general',
            is_active INTEGER DEFAULT 1,
            updated_at TEXT DEFAULT '');""")

    def _table_exists(self, name: str) -> bool:
        row = self.get_connection().execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
        return row is not None

    def _column_exists(self, table: str, column: str) -> bool:
        return any(r["name"] == column
                   for r in self.get_connection().execute(f"PRAGMA table_info({table})"))

    @staticmethod
    def _slug(text: str) -> str:
        return "".join(c.lower() if c.isalnum() else "_" for c in (text or "")).strip("_")

    # ---------- 4.3 字典种子 ----------
    def init_field_definitions(self) -> int:
        """灌入 60 条字段字典（幂等），返回新增数（§8.1）"""
        conn = self.get_connection()
        inserted = 0
        for i, (key, section, cn, en, vtype, multi, unit_cn, unit_en) in enumerate(FIELD_DEFINITIONS):
            cur = conn.execute(
                "INSERT OR IGNORE INTO field_definitions "
                "(field_key, section, label_cn, label_en, value_type, is_multi, unit_cn, unit_en, sort_order) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (key, section, cn, en, vtype, multi, unit_cn, unit_en, (i + 1) * 10))
            inserted += cur.rowcount
        conn.commit()
        self._field_def_cache = {}
        return inserted

    def init_disease_terms(self) -> int:
        """灌入病症词典（幂等，按缺失增量插入）。
        优先读 docs/seed/disease_terms.csv（term_key,chinese,english,category），
        不存在则用内置默认词条。"""
        conn = self.get_connection()
        rows: List[Tuple[str, str, str, str]] = list(DEFAULT_DISEASE_TERMS)
        seed = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "docs", "seed", "disease_terms.csv")
        if os.path.exists(seed):
            import csv
            with open(seed, "r", encoding="utf-8-sig") as f:
                rows = [tuple(r) for r in csv.reader(f) if r and not r[0].startswith("#")]
        inserted = 0
        for term_key, cn, en, cat in rows:
            cur = conn.execute(
                "INSERT OR IGNORE INTO disease_terms (term_key, chinese_name, english_name, category, updated_at) "
                "VALUES (?, ?, ?, ?, ?)", (term_key, cn, en, cat, _now()))
            inserted += cur.rowcount
        conn.commit()
        return inserted

    # ---------- 4.4 账号与日志（§8.2）----------
    def create_user(self, username: str, password: str, role: str = "user",
                    display_name: str = "") -> Tuple[bool, str]:
        username = (username or "").strip().lower()
        if not username:
            return False, "账号不能为空"
        if len(password or "") < 6:
            return False, "密码长度不能少于6位"
        if self.get_user(username=username):
            return False, "该账号已存在"
        salt = uuid.uuid4().hex[:16]
        self.get_connection().execute(
            "INSERT INTO users (username, password_hash, display_name, role, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (username, _hash_password(password, salt), display_name or username, role, _now()))
        self.get_connection().commit()
        uid = self.get_user(username=username)["id"]
        self.log_activity(uid, "register")
        return True, "注册成功，请登录"

    def verify_user(self, username: str, password: str) -> Optional[dict]:
        """成功返回 {id, username, display_name, role}；失败返回 None（不区分原因）"""
        user = self.get_user(username=(username or "").strip().lower())
        if not user or not user["is_active"]:
            return None
        try:
            _, salt, _ = user["password_hash"].split("$")
        except ValueError:
            return None
        if _hash_password(password, salt) != user["password_hash"]:
            return None
        self.touch_last_login(user["id"])
        self.log_activity(user["id"], "login")
        return {"id": user["id"], "username": user["username"],
                "display_name": user["display_name"], "role": user["role"]}

    def get_user(self, user_id: Optional[int] = None,
                 username: Optional[str] = None) -> Optional[dict]:
        conn = self.get_connection()
        if user_id is not None:
            row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        elif username is not None:
            row = conn.execute("SELECT * FROM users WHERE username=?",
                               (username.strip().lower(),)).fetchone()
        else:
            return None
        return dict(row) if row else None

    def set_user_active(self, user_id: int, active: bool) -> bool:
        cur = self.get_connection().execute(
            "UPDATE users SET is_active=? WHERE id=?", (1 if active else 0, user_id))
        self.get_connection().commit()
        return cur.rowcount > 0

    def touch_last_login(self, user_id: int) -> None:
        self.get_connection().execute("UPDATE users SET last_login_at=? WHERE id=?",
                                      (_now(), user_id))
        self.get_connection().commit()

    def log_activity(self, user_id: Optional[int], action: str,
                     target_record_id: str = "", detail: str = "") -> None:
        """写操作日志；失败只打印不阻断主流程（R9）"""
        try:
            self.get_connection().execute(
                "INSERT INTO user_activity_log (user_id, action, target_record_id, detail, created_at) "
                "VALUES (?, ?, ?, ?, ?)", (user_id, action, target_record_id, detail, _now()))
            self.get_connection().commit()
        except Exception as e:  # noqa: BLE001
            print(f"[日志] 写入失败（已忽略）: {e}")

    def list_activity(self, user_id: Optional[int] = None, action: Optional[str] = None,
                      limit: int = 50, offset: int = 0) -> Tuple[List[dict], int]:
        where, params = "WHERE 1=1", []
        if user_id is not None:
            where += " AND user_id=?"; params.append(user_id)
        if action:
            where += " AND action=?"; params.append(action)
        conn = self.get_connection()
        total = conn.execute(f"SELECT COUNT(*) FROM user_activity_log {where}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM user_activity_log {where} ORDER BY id DESC LIMIT ? OFFSET ?",
            (*params, limit, offset)).fetchall()
        return [dict(r) for r in rows], total

    def _migrate_users_json(self) -> None:
        """data/users.json → users 表，导入后改名（§10.2）"""
        path = os.path.join(self.data_dir, "users.json")
        if not os.path.exists(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                users = json.load(f)
            for username, pwd in users.items():
                if not self.get_user(username=username):
                    # 旧文件是明文密码，导入时立即转哈希
                    self.create_user(username, str(pwd))
            os.rename(path, path + ".migrated")
            print("[迁移] data/users.json 已导入 users 表并停用")
        except Exception as e:  # noqa: BLE001
            print(f"[迁移] users.json 导入失败: {e}")

    # ---------- 4.5 档案 CRUD（§8.3）----------
    def _next_record_id(self, conn: sqlite3.Connection) -> str:
        """同一事务内生成 record_id：ARCHIVE_{YYYYMMDD}_{NNN}（§3.3）"""
        prefix = f"ARCHIVE_{datetime.now().strftime('%Y%m%d')}_"
        row = conn.execute(
            "SELECT record_id FROM archive_records WHERE record_id LIKE ? "
            "ORDER BY record_id DESC LIMIT 1", (prefix + "%",)).fetchone()
        n = int(row["record_id"][len(prefix):]) + 1 if row else 1
        return f"{prefix}{n:03d}"

    def _field_def(self, field_key: str) -> Optional[sqlite3.Row]:
        if not self._field_def_cache:
            for r in self.get_connection().execute("SELECT * FROM field_definitions"):
                self._field_def_cache[r["field_key"]] = r
        return self._field_def_cache.get(field_key)

    def _normalize_entries(self, entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """校验并规范化内容行：R1 字段登记、R4 数值副本、R5 seq 规则"""
        normalized, seen = [], set()
        multi_counter: Dict[str, int] = {}
        for e in entries:
            key = e.get("field_key", "")
            fd = self._field_def(key)
            if fd is None or not fd["is_active"]:
                raise FieldKeyNotRegisteredError(f"field_key 未登记或已停用: {key}")
            if fd["is_multi"]:
                seq = e.get("seq") or 0
                if seq <= 0:
                    multi_counter[key] = multi_counter.get(key, 0) + 1
                    seq = multi_counter[key]
            else:
                seq = 0
            slot = (key, seq)
            if slot in seen:
                raise DuplicateSeqError(f"field_key={key} 的 seq={seq} 重复")
            seen.add(slot)
            value_cn = str(e.get("value_cn") or "")
            value_en = str(e.get("value_en") or value_cn)  # R6：开放文本 en 兜底等于 cn
            value_num = e.get("value_num")
            if fd["value_type"] == "number" and value_num is None:
                try:
                    value_num = float(value_en.replace(",", "").strip())
                except (ValueError, AttributeError):
                    value_num = None
            normalized.append({"field_key": key, "seq": seq, "value_cn": value_cn,
                               "value_en": value_en, "value_num": value_num})
        return normalized

    def save_record(self, record: ArchiveRecord, owner_id: Optional[int] = None) -> str:
        """单事务写入身份 + 内容 + 病症，返回 record_id（§8.3）
        owner_id 为 None 时用记录自带归属；新建时无归属 -> 抛 GuestWriteForbiddenError（R8）"""
        conn = self.get_connection()
        effective_owner = owner_id if owner_id is not None else record.owner_id
        entries = self._normalize_entries(record.entries)
        is_new = not record.record_id or not self._exists(record.record_id)

        if is_new and effective_owner is None:
            raise GuestWriteForbiddenError("游客模式不可保存档案，请登录后再操作")

        now = _now()
        try:
            conn.execute("BEGIN")
            if is_new:
                for _ in range(3):  # 撞号重试（§3.3）
                    record.record_id = self._next_record_id(conn)
                    try:
                        conn.execute(
                            "INSERT INTO archive_records (record_id, owner_id, archive_number, name, gender, "
                            "nation, id_number, residence_address, create_date, source, created_at, updated_at) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (record.record_id, effective_owner, record.archive_number, record.name,
                             record.gender, record.nation, record.id_number, record.residence_address,
                             record.create_date, record.source, now, now))
                        break
                    except sqlite3.IntegrityError:
                        continue
                else:
                    raise DataStoreError("record_id 生成失败（连续撞号）")
                action = "create_record"
            else:
                # 更新：owner 不传则保留原归属
                if effective_owner is None:
                    row = conn.execute("SELECT owner_id FROM archive_records WHERE record_id=?",
                                       (record.record_id,)).fetchone()
                    effective_owner = row["owner_id"] if row else None
                conn.execute(
                    "UPDATE archive_records SET owner_id=?, archive_number=?, name=?, gender=?, nation=?, "
                    "id_number=?, residence_address=?, create_date=?, source=?, updated_at=? "
                    "WHERE record_id=? AND is_deleted=0",
                    (effective_owner, record.archive_number, record.name, record.gender, record.nation,
                     record.id_number, record.residence_address, record.create_date, record.source,
                     now, record.record_id))
                conn.execute("DELETE FROM record_entries WHERE record_id=?", (record.record_id,))
                conn.execute("DELETE FROM record_diseases WHERE record_id=?", (record.record_id,))
                action = "update_record"

            for e in entries:
                conn.execute(
                    "INSERT INTO record_entries (record_id, field_key, seq, value_cn, value_en, value_num, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (record.record_id, e["field_key"], e["seq"], e["value_cn"],
                     e["value_en"], e["value_num"], now))

            for d in record.diseases:
                self._insert_disease(conn, record.record_id, d, now)

            conn.commit()
        except Exception:
            conn.rollback()
            raise

        record.owner_id = effective_owner
        record.updated_at = now
        if not record.created_at:
            record.created_at = now
        self.log_activity(effective_owner, action, record.record_id)
        return record.record_id

    def _exists(self, record_id: str) -> bool:
        return self.get_connection().execute(
            "SELECT 1 FROM archive_records WHERE record_id=? AND is_deleted=0",
            (record_id,)).fetchone() is not None

    def _insert_disease(self, conn: sqlite3.Connection, record_id: str,
                        d: Dict[str, Any], now: str) -> None:
        term = self.get_disease_by_key(d.get("term_key", ""))
        if term is None:
            raise DataStoreError(f"病症词条未登记: {d.get('term_key')}")
        result_cn = d.get("result_cn", "")
        result_en = d.get("result_en", "")
        if result_cn and not result_en:
            result_en = _DISEASE_RESULT_CN2EN.get(result_cn, result_cn)
        if result_en and not result_cn:
            result_cn = _DISEASE_RESULT_EN2CN.get(result_en, result_en)
        conn.execute(
            "INSERT INTO record_diseases (record_id, disease_term_id, result_cn, result_en, seq, checked_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (record_id, term.id, result_cn, result_en, d.get("seq", 0),
             d.get("checked_at", ""), now))

    def load_record(self, record_id: str) -> Optional[ArchiveRecord]:
        """返回完整档案（身份 + 内容 + 病症）；不存在或已软删返回 None"""
        conn = self.get_connection()
        row = conn.execute(
            "SELECT * FROM archive_records WHERE record_id=? AND is_deleted=0",
            (record_id,)).fetchone()
        if row is None:
            return None
        record = ArchiveRecord(**{k: row[k] for k in row.keys() if k in ArchiveRecord.__dataclass_fields__})
        record.entries = [dict(r) for r in conn.execute(
            "SELECT e.field_key, e.seq, e.value_cn, e.value_en, e.value_num "
            "FROM record_entries e JOIN field_definitions f ON e.field_key = f.field_key "
            "WHERE e.record_id=? ORDER BY f.section, f.sort_order, e.seq", (record_id,))]
        record.diseases = [dict(r) for r in conn.execute(
            "SELECT t.term_key, t.chinese_name, t.english_name, d.result_cn, d.result_en, d.seq, d.checked_at "
            "FROM record_diseases d JOIN disease_terms t ON d.disease_term_id = t.id "
            "WHERE d.record_id=? ORDER BY t.chinese_name, d.seq", (record_id,))]
        return record

    def update_record(self, record: ArchiveRecord) -> bool:
        """全量覆盖已有档案（§8.3）"""
        if not record.record_id or not self._exists(record.record_id):
            return False
        self.save_record(record)
        return True

    def update_meta(self, record_id: str, **fields) -> bool:
        """只更新身份列（§8.3）"""
        allowed = {"archive_number", "name", "gender", "nation", "id_number",
                   "residence_address", "create_date", "source", "owner_id"}
        sets = {k: v for k, v in fields.items() if k in allowed}
        if not sets:
            return False
        sets["updated_at"] = _now()
        sql = f"UPDATE archive_records SET {', '.join(f'{k}=?' for k in sets)} WHERE record_id=?"
        cur = self.get_connection().execute(sql, (*sets.values(), record_id))
        self.get_connection().commit()
        return cur.rowcount > 0

    def upsert_entries(self, record_id: str, entries: List[Dict[str, Any]]) -> int:
        """局部更新内容；未出现的 field_key 保持原值（§8.3，R7 覆盖语义）"""
        if not self._exists(record_id):
            raise RecordNotFoundError(record_id)
        normalized = self._normalize_entries(entries)
        conn = self.get_connection()
        now = _now()
        for e in normalized:
            conn.execute(
                "INSERT INTO record_entries (record_id, field_key, seq, value_cn, value_en, value_num, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(record_id, field_key, seq) "
                "DO UPDATE SET value_cn=excluded.value_cn, value_en=excluded.value_en, "
                "value_num=excluded.value_num, updated_at=excluded.updated_at",
                (record_id, e["field_key"], e["seq"], e["value_cn"], e["value_en"], e["value_num"], now))
        conn.execute("UPDATE archive_records SET updated_at=? WHERE record_id=?", (now, record_id))
        conn.commit()
        return len(normalized)

    def delete_record(self, record_id: str, user_id: Optional[int] = None) -> bool:
        """软删除（§8.3）；内容行保留"""
        cur = self.get_connection().execute(
            "UPDATE archive_records SET is_deleted=1, updated_at=? WHERE record_id=?",
            (_now(), record_id))
        self.get_connection().commit()
        if cur.rowcount > 0:
            self.log_activity(user_id, "delete_record", record_id)
        return cur.rowcount > 0

    def list_records(self, offset: int = 0, limit: int = 20, keyword: Optional[str] = None,
                     owner_id: Optional[int] = None) -> Tuple[List[ArchiveRecord], int]:
        """分页，返回 (items, 过滤后总数)。owner_id=None 不过滤（admin 用）"""
        where, params = "WHERE is_deleted=0", []
        if keyword:
            where += " AND (name LIKE ? OR archive_number LIKE ? OR id_number LIKE ?)"
            params += [f"%{keyword}%"] * 3
        if owner_id is not None:
            where += " AND owner_id=?"; params.append(owner_id)
        conn = self.get_connection()
        total = conn.execute(f"SELECT COUNT(*) FROM archive_records {where}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM archive_records {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (*params, limit, offset)).fetchall()
        items = []
        for row in rows:
            rec = ArchiveRecord(**{k: row[k] for k in row.keys()
                                   if k in ArchiveRecord.__dataclass_fields__})
            rec.entries = [dict(r) for r in conn.execute(
                "SELECT field_key, seq, value_cn, value_en, value_num FROM record_entries "
                "WHERE record_id=? ORDER BY field_key, seq", (rec.record_id,))]
            items.append(rec)
        return items, total

    # ---------- 4.6 字段字典（§8.4）----------
    def list_field_definitions(self, section: Optional[str] = None,
                               only_active: bool = True) -> List[FieldDefinition]:
        """UI 动态渲染表单的唯一依据"""
        where, params = "WHERE 1=1", []
        if section:
            where += " AND section=?"; params.append(section)
        if only_active:
            where += " AND is_active=1"
        rows = self.get_connection().execute(
            f"SELECT * FROM field_definitions {where} ORDER BY section, sort_order", params)
        return [FieldDefinition(**dict(r)) for r in rows]

    def get_field_definition(self, field_key: str) -> Optional[FieldDefinition]:
        row = self._field_def(field_key)
        return FieldDefinition(**dict(row)) if row else None

    def add_field_definition(self, field_key: str, section: str, label_cn: str,
                             label_en: str, value_type: str = "text",
                             is_multi: bool = False, unit_cn: str = "",
                             unit_en: str = "", sort_order: int = 0) -> int:
        """新增字段；field_key 已存在抛 IntegrityError"""
        cur = self.get_connection().execute(
            "INSERT INTO field_definitions (field_key, section, label_cn, label_en, value_type, "
            "is_multi, unit_cn, unit_en, sort_order) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (field_key, section, label_cn, label_en, value_type,
             1 if is_multi else 0, unit_cn, unit_en, sort_order))
        self.get_connection().commit()
        self._field_def_cache = {}
        return int(cur.lastrowid or 0)

    # ---------- 4.7 病症（§8.5）----------
    def search_disease(self, keyword: str, limit: int = 10) -> List[DiseaseTerm]:
        rows = self.get_connection().execute(
            "SELECT * FROM disease_terms WHERE is_active=1 AND "
            "(chinese_name LIKE ? OR english_name LIKE ? OR term_key LIKE ?) LIMIT ?",
            (f"%{keyword}%", f"%{keyword}%", f"%{keyword}%", limit))
        return [DiseaseTerm(**dict(r)) for r in rows]

    def get_disease_by_chinese(self, chinese_name: str) -> Optional[DiseaseTerm]:
        row = self.get_connection().execute(
            "SELECT * FROM disease_terms WHERE chinese_name=?", (chinese_name,)).fetchone()
        return DiseaseTerm(**dict(row)) if row else None

    def get_disease_by_english(self, english_name: str) -> Optional[DiseaseTerm]:
        row = self.get_connection().execute(
            "SELECT * FROM disease_terms WHERE english_name=?", (english_name,)).fetchone()
        return DiseaseTerm(**dict(row)) if row else None

    def get_disease_by_key(self, term_key: str) -> Optional[DiseaseTerm]:
        row = self.get_connection().execute(
            "SELECT * FROM disease_terms WHERE term_key=?", (term_key,)).fetchone()
        return DiseaseTerm(**dict(row)) if row else None

    def list_disease_results(self, record_id: str) -> List[dict]:
        record = self.load_record(record_id)
        return record.diseases if record else []

    def upsert_disease_result(self, record_id: str, term_key: str, result_cn: str,
                              seq: int = 0, checked_at: str = "") -> int:
        if not self._exists(record_id):
            raise RecordNotFoundError(record_id)
        conn = self.get_connection()
        self._insert_disease(conn, record_id,
                             {"term_key": term_key, "result_cn": result_cn,
                              "seq": seq, "checked_at": checked_at}, _now())
        conn.commit()
        return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])

    def get_all_categories(self) -> List[str]:
        rows = self.get_connection().execute(
            "SELECT DISTINCT category FROM disease_terms WHERE is_active=1")
        return [r["category"] for r in rows if r["category"]]

    def add_disease_term(self, term_key: str, chinese_name: str,
                         english_name: str, category: str = "general") -> int:
        cur = self.get_connection().execute(
            "INSERT INTO disease_terms (term_key, chinese_name, english_name, category, updated_at) "
            "VALUES (?, ?, ?, ?, ?)", (term_key, chinese_name, english_name, category, _now()))
        self.get_connection().commit()
        return int(cur.lastrowid or 0)

    # ---------- 4.8 文件处理（§8.6）----------
    def parse_document(self, file_path: str) -> str:
        """解析 .txt/.docx/.pdf 提取纯文本；不支持格式抛 ValueError"""
        ext = os.path.splitext(file_path)[1].lower()
        try:
            if ext == ".txt":
                with open(file_path, "r", encoding="utf-8") as f:
                    return f.read()
            if ext == ".docx":
                doc = docx.Document(file_path)
                return "\n".join(p.text for p in doc.paragraphs)
            if ext == ".pdf":
                text = ""
                with pdfplumber.open(file_path) as pdf:
                    for page in pdf.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text + "\n"
                return text
            raise ValueError(f"不支持的文件类型: {ext}（仅支持 txt / docx / pdf）")
        except ValueError:
            raise
        except Exception as e:
            raise DataStoreError(f"文件解析失败: {e}") from e

    def save_upload_file(self, file_content: bytes, filename: str) -> str:
        date_str = datetime.now().strftime("%Y%m%d")
        upload_dir = os.path.join(self.data_dir, "uploads", date_str)
        os.makedirs(upload_dir, exist_ok=True)
        file_path = os.path.join(upload_dir, f"{uuid.uuid4().hex[:8]}_{filename}")
        with open(file_path, "wb") as f:
            f.write(file_content)
        return file_path

    def cleanup_temp_files(self, older_than_hours: int = 24) -> int:
        upload_dir = os.path.join(self.data_dir, "uploads")
        if not os.path.exists(upload_dir):
            return 0
        now = datetime.now().timestamp()
        deleted = 0
        for root, _, files in os.walk(upload_dir):
            for name in files:
                path = os.path.join(root, name)
                if os.path.getmtime(path) < now - older_than_hours * 3600:
                    os.remove(path)
                    deleted += 1
        return deleted

    # ---------- 4.9 DNA 与解码（§8.7）----------
    def save_dna_sequence(self, dna_record: DNASequenceRecord) -> int:
        """保存编码结果；同档案旧版本自动置 is_valid=0（设计书 §3.8）"""
        conn = self.get_connection()
        if not dna_record.encoded_at:
            dna_record.encoded_at = _now()
        conn.execute("UPDATE dna_sequences SET is_valid=0 WHERE record_id=? AND is_valid=1",
                     (dna_record.record_id,))
        cur = conn.execute(
            "INSERT INTO dna_sequences (record_id, dna_sequence, key_hash, cg_content, "
            "thermal_stability, padded_zeros, sequence_length, original_text, encoded_at, "
            "is_valid, payload_version, payload_mode) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (dna_record.record_id, dna_record.dna_sequence, dna_record.key_hash,
             dna_record.cg_content, dna_record.thermal_stability, dna_record.padded_zeros,
             dna_record.sequence_length, dna_record.original_text, dna_record.encoded_at,
             1 if dna_record.is_valid else 0,
             dna_record.payload_version, dna_record.payload_mode))
        conn.commit()
        return int(cur.lastrowid or 0)

    def load_dna_sequence(self, record_id: str) -> Optional[DNASequenceRecord]:
        row = self.get_connection().execute(
            "SELECT * FROM dna_sequences WHERE record_id=? AND is_valid=1 "
            "ORDER BY id DESC LIMIT 1", (record_id,)).fetchone()
        if not row:
            return None
        data = dict(row)
        data["is_valid"] = bool(data["is_valid"])
        return DNASequenceRecord(**data)

    def load_dna_by_sequence(self, dna_sequence: str) -> Optional[DNASequenceRecord]:
        row = self.get_connection().execute(
            "SELECT * FROM dna_sequences WHERE dna_sequence=? ORDER BY id DESC LIMIT 1",
            (dna_sequence,)).fetchone()
        if not row:
            return None
        data = dict(row)
        data["is_valid"] = bool(data["is_valid"])
        return DNASequenceRecord(**data)

    def list_dna_sequences(self, offset: int = 0, limit: int = 20) -> List[DNASequenceRecord]:
        rows = self.get_connection().execute(
            "SELECT * FROM dna_sequences ORDER BY id DESC LIMIT ? OFFSET ?",
            (limit, offset)).fetchall()
        result = []
        for row in rows:
            data = dict(row)
            data["is_valid"] = bool(data["is_valid"])
            result.append(DNASequenceRecord(**data))
        return result

    def invalidate_dna_sequence(self, dna_id: int) -> bool:
        cur = self.get_connection().execute(
            "UPDATE dna_sequences SET is_valid=0 WHERE id=?", (dna_id,))
        self.get_connection().commit()
        return cur.rowcount > 0

    def save_decode_record(self, decode_record: DecodeRecord) -> int:
        if not decode_record.decoded_at:
            decode_record.decoded_at = _now()
        cur = self.get_connection().execute(
            "INSERT INTO decode_records (dna_record_id, decoded_text, corrected_text, confidence, "
            "error_rate, correction_log, decoded_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (decode_record.dna_record_id, decode_record.decoded_text,
             decode_record.corrected_text, decode_record.confidence,
             decode_record.error_rate, decode_record.correction_log, decode_record.decoded_at))
        self.get_connection().commit()
        return int(cur.lastrowid or 0)

    def list_decode_records(self, dna_record_id: Optional[int] = None,
                            limit: int = 20) -> List[DecodeRecord]:
        conn = self.get_connection()
        if dna_record_id is not None:
            rows = conn.execute(
                "SELECT * FROM decode_records WHERE dna_record_id=? ORDER BY id DESC LIMIT ?",
                (dna_record_id, limit)).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM decode_records ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [DecodeRecord(**dict(r)) for r in rows]

    # ---------- 4.10 相似度与导出（§8.8）----------
    def find_similar_records(self, text: str, threshold: float = 0.7,
                             limit: int = 5) -> List[Tuple[ArchiveRecord, float]]:
        rows = self.get_connection().execute(
            "SELECT * FROM archive_records WHERE is_deleted=0").fetchall()
        results = []
        for row in rows:
            rec = ArchiveRecord(**{k: row[k] for k in row.keys()
                                   if k in ArchiveRecord.__dataclass_fields__})
            score = fuzz.ratio(text, rec.name) / 100.0
            if score >= threshold:
                results.append((rec, score))
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]

    def find_similar_dna_sequences(self, dna_sequence: str, threshold: float = 0.8,
                                   limit: int = 10) -> List[Tuple[DNASequenceRecord, float]]:
        rows = self.get_connection().execute(
            "SELECT * FROM dna_sequences WHERE is_valid=1").fetchall()
        results = []
        for row in rows:
            data = dict(row)
            data["is_valid"] = True
            score = fuzz.ratio(dna_sequence, data["dna_sequence"]) / 100.0
            if score >= threshold:
                results.append((DNASequenceRecord(**data), score))
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]

    def export_record_to_json(self, record_id: str, output_path: Optional[str] = None) -> str:
        record = self.load_record(record_id)
        if not record:
            return ""
        if not output_path:
            output_path = os.path.join(self.data_dir, "exports", "json", f"{record_id}.json")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(record.__dict__, f, ensure_ascii=False, indent=2)
        return output_path

    def backup_database(self, backup_dir: Optional[str] = None) -> str:
        backup_dir = backup_dir or os.path.join(self.data_dir, "backups")
        os.makedirs(backup_dir, exist_ok=True)
        backup_path = os.path.join(
            backup_dir, f"medical_archive_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db")
        self.get_connection().commit()
        shutil.copy2(self.db_path, backup_path)
        return backup_path

    def restore_database(self, backup_path: str) -> bool:
        if not os.path.exists(backup_path):
            return False
        self.close()
        shutil.copy2(backup_path, self.db_path)
        return True

    def get_statistics(self) -> dict:
        conn = self.get_connection()
        return {
            "total_records": conn.execute(
                "SELECT COUNT(*) FROM archive_records WHERE is_deleted=0").fetchone()[0],
            "total_users": conn.execute("SELECT COUNT(*) FROM users").fetchone()[0],
            "total_dna": conn.execute("SELECT COUNT(*) FROM dna_sequences").fetchone()[0],
            "total_decodes": conn.execute("SELECT COUNT(*) FROM decode_records").fetchone()[0],
            "total_diseases": conn.execute("SELECT COUNT(*) FROM disease_terms").fetchone()[0],
            "db_size_bytes": os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0,
        }


if __name__ == "__main__":
    print("DataStore v3.0 自检开始")
    db = DataStore()
    db.init_database()
    print(f"字段字典新增: {db.init_field_definitions()} 条")
    print(f"病症词典新增: {db.init_disease_terms()} 条")

    ok, msg = db.create_user("demo", "demo123")
    print(f"注册: {ok} - {msg}")
    user = db.verify_user("demo", "demo123")
    print(f"登录: {'成功' if user else '失败'}")

    record = ArchiveRecord(
        name="张三", gender="male", nation="汉族",
        entries=[
            {"field_key": "chief_complaint", "value_cn": "咳嗽三天"},
            {"field_key": "temperature", "value_cn": "36.8", "value_en": "36.8"},
            {"field_key": "followup_date", "seq": 1, "value_cn": "2026-11-01"},
            {"field_key": "followup_date", "seq": 2, "value_cn": "2026-11-07"},
        ],
        diseases=[{"term_key": "phenylketonuria", "result_cn": "阴性"}],
    )
    rid = db.save_record(record, owner_id=user["id"])
    print(f"保存档案: {rid}")
    loaded = db.load_record(rid)
    print(f"读回: {loaded.name}, 内容 {len(loaded.entries)} 行, 病症 {len(loaded.diseases)} 条")
    items, total = db.list_records(owner_id=user["id"])
    print(f"我的档案: {total} 条")
    db.close()
    print("自检完成")
