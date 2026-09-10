# -*- coding: utf-8 -*-
"""对标分析审计验收：三步法输出格式/差异准确率/口径一致性/建议可执行性。"""
from app.agents.guard import check_rpa_task
from app.benchmark.steps import plan_to_task, step1_find, step2_struct, step3_cause

GOLDEN_DIFF = {
    "材料": {"银黄口服液": -0.01, "板蓝根颗粒": -4.47, "六味地黄胶囊": -5.05},
    "人工": {"银黄口服液": -11.70, "板蓝根颗粒": -11.06, "六味地黄胶囊": -10.32},
    "制费": {"银黄口服液": -7.90, "板蓝根颗粒": -9.42, "六味地黄胶囊": -8.99},
    "单位成本": {"银黄口服液": -3.56, "板蓝根颗粒": -6.63, "六味地黄胶囊": -6.40},
}


def test_step1_format_and_anchor():
    rows = step1_find()["rows"]
    assert len(rows) == 12
    for r in rows:
        for field in ("product", "element", "diff_pct", "diff_amount", "direction"):
            assert field in r, f"差异表缺字段 {field}"
    yh = next(r for r in rows if r["product"] == "银黄口服液" and r["element"] == "材料")
    assert abs(yh["diff_pct"] - (-0.01)) < 0.05, "银黄材料锚点 -0.01%"
    assert abs(yh["diff_amount"] - (7.0190 - 7.0200)) < 0.005, "差异金额=加权差"


def test_step1_accuracy_within_1pct():
    rows = step1_find()["rows"]
    for r in rows:
        golden = GOLDEN_DIFF[r["element"]][r["product"]]
        rel = abs(r["diff_pct"] - golden) / max(abs(golden), 1e-9) * 100
        assert rel <= 1.0, f"{r['product']}-{r['element']} 相对误差 {rel}% 超标"


def test_step2_drilldown_and_contributor():
    t = step2_struct("银黄口服液")
    assert t["tree"] and t["material_drilldown"], "结构树须下钻至原材料"
    assert t["max_contributor"]["name"] == "人工", "最大贡献因子应为人工(-11.70%)"
    assert "无原材料明细" in t["note"], "二厂无明细必须如实标注"


def test_step3_evidence_and_plan():
    c = step3_cause("银黄口服液")
    assert len(c["evidence"]) >= 3
    assert len(c["graph_evidence"]) >= 1
    assert len(c["rpa_plan"]) >= 3
    for item in c["rpa_plan"]:
        for field in ("assignee", "priority", "deadline", "suggestion"):
            assert item[field], f"建议缺 {field}"
        task = plan_to_task(item, "银黄口服液")
        assert check_rpa_task(task).passed, "每条建议必须可转合规 RPA 任务 JSON"


def test_caliber_explicit():
    from app.core.calc import CalculationService
    from app.core.datastore import DataStore
    svc = CalculationService(DataStore())
    u, t = svc.yoy_unit_cost_overall(), svc.yoy_total_cost_overall()
    assert abs(u - 2.43) < 0.03 and abs(t - 7.77) < 0.03
    assert abs(u - t) > 1.0, "单位成本加权 vs 总成本必须显式区分"
