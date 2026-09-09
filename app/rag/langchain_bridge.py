# -*- coding: utf-8 -*-
"""LangChain 集成专家交付：三通道检索器 → langchain_core BaseRetriever（6.1 框架条款）。

- 每个 Document 携带完整溯源 metadata（source/page/type/channel/chunk_id）；
- 图谱通道证据（channel=graph）一并返回，供下游 chain 引用 [C] 角标；
- 可在 LCEL 链中直接使用：prompt | retriever | llm。
"""
from typing import List

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

from .retrieve import retrieve


class PharmaKnowledgeRetriever(BaseRetriever):
    """三通道（BM25+向量+图谱）混合检索的 LangChain 封装。"""

    k: int = 5
    filter_forbidden: bool = True

    def _get_relevant_documents(self, query: str, *, run_manager=None) -> List[Document]:
        bundle = retrieve(query, top_k=self.k, filter_forbidden=self.filter_forbidden)
        docs = []
        for item in bundle.results:
            docs.append(Document(
                page_content=item.text,
                metadata={
                    "chunk_id": item.chunk_id,
                    "source": item.source,
                    "page": item.page,
                    "doc_version": item.doc_version,
                    "type": item.type,
                    "channel": item.channel,
                    "score": item.score,
                    "title": item.title,
                    "forbid_current_numbers": item.forbid_current_numbers,
                },
            ))
        for w in bundle.warnings:
            docs.append(Document(page_content="", metadata={"warning": w, "type": "检索告警"}))
        return docs
