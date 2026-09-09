# -*- coding: utf-8 -*-
"""人工确认网关（human-in-the-loop）+ 状态追踪看板数据。

- 任务先生成进"待确认"清单（M4-3 审批助手给风险评估）；
- 用户逐条确认后才真正推送 RPA 接口（答辩回答鉴权质疑的武器）；
- 状态追踪：已生成/已发送/已确认计数（对接 mock 的 /api/stats 与任务状态）。
"""
import json

from ..agents.llm import MockLLM, make_llm
from ..agents.prompts import M4_3_HUMAN_GATE
from .client import RPAClient


class Gateway:
    def __init__(self, client: RPAClient = None, llm=None):
        self.client = client or RPAClient()
        self.llm = llm or make_llm()
        self.pending: list = []   # 待确认任务
        self.sent: list = []      # 已推送

    def review(self, tasks: list) -> list:
        """M4-3 审批助手：给每任务打风险点与建议。"""
        prompt = M4_3_HUMAN_GATE + "\n待推送任务:\n" + json.dumps(tasks, ensure_ascii=False)
        raw = self.llm.invoke([{"role": "user", "content": prompt}])
        try:
            parsed = json.loads(raw)
            reviews = parsed.get("review", [])
        except json.JSONDecodeError:
            reviews = [{"task_id": t.get("task_id"), "risk": "待人工评估", "suggest": "hold"} for t in tasks]
        by_id = {r.get("task_id"): r for r in reviews}
        return [{"task": t, "review": by_id.get(t.get("task_id"),
                                                 {"risk": "待人工评估", "suggest": "hold"})}
                for t in tasks]

    def enqueue(self, tasks: list):
        self.pending.extend(self.review(tasks))
        return self.pending

    def confirm(self, task_id: str) -> dict:
        """逐条人工确认后推送。"""
        for item in self.pending:
            if item["task"]["task_id"] == task_id:
                result = self.client.push_task(item["task"])
                if result.get("ok"):
                    self.sent.append(item["task"])
                    self.pending.remove(item)
                return result
        return {"ok": False, "error": f"task_id {task_id} 不在待确认清单"}

    def board(self) -> dict:
        """任务追踪看板数据。"""
        stats = self.client.stats()
        sent = self.client.list_tasks()
        tasks = (sent.get("data") or {}).get("tasks", [])
        status_count = {}
        for t in tasks:
            st = t.get("status", "sent")
            status_count[st] = status_count.get(st, 0) + 1
        return {"pending": len(self.pending), "sent": len(self.sent),
                "server_stats": stats.get("data"), "status_count": status_count}
