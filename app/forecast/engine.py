# -*- coding: utf-8 -*-
"""时序预测 + 双重差分整改效果评估（两条诚实警告必须输出）。"""
import json
import statistics
from typing import List

from pydantic import BaseModel

from ..core.calc import CalculationService
from ..core.datastore import DataStore

DID_WARNINGS = [
    "⚠️ 单期启发式估计（n=1 个月对，仅作方向性参考，不具备统计显著性）",
    "⚠️ 存在行情混淆（如金银花 6 月行情自身回落 -3.3%，市场效应与整改效应无法分离）",
]


class Forecast(BaseModel):
    product: str
    month: str
    moving_average_3: float
    exponential_smoothing: float
    confidence_band: float
    history: List[float]


class DiDResult(BaseModel):
    product: str
    target: str
    control: str
    month: str
    target_mom_pct: float
    control_mom_pct: float
    net_effect_pct: float
    warnings: List[str]


def forecast_unit_cost(product: str, month: str = "2026-07", alpha: float = 0.3) -> Forecast:
    ds = DataStore()
    hist = [float(ds.cost_row("中药一厂", product, f"2026-{m:02d}")["单位成本(元/盒)"])
            for m in range(1, 7)]
    ma3 = round(sum(hist[-3:]) / 3, 4)
    es = hist[0]
    for v in hist[1:]:
        es = alpha * v + (1 - alpha) * es
    band = round(statistics.pstdev(hist), 4)
    return Forecast(product=product, month=month, moving_average_3=ma3,
                    exponential_smoothing=round(es, 4), confidence_band=band,
                    history=hist)


def did_effect(product: str, target: str = "材料", control: str = "人工",
               month: str = "2026-06") -> DiDResult:
    """干预前后对比：目标要素环比 − 对照要素环比（同产品同月）。"""
    svc = CalculationService(DataStore())
    t = svc.mom(product, month, target)
    c = svc.mom(product, month, control)
    return DiDResult(product=product, target=target, control=control, month=month,
                     target_mom_pct=round(t, 2), control_mom_pct=round(c, 2),
                     net_effect_pct=round(t - c, 2), warnings=list(DID_WARNINGS))


def demo_forecast() -> str:
    """演示动线：预测线 + '整改后成本下降X（⚠️单期启发式，行情可能混淆）'。"""
    f = forecast_unit_cost("银黄口服液")
    d = did_effect("银黄口服液")
    log = {
        "demo": f"预测线：银黄 2026-07 单位成本 MA3={f.moving_average_3} / ES(α=0.3)={f.exponential_smoothing}"
                f"（历史σ={f.confidence_band}）；整改净效应：材料环比 {d.target_mom_pct}% − 人工环比 "
                f"{d.control_mom_pct}% = {d.net_effect_pct}pp",
        "forecast": f.model_dump(),
        "did": d.model_dump(),
    }
    return json.dumps(log, ensure_ascii=False, indent=1)
