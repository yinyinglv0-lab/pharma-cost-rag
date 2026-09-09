# -*- coding: utf-8 -*-
"""模块二验收：阈值分层校准（新旧对比）+ ECharts 四图数据与金丝雀一致。"""
from app.dashboard.calibration import build_calibration
from app.dashboard.charts import structure, trend, waterfall, heatmap


def test_calibration_bands():
    cal = build_calibration()
    t = cal["table"]
    assert t["要素级"]["band"] == 5.0, t
    assert t["派生指标"]["band"] == 10.0 and t["汇总级"]["band"] == 10.0
    assert 4.5 <= t["要素级"]["p95"] <= 5.5
    assert cal["old_rule_alerts"] == [], "旧 ±10% 要素级应 0 命中"
    assert cal["new_rule_alerts"], "新 ±5% 应命中"
    assert any("板蓝根颗粒 2026-04" in a and "材料" in a for a in cal["new_rule_alerts"]), \
        "应命中板蓝根 4 月材料 +5.30%"
    assert "±5%" in cal["appendix"] and "±10%" in cal["appendix"]


def test_trend_data_matches_golden():
    opt = trend("银黄口服液")
    assert opt["series"][0]["data"] == [10.70, 10.87, 10.53, 10.90, 11.21, 10.93]


def test_waterfall_matches_three_factor():
    opt = waterfall("银黄口服液", "2026-02")
    vals = opt["series"][0]["data"]
    assert [v["value"] for v in vals[:3]] == [0.09, 0.03, 0.05]
    assert vals[3]["value"] == 0.17


def test_structure_sums_to_unit_cost():
    opt = structure("银黄口服液", "2026-05")
    vals = [d["value"] for d in opt["series"][0]["data"]]
    assert abs(sum(vals) - 11.21) < 1e-9
    assert abs(vals[0] - 7.30) < 1e-9


def test_heatmap_full_matrix():
    opt = heatmap()
    assert len(opt["series"][0]["data"]) == 3 * 3 * 6
    assert len(opt["xAxis"]["data"]) == 18 and len(opt["yAxis"]["data"]) == 3
