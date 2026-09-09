# -*- coding: utf-8 -*-
"""检索门面：EvidenceBundle + 类型过滤（写作层禁引"处方参考价"为当期数字）。"""
from dataclasses import dataclass, field
from functools import lru_cache
from typing import List, Optional

from .parse import build_document_chunks
from .store import HybridRetriever

# 数值敏感意图词：命中则过滤 forbid_current_numbers 的块（I5 防线，纵深防御第二层）
_NUMERIC_INTENT = ["价格", "单价", "多少钱", "元/kg", "元/盒", "当前", "本月", "成本是多少",
                   "涨价", "降价", "行情"]


@dataclass
class EvidenceItem:
    chunk_id: str
    source: str
    page: Optional[int]
    doc_version: str
    type: str
    channel: str
    score: float
    title: str
    text: str
    forbid_current_numbers: bool = False


@dataclass
class EvidenceBundle:
    query: str
    results: List[EvidenceItem] = field(default_factory=list)
    graph_paths: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def top(self, k: int = 5) -> List[EvidenceItem]:
        return self.results[:k]


@lru_cache(maxsize=1)
def _kb():
    from ..core.datastore import DataStore
    chunks = build_document_chunks()
    return HybridRetriever(chunks, ds=DataStore())


def _is_numeric_query(query: str) -> bool:
    return any(w in query for w in _NUMERIC_INTENT)


def retrieve(query: str, top_k: int = 5, filter_forbidden: bool = True) -> EvidenceBundle:
    """三通道检索入口。

    规则（v7 硬约束）：
    - 数值敏感查询（价格/行情/成本）自动过滤 forbid_current_numbers=True 的块；
    - 图谱通道输出实体路径，供归因链引用（[C1] 角标来源）。
    """
    kb = _kb()
    results, paths = kb.retrieve(query, top_k=top_k)
    bundle = EvidenceBundle(query=query, graph_paths=paths[:10])
    numeric = _is_numeric_query(query)
    for r in results:
        if numeric and filter_forbidden and r["forbid_current_numbers"]:
            bundle.warnings.append(
                f"已过滤静态价块 {r['chunk_id']}（type={r['type']}，禁引为当期数字）")
            continue
        bundle.results.append(EvidenceItem(
            chunk_id=r["chunk_id"], source=r["source"], page=r.get("page"),
            doc_version=r["doc_version"], type=r["type"], channel=r.get("channel", ""),
            score=r.get("score", 0.0), title=r["title"], text=r["text"],
            forbid_current_numbers=r["forbid_current_numbers"],
        ))
    return bundle


def knowledge_base():
    """供测试/调试直接访问底层三通道。"""
    return _kb()
