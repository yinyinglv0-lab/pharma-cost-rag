# -*- coding: utf-8 -*-
"""LangGraph 状态机专家交付：多 Agent 编排流水线。

流程：route(意图路由) → data(fact_pack) → retrieve(evidence) → write(草稿)
     → verify(一致性守卫) → execute(RPA任务JSON) → track(收尾)
- SQLite checkpoint（可用时）+ 中间产物版本化落盘（断点续跑，重试不重算）；
- 意图路由：4 类有限意图 + 低置信兜底"需澄清"；
- 数值零信任：data 节点全部走 CalculationService，LLM 不碰算术；
- 守卫失败 → 打回 writer 重写（最多 2 次），耗尽则终止。
"""
import json
import os
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from ..core.assertions import run_all
from ..core.calc import CalculationService, PRODUCTS
from ..core.datastore import DataStore
from ..rag.retrieve import retrieve
from .guard import check_draft, check_identity, check_rpa_task
from .llm import MockLLM, make_llm
from .prompts import A0_NUMERIC_LOCK, M1_2_ATTRIBUTION, M4_1_RPA_TASK

MAX_RETRIES = 2
INTENT_KEYWORDS = {
    "report": ["报告", "月度分析", "季度", "专题", "生成"],
    "dashboard": ["看板", "趋势", "图表", "环比", "归因"],
    "benchmark": ["对标", "二厂", "对比", "差异"],
    "remediate": ["整改", "任务", "推送", "督办"],
}


class AgentState(TypedDict, total=False):
    session_id: str
    query: str
    intent: str
    product: str
    month: str
    fact_pack: Optional[dict]
    evidence: Optional[list]
    draft: Optional[dict]
    guard_result: Optional[dict]
    rpa_task: Optional[dict]
    warnings: List[str]
    status: str
    retries: int
    artifact_dir: str


