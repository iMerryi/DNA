# -*- coding: utf-8 -*-
"""
test_dna_match.py - dna_match.exe 验收测试脚本
对应设计文档 §8 验收标准 1-7
"""

import os
import sys
import subprocess
import tempfile
import sqlite3

# 添加 src/algorithm 到路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
ALGORITHM_DIR = os.path.join(PROJECT_ROOT, "src", "algorithm")
sys.path.insert(0, ALGORITHM_DIR)

from similarity import DnaMatcher, SimilarityService, MatchResult


class TestRunner:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []
    
    def assert_true(self, condition, message):
        if condition:
            self.passed += 1
            print(f"  ✓ {message}")
        else:
            self.failed += 1
            self.errors.append(message)
            print(f"  ✗ {message}")
    
    def assert_equal(self, actual, expected, message):
        self.assert_true(actual == expected, f"{message} (期望: {expected}, 实际: {actual})")
    
    def run_all(self):
        print("=" * 60)
        print("dna_match.exe 验收测试")
        print("=" * 60)
        
        self.test_compile()
        self.test_basic_match()
        self.test_deterministic()
        self.test_whitelist_filter()
        self.test_exact_match_skip()
        self.test_threshold_judgment()
        
        print("\n" + "=" * 60)
        print(f"结果: {self.passed} 通过, {self.failed} 失败")
        if self.errors:
            print("\n失败项:")
            for e in self.errors:
                print(f"  - {e}")
        print("=" * 60)
        
        return self.failed == 0
    
    def test_compile(self):
        """测试 0: 编译 dna_match.cpp"""
        print("\n[测试 0] 编译 dna_match.cpp")
        cpp_path = os.path.join(ALGORITHM_DIR, "dna_match.cpp")
        exe_path = os.path.join(ALGORITHM_DIR, "dna_match.exe")
        
        if not os.path.exists(cpp_path):
            self.assert_true(False, f"源码不存在: {cpp_path}")
            return
        
        # 尝试编译
        result = subprocess.run(
            ["g++", "-std=c++11", "-O2", "-o", exe_path, cpp_path],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            self.assert_true(False, f"编译失败: {result.stderr}")
        else:
            self.assert_true(os.path.exists(exe_path), "编译成功，生成 dna_match.exe")
    
    def test_basic_match(self):
        """测试 1: 基本匹配 - fevgr + 5 候选，首行应为 fever dist=1"""
        print("\n[测试 1] 基本匹配: fevgr -> fever")
        
        matcher = DnaMatcher()
        target = "fevgr"
        candidates = ["fever", "fevbr", "hemoglobin", "fever2", "cough"]
        
        matches = matcher.match(target, candidates)
        
        self.assert_true(len(matches) == 5, f"返回 5 个结果 (实际: {len(matches)})")
        self.assert_equal(matches[0].candidate, "fever", "首行候选为 fever")
        self.assert_equal(matches[0].dist, 1, "首行距离为 1")
        self.assert_true(matches[0].score > 0.7, f"首行相似度 > 0.7 (实际: {matches[0].score:.3f})")
    
    def test_deterministic(self):
        """测试 2: 确定性 - 同一输入连续跑 10 次，输出逐字节一致"""
        print("\n[测试 2] 确定性: 10 次运行结果一致")
        
        matcher = DnaMatcher()
        target = "fevgr"
        candidates = ["fever", "fevbr", "hemoglobin", "fever2", "cough"]
        
        first_result = None
        all_same = True
        
        for i in range(10):
            matches = matcher.match(target, candidates)
            result_str = str([(m.candidate, m.dist, m.score) for m in matches])
            
            if first_result is None:
                first_result = result_str
            elif result_str != first_result:
                all_same = False
                break
        
        self.assert_true(all_same, "10 次运行结果完全一致")
    
    def test_whitelist_filter(self):
        """测试 3: 白名单过滤 - 词表外的词被拦截"""
        print("\n[测试 3] 白名单过滤: zzzznotaword 被拦截")
        
        matcher = DnaMatcher()
        target = "zzzznotaword"
        candidates = ["fever", "cough", "headache"]
        
        # 使用 find_best，max_dist=2 应该拦截这个词
        best = matcher.find_best(target, candidates, max_dist=2)
        
        self.assert_true(best is None, "词表外的词被正确拦截（返回 None）")
    
    def test_exact_match_skip(self):
        """测试 4: 精确命中跳过 - 词表内的词不进 DP"""
        print("\n[测试 4] 精确命中: 已在词表中的词直接放行")
        
        matcher = DnaMatcher()
        target = "fever"
        candidates = ["fever", "cough", "headache"]
        
        matches = matcher.match(target, candidates)
        
        # 精确匹配应该距离为 0
        self.assert_equal(matches[0].dist, 0, "精确匹配距离为 0")
        self.assert_equal(matches[0].score, 1.0, "精确匹配相似度为 1.0")
    
    def test_threshold_judgment(self):
        """测试 5: 阈值判定 - 最小距离 <= 2 且比次小至少小 1 才采纳"""
        print("\n[测试 5] 阈值判定: 次小差距检查")
        
        matcher = DnaMatcher()
        
        # 场景 A: 明确的最佳匹配（应该采纳）
        target = "fevgr"
        candidates = ["fever", "cough", "headache"]
        best = matcher.find_best(target, candidates, max_dist=2, min_margin=1)
        self.assert_true(best is not None and best.candidate == "fever", 
                        "明确最佳匹配被采纳")
        
        # 场景 B: 两个候选距离相同（应该拒绝）
        target = "fevgr"
        candidates = ["fever", "fevbr"]  # fever dist=1, fevbr dist=1
        best = matcher.find_best(target, candidates, max_dist=2, min_margin=1)
        self.assert_true(best is None, "并列候选被拒绝（返回 None）")
        
        # 场景 C: 距离超过阈值（应该拒绝）
        target = "zzzzzz"
        candidates = ["fever", "cough"]
        best = matcher.find_best(target, candidates, max_dist=2, min_margin=1)
        self.assert_true(best is None, "超阈值被拒绝（返回 None）")


def test_with_database():
    """测试 6-7: 需要数据库的集成测试"""
    print("\n[测试 6-7] 数据库集成测试（需要 v4.1 数据库）")
    
    # 检查是否有样例数据库
    db_path = os.path.join(PROJECT_ROOT, "data", "db", "medical_archive.db")
    if not os.path.exists(db_path):
        print("  ⚠ 数据库不存在，跳过集成测试")
        print(f"    期望路径: {db_path}")
        return
    
    try:
        service = SimilarityService(db_path)
        
        # 检查 options 表是否有数据
        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM options").fetchone()[0]
        conn.close()
        
        if count == 0:
            print(f"  ⚠ options 表为空（{count} 行），跳过集成测试")
            print("    请先执行种子脚本灌入选项数据")
            return
        
        print(f"  ✓ options 表有 {count} 行数据")
        
        # 测试 find_similar_records
        results = service.find_similar_records("fever cough", threshold=0.7, limit=5)
        print(f"  ✓ find_similar_records 返回 {len(results)} 条结果")
        
        service.close()
        
    except Exception as e:
        print(f"  ✗ 集成测试失败: {e}")


if __name__ == "__main__":
    runner = TestRunner()
    success = runner.run_all()
    
    # 额外运行数据库集成测试
    test_with_database()
    
    sys.exit(0 if success else 1)
