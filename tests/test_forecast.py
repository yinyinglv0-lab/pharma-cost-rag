# -*- coding: utf-8 -*-
"""项目4验收：预测非空 + DiD 必须含两条诚实标注。"""
from app.forecast.engine import DID_WARNINGS, demo_forecast, did_effect, forecast_unit_cost


def test_forecast_nonempty():
    f = forecast_unit_cost("银黄口服液")
    assert len(f.history) == 6
    assert f.moving_average_3 > 0 and f.exponential_smoothing > 0
    # MA3 = (10.93+11.21+10.87)/3? 实际最后三个月 4/5/6月 = 10.90, 11.21, 10.93 → 11.0133
    assert abs(f.moving_average_3 - round((10.90 + 11.21 + 10.93) / 3, 4)) < 1e-9


def test_did_two_honest_warnings():
    d = did_effect("银黄口服液")
    assert len(d.warnings) == 2
    assert any("单期启发式" in w for w in d.warnings)
    assert any("行情混淆" in w for w in d.warnings)
    assert len(DID_WARNINGS) == 2


def test_demo_log_contains_warning():
    log = demo_forecast()
    assert "单期启发式" in log and "行情" in log
