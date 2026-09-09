# -*- coding: utf-8 -*-
"""免 pytest 的阶段 3 一键检查：python scripts/run_agent_checks.py"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from app.agents.graph import run_agent
from app.agents.llm import MockLLM
from app.agents.prompts import PROMPTS, TEMPERATURE_RULE
from app.rag.langchain_bridge import PharmaKnowledgeRetriever


def main():
    tmp = Path(tempfile.mkdtemp(prefix="agent_demo_"))
    import os
    os.environ["AGENT_ARTIFACT_DIR"] = str(tmp)
    print("=" * 62)
    print("  阶段 3 验收：多 Agent 编排（Prompt/状态机/守卫/LangChain）")
    print("=" * 62)

    print(f"\n[提示词落盘] {len(PROMPTS)} 个 Prompt；{TEMPERATURE_RULE}")
    ok1 = len(PROMPTS) >= 13 and all(p["template"].strip() for p in PROMPTS.values())
    print(f"  {'PASS' if ok1 else 'FAIL'}  全量落盘且模板非空")

    print("\n[端到端流水线]")
    out = run_agent("请生成银黄口服液2026-05的月度成本分析报告", session_id="demo",
                    llm=MockLLM())
    ok2 = out["status"] == "完成" and out["guard"]["passed"] and bool(out["rpa_task"])
    print(f"  {'PASS' if ok2 else 'FAIL'}  状态={out['status']}, 守卫={out['guard']['passed']}, "
          f"evidence {len(out['evidence'])} 条, rpa_task={'有' if out.get('rpa_task') else '无'}")
    if out.get("rpa_task"):
        print(f"    任务: {out['rpa_task']['task_id']} | {out['rpa_task']['task_title']}")

    print("\n[需澄清兜底]")
    o3 = run_agent("你好", session_id="demo2", llm=MockLLM())
    print(f"  {'PASS' if o3['status'] == '需澄清' else 'FAIL'}  状态={o3['status']}")

    print("\n[LangChain BaseRetriever]")
    docs = PharmaKnowledgeRetriever(k=5).invoke("金银花涨价的原因")
    ok4 = docs and any(d.metadata.get("channel") == "graph" for d in docs)
    print(f"  {'PASS' if ok4 else 'FAIL'}  {len(docs)} 个 Document, 图谱通道={'有' if ok4 else '无'}")

    total = ok1 + ok2 + (o3["status"] == "需澄清") + ok4
    print("-" * 62)
    print(f"  结论: {total}/4 通过" + (" ✅ 阶段 3 下闸" if total == 4 else " ❌ 需修复"))
    return 0 if total == 4 else 1


if __name__ == "__main__":
    sys.exit(main())
