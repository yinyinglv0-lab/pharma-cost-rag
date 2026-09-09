# -*- coding: utf-8 -*-
"""阶段 2 验收：三类知识可检索、可溯源、可过滤 + 图谱多跳路径 + 确定性。"""
import pytest

from app.rag import retrieve as r


@pytest.fixture(scope="module")
def kb():
    return r.knowledge_base()


# ---------- 2.1 PDF 解析与切分 ----------
def test_chunk_counts_and_metadata(kb):
    chunks = kb.chunks
    assert len(chunks) >= 40, f"知识块数量不足: {len(chunks)}"
    for c in chunks:
        assert c["chunk_id"] and c["source"] and c["type"], f"元数据缺失: {c.get('chunk_id')}"
        assert "forbid_current_numbers" in c and c["text"].strip()
    sources = {c["source"] for c in chunks}
    assert len(sources) >= 9, f"来源文件不足: {sources}"  # 7 PDF + 行情 + 行业基准


def test_spot_check_verified_fragments(kb):
    """逐文件抽检关键原文片段（人工核对过的锚点）。"""
    all_text = "\n".join(c["text"] for c in kb.chunks)
    for frag in ["金银花", "0.08", "8,500", "0.7917%", "115 °C",
                 "提取收率", "375.0mg", "物料平衡", "洁净区", "收率"]:
        assert frag in all_text, f"缺失原文片段: {frag}"
    # 部首补充区归一断言：2E80-2EFF 区块字符不允许残留（银⻩/⻋间 等必须归一）
    for c in kb.chunks:
        assert not any("⺀" <= ch <= "⻿" for ch in c["text"]), \
            f"{c['chunk_id']} 残留未归一部首字符"


# ---------- 2.2 知识块类型过滤（I5） ----------
def test_static_price_filtered_for_price_query():
    """硬保证：数值查询结果中绝不出现静态价块（纵深防御第二层）。

    注：语义模型+类型权重下静态价块常不进入候选，过滤可能无对象——保证点是结果洁净。
    过滤"动作"本身由下面两个测试证明（纯函数单测 + 自然触发端到端）。
    """
    b = r.retrieve("黄芩提取物当前价格是多少", top_k=8)
    for item in b.results:
        assert item.type != "处方参考价", f"静态价块漏进结果: {item.chunk_id}"


def test_filter_function_removes_and_warns():
    """过滤纯函数单测：喂入含静态价块的候选，断言移除 + 逐条告警。"""
    from app.rag.retrieve import _filter_forbidden
    items = [
        {"chunk_id": "PF-YH-003", "type": "处方参考价", "forbid_current_numbers": True},
        {"chunk_id": "MKT-金银花", "type": "行情价", "forbid_current_numbers": False},
        {"chunk_id": "PF-YH-002", "type": "处方量", "forbid_current_numbers": False},
    ]
    kept, warnings = _filter_forbidden(items, numeric=True)
    assert [i["chunk_id"] for i in kept] == ["MKT-金银花", "PF-YH-002"]
    assert len(warnings) == 1 and "PF-YH-003" in warnings[0]
    kept2, warnings2 = _filter_forbidden(items, numeric=False)
    assert len(kept2) == 3 and not warnings2, "非数值查询不应过滤"


def test_filter_triggers_end_to_end():
    """端到端：自然触发查询（候选含静态价块）→ 告警产生 + 结果洁净。"""
    b = r.retrieve("金银花涨价成本", top_k=8)
    assert any(w.startswith("已过滤静态价块") for w in b.warnings), "应产生过滤告警"
    for item in b.results:
        assert item.type != "处方参考价", f"静态价块漏进结果: {item.chunk_id}"


