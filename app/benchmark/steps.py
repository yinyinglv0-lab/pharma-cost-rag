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


def step2_struct(product: str, month: str = "2026-05") -> dict:
    """拆结构：总差异 → 要素层 → 原材料级下钻（一厂侧明细；二厂无明细如实标注）。"""
    svc, ds = _get()
    nodes = []
    for elem in ("材料", "人工", "制费"):
        d = svc.benchmark_diff(product, elem)
        nodes.append({"level": "要素", "name": elem, "diff_pct": round(d, 2),
                      "share_of_total": round(abs(d) / max(abs(svc.benchmark_diff(product, e))
                                                           for e in ("材料", "人工", "制费")) * 100, 1)})
    # 原材料级下钻（一厂侧明细可得）
    rows = ds.material_rows(product, month)
    material = [{"level": "原材料", "name": r["原材料名称"],
                 "unit_cost": float(r["单位消耗成本(元/盒)"]),
                 "share": float(str(r["占总材料成本比例"]).rstrip("%"))}
                for _, r in rows.iterrows()]
    material.sort(key=lambda x: -x["share"])
    return {"product": product, "month": month, "tree": nodes,
            "material_drilldown": material,
            "note": "对标厂（中药二厂）数据包仅含成本汇总，无原材料明细——二厂侧下钻止于要素级；"
                    "一厂侧已下钻至原材料级，二厂侧差异去向如实标注为'数据不可得'"}


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
            "graph_evidence": graph_ev, "attribution": parsed,
            "rpa_plan": _to_rpa_plan(parsed.get("suggestions", []), product)}


def _to_rpa_plan(suggestions: list, product: str) -> list:
    """改进建议 → RPA 指令计划（责任人/优先级/截止时间，规则映射）。"""
    plan = []
    for i, s in enumerate(suggestions, 1):
        if any(k in s for k in ("采购", "合同", "供应商")):
            dept, role, pri = "采购部", "采购经理", "high"
        elif any(k in s for k in ("工艺", "收率", "排产", "效率")):
            dept, role, pri = "生产部", "工艺工程师", "medium"
        elif any(k in s for k in ("设备", "折旧")):
            dept, role, pri = "设备部", "设备主管", "medium"
        else:
            dept, role, pri = "财务部", "成本会计", "low"
        plan.append({"seq": i, "suggestion": s, "assignee": {"name": "待指定", "department": dept, "role": role},
                     "priority": pri, "deadline": "2026-06-30"})
    return plan
