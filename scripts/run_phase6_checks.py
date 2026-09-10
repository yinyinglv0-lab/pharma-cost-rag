# -*- coding: utf-8 -*-
"""免 pytest 的阶段 6 一键检查 + 交付物生成：python scripts/run_phase6_checks.py"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")


def main():
    print("=" * 62)
    print("  阶段 6 验收：评测脚本 / 演示工程 / 交付物 / 合规终检")
    print("=" * 62)

    steps = [
        ("6.1 评测报告（3场景×4指标）", [sys.executable, "scripts/run_evaluation.py"]),
        ("6.2 演示缓存预热", [sys.executable, "scripts/demo_cache.py"]),
        ("6.3 技术方案文档", [sys.executable, "scripts/gen_tech_doc.py"]),
        ("6.3 答辩PPT", [sys.executable, "scripts/gen_ppt.py"]),
        ("6.4 合规终检", [sys.executable, "scripts/compliance_check.py"]),
    ]
    all_ok = True
    for name, cmd in steps:
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=900)
        ok = r.returncode == 0
        all_ok = all_ok and ok
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
        if not ok:
            print((r.stdout or "")[-300:], (r.stderr or "")[-200:])

    r = subprocess.run([sys.executable, "-m", "pytest", "tests/test_phase6.py", "-q"],
                       cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=900)
    ok = r.returncode == 0
    all_ok = all_ok and ok
    print(f"[{'PASS' if ok else 'FAIL'}] 阶段6 专项测试")
    print((r.stdout or "")[-200:])

    print("-" * 62)
    print(f"  结论: {'全部通过 ✅ 阶段 6 下闸' if all_ok else '存在失败 ❌'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
