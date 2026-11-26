# C++ 编解码器调用协议（桌面直调版）

> 适用：待实现的 `dna_codec.py`。本项目是 **Flet 桌面软件**——**同进程 `subprocess` 直调 exe**，不经 HTTP / Flask / 浏览器，不开端口、不起服务进程。
> 依据：`DNA_encoder.cpp` / `DNA_decoder.cpp` 源码逐行核对 + 实测编译（2026-11-17，g++ 14.2.0）。
> 配套：`../01_需求与总体设计/api_contract.md` §8（`export_payload()` 与载荷版本）。

---

## ⚠️ 输入限制：纯 ASCII

**C++ 编解码器只能处理纯 ASCII 文本。** 输入文本中如果包含中文或其他 Unicode 字符，会按字节截断导致乱码。

**调用方责任**：
- 编码前：确保输入文本为纯 ASCII。如果原始数据包含中文，必须先转义（如 `\uXXXX`）或只传 ASCII 安全的键（如 `option_key`）。
- 解码后：得到的是编码前的 ASCII 文本，如需展示中文，由上层做反向映射。

**X/Y 字符说明**：
- X/Y 是**编码过程产生的辅助字符**，不是用户数据的一部分
- X：标记补 0 位置（当总位数补到 10 的倍数时需要额外比特时插入）
- Y：标记小写字母（小写字母前插入 Y 占位）
- 它们保证解码时能精确还原比特流，最终解码结果中不包含 X/Y

---

## 0. 一句话链路

```
Flet 页面事件 → DataStore.export_payload() → dna_codec.encode()
   → subprocess.run([dna_encoder.exe, 英文载荷, 密钥], capture_output=True)
   → 解析 stdout → 存 dna_sequences / 回填界面

解码：dna_codec.decode(dna_sequence, key)
   → subprocess.run([dna_decoder.exe], input="<序列>\n<密钥>\n", ...)
   → 解析 stdout 中的 Decryption Result → 回填界面
```

---

## 1. 编译与产物位置

**编译状态**：两个源码均可直接编译。`DNA_encoder.cpp` 早期版本曾因 `stable_standard()` 使用 `min({a,b,c})` 却未包含 `<algorithm>`，在 g++ 下报 `no matching function for call to 'min(<brace-enclosed initializer list>)'`；该头文件已在源码头部补齐。若换用其他工具链仍报同类错误，确认包含：

```cpp
#include <algorithm>
```

在本目录下执行：

```bash
g++ -std=c++17 -O2 DNA_encoder.cpp -o dna_encoder.exe
g++ -std=c++17 -O2 DNA_decoder.cpp -o dna_decoder.exe
```

**产物位置约定**：把两个 exe 放到**仓库根目录的 `bin/`**（新建），并提交 GitHub（exe 是二进制，`git` 里只放成品不折腾）；编译好后再在微信群里发一份，免得别人自己编译。`dna_codec.py`（位于 `src/` 下）用 `Path(__file__).resolve().parent.parent / "bin"` 定位。**不要依赖当前工作目录**，否则从别的目录启动主程序就找不到 exe。

Windows 桌面软件建议加 `creationflags=subprocess.CREATE_NO_WINDOW`，避免每次编码闪一个黑色控制台窗口。

---

## 2. 编码器 `dna_encoder.exe <argv1> <argv2>`

| 参数 | 含义 | 来源 | 要求 |
|---|---|---|---|
| `argv[1]` `English` | **待编码的档案载荷文本** | `export_payload()` 的序列化结果 | **必须纯 ASCII**（见 §4） |
| `argv[2]` `mingwen` | **XOR 密钥字符串**（源码变量名有误导，它其实是密钥，不是明文） | 密钥派生规则（SHA-256(姓名+出生日期) 取前 16 位等） | 纯 ASCII |

- 缺参数：stdout 输出 `Error!!`，退出码 **1**。
- 内部流程：`to_num()` 每字符展开 8 位 ASCII 二进制（奇数长度补一个 `0`，`fix=1`）→ `encryption()` 与密钥逐位 XOR（密钥循环使用）→ `make_DNA()` 按 2bit 映射 `11=A / 01=T / 10=C / 00=G` → 约束修复循环。
- 约束循环：GC 含量 40–60%、热稳定性系数达标；不达标时用 `add()` 随机插入 `CG` 或 `AT` 片段，以 `X` 开头 `Y` 结尾定界，`joint()` 随机决定插在序列头还是尾。长度超过 `MAX_length=10000` 时输出 `Cannot realize the sequence` 并 `return 0`——**此时没有结果行，必须判为失败**。

**stdout 格式（5 个字段，逐行）**：

```
===---------------Content Analysis---------------===
Ciphertext: <argv[2]>
CG Content: <double>
Base Thermal Stability Coefficient: <double>
Final DNA Sequence: <ATCGXY 字符串>
Number of Padded Zeros: <0 或 1>
```

解析时逐行按 `: ` 切一次取 `Final DNA Sequence`；**不要把 `Ciphertext` 当密文用**（它就是密钥回显）。输出全为英文与数字，ASCII 安全。

