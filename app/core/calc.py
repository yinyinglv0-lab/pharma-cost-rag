# -*- coding: utf-8 -*-
"""计算服务：唯一合法的数字来源（单一事实源）。

铁律（v7 终版）：
- 一切报告数字只允许来自本模块；
- 价量分解只输出"变动贡献"（对数分解），绝对单耗不可校准（理论 vs 实际两套口径）；
- 同一比值的多个量必须取自同一时间窗口（窗口对齐硬规则）；
- 固定/变动分解统一最小二乘回归并标注 R²，高低点法仅作敏感性参照。
"""
from typing import Dict, List

import numpy as np

from .datastore import DataStore

PRODUCTS = ["银黄口服液", "板蓝根颗粒", "六味地黄胶囊"]
ELEMENTS = {
    "材料": "直接材料(元/盒)",
    "人工": "直接人工(元/盒)",
    "制费": "制造费用(元/盒)",
    "单位成本": "单位成本(元/盒)",
}
# 六味配方 PDF 2.3 表：单盒材料成本理论值约 2.20 元（PDF 注明实际约为理论值的 5-6 倍）
LIUWEI_THEORETICAL_MATERIAL = 2.20
MONTHS_2026 = [f"2026-{m:02d}" for m in range(1, 7)]


class CalculationService:
    def __init__(self, ds: DataStore):
        self.ds = ds

    # ---------- 基础取值 ----------
    def element_value(self, product, month, element, factory="中药一厂"):
        return float(self.ds.cost_row(factory, product, month)[ELEMENTS[element]])

    @staticmethod
    def _prev_month(month: str) -> str:
        y, m = int(month[:4]), int(month[5:7])
        assert m > 1, "数据包内不跨年取上月"
        return f"{y}-{m-1:02d}"

    @staticmethod
    def _month_idx(month: str) -> int:
        return int(month[5:7]) - 1  # "2026-01" -> 0

    # ---------- 环比 / 同比 / 预算偏差 ----------
    def mom(self, product, month, element, factory="中药一厂"):
        """环比 (%)。month 为 02~06。"""
        v0 = self.element_value(product, self._prev_month(month), element, factory)
        v1 = self.element_value(product, month, element, factory)
        return (v1 / v0 - 1) * 100

    def _weighted_unit_cost(self, factory, year, product):
        sub = self.ds.cost(factory, year)
        sub = sub[sub["产品名称"] == product]
        return float((sub["单位成本(元/盒)"] * sub["产量(盒)"]).sum() / sub["产量(盒)"].sum())

    def yoy_unit_cost(self, product, factory="中药一厂"):
        """单位成本加权同比（%）= Σ总成本/Σ产量，2026H1 vs 2025H1（口径与问题检查报告一致）。"""
        return (self._weighted_unit_cost(factory, "2026", product)
                / self._weighted_unit_cost(factory, "2025", product) - 1) * 100

    def yoy_unit_cost_overall(self, factory="中药一厂"):
        t26 = self.ds.cost(factory, "2026")["总成本(元)"].sum()
        q26 = self.ds.cost(factory, "2026")["产量(盒)"].sum()
        t25 = self.ds.cost(factory, "2025")["总成本(元)"].sum()
        q25 = self.ds.cost(factory, "2025")["产量(盒)"].sum()
        return ((t26 / q26) / (t25 / q25) - 1) * 100

    def yoy_total_cost_overall(self, factory="中药一厂"):
        """总成本同比（%，含产量增长效应——与单位成本口径不同，展示时必须显式标注口径）。"""
        t26 = self.ds.cost(factory, "2026")["总成本(元)"].sum()
        t25 = self.ds.cost(factory, "2025")["总成本(元)"].sum()
        return (t26 / t25 - 1) * 100

    def budget_deviation(self, product, month, element):
        """预算偏差（%）= (实际-预算)/预算。"""
        v = self.element_value(product, month, element)
        b = float(self.ds.budget_row(product, month)[f"预算{ELEMENTS[element]}"])
        return (v / b - 1) * 100

    # ---------- 三因素分解 / 贡献度 ----------
    def three_factor(self, product, month):
        """Δ单位成本分解为 材料/人工/制费 三要素：delta(元/盒) / share_pct(%) / rate_pct(%)。"""
        out: Dict[str, dict] = {}
        u0 = self.element_value(product, self._prev_month(month), "单位成本")
        u1 = self.element_value(product, month, "单位成本")
        d_unit = u1 - u0
        for elem in ("材料", "人工", "制费"):
            v0 = self.element_value(product, self._prev_month(month), elem)
            v1 = self.element_value(product, month, elem)
            delta = v1 - v0
            out[elem] = {
                "delta": delta,
                "share_pct": (delta / d_unit * 100) if d_unit else 0.0,
                "rate_pct": (v1 / v0 - 1) * 100,
            }
        out["unit_cost_delta"] = d_unit
        return out

    def contribution(self, product, month):
        """贡献度 = 要素变动额 / 单位成本变动额 × 100%（单位成本口径，恒和 100）。"""
        tf = self.three_factor(product, month)
        return {e: tf[e]["share_pct"] for e in ("材料", "人工", "制费")}

    # ---------- 固定/变动分解（回归口径，R² 标注） ----------
    def _month_totals(self, product, cost_type):
        if cost_type == "制费":
            return np.array([sum(r["费用总额(元)"] for _, r in self.ds.overhead_rows(product, m).iterrows())
                             for m in MONTHS_2026], dtype=float)
        return np.array([float(self.ds.labor_row(product, m)["直接人工总额(元)"]) for m in MONTHS_2026], dtype=float)

    def _volumes(self, product):
        return np.array([float(self.ds.cost_row("中药一厂", product, m)["产量(盒)"]) for m in MONTHS_2026], dtype=float)

    def regression_fixed_variable(self, product, cost_type):
        """最小二乘：总额 = a + b×产量（6 点）。cost_type: '制费' | '人工'。返回 {a, b, r2}。"""
        totals, Q = self._month_totals(product, cost_type), self._volumes(product)
        X = np.column_stack([np.ones(len(Q)), Q])
        beta, *_ = np.linalg.lstsq(X, totals, rcond=None)
        a, b = float(beta[0]), float(beta[1])
        yhat = X @ beta
        r2 = 1 - float(((totals - yhat) ** 2).sum()) / float(((totals - totals.mean()) ** 2).sum())
        return {"a": a, "b": b, "r2": r2}

    def high_low(self, product, cost_type):
        """高低点法（2 月低点 / 5 月高点）——仅作敏感性参照，不用于正式数字。"""
        totals, Q = self._month_totals(product, cost_type), self._volumes(product)
        lo, hi = 1, 4
        b = (totals[hi] - totals[lo]) / (Q[hi] - Q[lo])
        a = totals[lo] - b * Q[lo]
        return {"a": float(a), "b": float(b)}

    def dilution_split(self, product, cost_type):
        """1→2 月单位费用上升拆分：摊薄 = a×(1/Q2-1/Q1)，漂移 = Δ单位 - 摊薄（回归口径 a）。"""
        reg = self.regression_fixed_variable(product, cost_type)
        a = reg["a"]
        q1, q2 = self._volumes(product)[0], self._volumes(product)[1]
        col = ELEMENTS["制费"] if cost_type == "制费" else ELEMENTS["人工"]
        u1 = float(self.ds.cost_row("中药一厂", product, "2026-01")[col])
        u2 = float(self.ds.cost_row("中药一厂", product, "2026-02")[col])
        dilution = a * (1 / q2 - 1 / q1)
        drift = (u2 - u1) - dilution
        return {"dilution": float(dilution), "drift": float(drift), "a": a}

    # ---------- 价量分解（变动口径） ----------
    def implied_unit_consumption(self, product, material):
        """隐含单耗 = 消耗成本 ÷ 行情价（kg/盒）。

        绝对水平不可校准（理论投料 vs 含损耗实际两套口径），仅用于变动分析。
        返回 {months, values, mean, cv_pct}。
        """
        vals = np.array([self.ds.material_unit_cost(product, material, m)
                         / self.ds.market_price(material, m) for m in MONTHS_2026], dtype=float)
        return {"months": MONTHS_2026, "values": vals,
                "mean": float(vals.mean()),
                "cv_pct": float(vals.std(ddof=1) / vals.mean() * 100)}

    def window_change(self, product, material, m1, m2):
        """窗口对齐硬规则：单耗变动与行情变动同窗口一次返回，杜绝窗口错配。

        返回 {window, unit_pct, price_pct, ratio, monotonic}——三者严格同一窗口。
        """
        u = self.implied_unit_consumption(product, material)["values"]
        i1, i2 = self._month_idx(m1), self._month_idx(m2)
        assert i1 < i2, "m1 必须早于 m2"
        unit_pct = (u[i2] / u[i1] - 1) * 100
        price_pct = (self.ds.market_price(material, m2) / self.ds.market_price(material, m1) - 1) * 100
        monotonic = bool(all(u[k] >= u[k - 1] for k in range(i1 + 1, i2 + 1)))
        ratio = abs(price_pct / unit_pct) if unit_pct else float("inf")
        return {"window": f"{m1}→{m2}", "unit_pct": float(unit_pct),
                "price_pct": float(price_pct), "ratio": float(ratio), "monotonic": monotonic}

    # ---------- 对标差异（2026H1 产量加权） ----------
    def benchmark_diff(self, product, element, year="2026"):
        """(一厂加权平均 - 二厂加权平均) / 二厂 × 100%。符号即方向，负号=一厂更低。"""
        col = ELEMENTS[element]

        def wavg(factory):
            sub = self.ds.cost(factory, year)
            sub = sub[sub["产品名称"] == product]
            return float((sub[col] * sub["产量(盒)"]).sum() / sub["产量(盒)"].sum())

        v1, v2 = wavg("中药一厂"), wavg("中药二厂")
        return (v1 / v2 - 1) * 100

    # ---------- 阈值校准（分层） ----------
    def threshold_peaks(self, years=("2026",)):
        """要素级最大 |环比|：全产品 × 各年 02~06 月。"""
        peaks = {e: [0.0, None] for e in ("材料", "人工", "制费")}
        for y in years:
            for p in PRODUCTS:
                for m in [f"{y}-{mm:02d}" for mm in range(2, 7)]:
                    for e in ("材料", "人工", "制费"):
                        v = self.mom(p, m, e)
                        if abs(v) > peaks[e][0]:
                            peaks[e] = [abs(v), f"{p} {self._prev_month(m)}→{m}"]
        return {e: {"peak_pct": peaks[e][0], "where": peaks[e][1]} for e in peaks}

    def aggregate_peaks(self, years=("2026",)):
        """汇总级：产量 / 总成本 最大 |环比|。"""
        best = {"产量": [0.0, None], "总成本": [0.0, None]}
        for y in years:
            for p in PRODUCTS:
                for m in [f"{y}-{mm:02d}" for mm in range(2, 7)]:
                    r0 = self.ds.cost_row("中药一厂", p, self._prev_month(m))
                    r1 = self.ds.cost_row("中药一厂", p, m)
                    vq = abs(float(r1["产量(盒)"]) / float(r0["产量(盒)"]) - 1) * 100
                    vt = abs(float(r1["总成本(元)"]) / float(r0["总成本(元)"]) - 1) * 100
                    if vq > best["产量"][0]:
                        best["产量"] = [vq, f"{p} {m}"]
                    if vt > best["总成本"][0]:
                        best["总成本"] = [vt, f"{p} {m}"]
        return {k: {"peak_pct": best[k][0], "where": best[k][1]} for k in best}

    # ---------- 人工工时派生指标 ----------
    def labor_metrics(self, product, month):
        r = self.ds.labor_row(product, month)
        wage = float(r["直接人工总额(元)"]) / float(r["总工时(小时)"])
        hpb = float(r["总工时(小时)"]) / float(r["产量(盒)"])
        return {"wage_rate": wage, "hour_per_box": hpb}

    # ---------- 专项核验 ----------
    def depreciation_series(self, product):
        out = []
        for m in MONTHS_2026:
            rows = self.ds.overhead_rows(product, m)
            hit = rows[rows["费用类别"] == "折旧费"]
            out.append(float(hit.iloc[0]["费用总额(元)"]))
        return out

    def overhead_gap_free(self):
        """维修费无足迹：制费明细中不存在 8,000-9,000 元记录（设备清单 8500 元维修费无对应）。"""
        vals = self.ds.overhead["费用总额(元)"].values
        return not bool(((vals >= 8000) & (vals <= 9000)).any())

    def liuwei_material_mean(self):
        sub = self.ds.cost("中药一厂", "2026")
        sub = sub[sub["产品名称"] == "六味地黄胶囊"]
        return float(sub["直接材料(元/盒)"].mean())

    def industry_ratios(self, product):
        """2026H1 三要素占单位成本比重（%）——与行业基准"本厂水平"列核对。"""
        sub = self.ds.cost("中药一厂", "2026")
        sub = sub[sub["产品名称"] == product]
        q = sub["产量(盒)"]

        def w(col):
            return float((sub[col] * q).sum() / q.sum())

        u = w("单位成本(元/盒)")
        return {"材料": w("直接材料(元/盒)") / u * 100,
                "人工": w("直接人工(元/盒)") / u * 100,
                "制费": w("制造费用(元/盒)") / u * 100}

    def unit_cost_per(self, product):
        """折单位成本（元/支、元/袋、元/粒）。"""
        units = {"银黄口服液": 10, "板蓝根颗粒": 20, "六味地黄胶囊": 60}
        sub = self.ds.cost("中药一厂", "2026")
        sub = sub[sub["产品名称"] == product]
        u = float((sub["单位成本(元/盒)"] * sub["产量(盒)"]).sum() / sub["产量(盒)"].sum())
        return u / units[product]
