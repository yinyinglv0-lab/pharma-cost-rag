# -*- coding: utf-8 -*-
"""金丝雀基准集：七轮评审独立复算的全部锚点数字。

被 pytest（tests/test_golden.py）与免 pytest 脚本（scripts/run_checks.py）共用。
任何一条失败 = 计算层被破坏，30 秒内报警。
"""
import json
from pathlib import Path

from app.core.calc import CalculationService, LIUWEI_THEORETICAL_MATERIAL, PRODUCTS
from app.core.datastore import DataStore

ROOT = Path(__file__).parent.parent
GOLDEN = json.loads((ROOT / "golden_numbers.json").read_text(encoding="utf-8"))


def all_checks(svc: CalculationService | None = None) -> list:
    if svc is None:
        svc = CalculationService(DataStore())
    G = GOLDEN
    checks = []

    def add(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": str(detail)})

    # 1 对标差异（2026H1 产量加权）
    for elem, products in G["benchmark_diff"].items():
        for p, expected in products.items():
            v = svc.benchmark_diff(p, elem)
            add(f"对标差异·{elem}·{p}", abs(v - expected) < 0.02, f"got {v:.2f}%")

    # 2 同比（单位成本加权 vs 总成本，口径显式）
    for p, expected in G["yoy_unit_cost"].items():
        v = svc.yoy_unit_cost(p) if p != "整体" else svc.yoy_unit_cost_overall()
        add(f"单位成本加权同比·{p}", abs(v - expected) < 0.03, f"got {v:.2f}%")
    v = svc.yoy_total_cost_overall()
    add("总成本同比·整体", abs(v - G["yoy_total_cost"]["整体"]) < 0.03, f"got {v:.2f}%")

    # 3 三因素分解（银黄 2026-02）
    tf = svc.three_factor("银黄口服液", "2026-02")
    for elem in ("材料", "人工", "制费"):
        add(f"三因素·{elem}·delta", abs(tf[elem]["delta"] - G["three_factor"]["deltas"][elem]) < 1e-9,
            tf[elem]["delta"])
        add(f"三因素·{elem}·share", abs(tf[elem]["share_pct"] - G["three_factor"]["shares"][elem]) < 0.05,
            f"{tf[elem]['share_pct']:.2f}%")
        add(f"三因素·{elem}·rate", abs(tf[elem]["rate_pct"] - G["three_factor"]["rates"][elem]) < 0.05,
            f"{tf[elem]['rate_pct']:.2f}%")
    add("三因素·Δ单位成本", abs(tf["unit_cost_delta"] - G["three_factor"]["unit_cost_delta"]) < 1e-9,
        tf["unit_cost_delta"])

    # 4 回归（a/b/R²，方法敏感统一回归口径）
    for ct, exp in G["regression"].items():
        r = svc.regression_fixed_variable("银黄口服液", ct)
        add(f"回归·{ct}·a", abs(r["a"] - exp["a"]) < 5, f"{r['a']:.1f}")
        add(f"回归·{ct}·b", abs(r["b"] - exp["b"]) < 0.003, f"{r['b']:.3f}")
        add(f"回归·{ct}·R²", abs(r["r2"] - exp["r2"]) < 0.002, f"{r['r2']:.3f}")

    # 5 摊薄/漂移拆分（银黄 1→2 月）
    for ct, exp in G["dilution"].items():
        d = svc.dilution_split("银黄口服液", ct)
        add(f"摊薄·{ct}", abs(d["dilution"] - exp["dilution"]) < 0.0005, f"{d['dilution']:.4f}")
        add(f"漂移·{ct}", abs(d["drift"] - exp["drift"]) < 0.0005, f"{d['drift']:.4f}")

    # 6 隐含单耗均值（绝对水平仅做核验，不用于校准）
    for mat, expected in G["implied_mean"].items():
        u = svc.implied_unit_consumption("银黄口服液" if mat in ("金银花", "黄芩提取物")
                                         else ("板蓝根颗粒" if mat == "板蓝根" else "六味地黄胶囊"), mat)
        add(f"隐含单耗均值·{mat}", abs(u["mean"] - expected) < 0.0005, f"{u['mean']:.5f}")

    # 7 黄芩窗口（4→6 月，同一窗口：方向/幅度/比值）
    w = svc.window_change("银黄口服液", "黄芩提取物", "2026-04", "2026-06")
    add("黄芩·单耗4→6月", abs(w["unit_pct"] - G["huangqin_window"]["unit_pct"]) < 0.02, f"{w['unit_pct']:.2f}%")
    add("黄芩·行情4→6月", abs(w["price_pct"] - G["huangqin_window"]["price_pct"]) < 0.03, f"{w['price_pct']:.2f}%")
    add("黄芩·比值", abs(w["ratio"] - G["huangqin_window"]["ratio"]) < 0.1, f"{w['ratio']:.2f}")
    add("黄芩·单调性", w["monotonic"] == G["huangqin_window"]["monotonic"], w["monotonic"])

    # 8 金银花三口径（无任何单一口径=12%）
    for key, (m1, m2) in {"4_5": ("2026-04", "2026-05"),
                          "3_5": ("2026-03", "2026-05"),
                          "1_5": ("2026-01", "2026-05")}.items():
        v = (svc.ds.market_price("金银花", m2) / svc.ds.market_price("金银花", m1) - 1) * 100
        add(f"金银花口径·{key}", abs(v - G["jinyinhua_windows"][key]) < 0.03, f"{v:.2f}%")

    # 9 阈值峰值（2026 单年 / 两年全样本）
    p26 = svc.threshold_peaks(("2026",))
    for e, expected in G["peaks_2026"].items():
        add(f"阈值峰值2026·{e}", abs(p26[e]["peak_pct"] - expected) < 0.02, f"{p26[e]['peak_pct']:.2f}% @ {p26[e]['where']}")
    p2y = svc.threshold_peaks(("2025", "2026"))
    for e, expected in G["peaks_two_year"].items():
        add(f"阈值峰值两年·{e}", abs(p2y[e]["peak_pct"] - expected) < 0.02, f"{p2y[e]['peak_pct']:.2f}% @ {p2y[e]['where']}")

    # 10 汇总级峰值
    agg = svc.aggregate_peaks(("2026",))
    for e, expected in G["aggregate_peaks"].items():
        add(f"汇总峰值·{e}", abs(agg[e]["peak_pct"] - expected) < 0.05, f"{agg[e]['peak_pct']:.2f}% @ {agg[e]['where']}")

    # 11 人工工时派生（银黄 2026-02）
    f = svc.labor_metrics("银黄口服液", "2026-02")
    j = svc.labor_metrics("银黄口服液", "2026-01")
    add("时薪·2月", abs(f["wage_rate"] - G["labor_feb"]["wage"]) < 0.02, f"{f['wage_rate']:.2f}")
    add("时薪·环比", abs((f["wage_rate"] / j["wage_rate"] - 1) * 100 - G["labor_feb"]["wage_mom"]) < 0.2)
    add("工时/盒·2月", abs(f["hour_per_box"] - G["labor_feb"]["hpb"]) < 1e-5, f"{f['hour_per_box']:.6f}")
    add("工时/盒·环比", abs((f["hour_per_box"] / j["hour_per_box"] - 1) * 100 - G["labor_feb"]["hpb_mom"]) < 0.2)

    # 12 折旧序列（随产量分摊，非直线法固定）
    dep = svc.depreciation_series("银黄口服液")
    add("折旧序列·精确", all(abs(a - b) < 1e-6 for a, b in zip(dep, G["depreciation_series"])), dep)

    # 13 六味理论 vs 实际（PDF 注明 5-6 倍）
    mean = svc.liuwei_material_mean()
    add("六味·实际材料均值", abs(mean - G["liuwei"]["mean_material"]) < 0.001, f"{mean:.3f}")
    add("六味·实际/理论", abs(mean / LIUWEI_THEORETICAL_MATERIAL - G["liuwei"]["ratio_vs_theory"]) < 0.05,
        f"{mean / LIUWEI_THEORETICAL_MATERIAL:.2f}")

    # 14 行业基准"本厂水平"核对（通过项 P1）
    for p, exp in G["industry_ratios"].items():
        r = svc.industry_ratios(p)
        for e, expected in exp.items():
            add(f"行业基准·{p}·{e}", abs(r[e] - expected) < 0.05, f"{r[e]:.2f}%")
    for p, expected in G["unit_cost_per"].items():
        v = svc.unit_cost_per(p)
        add(f"折单位成本·{p}", abs(v - expected) < 0.005, f"{v:.3f}")

    # 15 维修费无足迹
    add("维修费无足迹", svc.overhead_gap_free())

    return checks
