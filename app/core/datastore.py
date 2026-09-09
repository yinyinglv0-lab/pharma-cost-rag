# -*- coding: utf-8 -*-
"""统一数据访问层：唯一合法取数入口。

规则：
- 月份内部统一 "YYYY-MM"（如 "2026-05"），展示层才转中文；
- 行情表仅覆盖 2026 年上半年，跨年取数会被断言拦截；
- 所有定位器对缺失数据抛 KeyError——不允许静默返回错误数字。
"""
import os
from pathlib import Path

import pandas as pd

DEFAULT_DATA_BASE = Path(os.environ.get(
    "COST_DATA_DIR",
    r"D:\23生信-团日活动（学习雷锋）\重庆比赛AI\创灵境_考题模拟数据0816\创灵境_考题模拟数据",
))


class DataStore:
    def __init__(self, base_dir=None):
        base = Path(base_dir) if base_dir else DEFAULT_DATA_BASE
        self._cost = {}
        for plant, year in [("中药一厂", "2025"), ("中药一厂", "2026"),
                            ("中药二厂", "2025"), ("中药二厂", "2026")]:
            self._cost[(plant, year)] = pd.read_csv(
                base / "01_成本明细数据" / f"{plant}_成本汇总_{year}年1-6月.csv",
                encoding="utf-8-sig")
        self.material = pd.read_csv(
            base / "01_成本明细数据" / "中药一厂_原材料消耗明细_2026年1-6月.csv", encoding="utf-8-sig")
        self.overhead = pd.read_csv(
            base / "01_成本明细数据" / "中药一厂_制造费用明细_2026年1-6月.csv", encoding="utf-8-sig")
        self.labor = pd.read_csv(
            base / "01_成本明细数据" / "中药一厂_人工工时明细_2026年1-6月.csv", encoding="utf-8-sig")
        self.budget = pd.read_csv(
            base / "01_成本明细数据" / "中药一厂_预算数据_2026年.csv", encoding="utf-8-sig")
        self.market = pd.read_csv(
            base / "02_行业参考数据" / "药材市场价格行情_2026年上半年.csv", encoding="utf-8-sig")
        self.benchmark = pd.read_csv(
            base / "02_行业参考数据" / "行业成本基准数据_2026.csv", encoding="utf-8-sig")

    # ---------- 访问器与定位器 ----------
    def cost(self, factory: str, year: str) -> pd.DataFrame:
        return self._cost[(factory, year)]

    @staticmethod
    def norm_month(month: str) -> str:
        assert len(month) == 7 and month[4] == "-", f"月份必须为 YYYY-MM: {month!r}"
        return month

    def cost_row(self, factory, product, month):
        month = self.norm_month(month)
        df = self.cost(factory, month[:4])
        hit = df[(df["产品名称"] == product) & (df["月份"] == month)]
        if hit.empty:
            raise KeyError(f"cost_row 未找到: {factory} {product} {month}")
        return hit.iloc[0]

    def material_rows(self, product, month):
        month = self.norm_month(month)
        return self.material[(self.material["产品名称"] == product) & (self.material["月份"] == month)]

    def material_unit_cost(self, product, material, month):
        rows = self.material_rows(product, month)
        hit = rows[rows["原材料名称"] == material]
        if hit.empty:
            raise KeyError(f"原材料未找到: {product} {material} {month}")
        return float(hit.iloc[0]["单位消耗成本(元/盒)"])

    def overhead_rows(self, product, month):
        month = self.norm_month(month)
        return self.overhead[(self.overhead["产品名称"] == product) & (self.overhead["月份"] == month)]

    def labor_row(self, product, month):
        month = self.norm_month(month)
        hit = self.labor[(self.labor["产品名称"] == product) & (self.labor["月份"] == month)]
        if hit.empty:
            raise KeyError(f"labor_row 未找到: {product} {month}")
        return hit.iloc[0]

    def budget_row(self, product, month):
        month = self.norm_month(month)
        hit = self.budget[(self.budget["产品名称"] == product) & (self.budget["月份"] == month)]
        if hit.empty:
            raise KeyError(f"budget_row 未找到: {product} {month}")
        return hit.iloc[0]

    def market_price(self, material, month):
        month = self.norm_month(month)
        assert month.startswith("2026"), "行情表仅覆盖 2026 年上半年"
        col = f"{int(month[5:7])}月价格"
        hit = self.market[self.market["药材名称"] == material]
        if hit.empty:
            raise KeyError(f"行情未找到: {material}")
        return float(hit.iloc[0][col])