```python
import re, subprocess
from pathlib import Path

EXE_DIR = Path(__file__).resolve().parent.parent / "bin"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

def encode(payload_ascii: str, key: str) -> dict:
    proc = subprocess.run(
        [str(EXE_DIR / "dna_encoder.exe"), payload_ascii, key],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=10, creationflags=NO_WINDOW,
    )
    out = proc.stdout
    if proc.returncode != 0:
        raise RuntimeError(f"编码器失败: {out.strip()} {proc.stderr.strip()}")
    if "Cannot realize the sequence" in out:
        raise RuntimeError("序列约束无法满足（长度超限或修复不收敛）")
    m = re.search(r"^Final DNA Sequence:\s*(\S+)", out, re.M)
    if not m:
        raise RuntimeError(f"编码器未返回序列: {out[:200]}")
    seq = m.group(1)
    if set(seq) - set("ATCGXY"):
        raise RuntimeError(f"序列含非法字符: {set(seq) - set('ATCGXY')}")
    return {
        "sequence": seq,
        "gc": float(re.search(r"^CG Content:\s*([\d.]+)", out, re.M).group(1)),
        "stability": float(re.search(r"^Base Thermal Stability Coefficient:\s*([\d.]+)", out, re.M).group(1)),
        "padded": int(re.search(r"^Number of Padded Zeros:\s*(\d+)", out, re.M).group(1)),
    }
```

---

## 3. 解码器 `dna_decoder.exe`（**stdin 交互，不是 argv**）

⚠️ 最容易踩的坑：解码器 `main()` 用两次 `getline(cin, ...)` 从**标准输入**读两行，不是命令行参数。

| 行 | 内容 |
|---|---|
| 第 1 行 | DNA 序列（含 X/Y 定界） |
| 第 2 行 | 密钥（必须与编码时 `argv[2]` 相同） |

**stdout**：

```
Please enter the ciphertext: Please enter the key: ========--------------[ Decryption Result ]--------------=======
<还原出的明文>
```

解析：找到含 `[ Decryption Result ]` 的那一行，取**下一行**作为明文。

✅ **已修复（2026-11-26）**：`DNA_decoder.cpp` 末尾的 `system("pause")` 已删除并重编译，`bin/dna_decoder.exe` 为新版。实测 stdout 只剩 2 行（第 1 行含 `Decryption Result` 与两句 `Please enter...` 提示，第 2 行为结果正文），不再有 `Press any key to continue...` 的 GBK 乱码行，长载荷也不会被截断。

> 历史坑位留档：该行在 subprocess 下曾导致 ①stdout 追加 GBK 字节使 `encoding="utf-8"` 抛 `UnicodeDecodeError`、`stdout=None`；②偶发截断长结果（实测 324 字符只还原 265）。写 `dna_codec.py` 时仍建议保留 `timeout` + `errors="replace"`，只按结果行解析，不要依赖行内固定位置。

> 实测记录：`HELLO_DNA_TEST` / `KEY123` → 序列长 56、GC 0.5、字符集仅 ATCG → 按下方 `decode()` 解析还原为 `HELLO_DNA_TEST`，往返一致。因 `srand(time(0))`，同一输入每次序列不同，验收只断言结构不变量与往返一致，不比对固定序列。

```python
def decode(sequence: str, key: str) -> str:
    proc = subprocess.run(
        [str(EXE_DIR / "dna_decoder.exe")],
        input=f"{sequence}\n{key}\n",
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=10, creationflags=NO_WINDOW,
    )
    lines = proc.stdout.splitlines()
    for i, line in enumerate(lines):
        if "[ Decryption Result ]" in line:
            return lines[i + 1] if i + 1 < len(lines) else ""
    raise RuntimeError(f"解码失败: {proc.stdout[:200]} {proc.stderr[:200]}")
```

---

## 4. 为什么不能传中文

`to_num()` / `key_to_num()` 都是 `int ascii = c;` 再按 8 位右移展开。Windows 下 `char` 有符号，中文 UTF-8 的多字节会被当成负数，展开出错，**编码/解码不可逆**。

载荷一律用 `export_payload()` 产出的 ASCII `option_key` 拼串；不要传中文标签，不要把含中文的 JSON 值塞进去。这也是契约 §8 强制 `option_key` 为 ASCII 的原因。

---

## 5. 不可复现性（重要）

`DNA_encoder.cpp` 的 `main()` 有 `srand(time(0))`，`add()` 与 `joint()` 用 `rand()` 决定插入的碱基与插入位置 → **同一份档案两次编码得到的 DNA 序列不同，这是设计行为，不是 bug**。

因此：

- 不要写「期望序列」的断言或固定黄金样例；
- 验收只断言**结构不变量**：字符集 ⊆ `{A,T,C,G,X,Y}`、`X…Y` 成对、GC ∈ [0.4, 0.6]、长度 ≤ 10000、`encode→decode` 往返还原与原文一致；
- 若将来要可复现（例如回归测试），给 C++ 加一个**可选种子参数**，不要直接去掉随机——随机修复本身就是约束算法的一部分。

---

## 6. 与其它模块的边界

- `dna_codec.py` **不直接连 SQLite**，档案数据由调用方传入；落库由 `DataStore` 负责（`dna_sequences` / `decode_records`）。
- 载荷结构为 `payload_version = "v3"`，见契约 §8.3。
- 全程不联网、不起服务；唯一的网络调用是 AI 模块 → 本机 Ollama `localhost:11434`（可选，与编解码无关，断网不影响）。
- `04/_历史遗留/` 里的 Flask 页面实现与旧版打包说明书**与本链路无关，勿参考**。

---

## 7. 自测清单（写完 `dna_codec.py` 逐条勾）

- [ ] 两个 exe 都能编译，放到仓库根 `bin/` 并提交 GitHub，从任意工作目录启动主程序都找得到
- [ ] `encode()` 能解析 5 个字段，非法字符断言生效
- [x] `decode()` 用 stdin 两行输入，能拿到明文；`system("pause")` 已从 C++ 删除并重编译（2026-11-26）
- [ ] 往返一致：`decode(encode(payload, key)["sequence"], key) == payload`
- [ ] 缺参数 / 约束不收敛 / exe 不存在 三种情况都有中文提示，界面不崩
- [ ] 断网且不开 Ollama 时仍能完成一次编解码
- [ ] 全程无浏览器窗口、无端口监听、无黑色控制台闪烁
