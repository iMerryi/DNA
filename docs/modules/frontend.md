# 前端界面模块开发文档

## 模块概述

| 属性 | 内容 |
|------|------|
| **模块名称** | ui_interface.py |
| **模块全称** | User Interface（用户界面） |
| **负责角色** | 前端开发（同学A） |
| **技术栈** | Flet >= 0.21.0 |
| **依赖模块** | data_store, ollama_api, dna_codec, core/* |
| **代码位置** | `modules/ui_interface.py` |

---

## 1. 模块职责

| 编号 | 职责描述 | 优先级 |
|------|---------|--------|
| UI-01 | 实现游客登录页面（无需账号注册） | P0 |
| UI-02 | 实现主平台页面（加密板块 + 解密板块） | P0 |
| UI-03 | 页面支持上传图片、文档、文本输入 | P0 |
| UI-04 | 预留加密/解密接口函数，调用后端模块 | P0 |
| UI-05 | 实现侧边任务栏，支持多任务并行 | P1 |
| UI-06 | 实现个人中心模块 | P1 |
| UI-07 | 运行效果演示（截图/录屏） | P1 |

---

## 2. 页面结构与导航

### 2.1 视图类型枚举

```python
class ViewType(Enum):
    SPLASH = "splash"           # 开场动画页
    LOGIN = "login"             # 登录页
    MAIN = "main"               # 主界面（加密/解密选择）
    ENCRYPT = "encrypt"         # 加密操作页
    DECRYPT = "decrypt"         # 解密操作页
    PROFILE = "profile"         # 个人中心页
```

### 2.2 页面组件层级

```
HealthArchiveApp
│
├── SplashScreen（开场动画）
│   ├── 全屏背景图 (cover.jpg)
│   ├── 半透明遮罩层
│   └── 标题 + "点击进入"提示
│
├── LoginPage（登录页）
│   ├── 游客登录按钮（一键进入）
│   └── 用户登录表单（预留）
│
├── MainPage（主界面）
│   ├── 顶部标题栏
│   ├── 双卡片选择区
│   │   ├── 🔒 加密卡片 → 进入 EncryptView
│   │   └── 🔓 解密卡片 → 进入 DecryptView
│   └── 底部版本信息
│
├── EncryptView（加密页面）
│   ├── 返回按钮 + 标题
│   ├── 输入方式选择
│   │   ├── 📝 在线填写 → 显示表单
│   │   ├── 📄 导入文档 → 弹出文件选择对话框
│   │   └── 🖼️ 上传图片 → 弹出图片选择对话框（预留OCR）
│   ├── 表单区域（三卡片布局）
│   │   ├── Card 1: 基本信息（档案编号、姓名、性别、出生日期...）
│   │   ├── Card 2: 个人基础信息（民族、血型、父母信息、出生情况...）
│   │   └── Card 3: 新生儿疾病筛查（PKU、甲减、听力、过敏史...）
│   ├── 操作按钮区
│   │   ├── 💾 保存数据
│   │   ├── 📄 从文档导入
│   │   └── ✅ 确认并编码
│   └── 数据分类预览弹窗（编码前确认）
│
├── DecryptView（解密页面）
│   ├── 返回按钮 + 标题
│   ├── 输入方式选择
│   │   ├── 📋 粘贴DNA序列
│   │   ├── 📂 读取加密文件
│   │   └── 🗄️ 从数据库选择
│   ├── 密钥输入框
│   ├── 操作按钮：🔓 开始解密
│   ├── 解码结果展示区
│   └── 导出按钮区
│
├── TaskBar（侧边任务栏）
│   ├── 任务列表（可折叠）
│   └── 任务计数徽章
│
└── ProfileView（个人中心）
    ├── 用户信息卡片
    ├── 历史任务记录
    ├── 统计信息
    └── 设置选项（预留）
```

---

## 3. 对外接口（需实现的公共方法）

> 详细签名见 `api_contract.md` 第3节，此处为简要清单。

### 3.1 应用生命周期

| 方法 | 说明 |
|------|------|
| `start()` | 启动Flet应用入口 |
| `navigate_to(view_type, **kwargs)` | 页面导航 |

### 3.2 加密流程回调

| 方法 | 说明 | 调用的后端模块 |
|------|------|---------------|
| `on_file_uploaded(file_path)` | 文件上传处理 | data_store.save_upload_file() |
| `on_text_input(text)` | 文本输入处理 | 直接存入form_data |
| `on_image_uploaded(image_path)` | 图片上传（预留OCR） | 预留 |
| `on_trigger_ai_extract(raw_text)` | 触发AI提取 | ollama_api.extract_fields() |
| `on_save_record(record)` | 保存档案 | data_store.save_record() |
| `on_encode_dna(record, key)` | 执行编码 | dna_codec.encode() |

### 3.3 解密流程回调

| 方法 | 说明 | 调用的后端模块 |
|------|------|---------------|
| `on_decode_dna(dna_sequence, key)` | 执行解码 | dna_codec.decode() |
| `on_export_result(data, format)` | 导出结果 | data_store.export_record_to_json/docx() |

### 3.4 任务管理

| 方法 | 说明 |
|------|------|
| `create_task(task_type, source_file)` | 创建后台任务 |
| `update_task_progress(task_id, progress, message)` | 更新进度 |
| `cancel_task(task_id)` | 取消任务 |
| `get_task_list()` | 获取任务列表 |

### 3.5 UI更新方法（供其他模块调用）

| 方法 | 说明 | 调用场景 |
|------|------|---------|
| `show_progress(percent, message)` | 更新进度条 | AI处理、编解码过程中 |
| `show_result(result_data)` | 显示结果 | AI提取完成、解码完成 |
| `show_error(error_msg)` | 错误提示 | 任何异常情况 |
| `show_success(msg)` | 成功提示 | 保存/编码/解码成功 |
| `show_confirmation(title, content, ...)` | 确认对话框 | 删除等危险操作 |

---

## 4. 表单字段定义

### 4.1 物理存储字段（Card 1 + Card 2）

| 字段名 | 字段类型 | 必填 | 示例值 |
|--------|---------|------|--------|
| 档案编号 | TextField | 是 | ARCHIVE_20261013_001 |
| 姓名 | TextField | 是 | 张三 |
| 性别 | Dropdown | 是 | 男/女 |
| 出生日期 | DatePicker | 是 | 2026-01-15 |
| 证件号码 | TextField | 否 | 110101202601150011 |
| 户籍地址 | TextField | 否 | 北京市朝阳区xxx |
| 常住地址 | TextField | 否 | 北京市朝阳区xxx |
| 建档机构 | TextField | 是 | xxx社区卫生服务中心 |
| 建档日期 | DatePicker | 是 | 2026-10-13 |
| 联系电话 | TextField | 是 | 13800138000 |
| 民族 | Dropdown | 否 | 汉族 |
| ABO血型 | Dropdown | 否 | A/B/AB/O |
| Rh血型 | Dropdown | 否 | 阳性/阴性 |
| 父亲姓名 | TextField | 否 | 张父 |
| 父亲联系电话 | TextField | 否 | 13900139000 |
| 母亲姓名 | TextField | 否 | 张母 |
| 母亲联系电话 | TextField | 否 | 13700137000 |
| 出生孕周 | TextField | 否 | 40周 |
| 出生体重 | TextField | 否 | 3500g |
| 出生身长 | TextField | 否 | 50cm |
| 分娩机构 | TextField | 否 | xxx医院 |
| Apgar_1分钟 | TextField | 否 | 9 |
| Apgar_5分钟 | TextField | 否 | 10 |

### 4.2 病症记录字段（Card 3）

| 字段名 | 字段类型 | 选项 |
|--------|---------|------|
| 苯丙酮尿症 | Dropdown | 阴性/阳性/疑似 |
| 先天性甲状腺功能减低症 | Dropdown | 阴性/阳性/疑似 |
| 听力筛查 | Dropdown | 通过/未通过/复查中 |
| 过敏史 | TextField | 自由填写 |
| 先天异常 | TextField | 自由填写 |
| 既往住院史 | TextField | 自由填写 |
| 家族遗传病史 | TextField | 自由填写 |

### 4.3 反复存储字段（动态表格）

| 字段名 | 字段类型 | 说明 |
|--------|---------|------|
| 随访日期 | DatePicker | 可添加多行 |
| 当前体重 | TextField | 单位：kg |
| 体温 | TextField | 单位：℃ |

---

## 5. 任务状态管理

### 5.1 任务状态枚举

```python
class TaskStatus(Enum):
    PENDING = "pending"         # 等待中
    RUNNING = "running"         # 执行中
    COMPLETED = "completed"     # 已完成
    FAILED = "failed"           # 失败
    CANCELLED = "cancelled"     # 已取消
```

### 5.2 任务信息结构

```python
@dataclass
class TaskInfo:
    task_id: str                # 任务唯一ID
    task_type: str              # "encrypt" / "decode"
    status: TaskStatus          # 当前状态
    progress: float             # 0.0 - 100.0
    message: str                # 状态描述
    created_at: str             # ISO格式时间
    source_file: Optional[str]  # 源文件路径
    result: Optional[Any]       # 完成后的结果
```

---

## 6. 异步处理规范

### 6.1 耗时操作必须异步执行

以下操作**必须**在后台线程执行，不能阻塞UI主线程：

| 操作 | 预估耗时 | 处理方式 |
|------|---------|---------|
| AI字段提取 | 10-30秒 | threading.Thread + on_progress回调 |
| DNA编码 | 1-5秒 | threading.Thread |
| DNA解码 | 1-5秒 | threading.Thread |
| 文档解析 | 1-3秒 | threading.Thread |
| AI纠错 | 10-30秒 | threading.Thread + on_progress回调 |

### 6.2 异步模式模板

```python
def on_trigger_ai_extract(self, raw_text: str) -> None:
    """触发AI字段提取（异步，不阻塞UI）"""
    task_id = self.create_task("extract")

    def background_task():
        try:
            self.update_task_progress(task_id, 0, "正在连接AI服务...")
            result = self.ai_client.extract_fields(
                raw_text,
                on_progress=lambda p, m: self.update_task_progress(task_id, p, m)
            )
            self.page.run_thread(lambda: self.on_ai_extract_complete(result.data))
            self.update_task_progress(task_id, 100, "完成", TaskStatus.COMPLETED)
        except Exception as e:
            self.page.run_thread(lambda: self.show_error(str(e)))
            self.update_task_progress(task_id, 0, f"失败: {e}", TaskStatus.FAILED)

    threading.Thread(target=background_task).start()
```

---

## 7. 交付物清单

### 第一阶段交付（桩函数版本）

- [ ] 项目骨架搭建（目录结构、__init__.py）
- [ ] HealthArchiveApp 类框架
- [ ] 6个视图页面的UI布局（Splash/Login/Main/Encrypt/Decrypt/Profile）
- [ ] 表单组件（33个字段的输入控件）
- [ ] 任务栏组件（TaskBar）
- [ ] 所有回调方法的**桩函数实现**（print日志即可）
- [ ] 页面导航功能
- [ ] 文件选择器集成

### 最终交付

- [ ] 替换桩函数为真实后端调用
- [ ] 异步任务管理完整实现
- [ ] 进度条实时更新
- [ ] 错误提示与异常处理
- [ ] 界面截图/录屏演示

---

## 8. 注意事项

1. **不要实现业务逻辑**：UI模块只负责展示和交互，所有数据处理调用后端模块
2. **桩函数先行**：第一阶段先用桩函数，等后端模块就绪后再替换
3. **线程安全**：UI更新必须通过 `page.run_thread()` 回到主线程
4. **FilePicker全局单例**：避免重复创建导致卡顿
5. **分辨率适配**：最低支持 1280×720
