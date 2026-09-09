# -*- coding: utf-8 -*-
"""验证2：守卫拦截有效性实操验证。

证明：一致性守卫能真实拦截幻觉数字，触发重写（≤2次），耗尽后优雅终止不崩溃。
"""
import json

import pytest

from app.agents.graph import run_agent
from app.agents.llm import MockLLM


@pytest.fixture(autouse=True)
def clean(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("AGENT_CKP_DB", str(tmp_path / "ckp.sqlite"))
    yield


class AlwaysHallucinatingLLM(MockLLM):
    """写作Agent始终输出不在 fact_pack 中的数字 99.99。"""

    def __init__(self):
        super().__init__()
        self.writer_calls = 0

    def invoke(self, messages):
        text = " ".join(str(m.get("content", m)) for m in messages)
        if "成本归因分析师" in text:
            self.writer_calls += 1
            return json.dumps({
                "finding": "材料成本大幅波动",
                "chain": "材料成本变动 99.99 元/盒 [S1]，由行情传导 [C1]。",
                "suggestion": ["核查采购合同"],
                "citations": ["S1", "C1"],
            }, ensure_ascii=False)
        return super().invoke(messages)


class OnceBadThenGoodLLM(MockLLM):
    """第一次写作输出幻觉数字，之后正常（重写路径被守卫放行）。"""

    def __init__(self):
        super().__init__()
        self.writer_calls = 0

    def invoke(self, messages):
        text = " ".join(str(m.get("content", m)) for m in messages)
        if "成本归因分析师" in text:
            self.writer_calls += 1
            if self.writer_calls == 1:
                return json.dumps({
                    "finding": "材料成本大幅波动",
                    "chain": "材料成本变动 99.99 元/盒 [S1]，由行情传导 [C1]。",
                    "suggestion": ["核查采购合同"],
                    "citations": ["S1", "C1"],
                }, ensure_ascii=False)
        return super().invoke(messages)


def test_hallucination_blocked_and_retries_exhaust():
    llm = AlwaysHallucinatingLLM()
    out = run_agent("生成六味地黄胶囊2026-05成本分析报告", session_id="halluc",
                    llm=llm)
    # 验证标准 1：拦截成功（违规含数字指纹）
    assert not out["guard"]["passed"]
    assert any("数字指纹" in v for v in out["guard"]["violations"])
    # 验证标准 2：触发重写（初始 1 次 + 重试 2 次 = 3 次调用）
    assert llm.writer_calls == 3, f"写作Agent调用次数 {llm.writer_calls}（期望 3）"
    # 验证标准 3：耗尽后优雅终止，不崩溃
    assert out["status"] == "守卫失败(重试耗尽)"
    assert out["rpa_task"] is None, "守卫失败时不得产出任务"


def test_hallucination_retry_then_pass():
    llm = OnceBadThenGoodLLM()
    out = run_agent("生成板蓝根颗粒2026-05成本分析报告", session_id="recover",
                    llm=llm)
    assert llm.writer_calls == 2, "一次坏输出 + 一次重写"
    assert out["status"] == "完成"
    assert out["guard"]["passed"]
