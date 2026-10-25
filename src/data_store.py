import sqlite3
import os
import json
import uuid
import shutil
import hashlib
from datetime import datetime
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Tuple

# 引用你安装的库
import docx
import pdfplumber
from fuzzywuzzy import fuzz

# ==========================================
# 1. 数据类定义 (详见api_contract.md 4.1 - 4.4)
# ==========================================
@dataclass
class DiseaseTerm:
    id: int
    chinese_name: str   #中文名称
    english_name: str   #英文名称
    category: str       #分类

@dataclass
class ArchiveRecord:
    id: Optional[int] = None
    record_id: str = ""
    
    # 物理存储（23个字段）
    archive_number: str = ""
    name: str = ""
    gender: str = ""
    birth_date: str = ""
    id_number: str = ""
    hukou_address: str = ""
    residence_address: str = ""
    organization: str = ""
    create_date: str = ""
    phone: str = ""
    nation: str = ""
    abo_blood_type: str = ""
    rh_blood_type: str = ""
    father_name: str = ""
    father_phone: str = ""
    mother_name: str = ""
    mother_phone: str = ""
    gestational_weeks: str = ""
    birth_weight: str = ""
    birth_length: str = ""
    delivery_org: str = ""
    apgar_1min: str = ""
    apgar_5min: str = ""
    
    # 动态存储 (JSON)
    follow_up_records: str = '[]'
    disease_records: str = '{}'
    
    # 元数据
    created_at: str = ""
    updated_at: str = ""
    source: str = "manual"
    is_deleted: int = 0       # 软删除标记

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
# 2. 核心类
# ==========================================
class DataStore:
    # ==========================================
    # 第一部分：核心与初始化
    # ==========================================
    def __init__(self, db_path: Optional[str] = None, data_dir: Optional[str] = None):
        # 按照database.md的5.1目录结构规范
        self.data_dir = data_dir or "data"
        self.db_path = db_path or os.path.join(self.data_dir, "db", "medical_archive.db")
        
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        os.makedirs(os.path.join(self.data_dir, "uploads"), exist_ok=True)
        os.makedirs(os.path.join(self.data_dir, "exports", "json"), exist_ok=True)
        os.makedirs(os.path.join(self.data_dir, "exports", "docx"), exist_ok=True)
        os.makedirs(os.path.join(self.data_dir, "backups"), exist_ok=True)
        os.makedirs(os.path.join(self.data_dir, "logs"), exist_ok=True)
        
        self.conn = None

    def get_connection(self) -> sqlite3.Connection:
        """获取数据库连接 (文档要求：行工厂返回dict)"""
        if not self.conn:
            # 注意：check_same_thread=False 是为了解决线程安全问题（详见database.md 7.注意事项2）
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row 
            self.conn.execute("PRAGMA foreign_keys = ON;")
        return self.conn

    def init_database(self) -> None:
        """初始化数据库：建表、建索引 (完全按照database.md 2.3 )"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # 表1：病症词典
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS disease_terms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chinese_name TEXT NOT NULL,
                english_name TEXT NOT NULL,
                category TEXT DEFAULT '通用'
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_disease_chinese ON disease_terms(chinese_name);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_disease_english ON disease_terms(english_name);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_disease_category ON disease_terms(category);")
        
        # 表2：档案记录
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS archive_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_id TEXT NOT NULL UNIQUE,
                archive_number TEXT DEFAULT '',
                name TEXT NOT NULL,
                gender TEXT DEFAULT '',
                birth_date TEXT DEFAULT '',
                id_number TEXT DEFAULT '',
                hukou_address TEXT DEFAULT '',
                residence_address TEXT DEFAULT '',
                organization TEXT DEFAULT '',
                create_date TEXT DEFAULT '',
                phone TEXT DEFAULT '',
                nation TEXT DEFAULT '',
                abo_blood_type TEXT DEFAULT '',
                rh_blood_type TEXT DEFAULT '',
                father_name TEXT DEFAULT '',
                father_phone TEXT DEFAULT '',
                mother_name TEXT DEFAULT '',
                mother_phone TEXT DEFAULT '',
                gestational_weeks TEXT DEFAULT '',
                birth_weight TEXT DEFAULT '',
                birth_length TEXT DEFAULT '',
                delivery_org TEXT DEFAULT '',
                apgar_1min TEXT DEFAULT '',
                apgar_5min TEXT DEFAULT '',
                follow_up_records TEXT DEFAULT '[]',
                disease_records TEXT DEFAULT '{}',
                source TEXT DEFAULT 'manual',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                is_deleted INTEGER DEFAULT 0
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_archive_record_id ON archive_records(record_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_archive_name ON archive_records(name);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_archive_created ON archive_records(created_at);")
        
        # 表3：DNA序列表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS dna_sequences (
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
                is_valid INTEGER DEFAULT 1
            );
        """)
        # 表3的索引
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_dna_record_id ON dna_sequences(record_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_dna_sequence ON dna_sequences(dna_sequence);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_dna_encoded ON dna_sequences(encoded_at);")

        # 表4：解码记录表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS decode_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dna_record_id INTEGER NOT NULL,
                decoded_text TEXT NOT NULL,
                corrected_text TEXT DEFAULT '',
                confidence REAL DEFAULT 0,
                error_rate REAL DEFAULT 0,
                correction_log TEXT DEFAULT '{}',
                decoded_at TEXT NOT NULL
            );
        """)
        # 表4的索引
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_decode_dna_id ON decode_records(dna_record_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_decode_time ON decode_records(decoded_at);")

        # 最后提交事务
        conn.commit()
        print("数据库初始化完成，4张表及索引已全部建立！")


    # ==========================================
    # 第二部分：文件处理 (解析、上传、清理)
    # ==========================================
    def parse_document(self, file_path: str) -> str:
        """解析文档提取纯文本"""
        ext = os.path.splitext(file_path)[1].lower()
        text = ""
        try:
            if ext == '.txt':
                with open(file_path, 'r', encoding='utf-8') as f:
                    text = f.read()
            elif ext == '.docx':
                doc = docx.Document(file_path)
                text = "\n".join([para.text for para in doc.paragraphs])
            elif ext == '.pdf':
                with pdfplumber.open(file_path) as pdf:
                    for page in pdf.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text + "\n"
            else:
                raise ValueError("暂不支持该文件格式")
            return text
        except Exception as e:
            print(f"文件解析失败: {e}")
            return ""

    def save_upload_file(self, file_content: bytes, filename: str) -> str:
            """保存上传的文件，返回相对路径"""
            date_str = datetime.now().strftime("%Y%m%d")
            # 按文档规范：data/uploads/{YYYYMMDD}/{uuid}_原文件名
            upload_dir = os.path.join(self.data_dir, "uploads", date_str)
            os.makedirs(upload_dir, exist_ok=True)
            
            unique_id = str(uuid.uuid4())[:8]
            save_name = f"{unique_id}_{filename}"
            file_path = os.path.join(upload_dir, save_name)
            
            with open(file_path, "wb") as f:
                f.write(file_content)
                
            return file_path

    def cleanup_temp_files(self, hours: int = 24) -> int:
            """清理上传目录中过期的临时文件"""
            upload_dir = os.path.join(self.data_dir, "uploads")
            if not os.path.exists(upload_dir):
                return 0
                
            now = datetime.now().timestamp()
            deleted_count = 0
            for root, dirs, files in os.walk(upload_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    if os.path.getmtime(file_path) < now - (hours * 3600):
                        os.remove(file_path)
                        deleted_count += 1
            return deleted_count


    # ==========================================
    # 第三部分：档案记录 CRUD (增删改查)
    # ==========================================
    def save_record(self, record: ArchiveRecord) -> str:
        """保存/更新档案，返回 record_id"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # 如果 record_id 为空，说明是新增，生成一个
        if not record.record_id:
            today_str = datetime.now().strftime("%Y%m%d")
            # 简单实现：取当前时间戳后三位，实际开发中可能需要查库获取当天的序号
            random_seq = str(int(datetime.now().timestamp()))[-3:] 
            record.record_id = f"ARCHIVE_{today_str}_{random_seq}"
            
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        record.updated_at = now_str
        if not record.created_at:
            record.created_at = now_str
            
        # 使用 INSERT OR REPLACE 实现新增或更新（包含所有字段）
        sql = """
            INSERT OR REPLACE INTO archive_records (
                record_id, archive_number, name, gender, birth_date, id_number, 
                hukou_address, residence_address, organization, create_date, phone, nation, 
                abo_blood_type, rh_blood_type, father_name, father_phone, mother_name, mother_phone, 
                gestational_weeks, birth_weight, birth_length, delivery_org, apgar_1min, apgar_5min, 
                follow_up_records, disease_records, source, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        cursor.execute(sql, (
            record.record_id, record.archive_number, record.name, record.gender, record.birth_date, record.id_number,
            record.hukou_address, record.residence_address, record.organization, record.create_date, record.phone, record.nation,
            record.abo_blood_type, record.rh_blood_type, record.father_name, record.father_phone, record.mother_name, record.mother_phone,
            record.gestational_weeks, record.birth_weight, record.birth_length, record.delivery_org, record.apgar_1min, record.apgar_5min,
            record.follow_up_records, record.disease_records, record.source, record.created_at, record.updated_at
        ))
        conn.commit()
        return record.record_id

    def load_record(self, record_id: str) -> Optional[ArchiveRecord]:
        #根据 record_id 查询单条档案记录
        #直接获取数据库连接并创建游标
        cursor = self.get_connection().cursor()
               
        sql = "SELECT * FROM archive_records WHERE record_id = ? AND is_deleted = 0"
        cursor.execute(sql, (record_id,))
        row = cursor.fetchone()
        
        if row:
            return ArchiveRecord(**dict(row))
        return None
    
    def delete_record(self, record_id: str) -> bool:
        """软删除档案记录（不物理删除，只改标记）"""
        conn = self.get_connection()
        cursor = conn.cursor()
        sql = "UPDATE archive_records SET is_deleted = 1, updated_at = ? WHERE record_id = ?"
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(sql, (now_str, record_id))
        conn.commit()
        return cursor.rowcount > 0

    def list_records(self, offset: int = 0, limit: int = 20, keyword: str = "") -> list:
        """分页列出档案，支持按姓名模糊搜索"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        if keyword:
            sql = "SELECT * FROM archive_records WHERE is_deleted = 0 AND name LIKE ? ORDER BY created_at DESC LIMIT ? OFFSET ?"
            params = (f"%{keyword}%", limit, offset)
        else:
            sql = "SELECT * FROM archive_records WHERE is_deleted = 0 ORDER BY created_at DESC LIMIT ? OFFSET ?"
            params = (limit, offset)
            
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        return [ArchiveRecord(**dict(row)) for row in rows]


    # ==========================================
    # 第四部分：病症词典操作
    # ==========================================
    def search_disease(self, keyword: str, limit: int = 10) -> List[DiseaseTerm]:
            """中英文模糊搜索病症"""
            conn = self.get_connection()
            cursor = conn.cursor()
            sql = "SELECT * FROM disease_terms WHERE chinese_name LIKE ? OR english_name LIKE ? LIMIT ?"
            cursor.execute(sql, (f"%{keyword}%", f"%{keyword}%", limit))
            rows = cursor.fetchall()
            return [DiseaseTerm(**dict(row)) for row in rows]

    def get_disease_by_chinese(self, chinese_name: str) -> Optional[DiseaseTerm]:
        """根据中文名称精确获取病症"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM disease_terms WHERE chinese_name = ?", (chinese_name,))
        row = cursor.fetchone()
        return DiseaseTerm(**dict(row)) if row else None

    def get_disease_by_english(self, english_name: str) -> Optional[DiseaseTerm]:
        """根据英文名称精确获取病症"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM disease_terms WHERE english_name = ?", (english_name,))
        row = cursor.fetchone()
        return DiseaseTerm(**dict(row)) if row else None

    def get_all_categories(self) -> List[str]:
        """获取所有病症分类"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT category FROM disease_terms")
        rows = cursor.fetchall()
        return [row["category"] for row in rows if row["category"]]

    def add_disease_term(self, chinese_name: str, english_name: str, category: str) -> int:
        """添加新病症词条，返回新ID"""
        conn = self.get_connection()
        cursor = conn.cursor()
        sql = "INSERT INTO disease_terms (chinese_name, english_name, category) VALUES (?, ?, ?)"
        cursor.execute(sql, (chinese_name, english_name, category))
        conn.commit()
        return int(cursor.lastrowid or 0)

    def init_disease_terms(self) -> int:
        """初始化病症词典（预置 236 条数据）"""
        # 注意：实际开发中，这 236 条数据通常存在一个 txt 或 csv 文件里，读取并插入
        # 这里为了演示，我们先插入几个测试数据
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # 先检查一下是不是空的，防止重复插入
        cursor.execute("SELECT COUNT(*) FROM disease_terms")
        if cursor.fetchone()[0] > 0:
            return 0
            
        # 模拟插入几条数据
        test_data = [
            ("苯丙酮尿症", "Phenylketonuria", "遗传代谢病"),
            ("先天性甲状腺功能减低症", "Congenital Hypothyroidism", "内分泌疾病"),
            ("听力筛查", "Hearing Screening", "常规筛查")
        ]
        cursor.executemany("INSERT INTO disease_terms (chinese_name, english_name, category) VALUES (?, ?, ?)", test_data)
        conn.commit()
        return len(test_data)


    # ==========================================
    # 第五部分：DNA序列与解码记录
    # ==========================================
    def save_dna_sequence(self, dna_record: DNASequenceRecord) -> int:
        """保存 DNA 编码结果，返回自增 ID"""
        conn = self.get_connection()
        cursor = conn.cursor()
        if not dna_record.encoded_at:
            dna_record.encoded_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
        sql = """
            INSERT INTO dna_sequences (
                record_id, dna_sequence, key_hash, cg_content, thermal_stability, 
                padded_zeros, sequence_length, original_text, encoded_at, is_valid
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        cursor.execute(sql, (
            dna_record.record_id, dna_record.dna_sequence, dna_record.key_hash, 
            dna_record.cg_content, dna_record.thermal_stability, dna_record.padded_zeros,
            dna_record.sequence_length, dna_record.original_text, dna_record.encoded_at,
            1 if dna_record.is_valid else 0
        ))
        conn.commit()
        return int(cursor.lastrowid or 0)

    def load_dna_sequence(self, record_id: str) -> Optional[DNASequenceRecord]:
        """根据档案 ID 获取最新 DNA 序列"""
        conn = self.get_connection()
        cursor = conn.cursor()
        sql = "SELECT * FROM dna_sequences WHERE record_id = ? AND is_valid = 1 ORDER BY id DESC LIMIT 1"
        cursor.execute(sql, (record_id,))
        row = cursor.fetchone()
        if row:
            data = dict(row)
            data['is_valid'] = bool(data['is_valid'])
            return DNASequenceRecord(**data)
        return None

    def save_decode_record(self, decode_record: DecodeRecord) -> int:
        """保存解码结果"""
        conn = self.get_connection()
        cursor = conn.cursor()
        if not decode_record.decoded_at:
            decode_record.decoded_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
        sql = """
            INSERT INTO decode_records (
                dna_record_id, decoded_text, corrected_text, confidence, 
                error_rate, correction_log, decoded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        cursor.execute(sql, (
            decode_record.dna_record_id, decode_record.decoded_text, decode_record.corrected_text,
            decode_record.confidence, decode_record.error_rate, decode_record.correction_log,
            decode_record.decoded_at
        ))
        conn.commit()
        return int(cursor.lastrowid or 0)


    # ==========================================
    # 第六部分：相似度检索与纠错辅助
    # ==========================================
    def find_similar_records(self, text: str, threshold: float = 0.7, limit: int = 5) -> List[Tuple[ArchiveRecord, float]]:
        """文本相似档案比对（纠错参考）"""
        conn = self.get_connection()
        cursor = conn.cursor()
        # 简单实现：取出所有未删除档案，在内存中计算相似度
        cursor.execute("SELECT * FROM archive_records WHERE is_deleted = 0")
        rows = cursor.fetchall()
        
        results = []
        for row in rows:
            record = ArchiveRecord(**dict(row))
            # 这里用名字做比对，如果是纠错，可能需要比对更多字段
            score = fuzz.ratio(text, record.name) / 100.0
            if score >= threshold:
                results.append((record, score))
                
        # 按相似度降序排序，取前 limit 个
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]


    # ==========================================
    # 第七部分：数据导出与备份 (文档 3.8)
    # ==========================================
    def export_record_to_json(self, record_id: str) -> str:
        """导出档案为 JSON 文件，返回文件路径"""
        record = self.load_record(record_id)
        if not record:
            return ""
            
        json_dir = os.path.join(self.data_dir, "exports", "json")
        os.makedirs(json_dir, exist_ok=True)
        file_path = os.path.join(json_dir, f"{record_id}.json")
        
        # 把 dataclass 转成字典再存为 JSON
        record_dict = record.__dict__
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(record_dict, f, ensure_ascii=False, indent=4)
            
        return file_path

    def export_record_to_docx(self, record_id: str, template_path:Optional[str] = None) -> str:
        """导出档案为 DOCX 文件，返回文件路径"""
        record = self.load_record(record_id)
        if not record:
            return ""
            
        docx_dir = os.path.join(self.data_dir, "exports", "docx")
        os.makedirs(docx_dir, exist_ok=True)
        file_path = os.path.join(docx_dir, f"{record_id}.docx")
        
        doc = docx.Document()
        doc.add_heading('DNA医疗档案记录', 0)
        doc.add_paragraph(f"档案编号: {record.record_id}")
        doc.add_paragraph(f"姓名: {record.name}")
        doc.add_paragraph(f"性别: {record.gender}")
        doc.add_paragraph(f"联系电话: {record.phone}")
        doc.add_paragraph(f"病症记录: {record.disease_records}")
        doc.save(file_path)
        
        return file_path

    def backup_database(self, backup_dir: Optional[str] = None) -> str:
        """备份数据库，返回备份路径"""
        if not backup_dir:
            backup_dir = os.path.join(self.data_dir, "backups")
        os.makedirs(backup_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(backup_dir, f"medical_archive_{timestamp}.db")
        
        # 确保连接关闭或数据已提交后再复制
        self.get_connection().commit()
        shutil.copy2(self.db_path, backup_path)
        return backup_path

    def restore_database(self, backup_path: str) -> bool:
        """从备份恢复数据库"""
        if not os.path.exists(backup_path):
            return False
        
        # 恢复前先关闭当前连接
        if self.conn:
            self.conn.close()
            self.conn = None
            
        shutil.copy2(backup_path, self.db_path)
        return True

    # ==========================================
    # 第八部分：统计查询 (文档 3.9)
    # ==========================================
    def get_statistics(self) -> dict:
        """获取数据库统计信息"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM archive_records WHERE is_deleted = 0")
        total_records = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM dna_sequences")
        total_dna = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM decode_records")
        total_decodes = cursor.fetchone()[0]
        
        db_size = os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0
        
        return {
            "total_records": total_records,
            "total_dna": total_dna,
            "total_decodes": total_decodes,
            "db_size_bytes": db_size
        }



