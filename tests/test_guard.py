# -*- coding: utf-8 -*-
"""数据完整性工程师验收：一致性守卫（数字指纹/角标/占位符/RPA schema）。"""
import pytest

from app.agents.guard import check_draft, check_identity, check_rpa_task
from app.core.assertions import run_all
from app.core.calc import CalculationService
from app.core.datastore import DataStore

FP = {"材料环比": 3.11, "贡献度": 68.0, "告警": []}


def test_pass_draft():
    g = check_draft("材料成本变动 3.11 元/盒 [S1]，贡献总变动的 68.0% [S2]。", FP)
    assert g.passed, g.violations


def test_placeholder_residue():
    g = check_draft("本月材料成本 {{材料}} 为 3.11 [S1]。", FP)
    assert not g.passed and any("占位符" in v for v in g.violations)


def test_number_without_citation():
    g = check_draft("材料成本变动 3.11 元/盒，贡献较大。", FP)
    assert not g.passed and any("无角标" in v for v in g.violations)


def test_hallucinated_number_detected():
    g = check_draft("材料成本变动 99.99 元/盒 [S1]。", FP)
    assert not g.passed and any("数字指纹" in v for v in g.violations)


def test_c_citation_requires_causal_evidence():
    ok = check_draft("材料成本变动 3.11 元/盒 [S1]，行情传导 [C1]。", FP, allow_causal=True)
    assert ok.passed
    bad = check_draft("材料成本变动 3.11 元/盒 [S1]，行情传导 [C1]。", FP, allow_causal=False)
    assert not bad.passed and any("[C]" in v for v in bad.violations)


def test_rpa_task_schema():
    good = {
        "task_id": "TASK-202605-0001", "task_title": "核查金银花采购合同调价条款",
        "assignee": {"name": "张伟", "department": "采购部", "role": "采购经理"},
        "source": {"analysis_type": "月度成本分析", "analysis_month": "2026-05",
                   "product": "银黄口服液", "finding": "金银花涨价"},
        "priority": "high", "deadline": "2026-06-03",
        "suggestion": "核查调价条款", "notify_method": "wechat",
        "created_at": "2026-06-01T09:00:00",
    }
    assert check_rpa_task(good).passed
    bad = dict(good, task_id="TASK-0001", priority="urgent", deadline="06/03")
    g = check_rpa_task(bad)
    assert not g.passed
    assert any("task_id" in v for v in g.violations)
    assert any("priority" in v for v in g.violations)


def test_identity_assertions_all_pass():
    ds, svc = DataStore(), CalculationService(DataStore())
    g = check_identity(ds, svc)
    assert g.passed, g.violations
