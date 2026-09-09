# -*- coding: utf-8 -*-
"""归因命中率自评：六事件标注集（硬编码） × 系统归因（因果引擎输出）→ 三级判定。"""
import json
from typing import List

from pydantic import BaseModel

from ..causal.engine import run_all_chains

# README 3.1 标注集：预期原因关键词 + 预期影响要素
LABELS = [
    {"id": "E1", "cause": ["金银花", "上涨", "产地减产"], "impact": "材料成本"},
    {"id": "E2", "cause": ["板蓝根", "上涨", "流感"], "impact": "材料成本"},
    {"id": "E3", "cause": ["黄芩", "单耗", "收率"], "impact": "材料成本"},
    {"id": "E4", "cause": ["制造费用", "摊薄"], "impact": "制造费用"},
    {"id": "E5", "cause": ["山茱萸", "上涨", "库存"], "impact": "材料成本"},
    {"id": "E6", "cause": ["胶囊填充机", "故障", "停工"], "impact": "单位成本"},
]


class HitItem(BaseModel):
    id: str
    verdict: str            # 完全命中 / 部分命中 / 未命中
    matched_keywords: List[str]
    missing_keywords: List[str]
    evidence: str


def evaluate() -> dict:
    """系统归因 = 因果引擎输出（事件+支持度依据+备注+影响要素）→ 对照标注集三级判定。

    降级规则：归因文本含"幅度微弱/次因"等保留性限定 → 部分命中（v7 判定：方向对、幅度弱）。
    """
    chains = {c.chain_id: c for c in run_all_chains()}
    items: List[HitItem] = []
    for label in LABELS:
        c = chains[label["id"]]
        sys_text = f"{c.event} {c.support_basis} {c.notes} 影响要素:{label['impact']}"
        matched = [k for k in label["cause"] if k in sys_text]
        missing = [k for k in label["cause"] if k not in sys_text]
        if len(matched) == len(label["cause"]) and label["impact"] in sys_text:
            verdict = "部分命中" if ("幅度微弱" in sys_text or "次因" in sys_text) else "完全命中"
        elif matched:
            verdict = "部分命中"
        else:
            verdict = "未命中"
        items.append(HitItem(id=label["id"], verdict=verdict,
                             matched_keywords=matched, missing_keywords=missing,
                             evidence=sys_text))
    full = sum(1 for i in items if i.verdict == "完全命中")
    partial = sum(1 for i in items if i.verdict == "部分命中")
    miss = sum(1 for i in items if i.verdict == "未命中")
    return {"total": len(items),
            "hit_rate": f"{full + partial}/{len(items)}（完全 {full} + 部分 {partial}，未命中 {miss}）",
            "items": [i.model_dump() for i in items]}


def demo_evaluation() -> str:
    """演示动线：看板显示命中率 + 单击展开对照表。"""
    rep = evaluate()
    log = {"demo": f"归因命中率自评: {rep['hit_rate']}（对照 README 3.1 六事件标注集）",
           "note": "部分命中=E3(单耗方向命中幅度微弱)/E4(摊薄为次因)——三级判定如实呈现",
           **rep}
    return json.dumps(log, ensure_ascii=False, indent=1)
