# -*- coding: utf-8 -*-
"""验证3：LangChain 桥接实操验证。

证明：BaseRetriever 与 LangChain 生态真实兼容（invoke / LCEL 组合 / 元数据完整）。
"""
from langchain_core.documents import Document
from langchain_core.runnables import RunnableLambda

from app.rag.langchain_bridge import PharmaKnowledgeRetriever


def test_invoke_returns_documents():
    retriever = PharmaKnowledgeRetriever(k=5)
    docs = retriever.invoke("金银花涨价原因")
    assert docs, "返回空列表"
    assert all(isinstance(d, Document) for d in docs)


def test_metadata_complete():
    docs = PharmaKnowledgeRetriever(k=5).invoke("金银花涨价原因")
    text_docs = [d for d in docs if d.metadata.get("type") != "检索告警"]
    assert text_docs, "无正文文档"
    for d in text_docs:
        for key in ("chunk_id", "source", "page", "type", "channel", "score"):
            assert key in d.metadata, f"缺元数据 {key}: {d.metadata}"


def test_graph_channel_document_present():
    docs = PharmaKnowledgeRetriever(k=5).invoke("金银花涨价原因")
    channels = {d.metadata.get("channel") for d in docs}
    assert "graph" in channels, "图谱通道 Document 缺失"


def test_lcel_composition():
    retriever = PharmaKnowledgeRetriever(k=3)
    chain = RunnableLambda(lambda q: f"请基于以下证据分析: {q}") | retriever
    docs = chain.invoke("金银花涨价原因")
    assert docs and all(isinstance(d, Document) for d in docs)
