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

# 【新增全局游客标记】
is_visitor = False

# ==========================================
# 1. 数据库查询模块
# ==========================================

DB_PATH = "medical_terms.db"

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
# 2. 拼音转换工具
# ==========================================

def to_pinyin_string(text):
    if not text:
        return ""
    py_list = pypinyin.pinyin(text, style=pypinyin.Style.NORMAL)
    return "_".join([item[0] for item in py_list])

# ==========================================
# 3. 文档解析模块（AI 识别用）
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

# =====================【新增登录选择页面】=====================

def login_select_page(page: ft.Page):
    page.title = "DNA医疗档案系统 - 登录"
    page.clean()

    def normal_login_click(e):
        user_input = ft.TextField(label="账号", width=250)
        pwd_input = ft.TextField(label="密码", password=True, width=250)

        dlg_login = ft.AlertDialog(
            title=ft.Text("账号登录"),
            content=ft.Column([user_input, pwd_input]),
            actions=[
                ft.TextButton("确认登录", on_click=lambda ev: verify_login(dlg_login, page, user_input.value, pwd_input.value)),
                ft.TextButton("取消", on_click=lambda ev: page.close(dlg_login))
            ]
        )
        page.open(dlg_login)

    def visitor_click(e):
        global is_visitor
        is_visitor = True
        page.clean()
        run_app_logic(page)

    def verify_login(dlg, page, username, password):
        global is_visitor
        if username == "admin" and password == "123456":
            is_visitor = False
            page.close(dlg)
            page.clean()
            run_app_logic(page)
        else:
            page.add(ft.SnackBar(ft.Text("账号或密码错误"), bgcolor=ft.colors.RED, open=True))

    page.add(
        ft.Column(
            [
                ft.Text("DNA医疗档案系统", size=32, weight=ft.FontWeight.BOLD),
                ft.Text("请选择登录方式", size=16),
                ft.Row([
                    ft.ElevatedButton("账号登录", width=160, height=70, on_click=normal_login_click),
                    ft.ElevatedButton("游客模式", width=160, height=70, on_click=visitor_click)
                ], alignment=ft.MainAxisAlignment.CENTER)
            ],
            expand=True,
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER
        )
    )

# =====================【原main里面全部业务逻辑迁移到此函数】=====================

