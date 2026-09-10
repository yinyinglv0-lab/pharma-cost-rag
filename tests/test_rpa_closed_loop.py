# -*- coding: utf-8 -*-
"""RPA 闭环验收：Schema对齐/幂等台账/闭环回写/效果追踪/预热。"""
import importlib.util
import subprocess
import sys
import time
from pathlib import Path

import pytest

from app.agents.guard import RPA_REQUIRED, check_rpa_task
from app.rpa.closure import (closure_records, effect_trace, record_closure,
                             related_closures)
from app.rpa.ledger import assign_task_id

MOCK = Path(r"D:\23生信-团日活动（学习雷锋）\重庆比赛AI\创灵境_考题模拟数据0816"
            r"\创灵境_考题模拟数据\05_RPA接口文档\mock_rpa_server.py")


def _task(task_id="TASK-202605-0001"):
    return {
        "task_id": task_id, "task_title": "闭环验收测试",
        "assignee": {"name": "张伟", "department": "采购部", "role": "采购经理"},
        "source": {"analysis_type": "月度成本分析", "analysis_month": "2026-05",
                   "product": "银黄口服液", "finding": "金银花涨价"},
        "priority": "high", "deadline": "2026-06-03",
        "suggestion": "核查调价条款", "notify_method": "wechat",
        "created_at": "2026-06-01T09:00:00",
    }


def test_schema_aligned_with_mock_pydantic():
    spec = importlib.util.spec_from_file_location("mock_rpa_server", MOCK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mock_required = {n for n, f in mod.TaskCreateRequest.model_fields.items() if f.is_required()}
    assert RPA_REQUIRED == mock_required, "必填字段必须与 mock 逐字段对齐"
    assert check_rpa_task(_task()).passed


def test_ledger_idempotency(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_ARTIFACT_DIR", str(tmp_path))
    a = assign_task_id("银黄口服液", "金银花涨价", "2026-05")
    b = assign_task_id("银黄口服液", "金银花涨价", "2026-05")
    c = assign_task_id("银黄口服液", "金银花涨价", "2026-04")
    assert a == b and a != c and "202604" in c


def test_closure_write_back_and_relation(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_ARTIFACT_DIR", str(tmp_path))
    rec = record_closure(_task("TASK-CL-0002-DONE"))
    assert rec["status"] == "completed" and abs(rec["net_effect_pct"] - (-0.37)) < 0.05
    rel = related_closures("银黄口服液", "2026-06")
    assert any(r["task_id"] == "TASK-CL-0002-DONE" for r in rel), "下月分析须自动关联上月任务"


def test_effect_trace_chart():
    tr = effect_trace("银黄口服液", "材料")
    assert len(tr["values"]) == 6
    assert "series" in tr["option"] and "markPoint" in tr["option"]["series"][0]


def test_warmup_script_exists_and_fast():
    from app.rpa.warmup import warmup
    from app.rpa.client import RPAClient
    proc = subprocess.Popen([sys.executable, str(MOCK)], stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    try:
        client = RPAClient()
        for _ in range(40):
            if client.health():
                break
            time.sleep(0.5)
        t0 = time.time()
        results = warmup(client)
        dt = time.time() - t0
        assert dt < 5.0 and all(r.get("ok") for _, r in results)
        assert any(t["task_id"].endswith("-DONE") for t, _ in results)
        assert any(t["task_id"].endswith("-FAST") for t, _ in results)
    finally:
        proc.terminate()
        proc.wait(timeout=10)
