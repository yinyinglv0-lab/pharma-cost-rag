# -*- coding: utf-8 -*-
"""项目1验收：六条因果链可运行 + 链4反事实≠实际 + 链6诚实标注 + 支持度∈[0,1]。"""
from app.causal.engine import demo_causal, mermaid_diagram, run_all_chains


def test_six_chains_runnable():
    chains = run_all_chains()
    assert [c.chain_id for c in chains] == ["E1", "E2", "E3", "E4", "E5", "E6"]
    for c in chains:
        assert 0.0 <= c.support <= 1.0
        assert c.support_basis, f"{c.chain_id} 缺支持度依据"


def test_chain4_counterfactual_differs_from_actual():
    c = next(x for x in run_all_chains() if x.chain_id == "E4")
    assert c.counterfactual_unit_cost != c.actual_unit_cost, "链4 反事实必须≠实际（证明重算生效）"
    assert abs(c.delta - (c.actual_unit_cost - c.counterfactual_unit_cost)) < 1e-9


def test_chain6_honest_footprint_note():
    c = next(x for x in run_all_chains() if x.chain_id == "E6")
    assert "足迹" in c.notes and "假设性重算" in c.notes
    assert "无成本足迹" in c.support_basis


def test_chain1_counterfactual_matches_anchor():
    """金银花钉回3月价格: 11.21 - (3.50-3.18) = 10.89。"""
    c = next(x for x in run_all_chains() if x.chain_id == "E1")
    assert abs(c.counterfactual_unit_cost - 10.89) < 0.01, c.counterfactual_unit_cost
    assert abs(c.delta - 0.32) < 0.01


def test_demo_and_mermaid():
    log = demo_causal()
    assert "六味地黄胶囊2026-03" in log and "因果图" in log
    m = mermaid_diagram()
    assert "E1" in m and "E6" in m and "无成本足迹" in m