def run_app_logic(page: ft.Page):
    page.title = "DNA医疗档案系统"
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

    def show_dialog(page, title_text, button_texts):
        buttons = []
        for text in button_texts:
            btn = ft.ElevatedButton(
                text, width=300,
                on_click=lambda e, t=text: close_dlg(page, dlg, t)
            )
            buttons.append(btn)

        dlg = ft.AlertDialog(
            title=ft.Text(title_text, size=20, weight="bold"),
            content=ft.Column(tight=True, controls=buttons, spacing=10),
            actions=[ft.TextButton("取消", on_click=lambda e: close_dlg(page, dlg, "取消"))]
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
        upload_status = ft.Text("", size=14)

        def file_picker_result(e):
            if e.files:
                preview_image.src = e.files[0].path
                preview_image.visible = True
                upload_status.value = f"已选择: {e.files[0].name}"
                upload_status.color = "green"
                page.update()

        def pick_image(e):
            picker_callback["fn"] = file_picker_result
            file_picker.pick_files(allowed_extensions=["jpg", "jpeg", "png"])

        dlg = ft.AlertDialog(
            title=ft.Text("🖼️ 上传图片", size=20, weight="bold"),
            content=ft.Column(tight=True, spacing=20, controls=[
                ft.Text("请选择要上传的图片文件：", size=14),
                ft.ElevatedButton("📁 选择图片文件", icon=ft.icons.IMAGE, on_click=pick_image, width=300),
                upload_status, preview_image,
            ]),
            actions=[ft.TextButton("确认使用", on_click=lambda e: close_dialog(dlg)), ft.TextButton("取消", on_click=lambda e: close_dialog(dlg))]
        )
        page.dialog = dlg
        dlg.open = True
        page.update()

    # ========== 文档导入对话框：拖拽 / 点选 / 粘贴路径 ==========

    def open_doc_dialog(page, on_success=None):
        path_input = ft.TextField(label="或直接粘贴文件完整路径", width=420, hint_text="例如 C:/Users/HONOR/Desktop/档案.txt")
        status_text = ft.Text("", size=12, color="gray")

        def handle_path(path):
            path = (path or "").strip().strip('"')
            if not path:
                status_text.value = "⚠️ 请先拖入文件或输入路径"
                page.update()
                return
            if not os.path.exists(path):
                status_text.value = f"❌ 文件不存在: {path}"
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
                width=460, height=170,
                alignment=ft.alignment.center,
                bgcolor="#e8f4fd",
                border=ft.border.all(2, "#90caf9"),
                border_radius=12,
                content=ft.Column([
                    ft.Text("📂 将档案文档拖到这里", size=18, weight="bold", color="#1976d2"),
                    ft.Text("支持 pdf / docx / txt，识别后自动填入表格", size=12, color="#6B7280"),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8)
            )
        )

        def pick_by_click(e):
            def on_files(ev):
                if ev.files:
                    handle_path(ev.files[0].path)
            picker_callback["fn"] = on_files
            file_picker.pick_files(allowed_extensions=["pdf", "docx", "txt"])

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("📄 导入档案文档", size=20, weight="bold"),
            content=ft.Column([
                drag_area,
                ft.Divider(),
                ft.ElevatedButton("📁 或点击选择文件", icon=ft.icons.FOLDER_OPEN, on_click=pick_by_click, width=460),
                ft.Row([path_input, ft.ElevatedButton("开始识别", on_click=lambda e: handle_path(path_input.value))], spacing=8, wrap=True),
                status_text,
            ], spacing=12, tight=True),
            actions=[ft.TextButton("取消", on_click=lambda e: close_dialog(dlg))]
        )
        page.dialog = dlg
        dlg.open = True
        page.update()

    # ========== AI 识别：右上角悬浮进度卡片，兼容旧版 Flet ==========

    def start_ai_recognition(page, path, on_success=None):
        cancel_event = threading.Event()

        percent_text = ft.Text("0%", size=18, weight="bold", color="#1976d2")
        progress_bar = ft.ProgressBar(width=220, value=0.0, color="#1976d2")
        status_text = ft.Text("正在读取文档...", size=11, color="#6B7280")
        file_name_text = ft.Text(os.path.basename(path), size=10, color="gray")

        progress_card = ft.Container(
            width=260,
            padding=12,
            bgcolor="white",
            border_radius=8,
            shadow=ft.BoxShadow(blur_radius=8),
            right=20,
            top=20,
            content=ft.Column([
                percent_text,
                progress_bar,
                status_text,
                file_name_text,
                ft.Row([
                    ft.TextButton("取消")
                ], alignment=ft.MainAxisAlignment.END)
            ], spacing=6, tight=True),
            visible=False
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
                    page.snack_bar = ft.SnackBar(ft.Text("🛑 用户已取消识别"), bgcolor="blue")
                    page.snack_bar.open = True
                elif result and result[0] == "ok":
                    if on_success:
                        on_success(result[1])
                    else:
                        show_online_form(page, prefill=result[1])
                elif result and result[0] == "error":
                    page.snack_bar = ft.SnackBar(ft.Text(f"❌ 识别失败: {result[1]}"), bgcolor="red")
                    page.snack_bar.open = True
                page.update()

        threading.Thread(target=worker, daemon=True).start()

    # ========== 在线填写表单 ==========

    def show_online_form(page, prefill=None):
        page.controls.clear()
        page.padding = 20
        page.spacing = 20
        page.scroll = ft.ScrollMode.AUTO

        form_data = {}
        manual_inputs = {}
        field_controls = {}

        def save_field(field_name, value):
            form_data[field_name] = value

        def register_field(field_name, ctrl):
            field_controls[field_name] = ctrl

        def create_searchable_disease_field(field_name, label_text, width=600, multiline=False):
            search_field = ft.TextField(
                label=label_text, width=width, multiline=multiline, min_lines=2 if multiline else 1,
                hint_text="输入病症名称搜索（如：无、青霉素、黄疸），或手动输入...",
                on_change=lambda e: update_dropdown(e.control.value)
            )
            register_field(field_name, search_field)

            dropdown_container = ft.Column(spacing=5, visible=False)

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
                            content=ft.Text(f"🔹 {cn}  (英文: {en})  [{cat}]", size=13, color="black", weight="bold"),
                            padding=10, bgcolor="#e3f2fd", border=ft.border.all(1, "#90caf9"), border_radius=6,
                            on_click=lambda e, c=cn, e_name=en: select_item(c, e_name), ink=True
                        )
                        dropdown_container.controls.append(item)
                    dropdown_container.visible = True
                else:
                    dropdown_container.controls.append(ft.Container(
                        content=ft.Text("⚠️ 未找到匹配项，您可以直接手动输入", size=13, color="gray", italic=True),
                        padding=10, bgcolor="#f5f5f5", border=ft.border.all(1, "#e0e0e0"), border_radius=6
                    ))
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
                page.snack_bar = ft.SnackBar(ft.Text("✅ 识别完毕，表格已自动填写"), bgcolor="green")
                page.snack_bar.open = True
                page.update()
            open_doc_dialog(page, on_success=on_success)

        db_warning = ft.Text(
            f"⚠️ 警告: 未找到 {DB_PATH}，请先运行数据库初始化脚本！",
            color="red", weight="bold",
            visible=not os.path.exists(DB_PATH)
        )

        def save_all_data(e):
            global is_visitor
            if is_visitor:
                page.snack_bar = ft.SnackBar(ft.Text("⚠️ 游客模式禁止保存档案文件！"), bgcolor="orange")
                page.snack_bar.open = True
                page.update()
                return
            if not form_data.get("姓名"):
                page.snack_bar = ft.SnackBar(ft.Text("⚠️ 请至少填写姓名！"), bgcolor="orange")
                page.snack_bar.open = True
                page.update()
                return

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"儿童健康档案_{form_data.get('姓名')}_{timestamp}.json"

            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(form_data, f, ensure_ascii=False, indent=2)
                page.snack_bar = ft.SnackBar(ft.Text(f"✅ 数据已保存到 {filename} (含英文映射)"), bgcolor="green")
                page.snack_bar.open = True
                page.update()
            except Exception as ex:
                page.snack_bar = ft.SnackBar(ft.Text(f"❌ 保存失败: {str(ex)}"), bgcolor="red")
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

            print("\n" + "="*80)
            print("🚀 开始生成测试字符串 (为后续 C++ 加密/纠错程序做准备)")
            print("="*80)

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
            print("="*80 + "\n")

            dlg = ft.AlertDialog(
                title=ft.Text("✅ 数据分类确认", size=20, weight="bold"),
                content=ft.Container(
                    content=ft.Column([
                        ft.Card(content=ft.Container(padding=15, content=ft.Column([
                            ft.Text("📦 1. 物理存储 (固定信息)", weight="bold", color="blue", size=16),
                            ft.Divider(),
                            ft.Text(physical_text, size=11, font_family="Consolas")], spacing=5)), elevation=3),
                        ft.Card(content=ft.Container(padding=15, content=ft.Column([
                            ft.Text("🔄 2. 反复存储 (随访/动态信息)", weight="bold", color="orange", size=16),
                            ft.Divider(),
                            ft.Text("💡 提示: 终端已输出拼音字符串（每个字段随机重复3遍）", size=12, color="gray", italic=True),
                            ft.Text(repeated_text, size=11, font_family="Consolas")], spacing=5)), elevation=3),
                        ft.Card(content=ft.Container(padding=15, content=ft.Column([
                            ft.Text("🧬 3. 病症记录 (数据库映射)", weight="bold", color="green", size=16),
                            ft.Divider(),
                            ft.Text("💡 提示: 终端已输出英文连接字符串", size=12, color="gray", italic=True),
                            ft.Text(disease_text, size=11, font_family="Consolas")], spacing=5)), elevation=3),
                    ], scroll=ft.ScrollMode.AUTO, spacing=15),
                    width=650, height=600, padding=10
                ),
                actions=[ft.ElevatedButton("关闭", on_click=lambda e: close_test_dlg(dlg), style=ft.ButtonStyle(bgcolor="#2196f3", color="white"))],
                actions_alignment="end"
            )

            page.dialog = dlg
            dlg.open = True
            page.update()

            page.snack_bar = ft.SnackBar(ft.Text("✅ 数据已分类！请查看终端(CMD)输出的两个测试字符串"), bgcolor="blue", duration=3000)
            page.snack_bar.open = True
            page.update()

        def close_test_dlg(dlg):
            dlg.open = False
            page.update()

        # ========== 1. 基本信息模块 ==========

        gender_group = ft.RadioGroup(
            ft.Row([ft.Radio(value="男", label="男"), ft.Radio(value="女", label="女")]),
            on_change=lambda e: save_field("性别", e.data)
        )
        register_field("性别", gender_group)

        birth_field = ft.TextField(label="出生日期", width=200, hint_text="YYYY-MM-DD", on_change=lambda e: save_field("出生日期", e.control.value))
        register_field("出生日期", birth_field)

        id_field = ft.TextField(label="出生证/身份证号", width=400, on_change=lambda e: save_field("证件号码", e.control.value))
        register_field("证件号码", id_field)

        hukou_field = ft.TextField(label="户籍地址", width=600, on_change=lambda e: save_field("户籍地址", e.control.value))
        register_field("户籍地址", hukou_field)

        address_field = ft.TextField(label="常住地址", width=600, on_change=lambda e: save_field("常住地址", e.control.value))
        register_field("常住地址", address_field)

        org_field = ft.TextField(label="建档机构", width=300, on_change=lambda e: save_field("建档机构", e.control.value))
        register_field("建档机构", org_field)

        file_date_field = ft.TextField(label="建档日期", width=200, hint_text="YYYY-MM-DD", on_change=lambda e: save_field("建档日期", e.control.value))
        register_field("建档日期", file_date_field)

        phone_field = ft.TextField(label="联系电话", width=200, on_change=lambda e: save_field("联系电话", e.control.value))
        register_field("联系电话", phone_field)

        basic_info = ft.Card(content=ft.Container(padding=20, content=ft.Column([
            ft.Text("基本信息", size=24, weight="bold"), ft.Divider(),
            ft.Row([
                ft.TextField(label="档案编号", width=200, on_change=lambda e: save_field("档案编号", e.control.value)),
                ft.TextField(label="姓名", width=200, on_change=lambda e: save_field("姓名", e.control.value))]),
            ft.Column([
                ft.Text("性别"),
                gender_group]),
            birth_field,
            id_field,
            hukou_field,
            address_field,
            ft.Row([org_field, file_date_field, phone_field]),
        ])))

        # ========== 2. 个人基础信息模块 ==========

        nation_field = ft.TextField(label="民族", width=150, on_change=lambda e: save_field("民族", e.control.value))
        register_field("民族", nation_field)

        blood_field = ft.TextField(label="ABO血型", width=100, on_change=lambda e: save_field("ABO血型", e.control.value))
        register_field("ABO血型", blood_field)

        rh_group = ft.RadioGroup(
            ft.Row([ft.Radio(value="阳性", label="Rh阳性"), ft.Radio(value="阴性", label="Rh阴性")]),
            on_change=lambda e: save_field("Rh血型", e.data)
        )
        register_field("Rh血型", rh_group)

        father_name = ft.TextField(label="姓名", width=200, on_change=lambda e: save_field("父亲姓名", e.control.value))
        register_field("父亲姓名", father_name)

        father_phone = ft.TextField(label="联系电话", width=200, on_change=lambda e: save_field("父亲联系电话", e.control.value))
        register_field("父亲联系电话", father_phone)

        mother_name = ft.TextField(label="姓名", width=200, on_change=lambda e: save_field("母亲姓名", e.control.value))
        register_field("母亲姓名", mother_name)

        mother_phone = ft.TextField(label="联系电话", width=200, on_change=lambda e: save_field("母亲联系电话", e.control.value))
        register_field("母亲联系电话", mother_phone)

        week_field = ft.TextField(label="出生孕周(周)", width=150, on_change=lambda e: save_field("出生孕周", e.control.value))
        register_field("出生孕周", week_field)

        weight_field = ft.TextField(label="出生体重(g)", width=150, on_change=lambda e: save_field("出生体重", e.control.value))
        register_field("出生体重", weight_field)

        height_field = ft.TextField(label="出生身长(cm)", width=150, on_change=lambda e: save_field("出生身长", e.control.value))
        register_field("出生身长", height_field)

        hospital_field = ft.TextField(label="分娩出生机构", width=400, on_change=lambda e: save_field("分娩机构", e.control.value))
        register_field("分娩机构", hospital_field)

        apgar1_field = ft.TextField(label="Apgar评分(1分钟)", width=250, on_change=lambda e: save_field("Apgar_1分钟", e.control.value))
        register_field("Apgar_1分钟", apgar1_field)

        apgar5_field = ft.TextField(label="Apgar评分(5分钟)", width=250, on_change=lambda e: save_field("Apgar_5分钟", e.control.value))
        register_field("Apgar_5分钟", apgar5_field)

        personal_info = ft.Card(content=ft.Container(padding=20, content=ft.Column([
            ft.Text("个人基础信息", size=24, weight="bold"), ft.Divider(),
            ft.Row([nation_field, blood_field]),
            ft.Column([
                ft.Text("Rh血型"),
                rh_group]),
            ft.Text("父母信息", weight="bold", size=16),
            ft.Row([
                ft.Column([
                    ft.Text("父亲信息"),
                    father_name, father_phone]),
                ft.Column([
                    ft.Text("母亲信息"),
                    mother_name, mother_phone])]),
            ft.Row([week_field, weight_field, height_field]),
            hospital_field,
            ft.Row([apgar1_field, apgar5_field]),
        ])))

        # ========== 3. 新生儿疾病筛查模块 ==========

        pku_group = ft.RadioGroup(
            ft.Row([ft.Radio(value="阴性", label="阴性"), ft.Radio(value="阳性", label="阳性")]),
            on_change=lambda e: save_field("苯丙酮尿症", e.data)
        )
        register_field("苯丙酮尿症", pku_group)

        ch_group = ft.RadioGroup(
            ft.Row([ft.Radio(value="阴性", label="阴性"), ft.Radio(value="阳性", label="阳性")]),
            on_change=lambda e: save_field("先天性甲状腺功能减低症", e.data)
        )
        register_field("先天性甲状腺功能减低症", ch_group)

        hear_group = ft.RadioGroup(
            ft.Row([ft.Radio(value="通过", label="通过"), ft.Radio(value="未通过", label="未通过")]),
            on_change=lambda e: save_field("听力筛查", e.data)
        )
        register_field("听力筛查", hear_group)

        screening = ft.Card(content=ft.Container(padding=20, content=ft.Column([
            ft.Text("新生儿疾病筛查", size=24, weight="bold"), ft.Divider(),
            ft.Column([
                ft.Text("苯丙酮尿症"),
                pku_group]),
            ft.Column([
                ft.Text("先天性甲状腺功能减低症"),
                ch_group]),
            ft.Column([
                ft.Text("听力筛查"),
                hear_group]),
            create_searchable_disease_field("过敏史", "过敏史（搜索或输入）", width=600),
            create_searchable_disease_field("先天异常", "先天异常/特殊体质", width=600, multiline=True),
            create_searchable_disease_field("既往住院史", "既往住院史", width=600, multiline=True),
            create_searchable_disease_field("家族遗传病史", "家族遗传病史", width=600, multiline=True),
        ])))

        page.add(
            ft.Row([
                ft.IconButton(icon=ft.icons.ARROW_BACK, tooltip="返回主界面", on_click=lambda e: enter_main(page)),
                ft.Text("医疗冷归档健康档案系统", size=24, weight="bold", color="blue")
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            db_warning,
            ft.Divider(),
            basic_info, personal_info, screening, ft.Divider(),
            ft.Row([
                ft.ElevatedButton("💾 保存数据", on_click=save_all_data, icon=ft.icons.SAVE),
                ft.ElevatedButton("📄 从文档导入", on_click=lambda e: import_doc_in_form(), icon=ft.icons.UPLOAD_FILE),
                ft.ElevatedButton("✅ 确认并测试", on_click=confirm_and_test, icon=ft.icons.CHECK_CIRCLE, style=ft.ButtonStyle(bgcolor="#ff9800", color="white")),
            ], spacing=20, alignment=ft.MainAxisAlignment.CENTER, wrap=True),
            ft.Container(height=50),
        )

        if prefill:
            fill_form_from_data(prefill)
            page.update()
            page.snack_bar = ft.SnackBar(ft.Text("✅ 识别完毕，表格已自动填写"), bgcolor="green")
            page.snack_bar.open = True
            page.update()

    # ========== 开场画面 ==========

    splash_text_content = ft.Column(
        horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=25,
        controls=[
            ft.Text("DNA医疗档案系统", size=52, weight="bold", color="white", text_align=ft.TextAlign.CENTER),
            ft.Container(
                padding=ft.padding.symmetric(horizontal=24, vertical=12), border=ft.border.all(1, "#334155"), border_radius=50, bgcolor="#1e293b50",
                content=ft.Row(tight=True, spacing=8, controls=[
                    ft.Text("↩️", size=18),
                    ft.Text("点击屏幕任意位置进入系统", size=16, color="#cbd5e1", weight=ft.FontWeight.W_300)
                ])
            ),
        ]
    )

    splash = ft.Container(
        expand=True, on_click=lambda e: enter_main(page),
        content=ft.Stack(expand=True, controls=[
            ft.Container(expand=True, image_src="C:/Users/HONOR/Desktop/DNA_new_version/cover.jpg", image_fit=ft.ImageFit.COVER),
            ft.Container(expand=True, bgcolor="#0f172a", opacity=0.75),
            ft.Column(expand=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER, controls=[
                ft.Container(expand=True), splash_text_content, ft.Container(expand=True)
            ])
        ])
    )

    page.add(splash)
    page.update()

    # ========== 进入主界面 ==========

    def enter_main(page):
        page.controls.clear()
        page.padding = 0
        page.spacing = 0
        page.bgcolor = "#f0f2f5"
        page.vertical_alignment = ft.MainAxisAlignment.CENTER
        page.horizontal_alignment = ft.CrossAxisAlignment.CENTER

        main_content = ft.Column(
            horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=40,
            controls=[
                ft.Text("DNA医疗档案系统", size=32, weight="bold", color="#1e293b"),
                ft.Row(alignment=ft.MainAxisAlignment.CENTER, spacing=40, controls=[
                    ft.Container(
                        width=400, height=400, bgcolor="white", border_radius=16, alignment=ft.alignment.center,
                        content=ft.Column(horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=15, controls=[
                            ft.Text("🔒", size=80), ft.Text("加密", size=32, weight="bold", color="#334155"),
                            ft.Text("保护您的医疗档案数据", size=14, color="#64748b")
                        ]),
                        on_click=lambda e: show_dialog(page, "选择加密信息传输方式", ["📝 在线填写", "📄 输入文档", "🖼️ 输入图片"]),
                        ink=True, shadow=ft.BoxShadow(blur_radius=20, color="#00000010", spread_radius=2),
                    ),
                    ft.Container(
                        width=400, height=400, bgcolor="white", border_radius=16, alignment=ft.alignment.center,
                        content=ft.Column(horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=15, controls=[
                            ft.Text("🔓", size=80), ft.Text("解密", size=32, weight="bold", color="#334155"),
                            ft.Text("还原您的医疗档案数据", size=14, color="#64748b")
                        ]),
                        on_click=lambda e: show_dialog(page, "选择解密信息输出方式", ["📄 读取加密文件", "📝 解密为文档", "🖼️ 解密为图片"]),
                        ink=True, shadow=ft.BoxShadow(blur_radius=20, color="#00000010", spread_radius=2),
                    ),
                ])
            ]
        )

        page.add(main_content)
        page.update()

def main(page: ft.Page):
    login_select_page(page)

if __name__ == "__main__":
    ft.app(target=main)
