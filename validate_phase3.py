# -*- coding: utf-8 -*-
"""阶段 3 统一验证入口：依次运行 5 项实操验证 + 全量回归，留存证据日志。

用法: python validate_phase3.py
产出: evidence/phase3_validate.log（答辩证据留存）
"""
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent
sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # GBK 控制台防崩


def run(cmd):
    # 子进程 stdout 是 UTF-8（脚本内部已 reconfigure），父进程显式按 UTF-8 解码
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=900)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


STEPS = [
    ("验证1-4: 断点续跑/守卫拦截/桥接/E2E场景",
     [sys.executable, "-m", "pytest", "tests/test_phase3/test_checkpoint_resume.py",
      "tests/test_phase3/test_guard_hallucination.py",
      "tests/test_phase3/test_langchain_bridge.py",
      "tests/test_phase3/test_e2e_scenarios.py", "-q"]),
    ("验证5a: 阶段1 pytest 基线 (77 passed)",
     [sys.executable, "-m", "pytest", "tests/test_golden.py", "tests/test_assertions.py", "-q"]),
    ("验证5b: 阶段1 验收脚本 (断言+金丝雀)",
     [sys.executable, "scripts/run_checks.py"]),
    ("验证5c: 阶段2 验收脚本 (14/14)",
     [sys.executable, "scripts/run_rag_checks.py"]),
    ("阶段3 验收脚本 (4/4)",
     [sys.executable, "scripts/run_agent_checks.py"]),
    ("阶段4 四模块验收脚本 (15 passed)",
     [sys.executable, "scripts/run_phase4_checks.py"]),
]


def main():
    lines = [f"===== 阶段 3 统一验证 {datetime.now():%Y-%m-%d %H:%M:%S} ====="]
    all_ok = True
    for name, cmd in STEPS:
        code, out = run(cmd)
        ok = code == 0
        all_ok = all_ok and ok
        # 取 pytest 汇总行（末尾常是 multiprocess 退出噪音，不可取末行）
        summary = next((l.strip() for l in reversed(out.splitlines())
                        if "passed" in l or "failed" in l or "结论" in l), "")
        lines.append(f"[{'PASS' if ok else 'FAIL'}] {name}  -> {summary[:80]}")
        print(lines[-1])
        if not ok:
            lines.append(out[-600:])
    lines.append("===== 结论: " + ("全部通过 ✅" if all_ok else "存在失败 ❌") + " =====")
    print(lines[-1])
    ev = ROOT / "evidence"
    ev.mkdir(exist_ok=True)
    (ev / "phase3_validate.log").write_text("\n".join(lines), encoding="utf-8")
    print(f"证据日志: {ev / 'phase3_validate.log'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
