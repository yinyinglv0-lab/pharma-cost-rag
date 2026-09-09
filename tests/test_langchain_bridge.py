# -*- coding: utf-8 -*-
"""LangChain 集成专家验收：BaseRetriever 元数据完整、三通道文档可达、LCEL 可组合。"""
from langchain_core.documents import Document

from app.rag.langchain_bridge import PharmaKnowledgeRetriever


def test_retriever_returns_documents_with_metadata():
    retriever = PharmaKnowledgeRetriever(k=5)
    docs = retriever.invoke("金银花涨价的原因")
    assert docs, "无文档返回"
    assert all(isinstance(d, Document) for d in docs)
    text_docs = [d for d in docs if d.metadata.get("type") != "检索告警"]
    for d in text_docs:
        for key in ("chunk_id", "source", "type", "channel"):
            assert key in d.metadata, f"缺 metadata: {key}"
    channels = {d.metadata["channel"] for d in text_docs}
    assert "graph" in channels, "图谱通道文档应包含在内"


def test_retriever_hits_expected_type():
    docs = PharmaKnowledgeRetriever(k=6).invoke("金银花涨价的原因")
    types = [d.metadata["type"] for d in docs]
    assert "行情价" in types


def test_lcel_composition():
    from langchain_core.runnables import RunnableLambda
    retriever = PharmaKnowledgeRetriever(k=3)
    chain = RunnableLambda(lambda q: f"请基于以下证据分析: {q}") | retriever
    docs = chain.invoke("金银花涨价的原因")
    assert docs
