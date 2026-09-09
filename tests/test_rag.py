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

    注：IDF 加权后静态价块常不进入候选，过滤可能无对象——保证点是结果洁净，
    而非"必须发生过过滤"。非数值查询仍可引用（见下一条测试）。
    """
    b = r.retrieve("黄芩提取物当前价格是多少", top_k=8)
    for item in b.results:
        assert item.type != "处方参考价", f"静态价块漏进结果: {item.chunk_id}"


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
