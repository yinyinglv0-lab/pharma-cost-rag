# -*- coding: utf-8 -*-
"""验证5：回归影响实操验证——阶段 3 未破坏阶段 1/2。

通过子进程运行既有验收入口，对比基线：
- 阶段 1：pytest 77 passed + run_checks.py 全绿（断言+金丝雀 88 项）；
- 阶段 2：run_rag_checks.py 14/14。
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent


def _run(cmd):
    # 子进程 stdout 是 UTF-8（脚本内部已 reconfigure），必须显式按 UTF-8 解码
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=600)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def test_phase1_pytest_baseline():
    code, out = _run([sys.executable, "-m", "pytest", "tests/test_golden.py",
                      "tests/test_assertions.py", "-q"])
    assert code == 0, out[-500:]
    assert "77 passed" in out, out[-300:]


def test_phase1_run_checks_baseline():
    code, out = _run([sys.executable, "scripts/run_checks.py"])
    assert code == 0, out[-500:]
    assert "全部通过" in out


def test_phase2_run_rag_checks_baseline():
    code, out = _run([sys.executable, "scripts/run_rag_checks.py"])
    assert code == 0, out[-500:]
    assert "14/14" in out
