# 载荷 JSON 规范 v3（DNA 编码输入契约）

> 归属：算法模块　|　实现：`src/core/payload.py`　|　上级依据：`docs/main/api_contract.md` §8.2/§8.3、`数据库开发书/00_数据库开发书_最终版_v4.0.md` §6/§7.5
> 本文定义「交给 C++ 编码器的那串东西」长什么样。改结构必须升版本号，并同步契约。

---

## 1. 一句话

档案 → **纯 ASCII 的扁平 JSON** → C++ 编码器。解码后原样还原。

```json
{"v":"v3","rid":"ARCHIVE_20261117_001","id":{"dob":"2020-01-01","g":"male","nm":"\u5f20\u4e09"},"ans":{"disease_classification.disease_category":["chapter_iii"],"symptoms.chief_complaint":["fever","cough"]}}
```

## 2. 字段表

| 键 | 必填 | 类型 | 说明 |
|---|---|---|---|
| `v` | ✅ | str | 固定 `"v3"`。解码必须校验，不匹配直接报错，不做兼容猜测 |
| `rid` | ✅ | str | `archive_records.record_id`，纯 ASCII |
| `id` | 否 | obj | 身份信息：`nm` 姓名（可中文）、`g` 性别、`dob` 出生日期。空值不写 |
| `ans` | ✅ | obj | 答案：key 为 `<section_key>.<field_key>`，value 为 `option_key` 数组 |

**ans 规则**（与开发书 §7.5 一致）：

- key = `section_key.field_key`，例 `symptoms.chief_complaint`
- value 恒为数组，**单选也放数组**（前端、数据库、算法三边结构统一）
- 数组顺序即 `answers.seq`，同一空多选不得重排
- **空值不出现**：没填的空不写 key、不写 `null`、不写 `[]`，保证同一份档案载荷稳定
- `option_key` 只允许小写英文 + 数字 + 下划线，遵循开发书 §6：`icd_e11_900` / `icd9_47_0900` / `wst_cv02_10_101_1` / `family__hypertension` / `chapter_iv`

## 3. 为什么必须纯 ASCII

`DNA_encoder.cpp` 的 `to_num()` 把每个字符按 **8 位 ASCII** 展开。传入 UTF-8/GBK 中文会被按字节拆成无意义比特，解码后无法还原。

解决办法是序列化时 `ensure_ascii=True`：中文变成 `\u5f20` 这样的**转义序列**，本身就是 ASCII 字符，信息无损、可逆。

> 不要用拼音替代中文：多音字有歧义（曾 zeng/ceng、仇 qiu/chou），且丢失字形。转义长度代价 1 汉字 = 6 字节，可接受。

## 4. 序列化必须稳定

固定 `ensure_ascii=True` + `sort_keys=True` + `separators=(",", ":")`，同一份数据永远得到同一串字节，便于比对与排查。

**注意区分**：DNA 序列本身因 `srand(time(0))` 不可复现，两次编码结果不同属正常。可比对的是「载荷文本」与「解码还原结果」，不是 DNA 序列。

## 5. 实测结论（2026-11-26）

| 用例 | 结果 |
|---|---|
| 短载荷 119 字符 | 编码 476 碱基（= 119×8÷2，精确）→ 解码 119 字符，完全相等 |
| 完整载荷 324 字符（4 个空 + 中文姓名） | 编码 1316 碱基（1296 + 20 个 GC 修复片段）→ 解码 324 字符，完全相等 |

## 6. 已知坑

1. **`DNA_decoder.cpp` 末尾的 `system("pause")` 必须删掉重编**。它不只是往 stdout 追加脏行，实测还会**截断输出**：一次长载荷往返中出现过还原只剩 265/324 字符的情况。删掉后重编即正常。
2. 解码器是 **stdin 两行交互**（序列 + 密钥），不是命令行参数。
3. 密钥回显（`Ciphertext:` 行）不是原文，别拿它当解码密钥。

## 7. 与契约的关系

- 契约 §8.2 的 `export_payload(record_id)` 返回结构 = 本文 §2 的 `ans` 字典
- 本文补的是契约未定义的：**外层包装（v/rid/id）、序列化参数、ASCII 约束的落地方式、校验规则**
- 若后续改结构：`v` 升 `v4`，契约 §8.3 同步改，并在本文追加变更记录
