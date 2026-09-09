# -*- coding: utf-8 -*-
"""边界用例（评审修复验收）：空查询、纯符号、超长、繁体、双后端一致性、哈希碰撞率。"""
import time

import pytest

from app.rag import retrieve as r
from app.rag.embed import JiebaIdfHashEmbedder, _h, tokenize
from app.rag.parse import build_document_chunks
from app.rag.store import HybridRetriever


@pytest.fixture(scope="module", autouse=True)
def _warmup():
    """预热知识库：构建耗时（Chroma 写入 137×8192 向量等）不计入查询限时断言。"""
    r.knowledge_base()


def test_empty_query_guarded_and_fast():
    t0 = time.time()
    b = r.retrieve("", top_k=5)
    elapsed = time.time() - t0
    assert b.results == [], "空查询不应返回结果"
    assert b.graph_paths == [], "空查询不应触发图谱锚定"
    assert any("空查询" in w for w in b.warnings)
    assert elapsed < 2.0, f"空查询耗时过长: {elapsed:.2f}s（守卫失效）"


@pytest.mark.parametrize("q", ["???", "   ", "!@#$%^&*()", "？？？"])
def test_symbol_queries_fast_no_crash(q):
    t0 = time.time()
    b = r.retrieve(q, top_k=5)
    assert time.time() - t0 < 2.0
    assert isinstance(b.results, list)


def test_overlong_query_no_crash():
    q = "金银花涨价的原因" * 300  # ~2700 字符
    t0 = time.time()
    b = r.retrieve(q, top_k=5)
    assert time.time() - t0 < 5.0
    assert isinstance(b.results, list)


def test_traditional_chinese_query_hits():
    """繁体查询经映射后命中行情块（评审修复 P1-4）。"""
    b = r.retrieve("金銀花漲價的原因", top_k=6)
    ids = [i.chunk_id for i in b.results]
    assert "MKT-金银花" in ids, f"繁体查询未命中: {ids}"


def test_dual_backend_consistency():
    """chroma 与 numpy 降级后端 top-5 逐位一致（防未来漂移）。

    强制哈希嵌入保证跨进程确定性；语义模型路径的等价性由同批嵌入函数保证。
    """
    chunks = build_document_chunks()
    corpus = [c.get("context", "") + " " + c["text"] for c in chunks]
    emb = JiebaIdfHashEmbedder(corpus=corpus)
    hc = HybridRetriever(chunks, use_chroma=True, embedder=emb)
    hn = HybridRetriever(chunks, use_chroma=False, embedder=emb)
    for q in ["金银花涨价的原因", "提取收率下降对材料成本的影响", "洁净区温湿度要求"]:
        rc, _ = hc.retrieve(q, top_k=5)
        rn, _ = hn.retrieve(q, top_k=5)
        assert [c["chunk_id"] for c in rc] == [c["chunk_id"] for c in rn], f"双后端不一致: {q}"


def test_hash_collision_rate_monitored():
    """词表→桶映射碰撞率断言（评审修复：防止向量通道静默劣化）。

    显式构造哈希嵌入器（语义模型维度不同，不适用此断言）。
    dim=8192、词表≈3000 时碰撞率≈17%；阈值 25% 预留增长空间。
    """
    kb = r.knowledge_base()
    corpus = [c.get("context", "") + " " + c["text"] for c in kb.chunks]
    emb = JiebaIdfHashEmbedder(corpus=corpus)
    vocab = set()
    for t in corpus:
        vocab.update(tokenize(t))
    n_tokens = len(vocab)
    n_buckets = len({_h(t, emb.dim) for t in vocab})
    rate = 1 - n_buckets / n_tokens
    assert rate < 0.25, f"碰撞率超标: {rate:.1%}（词表 {n_tokens} → {n_buckets} 桶）"


def test_synonym_paraphrase_hits_semantic():
    """同义改写查询（6.1 语义检索本义）：有本地语义模型时必测；未安装则 skip 并注明兜底。"""
    from app.rag.embed import SentenceTransformerEmbedder
    if not SentenceTransformerEmbedder.available:
        pytest.skip("语义模型未安装（IDF 哈希兜底中）——安装 sentence-transformers 后自动启用")
    b = r.retrieve("金银花行情为何走高", top_k=8)
    ids = [i.chunk_id for i in b.results]
    assert "MKT-金银花" in ids, f"同义改写查询未命中: {ids}"
