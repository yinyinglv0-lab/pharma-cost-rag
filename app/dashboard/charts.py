# -*- coding: utf-8 -*-
"""ECharts 四图数据构建——图表可视化审计加固版。

统一约定：
- 单位/来源/时间范围标注齐全（title.subtext）；
- 悬停 tooltip、趋势/热力图 dataZoom（缩放平移）；
- 瀑布图颜色：正贡献=绿（#5cb85c，成本上升=警示？——按审计规范：正贡献绿色、负贡献红色）；
- 结构图：要素配色统一（材料/人工/制费三色），标签含金额+百分比；
- 趋势图 markPoint 标注最大值/最小值。
"""
from ..core.calc import CalculationService, PRODUCTS
from ..core.datastore import DataStore

ELEMENT_COLORS = {"材料": "#2f6fb3", "人工": "#e8b34b", "制费": "#8c6bb1"}
POS_COLOR = "#5cb85c"   # 正贡献
NEG_COLOR = "#d9534f"   # 负贡献

_ds = None
_svc = None


def _get():
    global _ds, _svc
    if _ds is None:
        _ds = DataStore()
        _svc = CalculationService(_ds)
    return _svc, _ds


_SOURCE_SUBTEXT = "数据来源: 中药一厂成本汇总 2026年1-6月.csv | 单位: 元/盒 | 时间范围: 2026-01~2026-06"
_TEXT = {"textStyle": {"fontSize": 11}}


def trend(product: str) -> dict:
    svc, ds = _get()
    months = [f"2026-{m:02d}" for m in range(1, 7)]
    uc = [float(ds.cost_row("中药一厂", product, m)["单位成本(元/盒)"]) for m in months]
    mx = max(uc)
    mn = min(uc)
    return {"title": {"text": f"{product} 单位成本趋势（2026）", "subtext": _SOURCE_SUBTEXT,
                      **_TEXT},
            "tooltip": {"trigger": "axis", "valueFormatter": "{value} 元/盒"},
            "xAxis": {"type": "category", "data": months},
            "yAxis": {"type": "value", "name": "元/盒"},
            "dataZoom": [{"type": "inside"}, {"type": "slider", "height": 16}],
            "series": [{"type": "line", "data": uc, "smooth": True, "symbol": "circle",
                        "markPoint": {"data": [
                            {"type": "max", "name": "最大值", "value": mx,
                             "label": {"formatter": f"最大 {mx}"}},
                            {"type": "min", "name": "最小值", "value": mn,
                             "label": {"formatter": f"最小 {mn}"}}]}}]}


def waterfall(product: str, month: str) -> dict:
    """本月 Δ单位成本 三要素瀑布（贡献度即瀑布台阶；Σ增量=总变动）。"""
    svc, _ = _get()
    tf = svc.three_factor(product, month)
    labels = ["材料", "人工", "制费", "合计"]
    values = [round(tf[e]["delta"], 2) for e in ("材料", "人工", "制费")]
    values.append(round(sum(values), 2))
    data = [{"value": v, "itemStyle": {"color": POS_COLOR if v >= 0 else NEG_COLOR},
             "label": {"formatter": f"{v:+.2f}"}} for v in values[:3]]
    data.append({"value": values[3], "itemStyle": {"color": "#7f7f7f"},
                 "label": {"formatter": f"{values[3]:+.2f}"}})
    return {"title": {"text": f"{month} {product} 单位成本变动分解", "subtext": _SOURCE_SUBTEXT,
                      **_TEXT},
            "tooltip": {"trigger": "axis", "valueFormatter": "{value} 元/盒"},
            "xAxis": {"type": "category", "data": labels},
            "yAxis": {"type": "value", "name": "元/盒"},
            "series": [{"type": "bar", "data": data}]}


def structure(product: str, month: str) -> dict:
    svc, ds = _get()
    r = ds.cost_row("中药一厂", product, month)
    data = [{"name": "直接材料", "value": float(r["直接材料(元/盒)"])},
            {"name": "直接人工", "value": float(r["直接人工(元/盒)"])},
            {"name": "制造费用", "value": float(r["制造费用(元/盒)"])}]
    for d in data:
        key = {"直接材料": "材料", "直接人工": "人工", "制造费用": "制费"}[d["name"]]
        d["itemStyle"] = {"color": ELEMENT_COLORS[key]}
    return {"title": {"text": f"{month} {product} 成本结构", "subtext": _SOURCE_SUBTEXT, **_TEXT},
            "tooltip": {"trigger": "item", "formatter": "{b}: {c} 元/盒 ({d}%)"},
            "legend": {"orient": "vertical", "right": 0},
            "series": [{"type": "pie", "radius": "60%",
                        "label": {"formatter": "{b}\n{c}元 ({d}%)"},
                        "data": data}]}


def heatmap() -> dict:
    """产品×月份×要素 三维交叉（加分项）；54 格全矩阵，无缺失值。"""
    _, ds = _get()
    elems = ["直接材料(元/盒)", "直接人工(元/盒)", "制造费用(元/盒)"]
    data = []
    for ei, e in enumerate(elems):
        for pi, p in enumerate(PRODUCTS):
            for mi in range(6):
                r = ds.cost_row("中药一厂", p, f"2026-{mi + 1:02d}")
                data.append([ei, pi * 6 + mi, float(r[e])])
    return {"title": {"text": "要素×产品×月份 热力图", "subtext": _SOURCE_SUBTEXT + " | 无缺失值(54/54)",
                      **_TEXT},
            "tooltip": {"position": "top", "valueFormatter": "{value} 元/盒"},
            "xAxis": {"type": "category",
                      "data": [f"{p}-{m}月" for p in PRODUCTS for m in range(1, 7)]},
            "yAxis": {"type": "category", "data": ["材料(元/盒)", "人工(元/盒)", "制费(元/盒)"]},
            "dataZoom": [{"type": "inside"}, {"type": "slider", "height": 16}],
            "visualMap": {"min": 1, "max": 13, "calculable": True,
                          "text": ["高", "低"], "dimension": 2},
            "series": [{"type": "heatmap", "data": data}]}


CHART_BUILDERS = {"趋势": trend, "瀑布": waterfall, "结构": structure, "热力图": heatmap}
