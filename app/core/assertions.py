# -*- coding: utf-8 -*-
"""恒等式断言库。

全部使用出题方《问题检查报告》声明的恒等式 + 七轮评审验证的关系。
任何一条失败 = 计算层或数据被破坏，报告生成必须阻断。
"""
import numpy as np

from .calc import MONTHS_2026, PRODUCTS


def run_all(ds, calc) -> list:
    results = []

    def add(name, ok, detail=""):
        results.append({"name": name, "ok": bool(ok), "detail": str(detail)})

    # A1 单位成本恒等式（全部成本汇总行，共 72 行）
    bad = []
    for (factory, year), df in ds._cost.items():
        for _, r in df.iterrows():
            s = r["直接材料(元/盒)"] + r["直接人工(元/盒)"] + r["制造费用(元/盒)"]
            if abs(s - r["单位成本(元/盒)"]) > 1e-6:
                bad.append((factory, year, r["产品名称"], r["月份"]))
    add("A1 单位成本=材料+人工+制费(72行)", not bad, bad[:3])

    # A2 总成本=产量×单位成本
    bad = []
    for (factory, year), df in ds._cost.items():
        for _, r in df.iterrows():
            if abs(r["总成本(元)"] - r["产量(盒)"] * r["单位成本(元/盒)"]) > 0.5:
                bad.append((factory, year, r["产品名称"], r["月份"]))
    add("A2 总成本=产量×单位成本(72行)", not bad, bad[:3])

    # A3 原材料明细合计=材料总额（一厂 2026，18 组）
    bad = []
    for p in PRODUCTS:
        for m in MONTHS_2026:
            detail = ds.material_rows(p, m)["原材料总成本(元)"].sum()
            total = ds.cost_row("中药一厂", p, m)["直接材料(元/盒)"] * ds.cost_row("中药一厂", p, m)["产量(盒)"]
            if abs(detail - total) > 0.5:
                bad.append((p, m, detail, total))
    add("A3 原材料明细合计=材料总额(18组)", not bad, bad[:3])

    # A4 制造费用明细合计=制费总额（18 组）
    bad = []
    for p in PRODUCTS:
        for m in MONTHS_2026:
            detail = ds.overhead_rows(p, m)["费用总额(元)"].sum()
            total = ds.cost_row("中药一厂", p, m)["制造费用(元/盒)"] * ds.cost_row("中药一厂", p, m)["产量(盒)"]
            if abs(detail - total) > 0.5:
                bad.append((p, m, detail, total))
    add("A4 制造费用明细合计=制费总额(18组)", not bad, bad[:3])

    # A5 人工明细=成本汇总（18 组）
    bad = []
    for p in PRODUCTS:
        for m in MONTHS_2026:
            detail = ds.labor_row(p, m)["直接人工总额(元)"]
            total = ds.cost_row("中药一厂", p, m)["直接人工(元/盒)"] * ds.cost_row("中药一厂", p, m)["产量(盒)"]
            if abs(detail - total) > 0.5:
                bad.append((p, m, detail, total))
    add("A5 人工明细=成本汇总(18组)", not bad, bad[:3])

    # A6 预算月度恒定（年度固定目标，3 产品）
    bad = []
    for p in PRODUCTS:
        vals = ds.budget[ds.budget["产品名称"] == p]["预算单位成本(元/盒)"].unique()
        if len(vals) != 1:
            bad.append((p, vals))
    add("A6 预算月度恒定(3产品)", not bad, bad[:3])

    # A7 行情 13 种 / 明细 18 条产品-原材料组合（17 个唯一名：蔗糖被银黄与板蓝根共用）
    add("A7 行情13种/明细18条组合",
        len(ds.market) == 13 and len(ds.material) == 108
        and ds.material["原材料名称"].nunique() == 17
        and ds.material[["产品名称", "原材料名称"]].drop_duplicates().shape[0] == 18)

    # A8 贡献度和为 100（单位成本口径，15 个月对）
    bad = []
    for p in PRODUCTS:
        for m in MONTHS_2026[1:]:
            s = sum(calc.contribution(p, m).values())
            if abs(s - 100) > 1e-9:
                bad.append((p, m, s))
    add("A8 贡献度和为100(15组)", not bad, bad[:3])

    # A9 三因素分解残差 < 1e-9
    bad = []
    for p in PRODUCTS:
        for m in MONTHS_2026[1:]:
            tf = calc.three_factor(p, m)
            resid = sum(tf[e]["delta"] for e in ("材料", "人工", "制费")) - tf["unit_cost_delta"]
            if abs(resid) > 1e-9:
                bad.append((p, m, resid))
    add("A9 三因素分解残差<1e-9(15组)", not bad, bad[:3])

    # A10 维修费无足迹（设备清单 8500 元无对应）
    add("A10 维修费无足迹(无8000-9000元记录)", calc.overhead_gap_free())

    # A11 折旧总额随产量同向波动（银黄，r>0.9）
    dep = np.array(calc.depreciation_series("银黄口服液"))
    vol = np.array([ds.cost_row("中药一厂", "银黄口服液", m)["产量(盒)"] for m in MONTHS_2026], dtype=float)
    r = float(np.corrcoef(dep, vol)[0, 1])
    add("A11 折旧总额随产量波动(银黄 r>0.9)", r > 0.9, f"r={r:.4f}")

    # A12 窗口对齐结构校验：window_change 三量同窗口（硬规则自检）
    w = calc.window_change("银黄口服液", "黄芩提取物", "2026-04", "2026-06")
    add("A12 窗口对齐规则自检", w["window"] == "2026-04→2026-06")

    return results


def all_pass(results) -> bool:
    return all(r["ok"] for r in results)
