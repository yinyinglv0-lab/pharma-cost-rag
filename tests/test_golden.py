# -*- coding: utf-8 -*-
"""金丝雀基准集 pytest 入口：pytest -q 全绿 = 计算层未被破坏。"""
import pytest

from tests.golden_checks import all_checks

_CHECKS = all_checks()


@pytest.mark.parametrize("c", _CHECKS, ids=[c["name"] for c in _CHECKS])
def test_golden(c):
    assert c["ok"], f"{c['name']}: {c['detail']}"
