# -*- coding: utf-8 -*-
"""
similarity.py - DNA 纠错相似度匹配 Python 封装
调用 dna_match.exe 进行 DP 细筛，支持白名单过滤。
"""

import os
import subprocess
import sqlite3
from typing import List, Tuple, Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class MatchResult:
    """匹配结果"""
    index: int
    candidate: str
    dist: int
    score: float


class DnaMatcher:
    """DNA 匹配器：调用 C++ dna_match.exe"""
    
    def __init__(self, exe_path: Optional[str] = None):
        if exe_path is None:
            # 默认查找同目录下的 dna_match.exe
            current_dir = os.path.dirname(os.path.abspath(__file__))
            exe_path = os.path.join(current_dir, "dna_match.exe")
        self.exe_path = exe_path
        
        if not os.path.exists(self.exe_path):
            raise FileNotFoundError(
                f"dna_match.exe 未找到: {self.exe_path}\n"
                f"请先编译: g++ -std=c++11 -O2 -o dna_match.exe dna_match.cpp"
            )
    
    def match(self, target: str, candidates: List[str]) -> List[MatchResult]:
        """
        对目标词和候选列表进行 DP 细筛
        
        Args:
            target: 待验证词（可能含突变）
            candidates: 候选词列表（来自白名单）
        
        Returns:
            按距离升序的 MatchResult 列表
        """
        if not candidates:
            return []
        
        # 构造 stdin 输入
        lines = [f"T 1", target, f"N {len(candidates)}"] + candidates
        input_text = "\n".join(lines) + "\n"
        
        # 调用 exe
        result = subprocess.run(
            [self.exe_path],
            input=input_text,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            raise RuntimeError(f"dna_match.exe 执行失败: {result.stderr}")
        
        # 解析输出
        matches = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split()
            if len(parts) != 3:
                continue
            idx, dist, score = int(parts[0]), int(parts[1]), float(parts[2])
            matches.append(MatchResult(
                index=idx,
                candidate=candidates[idx],
                dist=dist,
                score=score
            ))
        
        return matches
    
    def find_best(self, target: str, candidates: List[str], 
                  max_dist: int = 2, min_margin: int = 1) -> Optional[MatchResult]:
        """
        找最佳匹配（带阈值和次小差距判定）
        
        Args:
            target: 待验证词
            candidates: 候选列表
            max_dist: 最大可接受编辑距离
            min_margin: 最小差距（比次小至少小多少才采纳）
        
        Returns:
            最佳匹配，或 None（未纠正）
        """
        matches = self.match(target, candidates)
        if not matches:
            return None
        
        best = matches[0]
        
        # 阈值检查
        if best.dist > max_dist:
            return None
        
        # 次小差距检查（如果有多个候选）
        if len(matches) > 1:
            second = matches[1]
            if second.dist - best.dist < min_margin:
                return None  # 差距太小，不采纳
        
        return best


class SimilarityService:
    """
    相似度服务：整合 AI 粗配 + DP 细筛
    对应 api_contract.md 中的 find_similar_records / find_similar_dna_sequences
    """
    
    def __init__(self, db_path: str, matcher: Optional[DnaMatcher] = None):
        self.db_path = db_path
        self.matcher = matcher or DnaMatcher()
        self._conn = None
    
    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
        return self._conn
    
    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None
    
    def _get_whitelist(self, field_key: Optional[str] = None) -> List[str]:
        """从 options 表获取白名单词表

        注意：options 表没有 field_key 列，字段过滤需通过 fields 表 join
        （options.field_id -> fields.id -> fields.field_key）。
        """
        conn = self._get_conn()
        if field_key:
            rows = conn.execute(
                """SELECT o.option_key FROM options o
                   JOIN fields f ON o.field_id = f.id
                   WHERE f.field_key = ?""",
                (field_key,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT DISTINCT option_key FROM options").fetchall()
        return [r["option_key"] for r in rows]
    
    def find_similar_records(self, text: str, threshold: float = 0.7, 
                            limit: int = 5) -> List[Dict[str, Any]]:
        """
        找相似档案（v4.1 版本：基于 option_key 匹配）
        
        注意：此函数用于找相似档案，不是 DNA 序列比对。
        DNA 序列比对请用 find_similar_dna_sequences。
        """
        # 1. 分词（假设 text 已是空格分隔的 option_key 列表）
        tokens = text.strip().split()
        
        # 2. 获取白名单
        whitelist = self._get_whitelist()
        if not whitelist:
            return []
        
        # 3. 对每个 token 做匹配
        results = []
        for token in tokens:
            # 精确命中
            if token in whitelist:
                results.append({
                    "original": token,
                    "matched": token,
                    "dist": 0,
                    "score": 1.0,
                    "corrected": False
                })
                continue
            
            # DP 细筛
            best = self.matcher.find_best(token, whitelist)
            if best:
                results.append({
                    "original": token,
                    "matched": best.candidate,
                    "dist": best.dist,
                    "score": best.score,
                    "corrected": True
                })
            else:
                results.append({
                    "original": token,
                    "matched": None,
                    "dist": -1,
                    "score": 0.0,
                    "corrected": False,
                    "uncorrectable": True
                })
        
        # 按 score 排序，取 top limit
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]
    
    def find_similar_dna_sequences(self, dna_sequence: str, threshold: float = 0.8,
                                   limit: int = 10) -> List[Dict[str, Any]]:
        """
        找相似 DNA 序列
        
        注意：此函数按 DNA 序列比对，受 srand(time(0)) 不可复现影响，
        不能用于找相似档案，只可用于同序列完整性校验。
        """
        # TODO: 实现 DNA 序列相似度比对
        # 当前版本仅作占位，需后续实现基于碱基编辑距离的比对
        raise NotImplementedError(
            "find_similar_dna_sequences 待实现。当前版本请使用 find_similar_records 进行档案级匹配。"
        )


# 便捷函数（保持与旧版 api_contract 兼容）
_default_service: Optional[SimilarityService] = None

def init_similarity_service(db_path: str, exe_path: Optional[str] = None):
    """初始化全局相似度服务"""
    global _default_service
    matcher = DnaMatcher(exe_path) if exe_path else None
    _default_service = SimilarityService(db_path, matcher)

def find_similar_records(text: str, threshold: float = 0.7, limit: int = 5):
    """找相似档案（便捷函数）"""
    if _default_service is None:
        raise RuntimeError("请先调用 init_similarity_service()")
    return _default_service.find_similar_records(text, threshold, limit)

def find_similar_dna_sequences(dna_sequence: str, threshold: float = 0.8, limit: int = 10):
    """找相似 DNA 序列（便捷函数）"""
    if _default_service is None:
        raise RuntimeError("请先调用 init_similarity_service()")
    return _default_service.find_similar_dna_sequences(dna_sequence, threshold, limit)
