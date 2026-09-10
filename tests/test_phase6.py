# -*- coding: utf-8 -*-
"""阶段6验收：评测脚本指标 / 缓存秒开 / 流式进度 / 合规终检。"""
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from app.agents.graph import run_agent_stream
from app.agents.llm import MockLLM


@pytest.fixture(scope="module")
def eval_report():
    r = subprocess.run([sys.executable, "scripts/run_evaluation.py"], cwd=ROOT,
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=900)
    assert r.returncode == 0, (r.stdout or "")[-800:]
    data = json.loads((ROOT / "evidence" / "evaluation_report.json").read_text(encoding="utf-8"))
    return data


def test_eval_structure(eval_report):
    assert len(eval_report["scenarios"]) == 3
    for s in eval_report["scenarios"]:
        assert s["pipeline_status"] == "完成" and s["guard_passed"]
        assert s["chapters_hit"] == 5, s["chapters"]
        assert s["placeholder_residue"] == 0
        assert s["charts"] >= 3


def test_eval_attribution(eval_report):
    assert eval_report["attribution"]["hit_rate"].startswith("6/6")


def test_eval_diff_accuracy(eval_report):
    assert eval_report["diff_accuracy"]["rows"] == 12
    assert eval_report["diff_accuracy"]["within_1pct"]
    assert eval_report["diff_accuracy"]["max_rel_error_pct"] <= 1.0


def test_eval_rpa(eval_report):
    assert eval_report["rpa"]["generated"] == 3
    assert eval_report["rpa"]["unique_ids"]


def test_cache_second_open(tmp_path):
    from scripts.demo_cache import SCENARIOS, load_cached, warm_cache
    warm_cache(llm=MockLLM())
    t0 = time.time()
    hit = load_cached("银黄口服液", "2026-05", llm=MockLLM())
    dt = time.time() - t0
    assert "演示模式(预生成缓存)" in hit["mode"]
    assert hit["docx"] and hit["meta"]["guard"]["passed"]
    assert dt < 3.0, f"缓存秒开超时 {dt:.1f}s"


def test_stream_progress():
    nodes = [c["node"] for c in run_agent_stream(
        "请生成银黄口服液2026-05的月度成本分析报告", session_id="stream-test", llm=MockLLM())]
    assert "route" in nodes and "data" in nodes and "retrieve" in nodes
    assert "writer" in nodes and "verify" in nodes
    assert nodes[-1] == "__final__"


def test_compliance():
    r = subprocess.run([sys.executable, "scripts/compliance_check.py"], cwd=ROOT,
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=300)
    assert r.returncode == 0, r.stdout[-500:]


def test_deliverables_generated():
    ev = ROOT / "evidence"
    for f in ["评测报告.md", "evaluation_report.json", "技术方案文档.docx", "答辩PPT.pptx"]:
        assert (ev / f).exists(), f"缺交付物 {f}"
    for f in ["演示视频脚本.md", "演示脚本.md"]:
        assert (ROOT / "docs" / f).exists()
