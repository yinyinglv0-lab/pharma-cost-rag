# -*- coding: utf-8 -*-
"""三步法引擎：找差异（差异表）→ 拆结构（差异树）→ 拆原因（RAG+知识归因）。"""
from ..core.calc import CalculationService, PRODUCTS
from ..core.datastore import DataStore
from ..rag.retrieve import retrieve

_svc = None
_ds = None


def _get():
    global _svc, _ds
    if _svc is None:
        _ds = DataStore()
        _svc = CalculationService(_ds)
    return _svc, _ds


def step1_find() -> dict:
    """找差异：产品×要素×差异金额×差异率（2026H1 产量加权）。"""
    svc, _ = _get()
    rows = []
    for p in PRODUCTS:
        for elem in ("材料", "人工", "制费", "单位成本"):
            diff_pct = svc.benchmark_diff(p, elem)
            rows.append({"product": p, "element": elem,
                         "diff_pct": round(diff_pct, 2),
                         "direction": "一厂更优" if diff_pct < 0 else "二厂更优"})
    return {"rows": rows}


def step2_struct(product: str) -> dict:
    """拆结构：总差异 → 要素层；一厂内部成本结构对照（二厂无明细，如实标注）。"""
    svc, ds = _get()
    nodes = []
    for elem in ("材料", "人工", "制费"):
        d = svc.benchmark_diff(product, elem)
        nodes.append({"level": "要素", "name": elem, "diff_pct": round(d, 2),
                      "share_of_total": round(abs(d) / max(abs(svc.benchmark_diff(product, e))
                                                           for e in ("材料", "人工", "制费")) * 100, 1)})
    return {"product": product, "tree": nodes,
            "note": "对标厂（中药二厂）数据包仅含成本汇总，无原材料明细——结构树下钻止于要素级，如实标注"}


def step3_cause(product: str, month: str = "2026-05") -> dict:
    """拆原因：检索证据 + M3-3 归因（MockLLM 离线可跑，真实 LLM 可替换）。"""
    from ..agents.llm import MockLLM, make_llm
    from ..agents.prompts import M3_3_BENCH_CAUSE
    tree = step2_struct(product)
    b = retrieve(f"{product} 对标 差异 原因", top_k=5)
    evidence = [{"chunk_id": i.chunk_id, "source": i.source, "type": i.type,
                 "text": i.text[:150]} for i in b.results if i.type != "图谱证据"]
    graph_ev = [i.text for i in b.results if i.type == "图谱证据"]
    llm = make_llm()
    prompt = (M3_3_BENCH_CAUSE + "\n输入：\n差异树=" + str(tree) +
              "\nevidence=" + str(evidence) + "\n图谱证据=" + str(graph_ev))
    raw = llm.invoke([{"role": "user", "content": prompt}])
    import json
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {"attribution": raw, "suggestions": []}
    return {"product": product, "tree": tree, "evidence": evidence,
            "graph_evidence": graph_ev, "attribution": parsed}