def _artifact_dir() -> Path:
    d = Path(os.environ.get("AGENT_ARTIFACT_DIR",
                            Path(tempfile.gettempdir()) / "pharma_agents"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _save(state: AgentState, node: str, payload: dict):
    path = _artifact_dir() / f"{state['session_id']}_{node}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, default=str), encoding="utf-8")
    return str(path)


def _load(state: AgentState, node: str):
    path = _artifact_dir() / f"{state['session_id']}_{node}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


# ---------------- 节点 ----------------
def route(state: AgentState) -> AgentState:
    query = state.get("query", "")
    hits = [name for name, kws in INTENT_KEYWORDS.items() if any(k in query for k in kws)]
    if not hits:
        state["status"] = "需澄清"
        return state
    # 多命中时"更具体者胜"：整改 > 对标 > 看板 > 报告
    priority = ["remediate", "benchmark", "dashboard", "report"]
    state["intent"] = hits[0] if len(hits) == 1 else next(p for p in priority if p in hits)
    # 产品/月份抽取（缺省值保证可跑）
    state["product"] = next((p for p in PRODUCTS if p in query), state.get("product") or "银黄口服液")
    state["month"] = next((m for m in _MONTH_PAT.findall(query)), state.get("month") or "2026-05")
    state.setdefault("warnings", [])
    state["status"] = state["intent"]
    return state


_MONTH_PAT = __import__("re").compile(r"20\d{2}-\d{2}")


def data_node(state: AgentState) -> AgentState:
    """FactPack 生成——纯计算层，LLM 不参与（数值零信任）。断点续跑：产物存在即复用。"""
    cached = _load(state, "fact_pack")
    if cached:
        state["fact_pack"] = cached
        state["warnings"].append("断点恢复: fact_pack 复用已落盘产物，未重算")
        return state
    svc = CalculationService(DataStore())
    p, m = state["product"], state["month"]
    prev = f"{m[:4]}-{int(m[5:7]) - 1:02d}"
    fp = {
        "product": p, "month": m,
        "环比": {e: round(svc.mom(p, m, e), 2) for e in ("材料", "人工", "制费", "单位成本")},
        "同比_单位成本加权": round(svc.yoy_unit_cost(p), 2),
        "三因素贡献": {e: round(svc.three_factor(p, m)[e]["share_pct"], 2)
                       for e in ("材料", "人工", "制费")},
        "对标差异": {e: round(svc.benchmark_diff(p, e), 2)
                     for e in ("材料", "人工", "制费", "单位成本")},
        "告警": [e for e, v in ({"材料": svc.mom(p, m, "材料"),
                                 "人工": svc.mom(p, m, "人工"),
                                 "制费": svc.mom(p, m, "制费")}).items() if abs(v) > 5.0],
        "窗口对齐示例": svc.window_change("银黄口服液", "黄芩提取物", "2026-04", "2026-06")
        if p == "银黄口服液" else None,
    }
    state["fact_pack"] = fp
    _save(state, "fact_pack", fp)
    return state


def retrieve_node(state: AgentState) -> AgentState:
    cached = _load(state, "evidence")
    if cached:
        state["evidence"] = cached
        state["warnings"].append("断点恢复: evidence 复用已落盘产物，未重查")
        return state
    q = f"{state['product']} {state['query']}"
    b = retrieve(q, top_k=5)
    ev = [{"chunk_id": i.chunk_id, "source": i.source, "page": i.page,
           "type": i.type, "channel": i.channel, "text": i.text[:200]}
          for i in b.results]
    state["evidence"] = ev
    _save(state, "evidence", ev)
    return state


def writer_node(state: AgentState, llm=None) -> AgentState:
    llm = llm or make_llm()
    messages = [
        {"role": "system", "content": A0_NUMERIC_LOCK + "\n" + M1_2_ATTRIBUTION},
        {"role": "user", "content": json.dumps(
            {"fact_pack": state["fact_pack"], "evidence": state["evidence"],
             "violations_to_fix": state.get("guard_result", {}).get("violations", [])},
            ensure_ascii=False)},
    ]
    raw = llm.invoke(messages)
    try:
        state["draft"] = json.loads(raw)
    except json.JSONDecodeError:
        state["draft"] = {"finding": raw, "chain": "", "suggestion": [], "citations": []}
    _save(state, "draft", state["draft"])
    return state


def verify_node(state: AgentState) -> AgentState:
    svc = CalculationService(DataStore())
    ds = DataStore()
    ident = check_identity(ds, svc)
    if not ident.passed:
        state["guard_result"] = {"passed": False, "violations": ident.violations}
        state["status"] = "守卫失败"
        return state
    draft_text = json.dumps(state["draft"], ensure_ascii=False)
    has_causal = any(e.get("channel") == "graph" for e in (state["evidence"] or []))
    g = check_draft(draft_text, state["fact_pack"] or {}, allow_causal=has_causal)
    if g.passed:
        state["guard_result"] = {"passed": True, "violations": []}
        state["status"] = "校验通过"
        return state
    state["retries"] = state.get("retries", 0) + 1
    state["guard_result"] = {"passed": False, "violations": g.violations}
    # 重试耗尽判定放在节点内（条件边函数是只读路由，不能改 state）
    state["status"] = "守卫拦截" if state["retries"] <= MAX_RETRIES else "守卫失败(重试耗尽)"
    return state


def executor_node(state: AgentState, llm=None) -> AgentState:
    """RPA 任务 JSON 生成 + schema 校验（HTTP 推送属阶段 4）。"""
    llm = llm or make_llm()
    messages = [
        {"role": "system", "content": A0_NUMERIC_LOCK + "\n" + M4_1_RPA_TASK},
        {"role": "user", "content": json.dumps(
            {"draft": state["draft"], "product": state["product"],
             "month": state["month"]}, ensure_ascii=False)},
    ]
    raw = llm.invoke(messages)
    try:
        task = json.loads(raw)
    except json.JSONDecodeError:
        state["status"] = "RPA任务JSON解析失败"
        return state
    g = check_rpa_task(task)
    if not g.passed:
        state["status"] = "RPA任务校验失败"
        state["warnings"].extend(g.violations)
        return state
    state["rpa_task"] = task
    _save(state, "rpa_task", task)
    return state


def track_node(state: AgentState) -> AgentState:
    state["status"] = "完成"
    state["warnings"].append(
        f"流水线完成: fact_pack {len(state['fact_pack'] or {})} 键 / "
        f"evidence {len(state['evidence'] or [])} 条 / rpa_task "
        f"{'已生成' if state.get('rpa_task') else '未生成'}")
    return state


def _after_route(state: AgentState) -> str:
    if state.get("status") == "需澄清":
        return END
    return "data"


def _after_verify(state: AgentState) -> str:
    if state["status"] == "校验通过":
        return "executor"
    if "守卫失败" in state["status"]:
        return END
    return "writer"


def build_graph(llm=None):
    g = StateGraph(AgentState)
    g.add_node("route", route)
    g.add_node("data", data_node)
    g.add_node("retrieve", retrieve_node)
    g.add_node("writer", lambda s: writer_node(s, llm=llm))
    g.add_node("verify", verify_node)
    g.add_node("executor", lambda s: executor_node(s, llm=llm))
    g.add_node("track", track_node)
    g.add_edge(START, "route")
    g.add_conditional_edges("route", _after_route, {"data": "data", END: END})
    g.add_edge("data", "retrieve")
    g.add_edge("retrieve", "writer")
    g.add_edge("writer", "verify")
    g.add_conditional_edges("verify", _after_verify,
                            {"writer": "writer", "executor": "executor", END: END})
    g.add_edge("executor", "track")
    g.add_edge("track", END)
    # checkpoint：优先 SQLite 文件（断点续跑持久化），不可用则内存
    try:
        from langgraph.checkpoint.sqlite import SqliteSaver
        checkpointer = SqliteSaver.from_conn_string(
            os.environ.get("AGENT_CKP_DB", str(_artifact_dir() / "checkpoints.sqlite")))
    except Exception:
        from langgraph.checkpoint.memory import MemorySaver
        checkpointer = MemorySaver()
    return g.compile(checkpointer=checkpointer)


def run_agent(query: str, session_id: str = "demo", llm=None) -> dict:
    """一键入口：返回最终状态（供 API/演示调用）。"""
    graph = build_graph(llm=llm)
    out = graph.invoke({"session_id": session_id, "query": query},
                       config={"configurable": {"thread_id": session_id}})
    return {"status": out.get("status"), "intent": out.get("intent"),
            "fact_pack": out.get("fact_pack"), "evidence": out.get("evidence"),
            "draft": out.get("draft"), "guard": out.get("guard_result"),
            "rpa_task": out.get("rpa_task"), "warnings": out.get("warnings")}
