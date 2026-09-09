# -*- coding: utf-8 -*-
"""免 pytest 的一键检查：python scripts/run_checks.py

跑 恒等式断言库 + 金丝雀基准集，打印逐条结果与汇总。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.assertions import run_all
from app.core.calc import CalculationService
from app.core.datastore import DataStore
from tests.golden_checks import all_checks


def main():
    sys.stdout.reconfigure(encoding="utf-8")  # 兼容 GBK 控制台，避免 R² 等字符打印崩溃
    svc = CalculationService(DataStore())
    print("=" * 62)
    print("  阶段 1 验收：恒等式断言库 + 金丝雀基准集")
    print("=" * 62)

    print("\n[恒等式断言库]")
    n_fail = 0
    for r in run_all(svc.ds, svc):
        mark = "PASS" if r["ok"] else "FAIL"
        if not r["ok"]:
            n_fail += 1
        print(f"  {mark}  {r['name']}" + (f"  -> {r['detail']}" if not r["ok"] else ""))

    print("\n[金丝雀基准集]")
    n_gold_fail = 0
    for c in all_checks(svc):
        mark = "PASS" if c["ok"] else "FAIL"
        if not c["ok"]:
            n_gold_fail += 1
        print(f"  {mark}  {c['name']}" + (f"  -> {c['detail']}" if not c["ok"] else ""))

    print("-" * 62)
    total = n_fail + n_gold_fail
    print(f"  总计: 断言失败 {n_fail} 条 / 金丝雀失败 {n_gold_fail} 条")
    print("  结论: " + ("全部通过 ✅ 阶段 1 下闸" if total == 0 else f"存在 {total} 条失败 ❌ 禁止进入阶段 2"))
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
