# -*- coding: utf-8 -*-
"""恒等式断言库 pytest 入口。"""
import pytest

from app.core.assertions import run_all
from app.core.calc import CalculationService
from app.core.datastore import DataStore


@pytest.fixture(scope="module")
def svc():
    return CalculationService(DataStore())


def test_assertions(svc):
    results = run_all(svc.ds, svc)
    failed = [r for r in results if not r["ok"]]
    assert not failed, "\n".join(f"{r['name']}: {r['detail']}" for r in failed)
