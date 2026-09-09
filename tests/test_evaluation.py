# -*- coding: utf-8 -*-
"""项目3验收：六事件全部可评估、零未命中、三级判定（含 2 个部分命中）。"""
from app.evaluation.engine import demo_evaluation, evaluate


def test_six_events_all_evaluated():
    rep = evaluate()
    assert rep["total"] == 6
    ids = [i["id"] for i in rep["items"]]
    assert ids == ["E1", "E2", "E3", "E4", "E5", "E6"]


def test_no_miss_at_least_partial():
    rep = evaluate()
    verdicts = [i["verdict"] for i in rep["items"]]
    assert "未命中" not in verdicts, verdicts


def test_expected_partial_hits():
    rep = evaluate()
    by_id = {i["id"]: i["verdict"] for i in rep["items"]}
    assert by_id["E3"] == "部分命中", "E3 单耗方向命中幅度微弱应为部分命中"
    assert by_id["E4"] == "部分命中", "E4 摊薄为次因应为部分命中"
    assert by_id["E1"] == "完全命中"


def test_demo_log():
    log = demo_evaluation()
    assert "命中率" in log and "部分命中" in log
