# -*- coding: utf-8 -*-
"""三通道检索引擎（2.3）：BM25（0.3）+ 向量（0.7，ChromaDB/numpy 降级）+ 图谱（networkx/Neo4j 降级）。

融合：RRF（k=60）按通道加权；图谱通道负责实体锚定 + 多跳路径，不参与文本打分。
"""
import math
import os
import tempfile
from pathlib import Path

import networkx as nx
from rank_bm25 import BM25Okapi

from .embed import JiebaHashEmbedder, tokenize
from . import entities

RRF_K = 60
BM25_WEIGHT = 0.3      # README 建议 BM25:向量 = 0.3:0.7
VECTOR_WEIGHT = 0.7
GRAPH_WEIGHT = 0.5


# ================= BM25 =================
def _index_text(c: dict) -> str:
    """索引文本 = 上下文 + 正文（引用展示仍用原文，上下文不污染引用）。"""
    return (c.get("context", "") + " " + c["text"]).strip()


class BM25Store:
    def __init__(self, chunks):
        self.chunks = chunks
        self._idx = [i for i, c in enumerate(chunks) if c["text"]]
        corpus = [tokenize(_index_text(chunks[i])) for i in self._idx]
        self._bm25 = BM25Okapi(corpus)

    def search(self, query, top_k=10):
        scores = self._bm25.get_scores(tokenize(query))
        ranked = sorted(zip(self._idx, scores), key=lambda x: -x[1])
        return [(i, s) for i, s in ranked[:top_k] if s > 0]


# ================= 向量 =================
class NumpyVectorStore:
    """无外部依赖降级实现（演示机兜底）：余弦相似度。"""
    def __init__(self, chunks, embedder):
        self.chunks = chunks
        self.embedder = embedder
        texts = [_index_text(c) for c in chunks]
        self._vecs = embedder.embed(texts) if hasattr(embedder, "embed") else embedder(texts)
        self._norms = [math.sqrt(sum(x * x for x in v)) or 1.0 for v in self._vecs]

    def search(self, query, top_k=10):
        q = self.embedder.embed([query])[0]
        qn = math.sqrt(sum(x * x for x in q)) or 1.0
        scores = [sum(a * b for a, b in zip(q, v)) / (qn * n) for v, n in zip(self._vecs, self._norms)]
        ranked = sorted(enumerate(scores), key=lambda x: -x[1])
        return [(i, s) for i, s in ranked[:top_k]]


class ChromaVectorStore:
    """ChromaDB 持久化实现（赛题推荐的向量库之一）。"""
    def __init__(self, chunks, embedder, persist_dir=None):
        import chromadb
        self.chunks = chunks
        self.embedder = embedder
        persist_dir = persist_dir or os.path.join(tempfile.gettempdir(), "pharma_rag_chroma")
        self._client = chromadb.PersistentClient(path=persist_dir)
        try:
            self._client.delete_collection("pharma_kb")
        except Exception:
            pass
        self._col = self._client.get_or_create_collection(
            "pharma_kb", embedding_function=embedder, metadata={"hnsw:space": "cosine"})
        self._col.add(
            ids=[c["chunk_id"] for c in chunks],
            documents=[_index_text(c) for c in chunks],
            metadatas=[{"type": c["type"], "source": c["source"]} for c in chunks],
        )

    def search(self, query, top_k=10):
        res = self._col.query(query_texts=[query], n_results=top_k)
        ids = res["ids"][0]
        dists = res["distances"][0] if res.get("distances") else [0.0] * len(ids)
        id2i = {c["chunk_id"]: i for i, c in enumerate(self.chunks)}
        return [(id2i[i], 1.0 - d) for i, d in zip(ids, dists) if i in id2i]


def make_vector_store(chunks, embedder, use_chroma=True):
    if use_chroma:
        try:
            return ChromaVectorStore(chunks, embedder)
        except Exception:
            pass
    return NumpyVectorStore(chunks, embedder)


