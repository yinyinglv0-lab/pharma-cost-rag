# -*- coding: utf-8 -*-
"""ECharts 四图数据构建（趋势/瀑布/结构/热力图）——纯 option dict，前端直接渲染。"""
from ..core.calc import CalculationService, PRODUCTS
from ..core.datastore import DataStore

_ds = None
_svc = None


def _get():
    global _ds, _svc
    if _ds is None:
        _ds = DataStore()
        _svc = CalculationService(_ds)
    return _svc, _ds


_SOURCE_SUBTEXT = "数据来源: 中药一厂成本汇总 2026年1-6月.csv | 单位: 元/盒 | 时间范围: 2026-01~2026-06"


def trend(product: str) -> dict:
    svc, ds = _get()
    months = [f"2026-{m:02d}" for m in range(1, 7)]
    uc = [float(ds.cost_row("中药一厂", product, m)["单位成本(元/盒)"]) for m in months]
    return {"title": {"text": f"{product} 单位成本趋势（2026）", "subtext": _SOURCE_SUBTEXT},
            "xAxis": {"type": "category", "data": months},
            "yAxis": {"type": "value", "name": "元/盒"},
            "series": [{"type": "line", "data": uc, "smooth": True, "symbol": "circle"}]}


def waterfall(product: str, month: str) -> dict:
    """本月 Δ单位成本 三要素瀑布（贡献度即瀑布台阶）。"""
    svc, _ = _get()
    tf = svc.three_factor(product, month)
    labels = ["材料", "人工", "制费", "合计"]
    values = [round(tf[e]["delta"], 2) for e in ("材料", "人工", "制费")]
    values.append(round(sum(values), 2))
    return {"title": {"text": f"{month} {product} 单位成本变动分解", "subtext": _SOURCE_SUBTEXT},
            "xAxis": {"type": "category", "data": labels},
            "yAxis": {"type": "value", "name": "元/盒"},
            "series": [{"type": "bar",
                        "data": [{"value": v, "itemStyle": {"color": "#c0504d" if v >= 0 else "#4f81bd"}}
                                 for v in values]}]}


def structure(product: str, month: str) -> dict:
    svc, ds = _get()
    r = ds.cost_row("中药一厂", product, month)
    return {"title": {"text": f"{month} {product} 成本结构", "subtext": _SOURCE_SUBTEXT},
            "tooltip": {"trigger": "item", "formatter": "{b}: {c} 元/盒 ({d}%)"},
            "series": [{"type": "pie", "radius": "60%",
                        "data": [{"name": "直接材料", "value": float(r["直接材料(元/盒)"])},
                                 {"name": "直接人工", "value": float(r["直接人工(元/盒)"])},
                                 {"name": "制造费用", "value": float(r["制造费用(元/盒)"])}]}]}


def heatmap() -> dict:
    """产品×月份×要素 三维交叉（加分项）。"""
    _, ds = _get()
    elems = ["直接材料(元/盒)", "直接人工(元/盒)", "制造费用(元/盒)"]
    data = []
    for ei, e in enumerate(elems):
        for pi, p in enumerate(PRODUCTS):
            for mi in range(6):
                r = ds.cost_row("中药一厂", p, f"2026-{mi + 1:02d}")
                data.append([ei, pi * 6 + mi, float(r[e])])
    return {"title": {"text": "要素×产品×月份 热力图", "subtext": _SOURCE_SUBTEXT},
            "xAxis": {"type": "category",
                      "data": [f"{p}-{m}月" for p in PRODUCTS for m in range(1, 7)]},
            "yAxis": {"type": "category", "data": ["材料(元/盒)", "人工(元/盒)", "制费(元/盒)"]},
            "visualMap": {"min": 1, "max": 13, "calculable": True,
                          "text": ["高", "低"], "dimension": 2},
            "series": [{"type": "heatmap", "data": data}]}


CHART_BUILDERS = {"趋势": trend, "瀑布": waterfall, "结构": structure, "热力图": heatmap}
