# -*- coding: utf-8 -*-
"""DNA医疗档案系统 - 程序入口

职责：初始化各模块 -> 组装依赖 -> 启动界面。
这里不写任何业务逻辑，业务全部交给各模块。

运行方式：
    python src/main.py
"""

import os
import sys

# 保证无论从哪个目录启动，都能 import 到 src 下的同级模块
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SRC_DIR)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

# ==========================================
# 全局配置（后续可抽到 config.py）
# ==========================================
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
DB_PATH = os.path.join(DATA_DIR, "db", "medical_archive.db")
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = "qwen2.5:7b-instruct"


def init_data_store():
    """初始化数据库模块：建表 + 预置病症词典"""
    from data_store import DataStore

    store = DataStore(db_path=DB_PATH, data_dir=DATA_DIR)
    store.init_database()
    inserted = store.init_disease_terms()
    print(f"[数据模块] 就绪: {DB_PATH}（本次新增病症词条 {inserted} 条）")
    return store


def init_ai_client():
    """初始化AI模块，连接失败只警告，不阻塞启动"""
    from ollama_api import OllamaClient

    client = OllamaClient(base_url=OLLAMA_BASE_URL, model_name=OLLAMA_MODEL)
    ok, message = client.test_connection()
    print(f"[AI模块] {'就绪' if ok else '警告'}: {message}")
    return client


def init_dna_codec():
    """DNA编解码模块（尚未实现时返回 None）"""
    try:
        from dna_codec import DNACodec
    except ImportError:
        print("[编解码模块] 未找到 dna_codec.py，暂以 None 注入")
        return None
    return DNACodec()


def init_error_corrector(data_store, ai_client, dna_codec):
    """智能纠错模块（尚未实现时返回 None）"""
    try:
        from error_corrector import ErrorCorrector
    except ImportError:
        print("[纠错模块] 未找到 error_corrector.py，暂以 None 注入")
        return None
    return ErrorCorrector(data_store=data_store, ai_client=ai_client, dna_codec=dna_codec)


def start_ui(data_store, ai_client, dna_codec, error_corrector):
    """启动界面：优先使用 HealthArchiveApp 类，否则回退到当前的过程式入口"""
    import ui_interface

    if hasattr(ui_interface, "HealthArchiveApp"):
        app = ui_interface.HealthArchiveApp(
            data_store=data_store,
            ai_client=ai_client,
            dna_codec=dna_codec,
            error_corrector=error_corrector,
        )
        app.start()
        return

    # 当前 ui_interface 还是过程式入口，无法注入依赖；
    # 先把它的全局 DB_PATH 指向统一数据库，避免出现两个数据库文件。
    print("[界面模块] 使用过程式入口（尚未重构为 HealthArchiveApp）")
    ui_interface.DB_PATH = DB_PATH
    import flet as ft

    ft.app(target=ui_interface.main)


def main():
    data_store = init_data_store()
    ai_client = init_ai_client()
    dna_codec = init_dna_codec()
    error_corrector = init_error_corrector(data_store, ai_client, dna_codec)

    try:
        start_ui(data_store, ai_client, dna_codec, error_corrector)
    finally:
        close = getattr(data_store, "close", None)
        if callable(close):
            close()


if __name__ == "__main__":
    main()
