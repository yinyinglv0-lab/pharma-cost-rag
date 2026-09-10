# -*- coding: utf-8 -*-
"""图表可视化审计验收：数据逐位/标注完整/交互配置/视觉一致性。"""
import json

from app.core.calc import CalculationService
from app.core.datastore import DataStore
from app.dashboard.charts import (CHART_BUILDERS, ELEMENT_COLORS, NEG_COLOR, POS_COLOR,
                                  _SOURCE_SUBTEXT)

MONTHS = [f"2026-{m:02d}" for m in range(1, 7)]


def test_trend_data_and_markpoint():
    opt = CHART_BUILDERS["趋势"]("银黄口服液")
    assert opt["xAxis"]["data"] == MONTHS
    data = opt["series"][0]["data"]
    assert data == [10.70, 10.87, 10.53, 10.90, 11.21, 10.93]
    mp = {d["type"]: d["value"] for d in opt["series"][0]["markPoint"]["data"]}
    assert mp["max"] == 11.21 and mp["min"] == 10.53, "markPoint 最大值/最小值必须正确标注"
    assert "tooltip" in opt and "dataZoom" in opt


def test_waterfall_identity_and_colors():
    svc = CalculationService(DataStore())
    for p in ("银黄口服液", "板蓝根颗粒", "六味地黄胶囊"):
        opt = CHART_BUILDERS["瀑布"](p, "2026-02")
        tf = svc.three_factor(p, "2026-02")
        vals = [d["value"] for d in opt["series"][0]["data"][:3]]
        assert [round(tf[e]["delta"], 2) for e in ("材料", "人工", "制费")] == vals, p
        assert abs(sum(vals) - opt["series"][0]["data"][3]["value"]) < 0.001, "Σ增量=总变动"
        for d in opt["series"][0]["data"][:3]:
            expect = POS_COLOR if d["value"] >= 0 else NEG_COLOR
            assert d["itemStyle"]["color"] == expect, "正贡献绿/负贡献红"


def test_structure_labels_and_colors():
    svc, ds = CalculationService(DataStore()), DataStore()
    for p in ("银黄口服液", "板蓝根颗粒", "六味地黄胶囊"):
        opt = CHART_BUILDERS["结构"](p, "2026-05")
        data = opt["series"][0]["data"]
        total = sum(d["value"] for d in data)
        row = ds.cost_row("中药一厂", p, "2026-05")
        assert abs(total - float(row["单位成本(元/盒)"])) < 1e-9, f"{p} 合计=100% 破坏"
        assert "元" in opt["series"][0]["label"]["formatter"] and "%" in opt["series"][0]["label"]["formatter"]
        color_map = {"直接材料": ELEMENT_COLORS["材料"], "直接人工": ELEMENT_COLORS["人工"],
                     "制造费用": ELEMENT_COLORS["制费"]}
        for d in data:
            assert d["itemStyle"]["color"] == color_map[d["name"]], "要素配色必须统一"


def test_heatmap_full_matrix_and_tooltip():
    opt = CHART_BUILDERS["热力图"]()
    assert len(opt["series"][0]["data"]) == 54
    assert "无缺失值" in opt["title"]["subtext"]
    assert "tooltip" in opt and "dataZoom" in opt and "visualMap" in opt


def test_annotations_all_charts():
    opts = [CHART_BUILDERS["趋势"]("银黄口服液"),
            CHART_BUILDERS["瀑布"]("银黄口服液", "2026-02"),
            CHART_BUILDERS["结构"]("银黄口服液", "2026-05"),
            CHART_BUILDERS["热力图"]()]
    for opt in opts:
        sub = opt["title"]["subtext"]
        assert "数据来源" in sub and "元/盒" in sub and "2026-01~2026-06" in sub
        assert "tooltip" in opt, "悬停提示必须配置"


def test_frontend_resize_listener():
    src = open(r"D:\23生信-团日活动（学习雷锋）\重庆比赛AI\project\frontend\app.py",
               encoding="utf-8").read()
    assert "addEventListener('resize'" in src and "chart.resize()" in src, \
        "前端必须配置容器自适应缩放"
