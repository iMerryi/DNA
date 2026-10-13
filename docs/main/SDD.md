# 软件设计说明书 (SDD)

## 基于DNA序列编码的医疗数据加密桌面系统

---

| 文档信息 | 内容 |
|---------|------|
| **项目名称** | DNA医疗档案系统 (DNA Medical Archive System) |
| **文档版本** | v1.0 |
| **编写日期** | 2026-10-13 |
| **文档状态** | 初稿（待评审） |
| **开发团队** | 4人（项目经理/核心算法 + 前端 + 数据库 + AI） |

---

## 目录

1. [项目概述](#1-项目概述)
2. [系统架构设计](#2-系统架构设计)
3. [模块详细设计](#3-模块详细设计)
4. [数据库设计](#4-数据库设计)
5. [接口契约](#5-接口契约)
6. [开发分工与任务分配](#6-开发分工与任务分配)
7. [非功能需求](#7-非功能需求)
8. [附录](#8-附录)

---

## 1. 项目概述

### 1.1 项目背景

医疗健康档案包含大量敏感个人信息，传统电子存储方式面临数据泄露、长期保存成本高、格式淘汰等风险。本项目创新性地将医疗数据编码为 **DNA序列** 进行存储，利用 DNA 分子的高密度存储特性（1克DNA可存储约215PB数据）和超长保质期（理论上可达数百年），实现医疗数据的**安全加密**与**长期冷归档**。

### 1.2 项目目标

构建一套完整的桌面端应用系统，实现：

| 目标编号 | 目标描述 | 优先级 |
|---------|---------|--------|
| G-01 | 支持医疗文档的智能识别与结构化提取 | P0 |
| G-02 | 实现文本→二进制→DNA序列的完整编码流程 | P0 |
| G-03 | 实现DNA序列→二进制→文本的完整解码流程 | P0 |
| G-04 | 编码结果满足DNA生物特性约束（GC含量、热稳定性） | P0 |
| G-05 | 解密时支持基于数据库的智能纠错 | P1 |
| G-06 | 支持多任务并行，UI不阻塞 | P1 |
| G-07 | 提供友好的图形用户界面 | P1 |
| G-08 | 数据本地存储，保护隐私 | P0 |

### 1.3 用户角色

| 角色 | 描述 | 权限 |
|------|------|------|
| **游客** | 未登录用户 | 可浏览系统首页，有限功能体验 |
| **普通用户** | 已注册/登录用户 | 完整加密/解密功能，个人中心 |
| **管理员** | 系统管理者 | 用户管理、数据维护（预留） |

### 1.4 技术栈

| 层级 | 技术选型 | 版本要求 | 说明 |
|------|---------|---------|------|
| **前端界面** | Flet | >= 0.21.0 | Python原生GUI框架，类似Flutter |
| **核心算法** | C++ | C++17 | 高性能编解码计算 |
| **数据库** | SQLite | 3.x | 轻量级，无需额外服务 |
| **AI引擎** | Ollama + Qwen2.5 | 最新版 | 本地部署，隐私保护 |
| **运行时** | Python | >= 3.8 | 主程序运行环境 |

### 1.5 核心业务流程

#### 1.5.1 加密流程（数据写入）

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          加密流程（Encode）                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  [输入源]                                                                │
│    ├── 手动填写表单                                                      │
│    ├── 导入文档（txt/docx/pdf） ──→ AI识别 ──→ 结构化字段               │
│    └── 上传图片 ──→ OCR识别 ──→ 文本提取                               │
│           │                                                             │
│           ▼                                                             │
│  [数据预处理]                                                            │
│    ├── 字段分类：物理存储(固定) / 反复存储(动态) / 病症记录(英文映射)    │
│    ├── 拼音转换：反复存储字段转拼音                                      │
│    ├── 病症标准化：中文→英文映射（查词典库）                            │
│    └── 密钥生成：基于患者身份信息（姓名+出生日期）                       │
│           │                                                             │
│           ▼                                                             │
│  [核心编码] （C++ 模块）                                                 │
│    ├── Step 1: 英文文本 → ASCII → 二进制串                             │
│    ├── Step 2: 密钥 → ASCII → 二进制串                                 │
│    ├── Step 3: XOR异或加密 → 加密后二进制                              │
│    ├── Step 4: 二进制 → DNA碱基映射（11→A, 01→T, 10→C, 00→G）        │
│    └── Step 5: 生物特性优化                                            │
│        ├── CG含量校验（目标40%-60%，标准50%）                         │
│        ├── 热稳定性系数校验（A/T=1.0, C/G=1.5, X/Y=1.8）             │
│        └── 自适应修复：插入CG/AT片段或人工碱基(X/Y标记)                │
│           │                                                             │
│           ▼                                                             │
│  [输出与存储]                                                            │
│    ├── DNA序列字符串                                                   │
│    ├── CG含量、热稳定性系数等参数                                       │
│    └── 存入数据库（关联原始记录）                                       │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

#### 1.5.2 解密流程（数据读取）

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          解密流程（Decode）                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  [输入源]                                                                │
│    ├── 粘贴/导入DNA序列字符串                                           │
│    ├── 从数据库读取已存储的DNA序列                                      │
│    └── 上传包含DNA序列的文件                                            │
│           │                                                             │
│           ▼                                                             │
│  [预处理]                                                                │
│    ├── 输入密钥（用于XOR解密）                                          │
│    └── 序列合法性初步校验                                              │
│           │                                                             │
│           ▼                                                             │
│  [核心解码] （C++ 模块）                                                 │
│    ├── Step 1: 移除人工碱基标记（X/Y配对剔除）                         │
│    ├── Step 2: DNA碱基 → 二进制（A→11, T→01, C→10, G→00）            │
│    ├── Step 3: XOR解密（使用相同密钥）                                  │
│    └── Step 4: 二进制 → ASCII → 原始文本                               │
│           │                                                             │
│           ▼                                                             │
│  [智能纠错] （AI + 数据库）                                             │
│    ├── 与数据库中已存储记录进行相似度比对                               │
│    ├── 识别数据损坏程度（位翻转率、缺失率）                             │
│    ├── AI辅助纠错：基于上下文推断修复                                   │
│    └── 输出纠错报告与置信度                                           │
│           │                                                             │
│           ▼                                                             │
│  [输出]                                                                  │
│    ├── 还原的医疗档案结构化数据                                         │
│    ├── 可导出为：JSON / DOCX / PDF 格式                                │
│    └── 纠错日志与数据完整性报告                                         │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. 系统架构设计

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           表示层 (Presentation Layer)                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        ui_interface.py                              │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────────────┐  │   │
│  │  │ 登录模块  │  │ 加密模块  │  │ 解密模块  │  │   个人中心模块    │  │   │
│  │  │ LoginView │  │EncryptView│  │DecryptView│  │  ProfileView     │  │   │
│  │  └──────────┘  └──────────┘  └──────────┘  └────────────────────┘  │   │
│  │  ┌──────────────────────────────────────────────────────────────┐  │   │
│  │  │                    侧边任务栏 (TaskBar)                       │  │   │
│  │  │         支持多任务并行 / 后台执行 / 进度显示                  │  │   │
│  │  └──────────────────────────────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────────────────┤
│                           业务逻辑层 (Business Logic Layer)                 │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         core/                                       │   │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐  │   │
│  │  │ field_extractor │  │ data_classifier │  │  pinyin_utils      │  │   │
│  │  │ 字段提取器       │  │ 数据分类器      │  │  拼音转换工具      │  │   │
│  │  └─────────────────┘  └─────────────────┘  └─────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────────────────┤
│                           服务层 (Service Layer)                            │
│  ┌──────────────────────┐  ┌──────────────────────┐  ┌─────────────────┐   │
│  │   ollama_api.py      │  │   dna_codec.py       │  │ error_corrector │   │
│  │   AI交互模块         │  │   DNA编解码模块      │  │ .py             │   │
│  │                      │  │                      │  │ 智能纠错模块   │   │
│  │ • 文档识别           │  │ • encode() 编码      │  │                  │   │
│  │ • 字段提取           │  │ • decode() 解码      │  │ • 相似度比对   │   │
│  │ • OCR（预留）        │  │ • 参数优化          │  │ • AI纠错推断   │   │
│  └──────────────────────┘  └──────────────────────┘  └─────────────────┘   │
├─────────────────────────────────────────────────────────────────────────────┤
│                           数据访问层 (Data Access Layer)                     │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        data_store.py                                │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌───────────┐  │   │
│  │  │ SQLite DB   │  │ 文件解析器  │  │ 文件管理器  │  │ 缓存管理  │  │   │
│  │  │ medical.db  │  │ txt/docx/pdf│  │ upload/export│  │           │  │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └───────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────────────────┤
│                           基础设施层 (Infrastructure Layer)                  │
│  ┌──────────────────────┐  ┌──────────────────────┐  ┌─────────────────┐   │
│  │   C++ 编解码器       │  │   Ollama 本地服务    │  │   config.py     │   │
│  │   DNA_encoder.exe   │  │   Qwen2.5:7b         │  │   全局配置      │   │
│  │   DNA_decoder.exe   │  │   (或其他模型)        │  │                 │   │
│  └──────────────────────┘  └──────────────────────┘  └─────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 项目目录结构

```
DNA_new_version/
│
├── 📄 main.py                    # 应用入口（极简启动器）
├── 📄 config.py                  # 全局配置管理
├── 📄 requirements.txt           # Python依赖清单
│
├── 📁 modules/                   # 业务模块层
│   ├── __init__.py
│   ├── ui_interface.py           # 【模块1】前端界面（Flet GUI）
│   ├── data_store.py             # 【模块2】数据库与文件处理
│   ├── ollama_api.py             # 【模块3】AI交互封装
│   ├── dna_codec.py              # 【新增】DNA编解码接口（封装C++）
│   └── error_corrector.py        # 【新增】智能纠错模块
│
├── 📁 core/                      # 核心纯逻辑层（无外部依赖）
│   ├── __init__.py
│   ├── field_extractor.py        # 字段提取与标准化
│   ├── data_classifier.py        # 数据分类（物理/反复/病症）
│   ├── pinyin_utils.py           # 拼音转换工具
│   └── similarity.py             # 相似度计算（纠错用）
│
├── 📁 DNA_code/                  # C++ 核心算法（已有）
│   └── DNA_code/
│       ├── DNA_encoder.cpp       # DNA编码器
│       ├── DNA_decoder.cpp       # DNA解码器
│       └── (编译后的 .exe 文件)
│
├── 📁 data/                      # 运行时数据目录
│   ├── db/                       # SQLite数据库文件
│   │   └── medical_archive.db    # 主数据库
│   ├── uploads/                  # 上传文件临时存储
│   ├── exports/                  # 导出文件（JSON/DOCX/PDF）
│   └── logs/                     # 运行日志
│
├── 📁 tests/                     # 单元测试
│   ├── test_data_store.py
│   ├── test_ollama_api.py
│   ├── test_dna_codec.py
│   ├── test_core/
│   │   ├── test_field_extractor.py
│   │   └── test_data_classifier.py
│   └── test_ui_interface.py
│
├── 📁 数据模板/                  # 档案文档模板（已有）
├── 📄 README.md                  # 项目说明
└── 📄 SDD.md                     # 本文档（软件设计说明书）
```

### 2.3 模块依赖关系

```
                    ┌─────────────────┐
                    │   main.py       │
                    │   (入口启动器)   │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  ui_interface.py │ ◄── 用户直接交互
                    │  (前端界面模块)  │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┬──────────────┐
              │              │              │              │
     ┌────────▼────────┐    │     ┌────────▼────────┐    │
     │  data_store.py  │    │     │  ollama_api.py  │    │
     │  (数据存储模块)  │    │     │  (AI交互模块)   │    │
     └────────┬────────┘    │     └────────┬────────┘    │
              │              │              │              │
     ┌────────▼────────┐    │              │     ┌────────▼────────┐
     │  SQLite / 文件   │    │              │     │  Ollama 服务    │
     └─────────────────┘    │              │     │  (外部进程)     │
                            │              │     └─────────────────┘
                   ┌────────▼────────┐    │
                   │  dna_codec.py   │    │
                   │  (DNA编解码)    │    │
                   └────────┬────────┘    │
                            │              │
                   ┌────────▼────────┐    │
                   │  C++ .exe       │    │
                   │  (外部进程)     │    │
                   └─────────────────┘    │
                                          │
                            ┌─────────────▼──────────┐
                            │      core/ (纯逻辑)     │
                            │  ├─ field_extractor.py │
                            │  ├─ data_classifier.py │
                            │  └─ pinyin_utils.py    │
                            └────────────────────────┘
```

**依赖规则**：
- `ui_interface.py` 依赖：`data_store`、`ollama_api`、`dna_codec`、`core/*`
- `data_store.py` 依赖：无（独立模块）
- `ollama_api.py` 依赖：无（仅依赖Ollama外部服务）
- `dna_codec.py` 依赖：无（仅依赖C++外部程序）
- `core/*` 依赖：无（纯Python逻辑，无外部依赖）

---

## 3. 模块详细设计

### 3.1 前端界面模块 (`ui_interface.py`)

#### 3.1.1 模块职责

| 职责编号 | 职责描述 | 优先级 |
|---------|---------|--------|
| UI-01 | 实现游客登录页面（无需账号注册） | P0 |
| UI-02 | 实现主平台页面（加密板块 + 解密板块） | P0 |
| UI-03 | 页面支持上传图片、文档、文本输入 | P0 |
| UI-04 | 预留加密/解密接口函数，调用后端模块 | P0 |
| UI-05 | 实现侧边任务栏，支持多任务并行 | P1 |
| UI-06 | 实现个人中心模块 | P1 |
| UI-07 | 运行效果演示（截图/录屏） | P1 |

#### 3.1.2 类定义

```python
# modules/ui_interface.py

import flet as ft
from typing import Callable, Optional, Any
from dataclasses import dataclass
from enum import Enum
import threading
import datetime


class ViewType(Enum):
    """页面类型枚举"""
    SPLASH = "splash"           # 开场动画页
    LOGIN = "login"             # 登录页
    MAIN = "main"               # 主界面（加密/解密选择）
    ENCRYPT = "encrypt"         # 加密操作页
    DECRYPT = "decrypt"         # 解密操作页
    PROFILE = "profile"         # 个人中心页


class TaskStatus(Enum):
    """任务状态枚举"""
    PENDING = "pending"         # 等待中
    RUNNING = "running"         # 执行中
    COMPLETED = "completed"     # 已完成
    FAILED = "failed"           # 失败
    CANCELLED = "cancelled"     # 已取消


@dataclass
class TaskInfo:
    """任务信息数据类"""
    task_id: str                # 任务唯一ID
    task_type: str              # 任务类型: "encrypt" / "decrypt"
    status: TaskStatus          # 当前状态
    progress: float             # 进度百分比 (0.0 - 100.0)
    message: str                # 状态描述文字
    created_at: str             # 创建时间
    source_file: Optional[str]  # 源文件路径（如有）
    result: Optional[Any]       # 任务结果（完成后）


class HealthArchiveApp:
    """
    DNA医疗档案系统 - 主应用类
    
    职责：
    - 管理Flet页面生命周期
    - 协调各业务模块调用
    - 处理用户交互事件
    - 管理后台任务队列
    """

    def __init__(
        self,
        data_store: 'DataStore',          # 数据存储模块实例
        ai_client: 'OllamaClient',         # AI交互模块实例
        dna_codec: 'DNACodec',             # DNA编解码模块实例
        error_corrector: 'ErrorCorrector'  # 纠错模块实例（可选）
    ):
        """
        初始化应用
        
        Args:
            data_store: 数据存储模块实例
            ai_client: AI交互模块实例
            dna_codec: DNA编解码模块实例
            error_corrector: 智能纠错模块实例
        """
        self.data_store = data_store
        self.ai_client = ai_client
        self.dna_codec = dna_codec
        self.error_corrector = error_corrector
        
        # Flet 页面实例
        self.page: Optional[ft.Page] = None
        
        # 当前视图状态
        self.current_view: ViewType = ViewType.SPLASH
        
        # 当前表单数据
        self.form_data: dict = {}
        
        # 任务管理
        self.tasks: dict[str, TaskInfo] = {}      # 任务字典 {task_id: TaskInfo}
        self.task_counter: int = 0                 # 任务计数器
        
        # 文件选择器（全局单例，避免重复创建导致卡顿）
        self.file_picker: Optional[ft.FilePicker] = None

    # ==================== 应用生命周期 ====================
    
    def start(self) -> None:
        """启动Flet应用（入口方法）"""
        pass
    
    def _initialize_page(self, page: ft.Page) -> None:
        """初始化页面基础配置"""
        pass
    
    # ==================== 视图导航 ====================
    
    def navigate_to(self, view_type: ViewType, **kwargs) -> None:
        """导航到指定视图"""
        pass
    
    def _show_splash(self) -> None:
        """显示开场动画页面"""
        pass
    
    def _show_login(self) -> None:
        """显示登录页面（游客模式 + 用户登录）"""
        pass
    
    def _show_main(self) -> None:
        """显示主界面（加密/解密选择）"""
        pass
    
    def _show_encrypt_view(self, prefill_data: dict = None) -> None:
        """显示加密操作页面
        
        Args:
            prefill_data: 预填充的表单数据（来自AI识别结果）
        """
        pass
    
    def _show_decrypt_view(self) -> None:
        """显示解密操作页面"""
        pass
    
    def _show_profile(self) -> None:
        """显示个人中心页面"""
        pass

    # ==================== 加密流程回调 ====================
    
    def on_file_uploaded(self, file_path: str) -> None:
        """文件上传完成回调"""
        pass
    
    def on_text_input(self, text: str) -> None:
        """文本输入回调"""
        pass
    
    def on_image_uploaded(self, image_path: str) -> None:
        """图片上传完成回调（预留OCR接口）"""
        pass
    
    def on_trigger_ai_extract(self, raw_text: str) -> None:
        """触发AI字段提取（异步，不阻塞UI）"""
        pass
    
    def on_ai_extract_complete(self, result: dict) -> None:
        """AI提取完成回调（主线程执行，更新UI）"""
        pass
    
    def on_save_record(self, record: dict) -> str:
        """保存档案记录"""
        pass
    
    def on_encode_dna(self, record: dict, encryption_key: str) -> None:
        """执行DNA编码（异步任务）"""
        pass
    
    def on_encode_complete(self, task_id: str, result: dict) -> None:
        """DNA编码完成回调"""
        pass

    # ==================== 解密流程回调 ====================
    
    def on_decode_dna(self, dna_sequence: str, decryption_key: str) -> None:
        """执行DNA解码（异步任务）"""
        pass
    
    def on_decode_complete(self, task_id: str, result: dict) -> None:
        """DNA解码完成回调"""
        pass
    
    def on_export_result(self, result_data: dict, format: str) -> str:
        """导出解密结果"""
        pass

    # ==================== 任务管理 ====================
    
    def create_task(self, task_type: str, source_file: str = None) -> str:
        """创建新任务，返回任务ID"""
        pass
    
    def update_task_progress(self, task_id: str, progress: float, message: str, status: TaskStatus = None) -> None:
        """更新任务进度"""
        pass
    
    def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        pass
    
    def get_task_list(self) -> list[TaskInfo]:
        """获取所有任务列表"""
        pass

    # ==================== UI更新方法（被其他模块/线程调用）====================
    
    def show_progress(self, percent: int, message: str) -> None:
        """更新进度条（线程安全）"""
        pass
    
    def show_result(self, result_data: dict) -> None:
        """显示结果（填充表单或展示解码结果）"""
        pass
    
    def show_error(self, error_msg: str) -> None:
        """显示错误提示"""
        pass
    
    def show_success(self, success_msg: str) -> None:
        """显示成功提示"""
        pass
    
    def show_confirmation(self, title: str, content: str, on_confirm: Callable = None, on_cancel: Callable = None) -> None:
        """显示确认对话框"""
        pass
```

#### 3.1.3 页面组件结构

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

### 3.2 数据库与文件处理模块 (`data_store.py`)

#### 3.2.1 模块职责

| 职责编号 | 职责描述 | 优先级 |
|---------|---------|--------|
| DS-01 | 搭建本地SQLite数据库 | P0 |
| DS-02 | 接收界面传入的图片/文档/文本，做数据预处理 | P0 |
| DS-03 | 存储原始文件、DNA编码结果、解码记录 | P0 |
| DS-04 | 对外提供读写数据库的接口 | P0 |
| DS-05 | 实现相似度检索功能（纠错用） | P1 |
| DS-06 | 实现数据备份与恢复 | P2 |

#### 3.2.2 类定义

```python
# modules/data_store.py

import sqlite3
import os
import json
import shutil
from datetime import datetime
from typing import Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum


class DocumentFormat(Enum):
    """支持的文档格式"""
    TXT = "txt"
    DOCX = "docx"
    PDF = "pdf"
    JPG = "jpg"
    JPEG = "jpeg"
    PNG = "png"


@dataclass
class DiseaseTerm:
    """病症词条数据类"""
    id: int
    chinese_name: str           # 中文名称
    english_name: str           # 英文名称
    category: str               # 分类（儿科/内科/外科/...）


@dataclass
class ArchiveRecord:
    """档案记录数据类"""
    id: Optional[int] = None    # 数据库自增ID
    record_id: str = ""         # 业务唯一标识（如：ARCHIVE_20261013_001）
    
    # === 物理存储（固定信息）===
    archive_number: str = ""    # 档案编号
    name: str = ""              # 姓名
    gender: str = ""            # 性别
    birth_date: str = ""        # 出生日期
    id_number: str = ""         # 证件号码
    hukou_address: str = ""     # 户籍地址
    residence_address: str = "" # 常住地址
    organization: str = ""      # 建档机构
    create_date: str = ""       # 建档日期
    phone: str = ""             # 联系电话
    nation: str = ""            # 民族
    abo_blood_type: str = ""    # ABO血型
    rh_blood_type: str = ""     # Rh血型
    father_name: str = ""       # 父亲姓名
    father_phone: str = ""      # 父亲联系电话
    mother_name: str = ""       # 母亲姓名
    mother_phone: str = ""      # 母亲联系电话
    gestational_weeks: str = "" # 出生孕周
    birth_weight: str = ""      # 出生体重
    birth_length: str = ""      # 出生身长
    delivery_org: str = ""      # 分娩机构
    apgar_1min: str = ""        # Apgar评分(1分钟)
    apgar_5min: str = ""        # Apgar评分(5分钟)
    
    # === 反复存储（随访/动态信息）===
    follow_up_records: str = "" # JSON格式的随访记录列表
    
    # === 病症记录 ===
    disease_records: str = ""   # JSON格式的病症记录
    
    # === 元数据 ===
    created_at: str = ""        # 记录创建时间
    updated_at: str = ""        # 最后更新时间
    source: str = ""            # 数据来源（手动填写/AI识别/导入）


@dataclass
class DNASequenceRecord:
    """DNA序列记录数据类"""
    id: Optional[int] = None
    record_id: str = ""         # 关联的档案记录ID
    dna_sequence: str = ""      # DNA序列
    encryption_key: str = ""    # 加密密钥（哈希存储，不存明文）
    cg_content: float = 0.0     # GC含量
    thermal_stability: float = 0.0  # 热稳定性系数
    padded_zeros: int = 0       # 填充零位数
    sequence_length: int = 0    # 序列长度
    original_text: str = ""     # 编码前的原始文本（英文病症）
    encoded_at: str = ""        # 编码时间
    is_valid: bool = True       # 序列是否有效


@dataclass
class DecodeRecord:
    """解码记录数据类"""
    id: Optional[int] = None
    dna_record_id: int = 0     # 关联的DNA序列记录ID
    decoded_text: str = ""      # 解码后的文本
    corrected_text: str = ""    # 纠错后的文本
    confidence: float = 0.0     # 置信度
    error_rate: float = 0.0     # 错误率
    correction_log: str = ""    # 纠错日志（JSON）
    decoded_at: str = ""        # 解码时间


class DataStore:
    """
    数据存储与文件处理模块
    
    职责：
    - SQLite数据库的初始化与管理
    - 医疗档案数据的CRUD操作
    - DNA序列的存储与检索
    - 文档文件的解析与临时存储
    - 相似度查询（纠错支持）
    """

    def __init__(self, db_path: str = None, data_dir: str = None):
        """初始化数据存储模块"""
        pass

    # ==================== 数据库初始化 ====================
    
    def init_database(self) -> None:
        """初始化数据库（建表、建索引、插入基础数据）"""
        pass
    
    def init_disease_terms(self) -> int:
        """初始化病症词典数据（236条预设词条）"""
        pass
    
    def get_connection(self) -> sqlite3.Connection:
        """获取数据库连接（带行工厂，返回dict）"""
        pass

    # ==================== 病典查询操作 ====================
    
    def search_disease(self, keyword: str, limit: int = 10) -> list[DiseaseTerm]:
        """搜索病症词条（支持中英文模糊搜索）"""
        pass
    
    def get_disease_by_chinese(self, chinese_name: str) -> Optional[DiseaseTerm]:
        """根据中文名称获取病症词条"""
        pass
    
    def get_disease_by_english(self, english_name: str) -> Optional[DiseaseTerm]:
        """根据英文名称获取病症词条"""
        pass
    
    def get_all_categories(self) -> list[str]:
        """获取所有病症分类"""
        pass
    
    def add_disease_term(self, chinese_name: str, english_name: str, category: str) -> int:
        """添加新病症词条"""
        pass

    # ==================== 文件解析操作 ====================
    
    def parse_document(self, file_path: str) -> str:
        """
        解析文档文件，提取纯文本
        支持: .txt / .docx / .pdf
        """
        pass
    
    def save_upload_file(self, file_content: bytes, filename: str) -> str:
        """保存上传的文件到临时目录"""
        pass
    
    def cleanup_temp_files(self, older_than_hours: int = 24) -> int:
        """清理过期的临时文件"""
        pass

    # ==================== 档案记录 CRUD ====================
    
    def save_record(self, record: ArchiveRecord) -> str:
        """保存/更新档案记录，返回record_id"""
        pass
    
    def load_record(self, record_id: str) -> Optional[ArchiveRecord]:
        """加载档案记录"""
        pass
    
    def delete_record(self, record_id: str) -> bool:
        """删除档案记录（软删除）"""
        pass
    
    def list_records(self, offset: int = 0, limit: int = 20, keyword: str = None) -> tuple[list[ArchiveRecord], int]:
        """列出档案记录（分页），返回(列表, 总数)"""
        pass
    
    def update_record(self, record: ArchiveRecord) -> bool:
        """更新档案记录"""
        pass

    # ==================== DNA 序列存储 ====================
    
    def save_dna_sequence(self, dna_record: DNASequenceRecord) -> int:
        """保存DNA编码结果，返回新记录ID"""
        pass
    
    def load_dna_sequence(self, record_id: str) -> Optional[DNASequenceRecord]:
        """加载DNA序列记录"""
        pass
    
    def load_dna_by_sequence(self, dna_sequence: str) -> Optional[DNASequenceRecord]:
        """根据DNA序列查找记录（模糊匹配）"""
        pass
    
    def list_dna_sequences(self, offset: int = 0, limit: int = 20) -> list[DNASequenceRecord]:
        """列出DNA序列记录"""
        pass
    
    def invalidate_dna_sequence(self, dna_id: int) -> bool:
        """标记DNA序列为无效"""
        pass

    # ==================== 解码记录 ====================
    
    def save_decode_record(self, decode_record: DecodeRecord) -> int:
        """保存解码记录"""
        pass
    
    def list_decode_records(self, dna_record_id: int = None, limit: int = 20) -> list[DecodeRecord]:
        """列出解码记录"""
        pass

    # ==================== 相似度查询（纠错支持）====================
    
    def find_similar_records(self, text: str, threshold: float = 0.7, limit: int = 5) -> list[tuple[ArchiveRecord, float]]:
        """查找相似的档案记录（用于纠错时的比对）"""
        pass
    
    def find_similar_dna_sequences(self, dna_sequence: str, threshold: float = 0.8, limit: int = 5) -> list:
        """查找相似的DNA序列（用于检测数据损坏）"""
        pass

    # ==================== 数据导出 ====================
    
    def export_record_to_json(self, record_id: str) -> str:
        """导出档案记录为JSON文件，返回文件路径"""
        pass
    
    def export_record_to_docx(self, record_id: str, template_path: str = None) -> str:
        """导出档案记录为DOCX文件，返回文件路径"""
        pass
    
    def backup_database(self, backup_dir: str = None) -> str:
        """备份数据库文件，返回备份路径"""
        pass
    
    def restore_database(self, backup_path: str) -> bool:
        """从备份恢复数据库"""
        pass

    # ==================== 统计查询 ====================
    
    def get_statistics(self) -> dict:
        """获取数据库统计信息"""
        pass
    
    def close(self) -> None:
        """关闭数据库连接"""
        pass
```

---

### 3.3 AI交互模块 (`ollama_api.py`)

#### 3.3.1 模块职责

| 职责编号 | 职责描述 | 优先级 |
|---------|---------|--------|
| AI-01 | 连接本地Ollama服务 | P0 |
| AI-02 | 调用指定模型执行文档字段提取 | P0 |
| AI-03 | 流式返回AI生成内容，支持进度回调 | P0 |
| AI-04 | 封装统一接口，方便后续替换模型 | P0 |
| AI-05 | 支持智能纠错推理（解码后） | P1 |
| AI-06 | 支持OCR图片文字识别（预留） | P2 |

#### 3.3.2 类定义

```python
# modules/ollama_api.py

import json
import urllib.request
import urllib.error
from typing import Generator, Callable, Optional, Any
from dataclasses import dataclass
from enum import Enum


class ModelType(Enum):
    """支持的AI模型类型"""
    FIELD_EXTRACTOR = "qwen2.5:7b-instruct"
    ERROR_CORRECTOR = "qwen2.5:14b-instruct"
    GENERAL_CHAT = "qwen2.5:7b-chat"
    CUSTOM = "custom"


@dataclass
class AIResponse:
    """AI响应数据类"""
    success: bool
    data: Optional[Any] = None
    error_message: str = ""
    tokens_used: int = 0
    duration_seconds: float = 0.0


class OllamaClient:
    """
    Ollama AI 交互模块
    """

    def __init__(self, model_name: str = None, base_url: str = None, timeout: int = 300, max_retries: int = 2):
        """初始化Ollama客户端"""
        pass

    def test_connection(self) -> tuple[bool, str]:
        """测试Ollama服务是否可用"""
        pass
    
    def extract_fields(self, document_text: str, on_progress: Callable = None, fields_hint: list = None) -> AIResponse:
        """
        从文档文本中提取结构化字段（流式调用）
        
        Returns:
            AIResponse.data 为提取的字段字典
        """
        pass
    
    def correct_errors(self, corrupted_text: str, reference_texts: list, on_progress: Callable = None) -> AIResponse:
        """
        AI辅助纠错（解码后使用）
        
        Returns:
            AIResponse.data 包含 corrected_text, corrections, confidence
        """
        pass
    
    def chat(self, prompt: str, system_prompt: str = None, temperature: float = 0.7) -> AIResponse:
        """通用对话接口（预留扩展）"""
        pass
```

---

### 3.4 DNA编解码核心模块 (`dna_codec.py`)

#### 3.4.1 类定义

```python
# modules/dna_codec.py

import subprocess
import os
import re
import hashlib
from dataclasses import dataclass
from typing import Optional
from enum import Enum


class CodecStatus(Enum):
    SUCCESS = "success"
    ENCODER_ERROR = "encoder_error"
    DECODER_ERROR = "decoder_error"
    TIMEOUT = "timeout"
    INVALID_INPUT = "invalid_input"


@dataclass
class EncodeResult:
    status: CodecStatus
    dna_sequence: str = ""
    cg_content: float = 0.0
    thermal_stability: float = 0.0
    padded_zeros: int = 0
    sequence_length: int = 0
    ciphertext: str = ""
    error_message: str = ""


@dataclass
class DecodeResult:
    status: CodecStatus
    original_text: str = ""
    error_message: str = ""


class DNACodec:
    """DNA编解码模块 - 封装C++编解码器的调用"""

    def __init__(self, encoder_path: str = None, decoder_path: str = None, timeout: int = 60):
        """初始化编解码器"""
        pass

    @staticmethod
    def generate_key(identity_info: dict) -> str:
        """
        基于患者身份信息生成加密密钥
        identity_info 至少包含: {"name": str, "birth_date": str}
        返回16字符密钥
        """
        pass
    
    def encode(self, plaintext: str, key: str) -> EncodeResult:
        """执行DNA编码"""
        pass
    
    def decode(self, dna_sequence: str, key: str) -> DecodeResult:
        """执行DNA解码"""
        pass
    
    @staticmethod
    def validate_dna_sequence(sequence: str) -> tuple[bool, str]:
        """验证DNA序列合法性"""
        pass
```

---

### 3.5 核心算法模块 (`core/`)

#### 3.5.1 模块概述

`core/` 目录存放**纯逻辑代码**，不依赖任何外部库。方便单独单元测试。

#### 3.5.2 字段定义常量 (`field_extractor.py`)

```python
# core/field_extractor.py

# 物理存储字段（固定信息，23个）
PHYSICAL_FIELDS = [
    "档案编号", "姓名", "性别", "出生日期", "证件号码",
    "户籍地址", "常住地址", "建档机构", "建档日期", "联系电话",
    "民族", "ABO血型", "Rh血型",
    "父亲姓名", "父亲联系电话", "母亲姓名", "母亲联系电话",
    "出生孕周", "出生体重", "出生身长", "分娩机构",
    "Apgar_1分钟", "Apgar_5分钟"
]

# 病症记录字段（7个）
DISEASE_FIELDS = [
    "苯丙酮尿症", "先天性甲状腺功能减低症", "听力筛查",
    "过敏史", "先天异常", "既往住院史", "家族遗传病史"
]

# 反复存储字段（动态信息，3个）
REPEATED_FIELDS = ["随访日期", "当前体重", "体温"]

ALL_FIELDS = PHYSICAL_FIELDS + DISEASE_FIELDS + REPEATED_FIELDS
```

---

## 4. 数据库设计

### 4.1 ER图

```
┌──────────────────┐       ┌──────────────────┐       ┌──────────────────┐
│  archive_records │       │  dna_sequences   │       │  decode_records  │
│------------------│       │------------------│       │------------------│
│ PK record_id     │───┐   │ PK id            │       │ PK id            │
│    name          │   │   │ FK record_id     │◀──┐   │ FK dna_record_id │──┘
│    gender        │   │   │    dna_sequence  │   │   │    decoded_text  │
│    ...           │   └──>│    cg_content    │   └──>│    confidence    │
└──────────────────┘       └──────────────────┘       └──────────────────┘
         │
         ▼
┌──────────────────┐
│  disease_terms   │
│------------------│
│ PK id            │
│    chinese_name  │
│    english_name  │
│    category      │
└──────────────────┘
```

### 4.2 表结构详细定义

#### 4.2.1 `disease_terms` 病症词典表

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | 自增主键 |
| chinese_name | TEXT | NOT NULL | 中文病症名称 |
| english_name | TEXT | NOT NULL | 英文名称 |
| category | TEXT | DEFAULT '通用' | 分类 |

**初始数据**：236条（8大分类）

---

#### 4.2.2 `archive_records` 档案记录表

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | INTEGER | PK AUTOINCREMENT | 主键 |
| record_id | TEXT | NOT NULL UNIQUE | 业务唯一标识 |
| name | TEXT | NOT NULL | 姓名 |
| gender | TEXT | DEFAULT '' | 性别 |
| birth_date | TEXT | DEFAULT '' | 出生日期 |
| ... (其他22个字段) | ... | ... | ... |
| follow_up_records | TEXT | DEFAULT '[]' | 随访记录(JSON) |
| disease_records | TEXT | DEFAULT '{}' | 病症记录(JSON) |
| source | TEXT | DEFAULT 'manual' | 来源 |
| created_at | TEXT | NOT NULL | 创建时间 |
| updated_at | TEXT | NOT NULL | 更新时间 |
| is_deleted | INTEGER | DEFAULT 0 | 软删除 |

---

#### 4.2.3 `dna_sequences` DNA序列表

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | INTEGER | PK AUTOINCREMENT | 主键 |
| record_id | TEXT | NOT NULL | 关联档案ID |
| dna_sequence | TEXT | NOT NULL | DNA序列 |
| key_hash | TEXT | NOT NULL | 密钥哈希 |
| cg_content | REAL | DEFAULT 0 | GC含量 |
| thermal_stability | REAL | DEFAULT 0 | 热稳定性 |
| original_text | TEXT | DEFAULT '' | 原始文本 |
| encoded_at | TEXT | NOT NULL | 编码时间 |
| is_valid | INTEGER | DEFAULT 1 | 是否有效 |

---

#### 4.2.4 `decode_records` 解码记录表

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | INTEGER | PK AUTOINCREMENT | 主键 |
| dna_record_id | INTEGER | NOT NULL | 关联DNA ID |
| decoded_text | TEXT | NOT NULL | 解码文本 |
| corrected_text | TEXT | DEFAULT '' | 纠错后文本 |
| confidence | REAL | DEFAULT 0 | 置信度 |
| error_rate | REAL | DEFAULT 0 | 错误率 |
| correction_log | TEXT | DEFAULT '{}' | 纠错日志 |
| decoded_at | TEXT | NOT NULL | 解码时间 |

---

## 5. 接口契约

### 5.1 模块间调用关系

```
ui_interface 调用:
  ├── data_store.save_record(record) → str (record_id)
  ├── data_store.parse_document(file_path) → str (纯文本)
  ├── data_store.search_disease(keyword) → list[DiseaseTerm]
  ├── ollama_api.extract_fields(text, on_progress) → AIResponse
  ├── ollama_api.correct_errors(corrupted, references) → AIResponse
  ├── dna_codec.encode(plaintext, key) → EncodeResult
  ├── dna_codec.decode(dna_sequence, key) → DecodeResult
  └── dna_codec.generate_key(identity_info) → str
```

### 5.2 接口稳定性规则

| 规则 | 描述 |
|------|------|
| IF-01 | 公共方法签名不可随意改动 |
| IF-02 | 新增方法可以随时加 |
| IF-03 | 返回值类型必须严格符合约定 |
| IF-04 | 异常类型必须显式声明 |
| IF-05 | 所有IO方法必须有超时参数 |

---

## 6. 开发分工与任务分配

### 6.1 团队成员与职责

| 角色 | 负责模块 | 主要职责 |
|------|---------|---------|
| **PM/核心算法（你）** | `core/`, `dna_codec.py`, `error_corrector.py`, `config.py`, `main.py` | 项目管理、核心算法、模块整合、接口评审 |
| **前端开发（同学A）** | `ui_interface.py` | Flet界面、交互逻辑、任务栏、页面导航 |
| **数据库开发（同学B）** | `data_store.py` | 表结构设计、CRUD、文件解析、相似度查询 |
| **AI工程师（同学C）** | `ollama_api.py` | Ollama集成、Prompt工程、字段提取、智能纠错 |

### 6.2 开发阶段规划

#### 第一阶段：接口契约确认（1天）⭐ 最重要！

**参与者**：全体4人

**产出物**：
- [ ] 确认本文档中的所有接口定义
- [ ] 搭建项目骨架（目录结构、空文件）
- [ ] 编写 `config.py` 和 `requirements.txt`
- [ ] 初始化 Git 仓库

---

#### 第二阶段：并行开发（5-7天）

| 开发者 | 任务 | 交付物 |
|--------|------|--------|
| **同学B** | DataStore全实现 + 测试 | `data_store.py` |
| **同学C** | OllamaClient全实现 + 测试 | `ollama_api.py` |
| **同学A** | GUI框架 + 桩函数 | `ui_interface.py` |
| **你** | config + core + dna_codec + 整合 | 多个模块 |

---

#### 第三阶段：集成联调（3-4天）

- Day 1-2: 替换桩函数，跑通加密全流程
- Day 3: 跑通解密全流程
- Day 4: Bug修复 + 边界处理

### 6.3 Git分支策略

```
main
  └── develop
        ├── feature/ui-interface (同学A)
        ├── feature/data-store (同学B)
        ├── feature/ollama-api (同学C)
        ├── feature/dna-codec (你)
        └── feature/core-modules (你)
```

---

## 7. 非功能需求

### 7.1 性能需求

| 指标 | 要求 |
|------|------|
| AI识别响应 | < 30秒 |
| DNA编解码 | < 5秒 |
| UI响应 | < 100ms |
| 并发任务数 | ≥ 3个 |

### 7.2 安全需求

| 需求 | 实现方式 |
|------|---------|
| 密钥安全 | 存储SHA-256哈希，不存明文 |
| 数据隐私 | 本地SQLite，不上云 |
| AI隐私 | Ollama本地部署 |
| 临时文件 | 退出时清理 |

### 7.3 兼容性

| 项目 | 要求 |
|------|------|
| OS | Windows 10/11 |
| Python | >= 3.8 |
| 分辨率 | 最低 1280×720 |

---

## 8. 附录

### 8.1 术语表

| 术语 | 解释 |
|------|------|
| DNA编码 | 二进制→DNA碱基(A/T/C/G)映射 |
| GC含量 | G和C所占比例，影响稳定性 |
| 热稳定性 | DNA耐热能力 |
| 人工碱基 | X/Y标记，标识填充区域 |
| XOR加密 | 异或加密算法 |
| 冷归档 | 长期低频访问存储 |

### 8.2 修改历史

| 日期 | 版本 | 修改内容 | 修改人 |
|------|------|---------|--------|
| 2026-10-13 | v1.0 | 初稿，完整架构设计与接口定义 | PM |

---

*本文档是团队协作的开发基准，所有接口变更需全体确认后更新本文档。*
