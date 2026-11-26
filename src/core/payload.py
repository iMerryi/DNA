"""载荷格式 v3（payload）—— DNA 编码的输入契约

职责：
    把「档案 + 答案」整理成一份 **纯 ASCII 的 JSON 文本**，交给 dna_codec.py 送进
    C++ 编码器；解码侧用 parse() 原样还原。

口径来源：
    - 结构：`02_数据库_开发书/00_数据库开发书_最终版_v4.0.md` §7.5
      「`section_key.field_key = option_key`，多值按 seq 拼数组；空值不出现」
    - 枚举项命名：同文件 §6（`icd_` / `icd9_` / `wst_` / `chapter_` 前缀，全小写）
    - 版本与 ASCII 约束：`docs/main/api_contract.md` §8.3

为什么必须是纯 ASCII：
    DNA_encoder.cpp 的 to_num() 对每个字符按「8 位 ASCII」展开，传入非 ASCII 字节
    （如 GBK/UTF-8 中文）会被按字节拆成无意义比特，解码后无法还原。
    因此序列化时必须 ensure_ascii=True —— 中文会被转成 \\uXXXX 转义（本身就是 ASCII
    字符），既不丢信息，也不破坏 C++ 的字节假设。

为什么不用拼音代替中文：
    拼音有多音字歧义（"曾" zeng/ceng、"仇" qiu/chou），且丢失原始字形；
    unicode 转义无损可逆，长度代价可接受（1 个汉字 = 6 个 ASCII 字节）。

结构（v3）：
    {
      "v": "v3",
      "rid": "ARCHIVE_20261117_001",
      "id": {"nm": "\\u5f20\\u4e09", "g": "male", "dob": "2020-01-01"},
      "ans": {
        "past_and_family_history.past_medical_history": ["anemia"],
        "symptoms.chief_complaint": ["fever", "cough"],
        "disease_classification.disease_category": ["chapter_iii"]
      }
    }

    ans 的 key   = `<section_key>.<field_key>`
    ans 的 value = `option_key` 数组（单选也放数组，统一结构；顺序即 seq）
    未填写的空直接省略，不写 null / 空数组。

稳定性：
    serialize() 固定 sort_keys=True + separators=(",", ":") + ensure_ascii=True，
    同一份数据得到同一串字节，便于比对与排查。
    注意：DNA 序列本身因 srand(time(0)) 不可复现，可比对的是载荷与还原结果，
    不是 DNA 序列。
"""

from __future__ import annotations

import json
import re
from typing import Any

PAYLOAD_VERSION = "v3"

# field_key / section_key / option_key：全小写英文 + 数字 + 下划线（§6 规则，如
# icd_e11_900、icd9_47_0900、wst_cv02_10_101_1、family__hypertension、chapter_iv）
_TOKEN_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_ANS_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}\.[a-z][a-z0-9_]{0,63}$")


class PayloadError(ValueError):
    """载荷构造或校验失败"""


# ==========================================
# 构造 / 序列化 / 解析
# ==========================================
def build_payload(
    record_id: str,
    answers: dict[str, list[str]],
    identity: dict[str, str] | None = None,
) -> dict:
    """组装载荷字典。

    record_id: archive_records.record_id，如 ARCHIVE_20261117_001
    answers:   {"section_key.field_key": [option_key, ...]}
               未填的空不传或传空列表都会被省略
    identity:  可选身份三件套 {"nm": 姓名, "g": "male"/"female", "dob": "YYYY-MM-DD"}
               允许中文，序列化时自动转 unicode 转义
    """
    if not record_id or not record_id.isascii():
        raise PayloadError(f"record_id 必须为非空 ASCII: {record_id!r}")

    clean: dict[str, list[str]] = {}
    for ans_key, values in (answers or {}).items():
        if not _ANS_KEY_RE.match(ans_key):
            raise PayloadError(
                f"答案 key 须为 `section_key.field_key`（全小写）: {ans_key!r}"
            )
        if values is None:
            continue
        items: list[str] = []
        for v in values:
            if not isinstance(v, str) or not _TOKEN_RE.match(v):
                raise PayloadError(
                    f"option_key 非法（须小写 ASCII，不要传中文标签）: {v!r} @ {ans_key}"
                )
            if v not in items:          # 同空去重，保留首次出现顺序
                items.append(v)
        if items:
            clean[ans_key] = items

    payload: dict[str, Any] = {"v": PAYLOAD_VERSION, "rid": record_id}
    if identity:
        ident = {k: str(v) for k, v in identity.items() if v not in (None, "")}
        if ident:
            payload["id"] = ident
    payload["ans"] = clean
    return payload


def serialize(payload: dict) -> str:
    """序列化为纯 ASCII JSON 文本（可直接作为 encoder 的 argv[1]）。"""
    text = json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    )
    if not text.isascii():
        raise PayloadError("序列化结果不是纯 ASCII，拒绝送入 C++ 编码器")
    return text


def parse(text: str) -> dict:
    """解析解码得到的 JSON 文本，并校验版本。"""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PayloadError(f"载荷不是合法 JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise PayloadError("载荷根节点必须是对象")
    version = payload.get("v")
    if version != PAYLOAD_VERSION:
        raise PayloadError(
            f"载荷版本不匹配：期望 {PAYLOAD_VERSION}，实际 {version!r}"
        )
    return payload


# ==========================================
# 校验（供数据库层 / 联调自检使用）
# ==========================================
def validate(payload: dict) -> list[str]:
    """返回问题清单，空列表表示通过。不抛异常，便于批量检查。"""
    problems: list[str] = []
    if payload.get("v") != PAYLOAD_VERSION:
        problems.append(f"v 应为 {PAYLOAD_VERSION}，实际 {payload.get('v')!r}")
    rid = payload.get("rid")
    if not isinstance(rid, str) or not rid or not rid.isascii():
        problems.append("rid 缺失或非 ASCII")
    ans = payload.get("ans")
    if not isinstance(ans, dict):
        problems.append("ans 必须是对象")
    else:
        for key, values in ans.items():
            if not _ANS_KEY_RE.match(key):
                problems.append(f"答案 key 格式错: {key!r}")
            if not isinstance(values, list) or not values:
                problems.append(f"{key} 的值必须是非空数组")
                continue
            for v in values:
                if not isinstance(v, str) or not _TOKEN_RE.match(v):
                    problems.append(f"{key} 含非法 option_key: {v!r}")
    ident = payload.get("id")
    if ident is not None and not isinstance(ident, dict):
        problems.append("id 必须是对象")
    return problems


# ==========================================
# 快速自检
# ==========================================
if __name__ == "__main__":
    demo = build_payload(
        record_id="ARCHIVE_20261117_001",
        answers={
            "symptoms.chief_complaint": ["fever", "cough"],
            "disease_classification.disease_category": ["chapter_iii"],
            "past_and_family_history.past_medical_history": ["anemia"],
            "personal_lifestyle.smoking_history": ["wst_cv02_10_101_2"],
        },
        identity={"nm": "张三", "g": "male", "dob": "2020-01-01"},
    )
    text = serialize(demo)
    print("载荷文本：")
    print(text)
    print(f"\n长度 {len(text)} 字节 | 纯 ASCII: {text.isascii()}")
    print(f"往返一致: {parse(text) == demo}")
    print(f"校验问题: {validate(demo) or '无'}")
