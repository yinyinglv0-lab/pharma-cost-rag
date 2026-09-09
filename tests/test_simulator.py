# -*- coding: utf-8 -*-
"""项目2验收：滑块传导恒等式 + 收率系数知识库引用 + 敏感度排序。"""
import pytest

from app.simulator.engine import YIELD_COEFFICIENT, demo_simulator, sensitivity_ranking, simulate_price


def test_waterfall_sums_to_total():
    sc = simulate_price("银黄口服液", "金银花", 10.0, "2026-05", yield_drop_pp=1.0)
    assert abs(sum(f["delta"] for f in sc.factors) - sc.total_delta) < 1e-9
    assert len(sc.factors) == 2  # 价格 + 收率两个因素
    # 金银花 +10%: 3.50×0.1=0.35; 收率 -1pp: +0.08; 合计 0.43
    assert abs(sc.factors[0]["delta"] - 0.35) < 1e-9
    assert abs(sc.factors[1]["delta"] - 0.08) < 1e-9
    assert abs(sc.total_delta - 0.43) < 1e-9
    assert abs(sc.new_unit_cost - 11.64) < 1e-9  # 11.21 + 0.43


def test_slider_bounds():
    with pytest.raises(AssertionError):
        simulate_price("银黄口服液", "金银花", 60.0)


def test_yield_coefficient_from_knowledge_base():
    assert YIELD_COEFFICIENT == 0.08, "收率系数必须为工艺文档的 0.08 元/盒·pp"
    assert "知识库引用" in demo_simulator()


def test_sensitivity_ranking_desc():
    rank = sensitivity_ranking("银黄口服液", "2026-05")
    assert rank[0]["material"] == "金银花", "金银花应居敏感度榜首"
    impacts = [r["impact_per_10pct"] for r in rank]
    assert impacts == sorted(impacts, reverse=True)