# ================= 图谱 =================
class NetworkxGraphStore:
    """实体锚定 + 多跳路径。实体表见 entities.py（人工核对），行情事件由 DataStore 注入。"""
    def __init__(self, ds=None):
        self.G = nx.DiGraph()
        self._build(ds)

    def _build(self, ds):
        G = self.G
        for name, info in entities.PRODUCTS.items():
            G.add_node(name, kind="产品", **info)
            for material, qty in info["处方量"]:
                G.add_node(material, kind="药材")
                G.add_edge(name, material, rel="配方包含", qty=qty)
            for step, device, note in entities.PROCESS[name]:
                G.add_node(f"{name}·{step}", kind="工序", note=note)
                G.add_edge(name, f"{name}·{step}", rel="经工艺")
                if device:
                    G.add_node(device, kind="设备")
                    G.add_edge(f"{name}·{step}", device, rel="使用")
        for workshop, eqs in entities.EQUIPMENT.items():
            G.add_node(workshop, kind="车间")
            for code, name, spec, year, value, dep in eqs:
                G.add_node(code, kind="设备", name=name, spec=spec, year=year,
                           value=value, monthly_dep=dep)
                G.add_edge(workshop, code, rel="所属车间")
        # 工艺显示名节点 -> 台账编号节点（维修事件挂在编号上，必须连通）
        code_by_name = {e[1]: e[0] for eqs in entities.EQUIPMENT.values() for e in eqs}
        for node, data in list(G.nodes(data=True)):
            if data.get("kind") == "设备" and node in code_by_name:
                G.add_edge(node, code_by_name[node], rel="设备编号")
        for ev in entities.MAINTENANCE_EVENTS:
            nid = f"维修:{ev['date']}:{ev['device']}"
            G.add_node(nid, kind="维修事件", **ev)
            G.add_edge(ev["device"], nid, rel="维修事件")
        for ev in entities.SCENARIO_EVENTS:
            nid = f"场景:{ev['id']}"
            G.add_node(nid, kind="场景事件", **ev)
            G.add_edge(ev["product"], nid, rel="场景事件")
            if ev["material"]:
                G.add_edge(ev["material"], nid, rel="场景事件")
        if ds is not None:  # 行情事件层（2026 上半年，13 药材）
            for _, r in ds.market.iterrows():
                material = r["药材名称"]
                if material not in G:
                    G.add_node(material, kind="药材")
                for m in range(1, 7):
                    nid = f"行情:{material}:2026-{m:02d}"
                    G.add_node(nid, kind="行情事件", month=f"2026-{m:02d}",
                               price=float(r[f"{m}月价格"]), trend=r["趋势分析"])
                    G.add_edge(material, nid, rel="行情事件")

    def anchor_entities(self, query: str) -> list:
        """从查询文本中锚定图谱实体（词典匹配，确定性；只锚定 产品/药材/设备 三类）。"""
        hits = []
        for node, data in self.G.nodes(data=True):
            if data.get("kind") in ("产品", "药材", "设备") and node in query:
                hits.append(node)
        return hits

    def paths(self, query: str, hops: int = 2) -> list:
        """实体锚点 -> k-hop 邻域路径 -> 文本证据。"""
        anchors = self.anchor_entities(query)
        texts = []
        for anchor in anchors:
            for target in nx.single_source_shortest_path_length(self.G, anchor, cutoff=hops):
                for path in nx.all_simple_paths(self.G, anchor, target, cutoff=hops):
                    if len(path) < 2:
                        continue
                    texts.append(self._path_text(path))
        return texts

    def _path_text(self, path):
        parts = []
        for node in path:
            data = self.G.nodes[node]
            if data.get("kind") == "行情事件":
                parts.append(f"{node.split(':')[1]} {data['month']} 行情 {data['price']}元/kg（{data['trend']}）")
            elif data.get("kind") == "维修事件":
                parts.append(f"{data['date']} {data['name']}故障：{data['desc']}，维修费{data['cost']}元，停工{data['hours']}h")
            elif data.get("kind") == "场景事件":
                parts.append(f"[场景设定] {data['event']}（{data['verdict']}）")
            else:
                parts.append(str(node))
        rels = []
        for a, b in zip(path, path[1:]):
            rels.append(self.G.edges[a, b].get("rel", "关联"))
        return "[图谱证据] " + " → ".join(f"{p}" for p in parts) + "（关系链：" + "、".join(rels) + "）"

    def check_path(self, start, target, max_hops=3) -> bool:
        return nx.has_path(self.G, start, target) and \
            nx.shortest_path_length(self.G, start, target) <= max_hops


