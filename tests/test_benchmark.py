# -*- coding: utf-8 -*-
"""模块三验收：三步法输出 + 一致性检验器 v7（四级判定与锚点证据）。"""
from app.benchmark.checker import audit
from app.benchmark.steps import step1_find, step2_struct, step3_cause


def test_step1_find_table():
    rows = step1_find()["rows"]
    assert len(rows) == 3 * 4
    yh_material = next(r for r in rows if r["product"] == "银黄口服液" and r["element"] == "材料")
    assert abs(yh_material["diff_pct"] - (-0.01)) < 0.05
    assert all(r["direction"] == "一厂更优" for r in rows), "全部要素一厂更优"


def test_step2_struct_tree():
    t = step2_struct("银黄口服液")
    assert len(t["tree"]) == 3
    assert "无原材料明细" in t["note"], "二厂无明细必须如实标注"


def test_step3_cause_outputs():
    c = step3_cause("银黄口服液")
    assert c["attribution"], "归因输出为空"
    assert c["evidence"], "检索证据为空"


def test_audit_levels_v7():
    rep = audit()
    assert rep["counts"] == {"红": 4, "黄": 2, "蓝": 1, "灰": 1, "绿": 4}, rep["counts"]
    f1 = next(i for i in rep["items"] if i["id"] == "F1")
    assert f1["level"] == "红" and "一厂材料全部更低" in f1["evidence"]
    f7 = next(i for i in rep["items"] if i["id"] == "F7")
    assert f7["level"] == "黄" and "1:" in f7["evidence"]
    p1 = next(i for i in rep["items"] if i["id"] == "P1")
    assert p1["level"] == "绿" and p1["verdict"] == "成立"
    c1 = next(i for i in rep["items"] if i["id"] == "C1")
    assert c1["level"] == "蓝" and "5-6 倍" in c1["evidence"]