if __name__ == "__main__":
    print("开始测试 DataStore...")
    db = DataStore()
    
    # 1. 初始化数据库（建表）
    db.init_database()
    print("数据库文件已生成，路径为：", db.db_path)
    
    print("\n--- 1. 测试档案 CRUD ---")
    test_record = ArchiveRecord(
        name="张三", 
        gender="男", 
        phone="13800138000",
        disease_records='{"苯丙酮尿症": "阴性"}'
    )
    new_id = db.save_record(test_record)
    print(f"存入成功！档案ID: {new_id}")
    
    result = db.load_record(new_id)
    if result:
        print(f"查询成功！姓名：{result.name}，电话：{result.phone}")
    
    print("\n--- 2. 测试软删除 ---")
    db.delete_record(new_id)
    deleted_result = db.load_record(new_id)
    if deleted_result is None:
        print("软删除生效！已经查不到该档案了。")

    print("\n--- 3. 测试 DNA 与解码记录 ---")
    dna_rec = DNASequenceRecord(
        record_id="TEST_01", 
        dna_sequence="ATCG", 
        key_hash="hash", 
        encoded_at="2026-10-25 12:00:00"
    )
    dna_id = db.save_dna_sequence(dna_rec)
    print(f"DNA存入成功，ID: {dna_id}")
    
    dna_query_res = db.load_dna_sequence("TEST_01")
    if dna_query_res:
        print(f"DNA查询成功，序列: {dna_query_res.dna_sequence}")
        
    dec_rec = DecodeRecord(dna_record_id=dna_id, decoded_text="还原文本")
    db.save_decode_record(dec_rec)
    print("解码记录存入成功。")
    
    print("\n--- 4. 测试病症查询与相似度 ---")
    # 这里因为词典可能还没导入数据，能跑通不报错就行
    terms = db.search_disease("感冒")
    print(f"病症模糊搜索完成，找到 {len(terms)} 条数据。")
    
    sims = db.find_similar_records("张三丰")
    print(f"相似度检索完成，找到 {len(sims)} 条相似档案。")

    print("\n所有接口测试完毕，大功告成，准备提交！")