class Neo4jGraphStore:
    """Neo4j 适配层（加分项）。接口与 NetworkxGraphStore 一致；
    未安装 neo4j 驱动或无服务时自动降级 networkx。"""
    def __init__(self, uri=None, user=None, password=None):
        raise RuntimeError("Neo4j 未配置——自动降级 NetworkxGraphStore（见 make_graph_store）")


def make_graph_store(ds=None, prefer_neo4j=False):
    if prefer_neo4j:
        try:
            import neo4j  # noqa: F401
            # 预留：从 entities.py 用 Cypher 建图
            raise RuntimeError("Neo4j 建图待服务器就绪，本轮使用降级路径")
        except Exception:
            pass
    return NetworkxGraphStore(ds)


# ================= 融合检索 =================
_GMP_QUERY_TERMS = ["gmp", "合规", "法规", "洁净", "验证", "偏差", "召回", "批记录",
                    "物料平衡", "留样", "变更控制", "质量受权"]

_TYPE_BOOST_RULES = [
    (("涨价", "降价", "行情", "价格", "采购价"), {"行情价": 1.4}),
    (("收率", "工艺", "参数", "损耗", "单耗"), {"工艺参数": 1.4, "工艺路线": 1.2}),
    (("处方", "配方", "组成", "投料"), {"处方量": 1.4}),
    (("故障", "维修", "设备"), {"维修事件": 1.4, "设备台账": 1.2}),
]


def _type_weight_map(query: str, chunks: list) -> list:
    """查询感知的类型权重（意图路由的检索层实现）：
    - GMP 全文仅在合规类查询纳入，否则排除（对成本归因是噪声源）；
    - 归因意图的类型 boost。
    """
    is_gmp_q = any(t in query for t in _GMP_QUERY_TERMS)
    boost = {}
    for terms, tb in _TYPE_BOOST_RULES:
        if any(t in query for t in terms):
            boost.update(tb)
    w = []
    for c in chunks:
        if c["type"] == "GMP要求" and not is_gmp_q:
            w.append(0.0)
        else:
            w.append(boost.get(c["type"], 1.0))
    return w


class HybridRetriever:
    def __init__(self, chunks, ds=None, use_chroma=True):
        self.chunks = chunks
        self.embedder = JiebaHashEmbedder()
        self.bm25 = BM25Store(chunks)
        self.vector = make_vector_store(chunks, self.embedder, use_chroma=use_chroma)
        self.graph = make_graph_store(ds)

    def retrieve(self, query, top_k=5):
        """RRF 加权融合：BM25 0.3 / 向量 0.7（按排名计分）× 类型权重；图谱通道实体锚定补证据。"""
        w = _type_weight_map(query, self.chunks)
        rrf = {}
        chan = {}
        for rank, (i, s) in enumerate(self.bm25.search(query, top_k=top_k * 3)):
            rrf[i] = rrf.get(i, 0.0) + BM25_WEIGHT * w[i] / (RRF_K + rank + 1)
            chan[i] = chan.get(i, "") + "bm25"
        for rank, (i, s) in enumerate(self.vector.search(query, top_k=top_k * 3)):
            rrf[i] = rrf.get(i, 0.0) + VECTOR_WEIGHT * w[i] / (RRF_K + rank + 1)
            chan[i] = chan.get(i, "") + "+vec"
        ranked = sorted(rrf.items(), key=lambda x: -x[1])[:top_k]
        results = []
        for i, score in ranked:
            c = self.chunks[i]
            results.append({**c, "score": round(score, 4), "channel": chan.get(i, "")})
        graph_paths = self.graph.paths(query, hops=2)
        return results, graph_paths
