# -*- coding: utf-8 -*-
"""权重消融验证：0.3/0.7（README 建议值）与 0.5/0.5、0.2/0.8 在归因查询集上的命中对比。

结论写入 README（技术文档引用）：三种权重在确定性嵌入下命中率一致（6/6），
查询感知类型权重层起主导作用——按 README 建议保留 0.3/0.7。
"""
import pytest

import app.rag.store as st
from app.rag.retrieve import retrieve

QUERIES = [
    ("金银花涨价的原因", "行情价", "产地减产"),
    ("提取收率下降对材料成本的影响", "工艺参数", "0.08"),
    ("银黄口服液处方组成", "处方量", "金银花"),
    ("胶囊填充机故障记录", "维修事件", "8,500"),
    ("洁净区温湿度要求", "GMP要求", "45-65%"),
    ("口服液车间设备折旧", "设备台账", "折旧"),
]

DEFAULT = (0.3, 0.7)


def _hits():
    n = 0
    for q, tk, tw in QUERIES:
        b = retrieve(q, top_k=6)
        if any(i.type == tk for i in b.results) and tw in " ".join(i.text for i in b.results):
            n += 1
    return n


def test_weight_ablation():
    st.BM25_WEIGHT, st.VECTOR_WEIGHT = DEFAULT
    baseline = _hits()
    assert baseline == len(QUERIES), f"默认权重 {DEFAULT} 未达全命中: {baseline}/{len(QUERIES)}"
    results = {f"{DEFAULT[0]}/{DEFAULT[1]}": baseline}
    try:
        for w in [(0.5, 0.5), (0.2, 0.8)]:
            st.BM25_WEIGHT, st.VECTOR_WEIGHT = w
            n = _hits()
            results[f"{w[0]}/{w[1]}"] = n
            assert n == len(QUERIES), f"权重 {w} 命中 {n}/{len(QUERIES)}，低于默认"
    finally:
        st.BM25_WEIGHT, st.VECTOR_WEIGHT = DEFAULT
    # 记录供文档引用
    print(f"权重消融: {results}")
