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


# 领域词繁→简映射（评审修复 P1-4）：评委输入繁体时先归一
_T2S = {
    "金銀花": "金银花", "黃芩": "黄芩", "板藍根": "板蓝根", "熟地黃": "熟地黄",
    "山茱萸": "山茱萸", "山藥": "山药", "澤瀉": "泽泻", "茯苓": "茯苓",
    "牡丹皮": "牡丹皮", "空心膠囊": "空心胶囊", "苯甲酸鈉": "苯甲酸钠",
    "純化水": "纯化水", "銀黃": "银黄", "顆粒": "颗粒", "膠囊": "胶囊",
    "漲價": "涨价", "降價": "降价", "價格": "价格", "單價": "单价",
    "工藝": "工艺", "參數": "参数", "設備": "设备", "維修": "维修",
    "潔淨": "洁净", "溫濕度": "温湿度", "車間": "车间", "折舊": "折旧",
    "處方": "处方", "藥材": "药材", "影響": "影响", "製造費用": "制造费用",
    "產品": "产品", "工廠": "工厂", "記錄": "记录", "提取收率": "提取收率",
}


def _to_simplified(query: str) -> str:
    for trad, simp in sorted(_T2S.items(), key=lambda x: -len(x[0])):
        query = query.replace(trad, simp)
    return query


def _is_numeric_query(query: str) -> bool:
    return any(w in query for w in _NUMERIC_INTENT)


def retrieve(query: str, top_k: int = 5, filter_forbidden: bool = True) -> EvidenceBundle:
    """三通道检索入口。

    规则（v7 硬约束 + 评审修复）：
    - 空查询守卫（P0-1）：返回空 EvidenceBundle，不触发图谱锚定爆炸；
    - 繁体归一（P1-4）；
    - over-fetch 后过滤（P1-5）：先取 top_k×2 再过滤静态价块，保证返回足量合法块；
    - 数值敏感查询自动过滤 forbid_current_numbers=True 的块；
    - 图谱通道输出实体路径，供归因链引用（[C1] 角标来源）。
    """
    query = _to_simplified(query)
    if not query.strip():
        return EvidenceBundle(query=query, warnings=["空查询：未执行检索"])
    kb = _kb()
    results, paths = kb.retrieve(query, top_k=max(top_k * 2, top_k + 5))
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
        if len(bundle.results) >= top_k:
            break
    return bundle


def knowledge_base():
    """供测试/调试直接访问底层三通道。"""
    return _kb()
