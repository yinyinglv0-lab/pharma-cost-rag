# -*- coding: utf-8 -*-
"""验证1：断点续跑实操验证。

证明：LangGraph checkpoint + 产物落盘真实工作，重跑不重算。
- 第一次运行在"写作Agent"处模拟故障（抛异常）；
- 修复后同 session 恢复，数据/检索产物字节级一致；
- 恢复运行不慢于全量运行（节点跳过/产物复用佐证：调用计数或断点恢复告警）。
"""
import time

import pytest

import app.agents.graph as G
from app.agents.graph import run_agent
from app.agents.llm import MockLLM

QUERY = "请生成银黄口服液2026-05的月度成本分析报告"


class CrashWriterLLM(MockLLM):
    def invoke(self, messages):
        text = " ".join(str(m.get("content", m)) for m in messages)
        if "成本归因分析师" in text:
            raise RuntimeError("模拟写作Agent故障（第一次运行崩溃）")
        return super().invoke(messages)


@pytest.fixture(autouse=True)
def clean(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("AGENT_CKP_DB", str(tmp_path / "ckp.sqlite"))
    yield tmp_path


def _install_counters(monkeypatch):
    calls = {"data": 0, "retrieve": 0}
    orig_d, orig_r = G.data_node, G.retrieve_node

    def w_d(s):
        calls["data"] += 1
        return orig_d(s)

    def w_r(s):
        calls["retrieve"] += 1
        return orig_r(s)

    monkeypatch.setattr(G, "data_node", w_d)
    monkeypatch.setattr(G, "retrieve_node", w_r)
    return calls


def test_crash_then_resume_artifacts_identical(tmp_path, monkeypatch):
    art = tmp_path / "artifacts"

    # 1) 全量干净运行（对照组，另一 session）
    t0 = time.time()
    clean_out = run_agent(QUERY, session_id="clean", llm=MockLLM())
    t_clean = time.time() - t0
    assert clean_out["status"] == "完成"
    clean_draft = clean_out["draft"]
    clean_task = clean_out["rpa_task"]

    # 2) 故障运行：写作者崩溃
    with pytest.raises(RuntimeError, match="模拟写作Agent故障"):
        run_agent(QUERY, session_id="crash", llm=CrashWriterLLM())
    # 崩溃前 data/retrieve 产物已落盘
    fp_before = (art / "crash_fact_pack.json").read_text(encoding="utf-8")
    ev_before = (art / "crash_evidence.json").read_text(encoding="utf-8")

    # 3) 恢复运行：同一 session + 计数包装（证明未重算）
    calls = _install_counters(monkeypatch)
    t0 = time.time()
    resume_out = run_agent(QUERY, session_id="crash", llm=MockLLM())
    t_resume = time.time() - t0

    fp_after = (art / "crash_fact_pack.json").read_text(encoding="utf-8")
    ev_after = (art / "crash_evidence.json").read_text(encoding="utf-8")

    # 验证标准 1：产物字节级一致
    assert fp_before == fp_after, "fact_pack 产物被重算/改变"
    assert ev_before == ev_after, "evidence 产物被重算/改变"

    # 验证标准 2：未重算的佐证（节点未再执行 或 断点恢复告警）
    restore_warnings = [w for w in resume_out["warnings"] if "断点恢复" in w]
    no_recompute = (calls["data"] == 0 and calls["retrieve"] == 0) or len(restore_warnings) >= 2
    assert no_recompute, f"节点计数 {calls}, 断点告警 {restore_warnings}"

    # 验证标准 3：最终产物与全量运行一致（确定性 MockLLM）
    assert resume_out["draft"] == clean_draft
    assert resume_out["rpa_task"] == clean_task

    # 辅助证据：恢复运行不慢于全量运行（留 1s 余量防抖动）
    assert t_resume <= t_clean + 1.0, f"恢复运行 {t_resume:.2f}s vs 全量 {t_clean:.2f}s"
