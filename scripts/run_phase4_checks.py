# -*- coding: utf-8 -*-
"""免 pytest 的阶段 4 一键检查：python scripts/run_phase4_checks.py"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding="utf-8")


def main():
    print("=" * 62)
    print("  阶段 4 验收：四模块产品化（报告/看板/对标/RPA）")
    print("=" * 62)
    tests = ["tests/test_report.py", "tests/test_dashboard.py",
             "tests/test_benchmark.py", "tests/test_rpa.py"]
    r = subprocess.run([sys.executable, "-m", "pytest", *tests, "-q"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=900)
    print((r.stdout or "")[-500:])
    print((r.stderr or "")[-300:])
    ok = r.returncode == 0
    print("-" * 62)
    print(f"  结论: {'全部通过 ✅ 阶段 4 下闸' if ok else '存在失败 ❌'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
