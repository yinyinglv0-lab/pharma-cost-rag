# -*- coding: utf-8 -*-
"""验证4：端到端实操验证——赛题 3 个评测场景（不同产品/月份）。

覆盖范围如实说明：5 章节模板渲染属阶段 4 模块一；本验证覆盖流水线归因质量、
数字全量溯源（守卫通过 = 每个数字可在 fact_pack 溯源）、RPA 任务生成与 schema 合规
（HTTP 推送属阶段 4）。
"""
import json

import pytest

from app.agents.graph import run_agent
from app.agents.guard import check_draft, check_rpa_task
from app.agents.llm import MockLLM

SCENARIOS = [
    ("请生成银黄口服液2026-05的月度成本分析报告", "银黄口服液", "2026-05"),
    ("请生成板蓝根颗粒2026-02的月度成本分析报告", "板蓝根颗粒", "2026-02"),
    ("请对标中药二厂生成六味地黄胶囊2026-03的对比报告", "六味地黄胶囊", "2026-03"),
]


@pytest.fixture(autouse=True)
def clean(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("AGENT_CKP_DB", str(tmp_path / "ckp.sqlite"))
    yield


@pytest.mark.parametrize("query,product,month", SCENARIOS,
                         ids=["场景1-银黄2026-05", "场景2-板蓝根2026-02", "场景3-六味2026-03"])
def test_scenario(query, product, month):
    out = run_agent(query, session_id=f"e2e-{product}-{month}", llm=MockLLM())
    # 1) 无报错完成
    assert out["status"] == "完成", out.get("warnings")
    # 2) 归因四要素（现象→原因→量化影响→可执行建议）
    draft = out["draft"]
    assert draft["finding"].strip(), "缺现象"
    assert draft["chain"].strip(), "缺原因链"
    assert draft["suggestion"], "缺可执行建议"
    # 量化影响：chain 含数字且守卫通过（数字指纹=全量可溯源）
    assert out["guard"]["passed"], out["guard"]["violations"]
    assert any(ch.isdigit() for ch in draft["chain"]), "chain 无量化数字"
    # 3) 数字溯源复验（独立于流水线再跑一遍守卫）
    g = check_draft(json.dumps(draft, ensure_ascii=False), out["fact_pack"],
                    allow_causal=True)
    assert g.passed, g.violations
    # 4) RPA 任务生成 + schema 合规（推送属阶段4）
    assert out["rpa_task"], "RPA 任务未生成"
    assert check_rpa_task(out["rpa_task"]).passed
    assert out["rpa_task"]["source"]["product"] == product
    assert out["rpa_task"]["source"]["analysis_month"] == month
