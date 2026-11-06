# -*- coding: utf-8 -*-
"""DNA 医疗档案系统 - 桌面端界面层

本文件只负责界面呈现与交互编排，业务数据规则见 docs/modules。
视觉规范：统一使用下方设计变量，避免各页面手工散写颜色与尺寸。
"""

import flet as ft
from datetime import datetime
import json
import sqlite3
import os
import random
import threading
import time
import urllib.request
import pypinyin

# 【全局游客标记】
is_visitor = False

# 项目路径与资源
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
COVER_IMAGE = os.path.join(PROJECT_ROOT, "assets", "cover.png")
USERS_FILE = os.path.join(PROJECT_ROOT, "data", "users.json")

# ==========================================
# 0. 设计变量（统一视觉风格）
# ==========================================
C_INK = "#0F172A"
C_TEXT = "#1E293B"
C_SUB = "#64748B"
C_MUTED = "#94A3B8"
C_LINE = "#E2E8F0"
C_BG = "#F4F7FB"
C_SURFACE = "#FFFFFF"
C_FIELD = "#F8FAFC"
C_PRIMARY = "#2563EB"
C_PRIMARY_SOFT = "#EFF6FF"
C_TEAL = "#0D9488"
C_AMBER = "#D97706"
C_AMBER_SOFT = "#FFFBEB"
C_DANGER = "#DC2626"
C_DANGER_SOFT = "#FEF2F2"

SHADOW_CARD = ft.BoxShadow(blur_radius=24, spread_radius=0, color="#0F172A12")

DIALOG_SHAPE = ft.RoundedRectangleBorder(radius=18)
BUTTON_SHAPE = ft.RoundedRectangleBorder(radius=10)


def _icon_badge(icon, color, size=42, icon_size=22, radius=12):
    """统一的图标胶囊：浅色底 + 主题色图标"""
    return ft.Container(
        width=size, height=size, border_radius=radius,
        bgcolor=f"{color}18", alignment=ft.alignment.center,
        content=ft.Icon(icon, color=color, size=icon_size),
    )


def _field_style():
    """表单输入框统一样式"""
    return dict(
        border_radius=10,
        filled=True,
        bgcolor=C_FIELD,
        border_color=C_LINE,
        focused_border_color=C_PRIMARY,
        content_padding=ft.padding.symmetric(horizontal=14, vertical=14),
        text_size=14,
        label_style=ft.TextStyle(size=13, color="#475569"),
        hint_style=ft.TextStyle(size=12, color=C_MUTED),
    )


def _primary_button(text, icon=None, on_click=None):
    return ft.ElevatedButton(
        text, icon=icon, on_click=on_click,
        style=ft.ButtonStyle(
            bgcolor=C_PRIMARY, color="white", shape=BUTTON_SHAPE,
            elevation=0, padding=ft.padding.symmetric(horizontal=22, vertical=16),
        ),
    )


def _ghost_button(text, icon=None, on_click=None):
    return ft.OutlinedButton(
        text, icon=icon, on_click=on_click,
        style=ft.ButtonStyle(
            color=C_TEXT, shape=BUTTON_SHAPE,
            side=ft.BorderSide(1, C_LINE),
            padding=ft.padding.symmetric(horizontal=20, vertical=16),
        ),
    )


def _pill(text, color=C_SUB, bgcolor="#FFFFFF14"):
    return ft.Container(
        padding=ft.padding.symmetric(horizontal=14, vertical=7),
        border_radius=50, bgcolor=bgcolor,
        content=ft.Text(text, size=12, color=color),
    )


# ==========================================
# 1. 用户账号管理（本地 JSON，后续可迁移到数据库）
# ==========================================

def _load_users():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_users(users):
    os.makedirs(os.path.dirname(USERS_FILE), exist_ok=True)
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)


# ==========================================
# 2. 数据库查询模块
# ==========================================

DB_PATH = os.path.join(PROJECT_ROOT, "data", "db", "medical_archive.db")


def search_disease_terms(search_text, limit=5):
    if not os.path.exists(DB_PATH):
        return []
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('''
    SELECT id, chinese_name, english_name, category
    FROM disease_terms
    WHERE chinese_name LIKE ? OR english_name LIKE ?
    ORDER BY category, chinese_name
    LIMIT ?
    ''', (f'%{search_text}%', f'%{search_text}%', limit))
    results = cur.fetchall()
    conn.close()
    return results


def get_disease_by_chinese(chinese_name):
    if not os.path.exists(DB_PATH):
        return chinese_name
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('SELECT english_name FROM disease_terms WHERE chinese_name = ?', (chinese_name,))
    result = cur.fetchone()
    conn.close()
    return result[0] if result else chinese_name


# ==========================================
# 3. 拼音转换工具
# ==========================================

def to_pinyin_string(text):
    if not text:
        return ""
    py_list = pypinyin.pinyin(text, style=pypinyin.Style.NORMAL)
    return "_".join([item[0] for item in py_list])


# ==========================================
# 4. 文档解析模块（AI 识别用）
# ==========================================

def extract_text_from_file(path):
    """按扩展名提取文档纯文本"""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".txt":
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    elif ext == ".docx":
        from docx import Document
        doc = Document(path)
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    elif ext == ".pdf":
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)
    else:
        raise ValueError(f"不支持的文件类型: {ext}（仅支持 txt / docx / pdf）")


