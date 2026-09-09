# -*- coding: utf-8 -*-
"""演示预热脚本：起 mock 服务后预发演示任务（-DONE 已完成 / -FAST 快速确认 / 常规）。"""
from ..agents.llm import make_llm
from ..agents.prompts import M4_1_RPA_TASK
from .client import RPAClient
from .ledger import assign_task_id


def _demo_task(product, root, month, suffix=""):
    llm = make_llm()
    prompt = (M4_1_RPA_TASK + f"\n输入: 产品={product} 月份={month} 根因={root}")
    import json
    raw = llm.invoke([{"role": "user", "content": prompt}])
    try:
        task = json.loads(raw)
    except json.JSONDecodeError:
        task = {"task_id": None, "task_title": f"核查{product}{month}成本异常", "assignee": {"name": "张伟", "department": "采购部"},
                "source": {"analysis_type": "月度成本分析", "analysis_month": month, "product": product, "finding": root},
                "priority": "high", "deadline": "2026-06-30", "suggestion": "核查", "notify_method": "wechat", "created_at": "2026-06-01T09:00:00"}
    task["task_id"] = assign_task_id(product, root, month) + suffix
    return task


def warmup(client: RPAClient = None) -> list:
    """预发 3 个演示任务：-DONE（已完成演示）/ -FAST（快速确认）/ 常规。"""
    client = client or RPAClient()
    specs = [
        ("银黄口服液", "金银花涨价-采购合同", "2026-05", "-DONE"),
        ("板蓝根颗粒", "板蓝根涨价-流感需求", "2026-05", "-FAST"),
        ("六味地黄胶囊", "设备故障-停工", "2026-03", ""),
    ]
    results = []
    for product, root, month, suffix in specs:
        task = _demo_task(product, root, month, suffix)
        results.append((task, client.push_task(task)))
    return results
