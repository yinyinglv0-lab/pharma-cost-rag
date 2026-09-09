# -*- coding: utf-8 -*-
"""前端验收：Streamlit 应用首屏加载无异常（AppTest 真实运行，防回归）。"""
import pytest

from streamlit.testing.v1 import AppTest

APP = r"D:\23生信-团日活动（学习雷锋）\重庆比赛AI\project\frontend\app.py"


@pytest.fixture(scope="module")
def app():
    at = AppTest.from_file(APP)
    at.run(timeout=180)
    return at


def test_first_load_no_exception(app):
    assert not app.exception, str(app.exception)


def test_four_tabs_present(app):
    labels = " ".join(t.label for t in app.tabs)
    for kw in ["报告", "看板", "对标", "RPA"]:
        assert kw in labels, f"缺页签: {kw}（实际 {labels}）"
