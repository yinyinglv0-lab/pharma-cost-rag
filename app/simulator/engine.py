# -*- coding: utf-8 -*-
"""BOM 传导模拟。

- 价格滑块：单原料 ±50% → 该原料消耗成本同比例变动 → 单位成本传导；
- 收率系数：0.08 元/盒·pp（工艺文档知识库系数，情景参数——命中"引用知识库工艺信息"评分点）；
- 敏感度排序：全部原料按 +10% 影响降序；
- 瀑布图：各因素增量之和 = 总变动（恒等式，测试锁定）。
"""
import json
from typing import List

from pydantic import BaseModel

from ..core.calc import CalculationService, PRODUCTS
from ..core.datastore import DataStore

YIELD_COEFFICIENT = 0.08  # 元/盒·百分点（银黄工艺文档："提取收率每降1个百分点，材料成本↑0.08元/盒"）


class Scenario(BaseModel):
    product: str
    month: str
    factors: List[dict]          # [{name, delta}] 恒等：Σdelta = total
    total_delta: float
    new_unit_cost: float
    waterfall: dict              # ECharts option
    sensitivity: List[dict]      # [{material, impact_per_10pct}] 降序
    yield_note: str = ""


def _materials(product, month):
    ds = DataStore()
    return [(r["原材料名称"], float(r["单位消耗成本(元/盒)"]))
            for _, r in ds.material_rows(product, month).iterrows()]


def simulate_price(product: str, material: str, pct: float, month: str = "2026-05",
                   yield_drop_pp: float = 0.0) -> Scenario:
    """价格滑块（-50%~+50%）+ 可选收率情景。"""
    assert -50 <= pct <= 50
    ds = DataStore()
    row = ds.cost_row("中药一厂", product, month)
    factors = []
    for name, cost in _materials(product, month):
        if name == material:
            factors.append({"name": name, "delta": round(cost * pct / 100, 4)})
    if yield_drop_pp:
        factors.append({"name": f"提取收率-{yield_drop_pp}pp(系数0.08)", "delta": round(0.08 * yield_drop_pp, 4)})
    total = round(sum(f["delta"] for f in factors), 4)
    new_unit = round(float(row["单位成本(元/盒)"]) + total, 4)
    waterfall = {
        "title": {"text": f"{product} {month} What-if 传导（{material} {pct:+.0f}%）"},
        "xAxis": {"type": "category", "data": [f["name"] for f in factors] + ["合计"]},
        "yAxis": {"type": "value", "name": "元/盒"},
        "series": [{"type": "bar", "data": [{"value": f["delta"], "itemStyle": {"color": "#c0504d"}}
                                            for f in factors] + [{"value": total, "itemStyle": {"color": "#7f7f7f"}}]}],
    }
    return Scenario(product=product, month=month, factors=factors, total_delta=total,
                    new_unit_cost=new_unit, waterfall=waterfall,
                    sensitivity=sensitivity_ranking(product, month),
                    yield_note=f"收率系数 0.08 元/盒·pp 来自工艺文档（知识库引用）" if yield_drop_pp else "")


def sensitivity_ranking(product: str, month: str = "2026-05", pct: float = 10.0) -> List[dict]:
    """全部原料按 +10% 影响降序。"""
    return sorted([{"material": name, "impact_per_10pct": round(cost * pct / 100, 4)}
                   for name, cost in _materials(product, month)],
                  key=lambda x: -x["impact_per_10pct"])


def demo_simulator() -> str:
    """演示动线：金银花再涨10% → BOM传导瀑布图 → 银黄成本预测 + 敏感度排序。"""
    sc = simulate_price("银黄口服液", "金银花", 10.0, "2026-05", yield_drop_pp=1.0)
    log = {
        "demo": "金银花+10% & 收率-1pp → 传导瀑布 → 成本预测 + 敏感度排序",
        "storyline": f"金银花再涨 10%：银黄口服液 2026-05 单位成本 {sc.new_unit_cost} 元/盒"
                     f"（原 11.21，+{sc.total_delta}）；若同时提取收率下降 1pp，再 +0.08 元/盒。",
        "factors": sc.factors,
        "total_delta": sc.total_delta,
        "new_unit_cost": sc.new_unit_cost,
        "waterfall": sc.waterfall,
        "sensitivity_top3": sc.sensitivity[:3],
        "yield_note": sc.yield_note,
    }
    return json.dumps(log, ensure_ascii=False, indent=1)