def ask_ollama(text, on_progress=None, model="qwen2.5:7b-instruct"):
    """流式调用本地 ollama：AI 边生成边回调进度，返回提取出的 dict"""
    fields_hint = "、".join(PHYSICAL_FIELDS + DISEASE_FIELDS)
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是健康档案信息提取助手。只从用户提供的文档中提取字段值，输出严格的 JSON 对象（不要 markdown 代码块、不要任何其他文字）。如果文档中某字段明确写着'无'、'正常'、'未检出'等，请把该值原样填入，不要留空；只有文档中完全没提到的字段才留空字符串。"},
            {"role": "user", "content": f"可提取的字段有：{fields_hint}\n\n以下是档案文档内容：\n{text}"}
        ],
        "stream": True,
        "format": "json",
        "options": {"temperature": 0.1}
    }

    req = urllib.request.Request(
        "http://localhost:11434/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )

    full = ""
    with urllib.request.urlopen(req, timeout=300) as resp:
        for raw_line in resp:
            line = raw_line.decode("utf-8").strip()
            if not line:
                continue
            chunk = json.loads(line)
            piece = chunk.get("message", {}).get("content", "")
            if piece:
                full += piece
                if on_progress:
                    on_progress(len(full))

    start = full.find("{")
    end = full.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("AI 输出不是 JSON")
    return json.loads(full[start:end + 1])


# 字段分类定义
PHYSICAL_FIELDS = [
    "档案编号", "姓名", "性别", "出生日期", "证件号码", "户籍地址", "常住地址",
    "建档机构", "建档日期", "联系电话", "民族", "ABO血型", "Rh血型",
    "父亲姓名", "父亲联系电话", "母亲姓名", "母亲联系电话", "出生孕周",
    "出生体重", "出生身长", "分娩机构", "Apgar_1分钟", "Apgar_5分钟"
]

DISEASE_FIELDS = ["苯丙酮尿症", "先天性甲状腺功能减低症", "听力筛查", "过敏史", "先天异常", "既往住院史", "家族遗传病史"]

REPEATED_FIELDS = ["随访日期", "当前体重", "体温"]


# =====================【登录选择页面】=====================

def login_select_page(page: ft.Page):
    page.title = "DNA 医疗档案系统"
    page.clean()
    page.padding = 0
    page.spacing = 0
    page.bgcolor = C_INK
    page.window_width = 1200
    page.window_height = 780
    page.window_min_width = 900
    page.window_min_height = 620

    users = _load_users()

    def show_snack(msg: str, color: str = C_DANGER):
        page.snack_bar = ft.SnackBar(ft.Text(msg, color="white"), bgcolor=color)
        page.snack_bar.open = True
        page.update()

    def close_dlg(dlg):
        dlg.open = False
        page.update()

    def enter_main(visitor: bool):
        global is_visitor
        is_visitor = visitor
        page.clean()
        run_app_logic(page)

    def dialog_input(label, password=False):
        return ft.TextField(
            label=label, password=password, can_reveal_password=password,
            width=320, **_field_style()
        )

    def build_auth_dialog(title, subtitle, icon, color, field_controls, confirm_text, on_confirm):
        dlg = ft.AlertDialog(
            modal=True,
            bgcolor=C_SURFACE,
            shape=DIALOG_SHAPE,
            title_padding=ft.padding.only(left=24, right=24, top=24, bottom=0),
            content_padding=ft.padding.only(left=24, right=24, top=18, bottom=8),
            actions_padding=ft.padding.only(left=24, right=24, top=8, bottom=20),
            title=ft.Row(
                spacing=12,
                controls=[
                    _icon_badge(icon, color, size=44, icon_size=22),
                    ft.Column(
                        spacing=2,
                        controls=[
                            ft.Text(title, size=19, weight="bold", color=C_TEXT),
                            ft.Text(subtitle, size=12, color=C_SUB),
                        ],
                    ),
                ],
            ),
            content=ft.Container(
                width=320,
                content=ft.Column(field_controls, spacing=14, tight=True),
            ),
            actions=[
                ft.TextButton("取消", on_click=lambda e: close_dlg(dlg)),
                _primary_button(confirm_text, on_click=on_confirm),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        return dlg

    def login_click(e):
        user_input = dialog_input("账号")
        pwd_input = dialog_input("密码", password=True)

        def do_login(ev):
            username = (user_input.value or "").strip()
            password = pwd_input.value or ""
            if not username or not password:
                show_snack("请输入账号和密码")
                return
            all_users = {"admin": "123456", **users}
            if all_users.get(username) == password:
                close_dlg(dlg_login)
                enter_main(visitor=False)
            else:
                show_snack("账号或密码错误")

        dlg_login = build_auth_dialog(
            "账号登录", "使用已注册账号进入系统", ft.icons.LOCK_OUTLINE, C_PRIMARY,
            [user_input, pwd_input], "确认登录", do_login
        )
        page.dialog = dlg_login
        dlg_login.open = True
        page.update()

    def register_click(e):
        user_input = dialog_input("账号")
        pwd_input = dialog_input("密码", password=True)
        pwd2_input = dialog_input("确认密码", password=True)

        def do_register(ev):
            nonlocal users
            username = (user_input.value or "").strip()
            password = pwd_input.value or ""
            password2 = pwd2_input.value or ""
            if not username or not password:
                show_snack("账号和密码不能为空")
                return
            if password != password2:
                show_snack("两次输入的密码不一致")
                return
            if username in users:
                show_snack("该账号已存在")
                return
            users[username] = password
            _save_users(users)
            close_dlg(dlg_register)
            show_snack(f"账号 {username} 注册成功，请登录", color=C_TEAL)

        dlg_register = build_auth_dialog(
            "注册账号", "创建新的本地档案账号", ft.icons.PERSON_ADD, C_TEAL,
            [user_input, pwd_input, pwd2_input], "确认注册", do_register
        )
        page.dialog = dlg_register
        dlg_register.open = True
        page.update()

    def visitor_click(e):
        enter_main(visitor=True)

    def make_option_tile(icon: str, title: str, subtitle: str, accent: str, on_click):
        def on_hover(e):
            e.control.bgcolor = "#FFFFFF1C" if e.data == "true" else "#FFFFFF0A"
            e.control.border = ft.border.all(1, "#FFFFFF40" if e.data == "true" else "#FFFFFF22")
            e.control.update()

        return ft.Container(
            height=82,
            padding=ft.padding.symmetric(horizontal=16, vertical=14),
            bgcolor="#FFFFFF0A",
            border=ft.border.all(1, "#FFFFFF22"),
            border_radius=16,
            ink=True,
            on_click=on_click,
            on_hover=on_hover,
            content=ft.Row(
                spacing=14,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    _icon_badge(icon, accent, size=46, icon_size=24, radius=13),
                    ft.Column(
                        expand=True,
                        spacing=3,
                        alignment=ft.MainAxisAlignment.CENTER,
                        controls=[
                            ft.Text(title, size=16, weight="bold", color="white"),
                            ft.Text(subtitle, size=12, color="#CBD5E1"),
                        ],
                    ),
                    ft.Icon(ft.icons.CHEVRON_RIGHT, color=C_MUTED, size=20),
                ],
            ),
        )

    logo = ft.Container(
        width=62, height=62, border_radius=18,
        gradient=ft.LinearGradient(
            colors=["#3B82F6", "#0D9488"],
            begin=ft.alignment.top_left, end=ft.alignment.bottom_right,
        ),
        alignment=ft.alignment.center,
        shadow=ft.BoxShadow(blur_radius=24, color="#2563EB59"),
        content=ft.Icon(ft.icons.BIOTECH, color="white", size=32),
    )

    brand_col = ft.Column(
        width=470,
        spacing=24,
        controls=[
            ft.Row(
                spacing=14,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    logo,
                    _pill("本地优先 · 离线可用", "#CBD5E1"),
                ],
            ),
            ft.Text("DNA 医疗档案系统", size=42, weight="bold", color="white"),
            ft.Text(
                "面向医疗冷归档的加密存储与双语可追溯方案",
                size=15, color="#CBD5E1",
            ),
            ft.Row(
                spacing=10, wrap=True,
                controls=[
                    _pill("端到端编码"),
                    _pill("中英双语"),
                    _pill("隐私优先"),
                ],
            ),
            ft.Container(height=6),
            ft.Text("v2.0 · Local First · Encrypted Archive", size=12, color="#64748B"),
        ],
    )

    auth_panel = ft.Container(
        width=400,
        padding=ft.padding.all(30),
        bgcolor="#FFFFFF0F",
        border=ft.border.all(1, "#FFFFFF26"),
        border_radius=24,
        content=ft.Column(
            spacing=16,
            controls=[
                ft.Text("欢迎使用", size=26, weight="bold", color="white"),
                ft.Text("请选择进入系统的方式", size=13, color="#CBD5E1"),
                ft.Container(height=4),
                make_option_tile(ft.icons.PERSON_ADD, "注册", "创建新的本地账号", "#38BDF8", register_click),
                make_option_tile(ft.icons.LOCK_OUTLINE, "账号登录", "已有账号直接登录", "#34D399", login_click),
                make_option_tile(ft.icons.PERSON_OUTLINE, "游客登录", "免登录体验，不可保存档案", "#FBBF24", visitor_click),
                ft.Container(height=6),
                ft.Text(
                    "账号信息仅保存在本机 data/users.json",
                    size=11, color="#94A3B8", text_align=ft.TextAlign.CENTER,
                ),
            ],
        ),
    )

    page.add(
        ft.Stack(
            expand=True,
            controls=[
                ft.Container(expand=True, image_src=COVER_IMAGE, image_fit=ft.ImageFit.COVER),
                ft.Container(
                    expand=True,
                    gradient=ft.LinearGradient(
                        colors=["#0F172AF2", "#0F172A99", "#0F172A8C", "#0F172AE0"],
                        begin=ft.alignment.center_left,
                        end=ft.alignment.center_right,
                    ),
                ),
                ft.Container(
                    expand=True,
                    padding=ft.padding.all(40),
                    alignment=ft.alignment.center,
                    content=ft.Row(
                        alignment=ft.MainAxisAlignment.CENTER,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=56,
                        wrap=True,
                        controls=[brand_col, auth_panel],
                    ),
                ),
            ],
        )
    )
    page.update()


# =====================【业务主逻辑】=====================

def run_app_logic(page: ft.Page):
    page.title = "DNA 医疗档案系统"
    page.padding = 0
    page.spacing = 0

    # ===== 全局唯一的文件选择器 =====
    picker_callback = {"fn": None}

    def on_picker_result(e: ft.FilePickerResultEvent):
        fn = picker_callback["fn"]
        picker_callback["fn"] = None
        if fn:
            fn(e)

    file_picker = ft.FilePicker(on_result=on_picker_result)
    page.overlay.append(file_picker)

    def close_dialog(dlg):
        dlg.open = False
        page.update()

    # ========== 基础弹窗 ==========

    def show_dialog(page, title_text, options):
        """options: [(key, icon, 标题, 说明), ...]"""

        def tile(key, icon, label, desc):
            def on_hover(e):
                e.control.bgcolor = C_PRIMARY_SOFT if e.data == "true" else C_FIELD
                e.control.border = ft.border.all(1, "#BFDBFE" if e.data == "true" else C_LINE)
                e.control.update()

            return ft.Container(
                width=168, height=142,
                bgcolor=C_FIELD,
                border=ft.border.all(1, C_LINE),
                border_radius=14,
                alignment=ft.alignment.center,
                ink=True,
                on_click=lambda e: close_dlg(page, dlg, key),
                on_hover=on_hover,
                content=ft.Column(
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=10,
                    controls=[
                        _icon_badge(icon, C_PRIMARY, size=48, icon_size=24),
                        ft.Text(label, size=15, weight="bold", color=C_TEXT),
                        ft.Text(desc, size=11, color=C_SUB, text_align=ft.TextAlign.CENTER),
                    ],
                ),
            )

        dlg = ft.AlertDialog(
            modal=True,
            bgcolor=C_SURFACE,
            shape=DIALOG_SHAPE,
            title_padding=ft.padding.only(left=24, right=24, top=24, bottom=0),
            content_padding=ft.padding.only(left=24, right=24, top=20, bottom=8),
            actions_padding=ft.padding.only(left=24, right=24, top=0, bottom=18),
            title=ft.Text(title_text, size=20, weight="bold", color=C_TEXT),
            content=ft.Row(
                wrap=True, spacing=14,
                alignment=ft.MainAxisAlignment.CENTER,
                controls=[tile(*o) for o in options],
            ),
            actions=[ft.TextButton("取消", on_click=lambda e: close_dlg(page, dlg, "取消"))],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.dialog = dlg
        dlg.open = True
        page.update()

    def close_dlg(page, dlg, action):
        dlg.open = False
        page.update()
        if action != "取消":
            if action == "📝 在线填写":
                show_online_form(page)
            elif action == "📄 输入文档":
                open_doc_dialog(page)
            elif action == "🖼️ 输入图片":
                show_upload_dialog(page)

    # ========== 图片上传对话框 ==========

    def show_upload_dialog(page):
        preview_image = ft.Image(width=300, height=300, fit=ft.ImageFit.CONTAIN, visible=False)
        upload_status = ft.Text("尚未选择图片", size=13, color=C_SUB)

        def file_picker_result(e):
            if e.files:
                preview_image.src = e.files[0].path
                preview_image.visible = True
                upload_status.value = f"已选择：{e.files[0].name}"
                upload_status.color = C_TEAL
                page.update()

        def pick_image(e):
            picker_callback["fn"] = file_picker_result
            file_picker.pick_files(allowed_extensions=["jpg", "jpeg", "png"])

        dlg = ft.AlertDialog(
            modal=True,
            bgcolor=C_SURFACE,
            shape=DIALOG_SHAPE,
            title_padding=ft.padding.only(left=24, right=24, top=24, bottom=0),
            content_padding=ft.padding.all(24),
            title=ft.Text("上传档案图片", size=20, weight="bold", color=C_TEXT),
            content=ft.Container(
                width=360,
                content=ft.Column(
                    spacing=18, tight=True,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Container(
                            width=360, height=180,
                            bgcolor=C_FIELD,
                            border=ft.border.all(1, C_LINE),
                            border_radius=14,
                            alignment=ft.alignment.center,
                            content=ft.Column(
                                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                alignment=ft.MainAxisAlignment.CENTER,
                                spacing=10,
                                controls=[
                                    ft.Icon(ft.icons.PHOTO_LIBRARY, size=40, color=C_PRIMARY),
                                    ft.Text("支持 jpg / jpeg / png", size=12, color=C_SUB),
                                ],
                            ),
                        ),
                        _ghost_button("选择图片文件", icon=ft.icons.FOLDER_OPEN, on_click=pick_image),
                        upload_status,
                        preview_image,
                    ],
                ),
            ),
            actions=[
                ft.TextButton("取消", on_click=lambda e: close_dialog(dlg)),
                _primary_button("确认使用", on_click=lambda e: close_dialog(dlg)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.dialog = dlg
        dlg.open = True
        page.update()

    # ========== 文档导入对话框：拖拽 / 点选 / 粘贴路径 ==========

    def open_doc_dialog(page, on_success=None):
        path_input = ft.TextField(
            label="或粘贴文件完整路径", width=420,
            hint_text="例如 C:/Users/HONOR/Desktop/档案.txt",
            **_field_style()
        )
        status_text = ft.Text("", size=12, color=C_SUB)

        def handle_path(path):
            path = (path or "").strip().strip('"')
            if not path:
                status_text.value = "请先拖入文件或输入路径"
                status_text.color = C_AMBER
                page.update()
                return
            if not os.path.exists(path):
                status_text.value = f"文件不存在：{path}"
                status_text.color = C_DANGER
                page.update()
                return
            dlg.open = False
            page.update()
            start_ai_recognition(page, path, on_success)

        def on_drop(e):
            handle_path(e.data)

        drag_area = ft.DragTarget(
            group="file",
            on_accept=on_drop,
            content=ft.Container(
                width=460, height=180,
                bgcolor=C_PRIMARY_SOFT,
                border=ft.border.all(1, "#BFDBFE"),
                border_radius=16,
                alignment=ft.alignment.center,
                content=ft.Column(
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=10,
                    controls=[
                        ft.Icon(ft.icons.CLOUD_UPLOAD, size=44, color=C_PRIMARY),
                        ft.Text("将档案文档拖到这里", size=17, weight="bold", color="#1E40AF"),
                        ft.Text("支持 pdf / docx / txt，识别后自动填入表格", size=12, color=C_SUB),
                    ],
                ),
            ),
        )

        def pick_by_click(e):
            def on_files(ev):
                if ev.files:
                    handle_path(ev.files[0].path)
            picker_callback["fn"] = on_files
            file_picker.pick_files(allowed_extensions=["pdf", "docx", "txt"])

        dlg = ft.AlertDialog(
            modal=True,
            bgcolor=C_SURFACE,
            shape=DIALOG_SHAPE,
            title_padding=ft.padding.only(left=24, right=24, top=24, bottom=0),
            content_padding=ft.padding.only(left=24, right=24, top=20, bottom=8),
            title=ft.Row(
                spacing=12,
                controls=[
                    _icon_badge(ft.icons.DESCRIPTION, C_PRIMARY, size=44),
                    ft.Column(
                        spacing=2,
                        controls=[
                            ft.Text("导入档案文档", size=19, weight="bold", color=C_TEXT),
                            ft.Text("AI 自动识别并回填表单", size=12, color=C_SUB),
                        ],
                    ),
                ],
            ),
            content=ft.Column(
                spacing=14, tight=True,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    drag_area,
                    ft.Row(
                        spacing=8, wrap=True,
                        alignment=ft.MainAxisAlignment.CENTER,
                        controls=[
                            _ghost_button("点击选择文件", icon=ft.icons.FOLDER_OPEN, on_click=pick_by_click),
                            ft.Text("或", size=12, color=C_MUTED),
                        ],
                    ),
                    ft.Row(
                        spacing=10,
                        alignment=ft.MainAxisAlignment.CENTER,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            path_input,
                            _primary_button("开始识别", icon=ft.icons.SEARCH,
                                            on_click=lambda e: handle_path(path_input.value)),
                        ],
                    ),
                    status_text,
                ],
            ),
            actions=[ft.TextButton("取消", on_click=lambda e: close_dialog(dlg))],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.dialog = dlg
        dlg.open = True
        page.update()

    # ========== AI 识别：右上角悬浮进度卡片 ==========

    def start_ai_recognition(page, path, on_success=None):
        cancel_event = threading.Event()

        percent_text = ft.Text("0%", size=22, weight="bold", color=C_PRIMARY)
        progress_bar = ft.ProgressBar(width=220, value=0.0, color=C_PRIMARY, bgcolor=C_LINE, bar_height=6)
        status_text = ft.Text("正在读取文档...", size=12, color=C_SUB)
        file_name_text = ft.Text(os.path.basename(path), size=10, color=C_MUTED)

        progress_card = ft.Container(
            width=280,
            padding=18,
            bgcolor=C_SURFACE,
            border=ft.border.all(1, C_LINE),
            border_radius=16,
            shadow=ft.BoxShadow(blur_radius=28, color="#0F172A26"),
            right=24,
            top=24,
            content=ft.Column(
                spacing=8, tight=True,
                controls=[
                    ft.Row(
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Icon(ft.icons.AUTO_AWESOME, size=18, color=C_PRIMARY),
                            ft.Text("AI 档案识别", size=13, weight="bold", color=C_TEXT, expand=True),
                            percent_text,
                        ],
                    ),
                    progress_bar,
                    status_text,
                    file_name_text,
                    ft.Row(
                        alignment=ft.MainAxisAlignment.END,
                        controls=[ft.TextButton("取消")],
                    ),
                ],
            ),
            visible=False,
        )

        def on_cancel(e):
            cancel_event.set()
            progress_card.visible = False
            page.update()

        progress_card.content.controls[-1].controls[0].on_click = on_cancel

        page.overlay.append(progress_card)
        progress_card.visible = True
        page.update()

        def set_progress(pct, status):
            if cancel_event.is_set():
                return
            progress_bar.value = pct / 100.0
            percent_text.value = f"{pct}%"
            status_text.value = status
            page.update()

        def worker():
            result = None
            try:
                if cancel_event.is_set():
                    return
                set_progress(5, "正在读取文档...")
                text = extract_text_from_file(path)

                if cancel_event.is_set():
                    return
                if not text.strip():
                    raise ValueError("文档中没有提取到文本内容")

                set_progress(12, "正在连接本地 AI...")
                stop_creep = threading.Event()

                def creep():
                    p = 12
                    while not stop_creep.is_set() and not cancel_event.is_set() and p < 20:
                        time.sleep(0.8)
                        p += 1
                        set_progress(p, "AI 正在思考...")

                creep_thread = threading.Thread(target=creep, daemon=True)
                creep_thread.start()

                def on_tokens(n):
                    if cancel_event.is_set():
                        return
                    pct = min(90, 20 + int(n / 900 * 70))
                    set_progress(pct, "AI 正在识别...")

                try:
                    if cancel_event.is_set():
                        return
                    data = ask_ollama(text, on_progress=on_tokens)
                finally:
                    stop_creep.set()
                    creep_thread.join(timeout=1)

                if cancel_event.is_set():
                    return
                if not data:
                    raise ValueError("AI 未返回有效数据")

                set_progress(100, "识别完成，正在整理")
                result = ("ok", data)

            except Exception as ex:
                if not cancel_event.is_set():
                    result = ("error", str(ex))

            finally:
                progress_card.visible = False
                if progress_card in page.overlay:
                    page.overlay.remove(progress_card)
                page.update()

                if cancel_event.is_set():
                    page.snack_bar = ft.SnackBar(ft.Text("已取消本次识别"), bgcolor=C_PRIMARY)
                    page.snack_bar.open = True
                elif result and result[0] == "ok":
                    if on_success:
                        on_success(result[1])
                    else:
                        show_online_form(page, prefill=result[1])
                elif result and result[0] == "error":
                    page.snack_bar = ft.SnackBar(ft.Text(f"识别失败：{result[1]}"), bgcolor=C_DANGER)
                    page.snack_bar.open = True
                page.update()

        threading.Thread(target=worker, daemon=True).start()

    # ========== 在线填写表单 ==========

    def show_online_form(page, prefill=None):
        page.controls.clear()
        page.padding = 0
        page.spacing = 0
        page.scroll = ft.ScrollMode.AUTO
        page.bgcolor = C_BG
        page.horizontal_alignment = ft.CrossAxisAlignment.CENTER

        form_data = {}
        manual_inputs = {}
        field_controls = {}

        def save_field(field_name, value):
            form_data[field_name] = value

        def register_field(field_name, ctrl):
            field_controls[field_name] = ctrl

        # ---------- 统一样式的字段构造器 ----------

        def tf(label_text, field_name, width=210, hint=None, multiline=False, min_lines=1):
            ctrl = ft.TextField(
                label=label_text, width=width, hint_text=hint,
                multiline=multiline,
                min_lines=min_lines if multiline else 1,
                on_change=lambda e, k=field_name: save_field(k, e.control.value),
                **_field_style(),
            )
            register_field(field_name, ctrl)
            return ctrl

        def radio_field(label_text, field_name, options, width=210):
            rg = ft.RadioGroup(
                content=ft.Row(
                    spacing=16, wrap=True,
                    controls=[
                        ft.Radio(
                            value=o, label=o, active_color=C_PRIMARY, fill_color=C_PRIMARY,
                            label_style=ft.TextStyle(size=13, color=C_TEXT),
                        )
                        for o in options
                    ],
                ),
                on_change=lambda e: save_field(field_name, e.data),
            )
            register_field(field_name, rg)
            return ft.Container(
                width=width,
                bgcolor=C_FIELD,
                border=ft.border.all(1, C_LINE),
                border_radius=10,
                padding=ft.padding.only(left=14, right=14, top=8, bottom=8),
                content=ft.Column(
                    spacing=2, tight=True,
                    controls=[
                        ft.Text(label_text, size=13, color="#475569"),
                        rg,
                    ],
                ),
            )

        def create_searchable_disease_field(field_name, label_text, width=430, multiline=False):
            search_field = ft.TextField(
                label=label_text, width=width,
                multiline=multiline,
                min_lines=2 if multiline else 1,
                hint_text="输入病症名称搜索（如：无、青霉素、黄疸），或手动输入...",
                on_change=lambda e: update_dropdown(e.control.value),
                **_field_style(),
            )
            register_field(field_name, search_field)

            dropdown_container = ft.Column(spacing=6, visible=False)

            def update_dropdown(search_text):
                if not search_text or len(str(search_text).strip()) < 1:
                    dropdown_container.visible = False
                    page.update()
                    return

                results = search_disease_terms(search_text, limit=5)
                dropdown_container.controls.clear()

                if results:
                    for r in results:
                        cn, en, cat = r[1], r[2], r[3]
                        item = ft.Container(
                            content=ft.Row(
                                spacing=8,
                                controls=[
                                    ft.Icon(ft.icons.SEARCH, size=14, color=C_PRIMARY),
                                    ft.Text(f"{cn}", size=13, color=C_TEXT, weight="bold"),
                                    ft.Text(f"{en} · {cat}", size=11, color=C_SUB, expand=True),
                                ],
                            ),
                            padding=ft.padding.symmetric(horizontal=12, vertical=10),
                            bgcolor=C_PRIMARY_SOFT,
                            border=ft.border.all(1, "#BFDBFE"),
                            border_radius=8,
                            on_click=lambda e, c=cn, e_name=en: select_item(c, e_name),
                            ink=True,
                        )
                        dropdown_container.controls.append(item)
                    dropdown_container.visible = True
                else:
                    dropdown_container.controls.append(
                        ft.Container(
                            content=ft.Text("未找到匹配词条，可直接手动输入", size=12, color=C_SUB, italic=True),
                            padding=ft.padding.symmetric(horizontal=12, vertical=10),
                            bgcolor=C_FIELD,
                            border=ft.border.all(1, C_LINE),
                            border_radius=8,
                        )
                    )
                    dropdown_container.visible = True
                page.update()

            def select_item(cn, en):
                search_field.value = cn
                dropdown_container.visible = False
                form_data[f"{field_name}_中文"] = cn
                form_data[f"{field_name}_英文"] = en
                form_data[f"{field_name}_来源"] = "数据库标准词条"
                page.update()

            def on_blur(e):
                if search_field.value:
                    value = search_field.value.strip()
                    en = get_disease_by_chinese(value)
                    if en:
                        form_data[f"{field_name}_中文"] = value
                        form_data[f"{field_name}_英文"] = en
                        form_data[f"{field_name}_来源"] = "数据库标准词条"
                    else:
                        form_data[f"{field_name}_中文"] = value
                        form_data[f"{field_name}_英文"] = value
                        form_data[f"{field_name}_来源"] = "手动输入"
                        manual_inputs[field_name] = {
                            "中文内容": value,
                            "录入时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "字段标签": label_text,
                            "备注": "需后续标准化处理"
                        }
                page.update()

            search_field.on_blur = on_blur
            return ft.Column([search_field, dropdown_container], spacing=5)

        def fill_form_from_data(data):
            for field, ctrl in field_controls.items():
                raw = data.get(field)
                if raw is None:
                    continue
                val = str(raw).strip()
                if not val:
                    continue
                if isinstance(ctrl, ft.TextField):
                    ctrl.value = val
                elif isinstance(ctrl, ft.RadioGroup):
                    options = [o.value for o in ctrl.content.controls]
                    if val in options:
                        ctrl.value = val
                    else:
                        continue
                form_data[field] = val

            for k in DISEASE_FIELDS:
                v = form_data.get(k)
                if v and not form_data.get(f"{k}_中文"):
                    form_data[f"{k}_中文"] = v
                    en = get_disease_by_chinese(v)
                    form_data[f"{k}_英文"] = en if en else v
                    form_data[f"{k}_来源"] = "数据库标准词条" if en else "手动输入"

        def import_doc_in_form():
            def on_success(data):
                fill_form_from_data(data)
                page.update()
                page.snack_bar = ft.SnackBar(ft.Text("识别完毕，表格已自动填写"), bgcolor=C_TEAL)
                page.snack_bar.open = True
                page.update()
            open_doc_dialog(page, on_success=on_success)

        def row(*controls):
            return ft.Row(wrap=True, spacing=16, run_spacing=16, controls=list(controls))

        def section(icon, title, subtitle, children, accent=C_PRIMARY):
            return ft.Container(
                bgcolor=C_SURFACE,
                border=ft.border.all(1, C_LINE),
                border_radius=18,
                padding=ft.padding.all(24),
                shadow=SHADOW_CARD,
                content=ft.Column(
                    spacing=18,
                    controls=[
                        ft.Row(
                            spacing=14,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            controls=[
                                _icon_badge(icon, accent),
                                ft.Column(
                                    spacing=2,
                                    controls=[
                                        ft.Text(title, size=18, weight="bold", color=C_TEXT),
                                        ft.Text(subtitle, size=12, color=C_SUB),
                                    ],
                                ),
                            ],
                        ),
                        ft.Container(height=1, bgcolor=C_LINE),
                    ] + children,
                ),
            )

        # ---------- 保存与确认 ----------

        def save_all_data(e):
            global is_visitor
            if is_visitor:
                page.snack_bar = ft.SnackBar(ft.Text("游客模式禁止保存档案文件"), bgcolor=C_AMBER)
                page.snack_bar.open = True
                page.update()
                return
            if not form_data.get("姓名"):
                page.snack_bar = ft.SnackBar(ft.Text("请至少填写姓名"), bgcolor=C_AMBER)
                page.snack_bar.open = True
                page.update()
                return

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"儿童健康档案_{form_data.get('姓名')}_{timestamp}.json"

            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(form_data, f, ensure_ascii=False, indent=2)
                page.snack_bar = ft.SnackBar(ft.Text(f"数据已保存到 {filename}（含英文映射）"), bgcolor=C_TEAL)
                page.snack_bar.open = True
                page.update()
            except Exception as ex:
                page.snack_bar = ft.SnackBar(ft.Text(f"保存失败：{str(ex)}"), bgcolor=C_DANGER)
                page.snack_bar.open = True
                page.update()

        def confirm_and_test(e):
            physical_data = {k: form_data.get(k, "") for k in PHYSICAL_FIELDS if form_data.get(k)}
            physical_text = json.dumps(physical_data, ensure_ascii=False, indent=2) or "无数据"

            repeated_data = {k: form_data.get(k, "") for k in REPEATED_FIELDS if form_data.get(k)}
            repeated_text = json.dumps(repeated_data, ensure_ascii=False, indent=2) or "无数据"

            disease_data = {}
            for k in DISEASE_FIELDS:
                cn = form_data.get(f"{k}_中文")
                en = form_data.get(f"{k}_英文")
                src = form_data.get(f"{k}_来源")
                if cn:
                    disease_data[k] = {"中文": cn, "英文": en, "来源": src}

            disease_text = json.dumps(disease_data, ensure_ascii=False, indent=2) or "无数据"

            print("\n" + "=" * 80)
            print("🚀 开始生成测试字符串 (为后续 C++ 加密/纠错程序做准备)")
            print("=" * 80)

            repeated_pool = []
            for key in REPEATED_FIELDS:
                val = form_data.get(key, "")
                if val:
                    py_str = to_pinyin_string(f"{key}_{val}")
                    repeated_pool.extend([py_str, py_str, py_str])

            random.shuffle(repeated_pool)
            repeated_string = " ".join(repeated_pool)

            print("\n📌 【反复存储字符串】 (拼音 + 随机冗余3遍):")
            print(repeated_string if repeated_string else " (当前界面无随访数据，暂为空)")

            disease_eng_list = [form_data.get(f"{k}_英文") for k in DISEASE_FIELDS if form_data.get(f"{k}_英文")]
            disease_string = " | ".join(disease_eng_list)

            print("\n📌 【病症记录字符串】 (数据库英文顺序连接):")
            print(disease_string if disease_string else " (无数据)")
            print("=" * 80 + "\n")

            def block(icon, color, title, desc, body):
                return ft.Container(
                    bgcolor=C_FIELD,
                    border=ft.border.all(1, C_LINE),
                    border_radius=14,
                    padding=ft.padding.all(16),
                    content=ft.Column(
                        spacing=8,
                        controls=[
                            ft.Row(
                                spacing=10,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                controls=[
                                    _icon_badge(icon, color, size=34, icon_size=18, radius=10),
                                    ft.Column(
                                        spacing=1,
                                        controls=[
                                            ft.Text(title, size=14, weight="bold", color=C_TEXT),
                                            ft.Text(desc, size=11, color=C_SUB),
                                        ],
                                    ),
                                ],
                            ),
                            ft.Container(
                                bgcolor=C_SURFACE,
                                border_radius=10,
                                padding=ft.padding.all(12),
                                content=ft.Text(body, size=11, font_family="Consolas", color="#334155",
                                                 selectable=True),
                            ),
                        ],
                    ),
                )

            dlg = ft.AlertDialog(
                modal=True,
                bgcolor=C_SURFACE,
                shape=DIALOG_SHAPE,
                title_padding=ft.padding.only(left=24, right=24, top=24, bottom=0),
                content_padding=ft.padding.all(24),
                title=ft.Text("数据分类结果", size=20, weight="bold", color=C_TEXT),
                content=ft.Container(
                    width=620, height=560,
                    content=ft.Column(
                        spacing=14,
                        scroll=ft.ScrollMode.AUTO,
                        controls=[
                            block(ft.icons.DATASET, C_PRIMARY, "物理存储（固定信息）",
                                  "写入档案主表的稳定字段", physical_text),
                            block(ft.icons.SYNC, C_AMBER, "反复存储（随访 / 动态信息）",
                                  "拼音编码，随机冗余 3 遍；终端已输出字符串", repeated_text),
                            block(ft.icons.FINGERPRINT, C_TEAL, "病症记录（数据库映射）",
                                  "中英双语映射；终端已输出英文连接字符串", disease_text),
                        ],
                    ),
                ),
                actions=[
                    ft.TextButton("关闭", on_click=lambda e: close_test_dlg(dlg)),
                    _primary_button("查看终端输出", on_click=lambda e: close_test_dlg(dlg)),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )

            page.dialog = dlg
            dlg.open = True
            page.update()

            page.snack_bar = ft.SnackBar(
                ft.Text("数据已分类，请查看终端 (CMD) 输出的测试字符串"),
                bgcolor=C_PRIMARY, duration=3000,
            )
            page.snack_bar.open = True
            page.update()

        def close_test_dlg(dlg):
            dlg.open = False
            page.update()

        # ========== 1. 基本信息 ==========

        gender_group = ft.RadioGroup(
            content=ft.Row(
                spacing=16,
                controls=[
                    ft.Radio(value="男", label="男", active_color=C_PRIMARY, fill_color=C_PRIMARY,
                             label_style=ft.TextStyle(size=13, color=C_TEXT)),
                    ft.Radio(value="女", label="女", active_color=C_PRIMARY, fill_color=C_PRIMARY,
                             label_style=ft.TextStyle(size=13, color=C_TEXT)),
                ],
            ),
            on_change=lambda e: save_field("性别", e.data),
        )
        register_field("性别", gender_group)

        basic_info = section(
            ft.icons.BADGE, "基本信息", "身份与建档基础资料",
            [
                row(
                    tf("档案编号", "档案编号", width=210),
                    tf("姓名", "姓名", width=210),
                    radio_field("性别", "性别", ["男", "女"], width=210),
                    tf("出生日期", "出生日期", width=210, hint="YYYY-MM-DD"),
                ),
                row(
                    tf("出生证 / 身份证号", "证件号码", width=320),
                    tf("联系电话", "联系电话", width=210),
                    tf("建档日期", "建档日期", width=210, hint="YYYY-MM-DD"),
                ),
                row(
                    tf("建档机构", "建档机构", width=320),
                    tf("户籍地址", "户籍地址", width=552),
                ),
                tf("常住地址", "常住地址", width=888),
            ],
        )

        # ========== 2. 个人基础信息 ==========

        personal_info = section(
            ft.icons.HEALTH_AND_SAFETY, "个人基础信息", "出生信息与父母联系方式",
            [
                row(
                    tf("民族", "民族", width=210),
                    tf("ABO 血型", "ABO血型", width=210, hint="如：A / B / O / AB"),
                    radio_field("Rh 血型", "Rh血型", ["阳性", "阴性"], width=260),
                ),
                row(
                    tf("出生孕周（周）", "出生孕周", width=210),
                    tf("出生体重（g）", "出生体重", width=210),
                    tf("出生身长（cm）", "出生身长", width=210),
                ),
                tf("分娩机构", "分娩机构", width=552),
                row(
                    tf("Apgar 评分（1 分钟）", "Apgar_1分钟", width=260),
                    tf("Apgar 评分（5 分钟）", "Apgar_5分钟", width=260),
                ),
                ft.Container(
                    bgcolor=C_FIELD,
                    border=ft.border.all(1, C_LINE),
                    border_radius=14,
                    padding=ft.padding.all(18),
                    content=ft.Row(
                        wrap=True, spacing=40, run_spacing=18,
                        controls=[
                            ft.Column(
                                spacing=12,
                                controls=[
                                    ft.Row(
                                        spacing=8,
                                        controls=[
                                            ft.Icon(ft.icons.PERSON_OUTLINE, size=16, color=C_PRIMARY),
                                            ft.Text("父亲信息", size=13, weight="bold", color=C_TEXT),
                                        ],
                                    ),
                                    row(
                                        tf("姓名", "父亲姓名", width=210),
                                        tf("联系电话", "父亲联系电话", width=210),
                                    ),
                                ],
                            ),
                            ft.Column(
                                spacing=12,
                                controls=[
                                    ft.Row(
                                        spacing=8,
                                        controls=[
                                            ft.Icon(ft.icons.PERSON_OUTLINE, size=16, color=C_TEAL),
                                            ft.Text("母亲信息", size=13, weight="bold", color=C_TEXT),
                                        ],
                                    ),
                                    row(
                                        tf("姓名", "母亲姓名", width=210),
                                        tf("联系电话", "母亲联系电话", width=210),
                                    ),
                                ],
                            ),
                        ],
                    ),
                ),
            ],
            accent=C_TEAL,
        )

        # ========== 3. 新生儿疾病筛查 ==========

        screening = section(
            ft.icons.VACCINES, "新生儿疾病筛查", "筛查结论与病史记录",
            [
                row(
                    radio_field("苯丙酮尿症", "苯丙酮尿症", ["阴性", "阳性"], width=260),
                    radio_field("先天性甲状腺功能减低症", "先天性甲状腺功能减低症", ["阴性", "阳性"], width=300),
                    radio_field("听力筛查", "听力筛查", ["通过", "未通过"], width=220),
                ),
                row(
                    create_searchable_disease_field("过敏史", "过敏史（搜索或输入）", width=430),
                    create_searchable_disease_field("先天异常", "先天异常 / 特殊体质", width=430, multiline=True),
                ),
                row(
                    create_searchable_disease_field("既往住院史", "既往住院史", width=430, multiline=True),
                    create_searchable_disease_field("家族遗传病史", "家族遗传病史", width=430, multiline=True),
                ),
            ],
            accent=C_AMBER,
        )

        db_warning = ft.Container(
            bgcolor=C_AMBER_SOFT,
            border=ft.border.all(1, "#FDE68A"),
            border_radius=12,
            padding=ft.padding.symmetric(horizontal=16, vertical=12),
            visible=not os.path.exists(DB_PATH),
            content=ft.Row(
                spacing=10,
                controls=[
                    ft.Icon(ft.icons.WARNING_AMBER_ROUNDED, size=18, color=C_AMBER),
                    ft.Text(f"未找到数据库 {DB_PATH}，请先运行数据库初始化脚本",
                            size=12, color="#92400E", expand=True),
                ],
            ),
        )

        header = ft.Container(
            width=940,
            bgcolor=C_SURFACE,
            border=ft.border.all(1, C_LINE),
            border_radius=18,
            padding=ft.padding.symmetric(horizontal=20, vertical=16),
            shadow=SHADOW_CARD,
            content=ft.Row(
                spacing=14,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.IconButton(ft.icons.ARROW_BACK, tooltip="返回主界面",
                                  icon_color=C_TEXT, on_click=lambda e: enter_main(page)),
                    ft.Container(width=1, height=34, bgcolor=C_LINE),
                    ft.Column(
                        expand=True, spacing=2,
                        controls=[
                            ft.Text("医疗健康档案 · 在线录入", size=19, weight="bold", color=C_TEXT),
                            ft.Text("中文字段录入，英文编码在后台统一转换", size=12, color=C_SUB),
                        ],
                    ),
                    _icon_badge(ft.icons.SECURITY, C_TEAL, size=36, icon_size=18),
                ],
            ),
        )

        action_bar = ft.Container(
            width=940,
            bgcolor=C_SURFACE,
            border=ft.border.all(1, C_LINE),
            border_radius=18,
            padding=ft.padding.symmetric(horizontal=20, vertical=16),
            shadow=SHADOW_CARD,
            content=ft.Row(
                wrap=True, spacing=12, run_spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text("填写完成后可保存为本地档案，或进行编码测试",
                            size=12, color=C_SUB, expand=True),
                    _ghost_button("从文档导入", icon=ft.icons.UPLOAD_FILE,
                                  on_click=lambda e: import_doc_in_form()),
                    _ghost_button("保存数据", icon=ft.icons.SAVE, on_click=save_all_data),
                    _primary_button("确认并测试", icon=ft.icons.CHECK_CIRCLE, on_click=confirm_and_test),
                ],
            ),
        )

        content_col = ft.Column(
            width=940,
            spacing=20,
            controls=[db_warning, basic_info, personal_info, screening, action_bar],
        )

        page.add(
            ft.Container(height=20),
            header,
            ft.Container(height=20),
            content_col,
            ft.Container(height=40),
        )

        if prefill:
            fill_form_from_data(prefill)
            page.update()
            page.snack_bar = ft.SnackBar(ft.Text("识别完毕，表格已自动填写"), bgcolor=C_TEAL)
            page.snack_bar.open = True
            page.update()

    # ========== 开场画面 ==========

    splash_text_content = ft.Column(
        horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=28,
        controls=[
            ft.Container(
                width=76, height=76, border_radius=22,
                gradient=ft.LinearGradient(
                    colors=["#3B82F6", "#0D9488"],
                    begin=ft.alignment.top_left, end=ft.alignment.bottom_right,
                ),
                alignment=ft.alignment.center,
                shadow=ft.BoxShadow(blur_radius=28, color="#2563EB59"),
                content=ft.Icon(ft.icons.BIOTECH, color="white", size=38),
            ),
            ft.Text("DNA 医疗档案系统", size=48, weight="bold", color="white",
                    text_align=ft.TextAlign.CENTER),
            ft.Text("安全 · 双语 · 可追溯", size=15, color="#CBD5E1"),
            ft.Container(
                padding=ft.padding.symmetric(horizontal=26, vertical=14),
                border=ft.border.all(1, "#FFFFFF26"),
                border_radius=50, bgcolor="#FFFFFF0F",
                content=ft.Row(
                    tight=True, spacing=10,
                    controls=[
                        ft.Icon(ft.icons.ARROW_FORWARD, size=16, color="#CBD5E1"),
                        ft.Text("点击屏幕任意位置进入系统", size=14, color="#CBD5E1"),
                    ],
                ),
            ),
        ],
    )

    splash = ft.Container(
        expand=True, on_click=lambda e: enter_main(page),
        content=ft.Stack(
            expand=True,
            controls=[
                ft.Container(expand=True, image_src=COVER_IMAGE, image_fit=ft.ImageFit.COVER),
                ft.Container(
                    expand=True,
                    gradient=ft.LinearGradient(
                        colors=["#0F172AE6", "#0F172A80", "#0F172AE6"],
                        begin=ft.alignment.top_center,
                        end=ft.alignment.bottom_center,
                    ),
                ),
                ft.Container(
                    expand=True,
                    alignment=ft.alignment.center,
                    content=splash_text_content,
                ),
            ],
        ),
    )

    page.add(splash)
    page.update()

    # ========== 进入主界面 ==========

    def enter_main(page):
        page.controls.clear()
        page.padding = 0
        page.spacing = 0
        page.scroll = ft.ScrollMode.AUTO
        page.bgcolor = C_BG
        page.horizontal_alignment = ft.CrossAxisAlignment.CENTER

        global is_visitor

        def action_card(icon, title, subtitle, accent, bullets, on_click):
            def on_hover(e):
                active = e.data == "true"
                e.control.border = ft.border.all(1, "#BFDBFE" if active else C_LINE)
                e.control.shadow = ft.BoxShadow(
                    blur_radius=32 if active else 24,
                    color="#2563EB26" if active else "#0F172A12",
                )
                e.control.update()

            return ft.Container(
                width=440, height=290,
                bgcolor=C_SURFACE,
                border=ft.border.all(1, C_LINE),
                border_radius=20,
                padding=ft.padding.all(28),
                ink=True,
                on_click=on_click,
                on_hover=on_hover,
                shadow=SHADOW_CARD,
                content=ft.Column(
                    spacing=14,
                    controls=[
                        _icon_badge(icon, accent, size=56, icon_size=28, radius=14),
                        ft.Text(title, size=24, weight="bold", color=C_TEXT),
                        ft.Text(subtitle, size=13, color=C_SUB),
                        ft.Container(height=1, bgcolor=C_LINE),
                        ft.Text(bullets, size=12, color=C_SUB),
                        ft.Container(expand=True),
                        ft.Row(
                            spacing=6,
                            controls=[
                                ft.Text("开始使用", size=13, weight="bold", color=accent),
                                ft.Icon(ft.icons.ARROW_FORWARD, size=15, color=accent),
                            ],
                        ),
                    ],
                ),
            )

        mode_chip = ft.Container(
            padding=ft.padding.symmetric(horizontal=14, vertical=8),
            border_radius=50,
            bgcolor=C_AMBER_SOFT if is_visitor else C_PRIMARY_SOFT,
            border=ft.border.all(1, "#FDE68A" if is_visitor else "#BFDBFE"),
            content=ft.Row(
                spacing=6,
                controls=[
                    ft.Icon(ft.icons.PERSON_OUTLINE, size=14, color=C_AMBER if is_visitor else C_PRIMARY),
                    ft.Text("游客模式 · 不可保存" if is_visitor else "已登录",
                            size=12, color=C_AMBER if is_visitor else C_PRIMARY),
                ],
            ),
        )

        top_bar = ft.Container(
            width=940,
            bgcolor=C_SURFACE,
            border=ft.border.all(1, C_LINE),
            border_radius=18,
            padding=ft.padding.symmetric(horizontal=20, vertical=14),
            shadow=SHADOW_CARD,
            content=ft.Row(
                spacing=14,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    _icon_badge(ft.icons.BIOTECH, C_PRIMARY, size=40, icon_size=20),
                    ft.Column(
                        expand=True, spacing=1,
                        controls=[
                            ft.Text("DNA 医疗档案系统", size=16, weight="bold", color=C_TEXT),
                            ft.Text("医疗冷归档 · 加密存储", size=11, color=C_SUB),
                        ],
                    ),
                    mode_chip,
                ],
            ),
        )

        hero = ft.Column(
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=8,
            controls=[
                ft.Text("选择数据处理方向", size=28, weight="bold", color=C_TEXT),
                ft.Text("加密用于归档存储，解密用于读取还原；两种方式均在本机完成",
                        size=13, color=C_SUB, text_align=ft.TextAlign.CENTER),
            ],
        )

        cards_row = ft.Row(
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=28, wrap=True,
            controls=[
                action_card(
                    ft.icons.LOCK_OUTLINE, "加密", "将档案信息编码为可安全存储的内容",
                    C_PRIMARY, "在线填写 · 文档导入 · 图片上传",
                    lambda e: show_dialog(page, "选择加密信息传输方式", [
                        ("📝 在线填写", ft.icons.EDIT_NOTE, "在线填写", "手动录入档案信息"),
                        ("📄 输入文档", ft.icons.DESCRIPTION, "输入文档", "上传 pdf / docx / txt"),
                        ("🖼️ 输入图片", ft.icons.PHOTO_LIBRARY, "输入图片", "上传档案照片"),
                    ]),
                ),
                action_card(
                    ft.icons.LOCK_OPEN, "解密", "将加密内容还原为可读的医疗档案",
                    C_TEAL, "读取文件 · 解密文档 · 解密图片",
                    lambda e: show_dialog(page, "选择解密信息输出方式", [
                        ("📄 读取加密文件", ft.icons.FOLDER_OPEN, "读取加密文件", "从本地加密文件还原"),
                        ("📝 解密为文档", ft.icons.DESCRIPTION, "解密为文档", "输出可读文档"),
                        ("🖼️ 解密为图片", ft.icons.PHOTO_LIBRARY, "解密为图片", "输出档案图片"),
                    ]),
                ),
            ],
        )

        hint = ft.Container(
            width=908,
            bgcolor=C_SURFACE,
            border=ft.border.all(1, C_LINE),
            border_radius=14,
            padding=ft.padding.symmetric(horizontal=18, vertical=14),
            content=ft.Row(
                spacing=10,
                controls=[
                    ft.Icon(ft.icons.SHIELD, size=18, color=C_TEAL),
                    ft.Text("所有档案数据仅保存在本机，编码与解码过程均在本地完成，不上传云端",
                            size=12, color=C_SUB, expand=True),
                ],
            ),
        )

        body_col = ft.Column(
            width=940,
            spacing=26,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[top_bar, hero, cards_row, hint],
        )

        page.add(
            ft.Container(height=20),
            body_col,
            ft.Container(height=40),
        )
        page.update()


def main(page: ft.Page):
    login_select_page(page)


if __name__ == "__main__":
    ft.app(target=main)
