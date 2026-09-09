# -*- coding: utf-8 -*-
"""LLM 提供者：MockLLM（离线确定性，测试/无网演示）+ OpenAICompatibleLLM（DeepSeek/Qwen 等）。

- MockLLM：按 Prompt 特征返回确定性 JSON/文本，让状态机与守卫在无 API key 下可测；
- OpenAICompatibleLLM：base_url/api_key 走环境变量，A0 协议前置注入由调用方负责。
"""
import json
import os
import re


class MockLLM:
    """确定性模拟 LLM：依据 Prompt 中的角色标记返回合法 schema 输出。

    仅用于测试与离线演示；线上替换为 OpenAICompatibleLLM。
    """

    def invoke(self, messages) -> str:
        text = " ".join(m if isinstance(m, str) else str(m.get("content", m)) for m in messages)
        if "整改任务调度器" in text:
            from calendar import monthrange
            from datetime import date, timedelta
            from ..core.calc import PRODUCTS
            product = next((p for p in PRODUCTS if p in text), "银黄口服液")
            m = re.search(r"(\d{4})-(\d{2})", text)
            year, mon = (int(m.group(1)), int(m.group(2))) if m else (2026, 5)
            mm = f"{year}{mon:02d}"
            deadline = date(year, mon, monthrange(year, mon)[1]) + timedelta(days=3)
            return json.dumps({
                "task_id": f"TASK-{mm}-0001",
                "task_title": f"请核查{product}{year}年{mon}月成本异常项采购合同调价条款",
                "assignee": {"name": "张伟", "department": "采购部", "role": "采购经理"},
                "source": {"analysis_type": "月度成本分析", "analysis_month": f"{year}-{mon:02d}",
                           "product": product, "finding": f"{product}成本要素超阈值告警"},
                "priority": "high",
                "deadline": deadline.isoformat(),
                "suggestion": "核查采购合同中调价条款；比对新老供应商报价",
                "notify_method": "wechat",
                "created_at": f"{year}-{mon:02d}-01T09:00:00",
            }, ensure_ascii=False)
        if "成本归因分析师" in text:
            # 只从 user 消息（内嵌 fact_pack）取第一个数字 + [S1] 引用（数值锁定协议正向示范）
            last = messages[-1]
            last_text = last["content"] if isinstance(last, dict) else str(last)
            nums = re.findall(r"-?\d+\.\d+", last_text)  # 保留负号（环比可为负）
            v = nums[0] if nums else "0.00"
            return json.dumps({
                "finding": "直接材料成本环比上涨，贡献总成本上涨的主要部分。",
                "chain": f"材料成本变动 {v} 元/盒 [S1]，主要由药材行情传导驱动 [C1]。",
                "suggestion": ["核查A药材采购合同调价条款", "排查提取车间工艺参数"],
                "citations": ["S1", "C1"],
            }, ensure_ascii=False)
        if "差异树" in text and "evidence" in text:
            # M3-3 拆原因：输出可转 RPA 的改进建议（≥3 条，带依据）
            return json.dumps({
                "attribution": "中药二厂人工与制造费用偏高，源于设备老旧与自采规模有限；"
                               "一厂材料端由规模采购占据优势。",
                "suggestions": [
                    "核查中药二厂设备台账与折旧政策，评估更新关键设备的经济性",
                    "对比两厂人工效率（盒/人·日）并排查排产差异",
                    "评估二厂黄芩自采规模扩大对材料成本的改善空间",
                    "将人工效率差距纳入月度对标指标跟踪",
                ],
            }, ensure_ascii=False)
        if "审批助手" in text:
            return json.dumps({"review": [{"task_id": "TASK-202605-0001",
                                           "risk": "将通知到采购经理", "suggest": "confirm"}]},
                              ensure_ascii=False)
        return json.dumps({"note": "mock-llm-default"}, ensure_ascii=False)


class OpenAICompatibleLLM:
    """OpenAI 兼容接口（DeepSeek API / 通义千问等），环境变量配置：

    LLM_API_KEY / LLM_BASE_URL / LLM_MODEL。
    """

    def __init__(self):
        self.api_key = os.environ.get("LLM_API_KEY", "")
        self.base_url = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com/v1")
        self.model = os.environ.get("LLM_MODEL", "deepseek-chat")

    def invoke(self, messages, temperature: float = 0.0) -> str:
        import requests
        resp = requests.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": self.model, "messages": messages, "temperature": temperature},
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


def make_llm(offline: bool = False):
    """LLM 工厂：无 key 或 offline=True 时用 MockLLM（演示机兜底，同语义模型两级方案）。"""
    if offline or not os.environ.get("LLM_API_KEY"):
        return MockLLM()
    return OpenAICompatibleLLM()