def test_temporal_tags_complete():
    """时效标签：行情/行业基准块带明确时间区间，静态参考价块带 static 标记。"""
    kb = r.knowledge_base()
    for c in kb.chunks:
        if c["type"] == "行情价":
            assert c["temporal"] == "2026-01~2026-06", f"{c['chunk_id']} 行情时效标签缺失"
        if c["type"] == "行业基准":
            assert c["temporal"] == "2026-01~2026-06", f"{c['chunk_id']} 基准时效标签缺失"
        if c["type"] == "处方参考价":
            assert c["temporal"] == "static" and c["forbid_current_numbers"], \
                f"{c['chunk_id']} 静态标记缺失"


def test_static_price_available_for_non_numeric_query():
    b = r.retrieve("银黄口服液成本参考", top_k=8, filter_forbidden=False)
    types = {item.type for item in b.results}
    assert "处方参考价" in types, "非数值查询应可引用静态价块"


# ---------- 2.3 归因驱动查询集（命中率 100%） ----------
@pytest.mark.parametrize("query,type_kw,text_kw", [
    ("金银花涨价的原因", "行情价", "产地减产"),
    ("提取收率下降对材料成本的影响", "工艺参数", "0.08"),
    ("银黄口服液处方组成", "处方量", "金银花"),
    ("胶囊填充机故障记录", "维修事件", "8,500"),
    ("洁净区温湿度要求", "GMP要求", "45-65%"),
    ("口服液车间设备折旧", "设备台账", "折旧"),
])
def test_attribution_query_hits(query, type_kw, text_kw):
    b = r.retrieve(query, top_k=6)
    assert any(i.type == type_kw for i in b.results), \
        f"查询[{query}]未命中类型 {type_kw}: {[i.chunk_id for i in b.results]}"
    joined = " ".join(i.text for i in b.results)
    assert text_kw in joined, f"查询[{query}]未命中关键词 {text_kw}"


# ---------- 2.4 图谱多跳路径 ----------
def test_graph_product_material_event_path(kb):
    g = kb.graph
    assert g.check_path("银黄口服液", "金银花", max_hops=1)
    assert g.check_path("金银花", "行情:金银花:2026-05", max_hops=1)


def test_graph_maintenance_path(kb):
    g = kb.graph
    assert g.check_path("六味地黄胶囊", "EQ-JN-006", max_hops=3), "产品→设备编号路径不可达"
    assert g.check_path("EQ-JN-006", "维修:2026-03:EQ-JN-006", max_hops=1)


def test_graph_workshop_equipment_paths(kb):
    """车间→设备 路径（评审改进：补全覆盖）。"""
    g = kb.graph
    assert g.check_path("口服液车间", "EQ-TQ-001", max_hops=1)
    assert g.check_path("颗粒剂车间", "EQ-KL-002", max_hops=1)
    assert g.check_path("胶囊剂车间", "EQ-JN-006", max_hops=1)


def test_graph_scenario_event_paths(kb):
    """六条场景事件（E1-E6）全部可达（评审改进：补全覆盖；E4 连通全部产品）。"""
    from app.rag import entities
    g = kb.graph
    for ev in entities.SCENARIO_EVENTS:
        nid = f"场景:{ev['id']}"
        products = list(entities.PRODUCTS) if ev["product"] == "全部产品" else [ev["product"]]
        for p in products:
            assert g.check_path(p, nid, max_hops=2), f"路径不可达: {p} → {nid}"


def test_graph_evidence_for_price_query():
    b = r.retrieve("金银花涨价原因", top_k=3)
    assert b.graph_paths, "图谱通道应输出行情事件路径"
    assert any("行情" in p and "金银花" in p for p in b.graph_paths)


# ---------- 可溯源 + 确定性 ----------
def test_all_results_traceable():
    for q in ["金银花涨价原因", "提取收率", "GMP洁净区"]:
        b = r.retrieve(q, top_k=5)
        for item in b.results:
            assert item.source and item.chunk_id, f"{q} 的结果缺少溯源字段"


def test_determinism():
    b1 = r.retrieve("金银花涨价原因", top_k=5)
    b2 = r.retrieve("金银花涨价原因", top_k=5)
    assert [i.chunk_id for i in b1.results] == [i.chunk_id for i in b2.results], "检索结果不可复现"
