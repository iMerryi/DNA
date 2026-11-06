# -*- coding: utf-8 -*-
"""数据分类：把 AI 返回的分层结构整理成界面可直接使用的平铺字段"""

# AI 提示词里的字段名与界面/数据库字段名不一致，这里做统一
AI_FIELD_ALIASES = {
    "父亲电话": "父亲联系电话",
    "母亲电话": "母亲联系电话",
    "Apgar(1min)": "Apgar_1分钟",
    "Apgar(5min)": "Apgar_5分钟",
}

_LAYERS = ("物理存储", "反复存储", "病症记录")


def normalize_extraction(data) -> dict:
    """把 AI 的三层结构（物理存储 / 反复存储 / 病症记录）拍平成表单字段"""
    if not isinstance(data, dict):
        return {}

    flat = {}

    physical = data.get("物理存储") or {}
    for key, value in physical.items():
        flat[AI_FIELD_ALIASES.get(key, key)] = value

    repeated = data.get("反复存储") or []
    if isinstance(repeated, list) and repeated:
        first = repeated[0]
        if isinstance(first, dict):
            for key, value in first.items():
                flat.setdefault(key, value)

    diseases = data.get("病症记录") or {}
    for key, value in diseases.items():
        flat[AI_FIELD_ALIASES.get(key, key)] = value

    # 兼容 AI 直接返回平铺结构
    for key, value in data.items():
        if key not in _LAYERS:
            flat.setdefault(AI_FIELD_ALIASES.get(key, key), value)

    return flat
