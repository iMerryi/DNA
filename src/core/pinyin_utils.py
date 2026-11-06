# -*- coding: utf-8 -*-
"""拼音工具"""

import pypinyin


def to_pinyin_string(text: str) -> str:
    """中文转拼音字符串，用下划线连接"""
    if not text:
        return ""
    py_list = pypinyin.pinyin(text, style=pypinyin.Style.NORMAL)
    return "_".join([item[0] for item in py_list])
