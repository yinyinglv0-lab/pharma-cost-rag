# -*- coding: utf-8 -*-
"""LangGraph 状态机专家验收：端到端流水线、断点续跑、守卫打回重试、需澄清兜底。"""
import json

import pytest

from app.agents.graph import build_graph, run_agent
from app.agents.llm import MockLLM


@pytest.fixture(autouse=True)
def clean_artifacts(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("AGENT_CKP_DB", str(tmp_path / "ckp.sqlite"))
    yield


def test_end_to_end_report(tmp_path):
    out = run_agent("请生成银黄口服液2026-05的月度成本分析报告", session_id="e2e", llm=MockLLM())
    assert out["status"] == "完成", out.get("warnings")
    assert out["fact_pack"]["product"] == "银黄口服液"
    assert out["evidence"], "evidence 为空"
    assert out["guard"]["passed"], out["guard"]
    assert out["rpa_task"], "rpa_task 未生成"
    art = tmp_path / "artifacts"
    assert (art / "e2e_fact_pack.json").exists()
    assert (art / "e2e_evidence.json").exists()
    assert (art / "e2e_draft.json").exists()
    assert (art / "e2e_rpa_task.json").exists()


def test_resume_from_artifacts(tmp_path):
    run_agent("生成银黄口服液2026-05月度成本分析报告", session_id="resume", llm=MockLLM())
    art = tmp_path / "artifacts"
    fp_before = (art / "resume_fact_pack.json").read_text(encoding="utf-8")
    out2 = run_agent("生成银黄口服液2026-05月度成本分析报告", session_id="resume", llm=MockLLM())
    assert any("断点恢复" in w for w in out2["warnings"]), "二次运行应走断点恢复"
    fp_after = (art / "resume_fact_pack.json").read_text(encoding="utf-8")
    assert fp_before == fp_after, "断点恢复不应重算产物"


def test_guard_rejects_hallucination_and_retries(tmp_path):
    class BadThenGoodLLM(MockLLM):
        def __init__(self):
            super().__init__()
            self._count = 0

        def invoke(self, messages):
            text = " ".join(str(m.get("content", m)) for m in messages)
            if "成本归因分析师" in text:
                self._count += 1
                if self._count == 1:
                    # 第一次故意输出幻觉数字 99.99（无角标）
                    return json.dumps({"finding": "材料成本变动 99.99 元/盒 [S1]。",
                                       "chain": "", "suggestion": [], "citations": []},
                                      ensure_ascii=False)
            return super().invoke(messages)

    out = run_agent("生成六味地黄胶囊2026-05成本分析报告", session_id="retry",
                    llm=BadThenGoodLLM())
    assert out["status"] == "完成", out.get("warnings")
    # 第一次被守卫打回（retries>=1），第二次修复后通过
    assert out["guard"]["passed"]


def test_guard_exhausts_retries(tmp_path):
    class AlwaysBadLLM(MockLLM):
        def invoke(self, messages):
            text = " ".join(str(m.get("content", m)) for m in messages)
            if "成本归因分析师" in text:
                return json.dumps({"finding": "材料成本变动 99.99 元/盒 [S1]。",
                                   "chain": "", "suggestion": [], "citations": []},
                                  ensure_ascii=False)
            return super().invoke(messages)

    out = run_agent("生成板蓝根颗粒2026-05成本分析报告", session_id="exhaust",
                    llm=AlwaysBadLLM())
    assert "守卫失败" in out["status"], out["status"]


def test_clarification_fallback(tmp_path):
    out = run_agent("你好", session_id="clarify", llm=MockLLM())
    assert out["status"] == "需澄清"


def test_identity_guard_in_pipeline(tmp_path):
    out = run_agent("请对标中药二厂生成银黄口服液2026-05对比报告", session_id="bench",
                    llm=MockLLM())
    assert out["status"] == "完成"
    assert out["intent"] == "benchmark"
