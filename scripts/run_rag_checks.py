# -*- coding: utf-8 -*-
"""免 pytest 的阶段 2 一键检查：python scripts/run_rag_checks.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding="utf-8")  # 必须先于任何中文输出（jieba 日志等）

from app.rag import retrieve as r  # noqa: E402


def main():
    print("=" * 62)
    print("  阶段 2 验收：RAG 知识库（三通道 + 图谱 + 过滤）")
    print("=" * 62)

    kb = r.knowledge_base()
    chunks = kb.chunks
    print(f"\n[知识块] 共 {len(chunks)} 块，来源 {len({c['source'] for c in chunks})} 个")
    from collections import Counter
    for t, n in Counter(c["type"] for c in chunks).most_common():
        print(f"  - {t}: {n}")

    print("\n[归因驱动查询集]")
    queries = [
        ("金银花涨价的原因", "行情价", "产地减产"),
        ("提取收率下降对材料成本的影响", "工艺参数", "0.08"),
        ("银黄口服液处方组成", "处方量", "金银花"),
        ("胶囊填充机故障记录", "维修事件", "8,500"),
        ("洁净区温湿度要求", "GMP要求", "45-65%"),
        ("口服液车间设备折旧", "设备台账", "折旧"),
    ]
    n_pass = 0
    for q, type_kw, text_kw in queries:
        b = r.retrieve(q, top_k=6)
        hit_type = any(i.type == type_kw for i in b.results)
        joined = " ".join(i.text for i in b.results)
        hit_text = text_kw in joined
        ok = hit_type and hit_text
        n_pass += ok
        print(f"  {'PASS' if ok else 'FAIL'}  {q}  -> {[i.chunk_id for i in b.results[:3]]}")

    print("\n[静态价过滤]")
    b = r.retrieve("黄芩提取物当前价格是多少", top_k=8)
    ok_f = all(i.type != "处方参考价" for i in b.results)
    print(f"  {'PASS' if ok_f else 'FAIL'}  价格类查询结果不含处方参考价块")
    n_pass += ok_f

    print("\n[图谱路径]")
    g = kb.graph
    p1 = g.check_path("银黄口服液", "金银花", max_hops=1)
    p2 = g.check_path("金银花", "行情:金银花:2026-05", max_hops=1)
    p3 = g.check_path("六味地黄胶囊", "EQ-JN-006", max_hops=3)
    p4 = g.check_path("EQ-JN-006", "维修:2026-03:EQ-JN-006", max_hops=1)
    for name, ok in [("银黄→金银花", p1), ("金银花→2026-05行情事件", p2),
                     ("六味→胶囊填充机编号", p3), ("设备编号→2026-03维修事件", p4)]:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    n_pass += p1 + p2 + p3 + p4
    b = r.retrieve("金银花涨价原因", top_k=3)
    print(f"\n[图谱证据示例]")
    for p in b.graph_paths[:3]:
        print(f"  · {p[:80]}...")

    print("\n[边界用例（评审修复验收）]")
    import time as _t
    t0 = _t.time(); b = r.retrieve("", top_k=5)
    ok1 = b.results == [] and _t.time() - t0 < 2.0
    print(f"  {'PASS' if ok1 else 'FAIL'}  空查询守卫（0 结果 + 快速返回）")
    b = r.retrieve("金銀花漲價的原因", top_k=6)
    ok2 = "MKT-金银花" in [i.chunk_id for i in b.results]
    print(f"  {'PASS' if ok2 else 'FAIL'}  繁体查询命中行情块")
    from app.rag.embed import JiebaIdfHashEmbedder, _h, tokenize
    corpus = [c.get("context", "") + " " + c["text"] for c in chunks]
    emb = JiebaIdfHashEmbedder(corpus=corpus)  # 碰撞率是哈希嵌入的专属指标（语义模型不适用）
    vocab = set()
    for t in corpus:
        vocab.update(tokenize(t))
    rate = 1 - len({_h(t, emb.dim) for t in vocab}) / len(vocab)
    ok3 = rate < 0.25
    print(f"  {'PASS' if ok3 else 'FAIL'}  哈希碰撞率 {rate:.1%} < 25%")
    n_pass += ok1 + ok2 + ok3

    total = len(queries) + 1 + 4 + 3
    print("-" * 62)
    print(f"  结论: {n_pass}/{total} 通过" + (" ✅ 阶段 2 下闸" if n_pass == total else " ❌ 需修复"))
    return 0 if n_pass == total else 1


if __name__ == "__main__":
    sys.exit(main())
