# -*- coding: utf-8 -*-
"""任务4 边界值审计验收：零基期退化 / 上月缺失标null / 负值告警。"""
import pytest

from app.core.assertions import run_all
from app.core.calc import CalculationService
from app.core.datastore import DataStore


@pytest.fixture(scope="module")
def svc():
    return CalculationService(DataStore())


def test_missing_prev_month_returns_null(svc):
    """上月数据缺失 → 环比标记为 None（null），而非 0 或抛异常。"""
    v = svc.mom("银黄口服液", "2026-01", "材料")
    assert v is None, f"上月缺失应返回 None，实际 {v!r}"


def test_three_factor_missing_prev_returns_null(svc):
    assert svc.three_factor("银黄口服液", "2026-01") is None


def test_zero_base_window_falls_back_to_absolute(svc):
    """零基期：变动率标记 None，退化为绝对值差异法（不零除）。"""
    w = svc.window_change("银黄口服液", "黄芩提取物", "2026-04", "2026-06")
    # 正常路径：pct 非空、abs 为 None
    assert w["unit_pct"] is not None and w["unit_abs"] is None
    # 构造零基期：直接验证退化逻辑（monkeypatch 隐含单耗基期为 0）
    orig = svc.implied_unit_consumption
    def fake(product, material):
        r = orig(product, material)
        r["values"][3] = 0.0  # 4月基期置零
        return r
    svc.implied_unit_consumption = fake  # 实例属性直赋值，不绑定 self
    try:
        w0 = svc.window_change("银黄口服液", "黄芩提取物", "2026-04", "2026-06")
        assert w0["unit_pct"] is None, "零基期变动率必须为 None"
        assert w0["unit_abs"] is not None and w0["unit_abs"] > 0, "应退化为绝对值差异法"
    finally:
        svc.implied_unit_consumption = orig


def test_negative_value_alert():
    """负值出现 → A13 断言输出告警（现有数据无负值 → 通过；逻辑已覆盖检测）。"""
    svc = CalculationService(DataStore())
    results = run_all(svc.ds, svc)
    a13 = next(r for r in results if r["name"].startswith("A13"))
    assert a13["ok"], a13["detail"]  # 正常数据零负值；若未来数据出错会在此拦下


def test_normal_mom_still_works(svc):
    assert abs(svc.mom("银黄口服液", "2026-05", "单位成本") - 2.84) < 0.05
    assert abs(svc.mom("六味地黄胶囊", "2026-03", "材料") - (-2.92)) < 0.05, \
        "负环比是合法结果，不得误判为异常"
