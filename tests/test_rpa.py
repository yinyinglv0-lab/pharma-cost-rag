# -*- coding: utf-8 -*-
"""模块四验收：幂等台账 + 真实 mock 服务集成（推送/查询/追踪/重复幂等）。"""
import subprocess
import sys
import time
from pathlib import Path

import pytest

from app.rpa.client import RPAClient
from app.rpa.gateway import Gateway
from app.rpa.ledger import assign_task_id

MOCK_SERVER = Path(r"D:\23生信-团日活动（学习雷锋）\重庆比赛AI\创灵境_考题模拟数据0816"
                   r"\创灵境_考题模拟数据\05_RPA接口文档\mock_rpa_server.py")


def test_ledger_idempotency(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_ARTIFACT_DIR", str(tmp_path))
    a = assign_task_id("银黄口服液", "金银花涨价-采购合同", "2026-05")
    b = assign_task_id("银黄口服液", "金银花涨价-采购合同", "2026-05")
    assert a == b, "同键必须复用同 ID"
    c = assign_task_id("银黄口服液", "金银花涨价-采购合同", "2026-04")
    assert c != a and "202604" in c, "跨月同根因必须不同 ID（金银花 4-5 月）"
    d = assign_task_id("板蓝根颗粒", "板蓝根涨价", "2026-05")
    assert d != a and "202605" in d


@pytest.fixture(scope="module")
def mock_server():
    proc = subprocess.Popen([sys.executable, str(MOCK_SERVER)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    client = RPAClient()
    for _ in range(40):
        if client.health():
            break
        time.sleep(0.5)
    assert client.health(), "mock 服务 20s 内未就绪"
    yield client
    proc.terminate()
    proc.wait(timeout=10)


def test_push_query_track(mock_server):
    gw = Gateway(client=mock_server)
    out = __import__("app.agents.graph", fromlist=["run_agent"]).run_agent(
        "请生成银黄口服液2026-05成本分析报告并派发整改任务",
        session_id="rpa-test", llm=__import__("app.agents.llm", fromlist=["MockLLM"]).MockLLM())
    task = out["rpa_task"]
    gw.enqueue([task])
    res = gw.confirm(task["task_id"])
    assert res.get("ok"), res
    assert not res.get("duplicate")
    got = mock_server.get_task(task["task_id"])
    assert got["ok"] and got["resp"]["data"]["task_id"] == task["task_id"]
    assert got["resp"]["data"]["status"] == "sent"
    board = gw.board()
    assert board["sent"] == 1 and board["server_stats"]["total_tasks"] >= 1
    listing = mock_server.list_tasks(product="银黄口服液")
    assert listing["ok"] and listing["data"]["total"] >= 1


def test_duplicate_push_idempotent(mock_server):
    """同 task_id 重复推送：mock 返回 400 已存在 → 客户端幂等承接，不崩溃。"""
    task = {
        "task_id": "TASK-DUP-0001", "task_title": "重复推送幂等测试",
        "assignee": {"name": "张伟", "department": "采购部", "role": "采购经理"},
        "source": {"analysis_type": "月度成本分析", "analysis_month": "2026-05",
                   "product": "银黄口服液", "finding": "幂等测试"},
        "priority": "medium", "deadline": "2026-06-03",
        "suggestion": "幂等测试", "notify_method": "wechat",
        "created_at": "2026-06-01T09:00:00",
    }
    first = mock_server.push_task(task)
    second = mock_server.push_task(task)
    assert first["ok"] and not first["duplicate"]
    assert second["ok"] and second["duplicate"], "重复推送应被幂等承接"
