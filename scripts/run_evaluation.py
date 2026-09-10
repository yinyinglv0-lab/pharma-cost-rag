# -*- coding: utf-8 -*-
"""6.1 评测脚本：3 评测场景 × 4 项指标（报告结构/归因命中/差异准确率/RPA成功率）→ 评测报告。"""
import io
import json
import re
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

import docx

from app.agents.graph import run_agent
from app.agents.llm import MockLLM, make_llm
from app.benchmark.steps import step1_find
from app.evaluation.engine import evaluate
from app.report.render import build_report

ROOT = Path(__file__).parent.parent
REQUIRED_CHAPTERS = ["封面与基本信息", "总成本概览", "成本要素明细分析", "重点产品专项分析",
                     "总结与建议"]
SCENARIOS = [("银黄口服液", "2026-05"), ("板蓝根颗粒", "2026-02"), ("六味地黄胶囊", "2026-03")]
GOLDEN_DIFF = {
    "材料": {"银黄口服液": -0.01, "板蓝根颗粒": -4.47, "六味地黄胶囊": -5.05},
    "人工": {"银黄口服液": -11.70, "板蓝根颗粒": -11.06, "六味地黄胶囊": -10.32},
    "制费": {"银黄口服液": -7.90, "板蓝根颗粒": -9.42, "六味地黄胶囊": -8.99},
    "单位成本": {"银黄口服液": -3.56, "板蓝根颗粒": -6.63, "六味地黄胶囊": -6.40},
}


def run():
    report = {"generated_at": date.today().isoformat(), "scenarios": []}
    all_ok = True

    # ---- 指标1: 报告结构完整度 + 数字零残留 ----
    for product, month in SCENARIOS:
        out = run_agent(f"请生成{product}{month}的月度成本分析报告",
                        session_id=f"ev-{product}-{month}", llm=make_llm())
        data = build_report(product, month, draft=out["draft"], rpa_task=out["rpa_task"],
                            llm=make_llm(), charts=True)
        d = docx.Document(io.BytesIO(data))
        text = "\n".join(p.text for p in d.paragraphs)
        chapters = {c: (c in text) for c in REQUIRED_CHAPTERS}
        residue = len(re.findall(r"\{\{.*?\}\}", text))
        report["scenarios"].append({
            "product": product, "month": month,
            "pipeline_status": out["status"],
            "guard_passed": out["guard"]["passed"],
            "chapters": chapters, "chapters_hit": sum(chapters.values()),
            "placeholder_residue": residue,
            "charts": len(d.inline_shapes),
        })

    # ---- 指标2: 归因命中（对照标注集） ----
    hit = evaluate()
    report["attribution"] = {"hit_rate": hit["hit_rate"], "items": hit["items"]}

    # ---- 指标3: 差异计算准确率（vs 金丝雀，相对误差 ≤1%） ----
    rows = step1_find()["rows"]
    errors = []
    for r in rows:
        golden = GOLDEN_DIFF[r["element"]][r["product"]]
        rel = abs(r["diff_pct"] - golden) / max(abs(golden), 1e-9) * 100
        errors.append({"row": f"{r['product']}-{r['element']}", "calc": r["diff_pct"],
                       "golden": golden, "rel_error_pct": round(rel, 4)})
    max_err = max(e["rel_error_pct"] for e in errors)
    report["diff_accuracy"] = {"rows": len(errors), "max_rel_error_pct": max_err,
                               "within_1pct": max_err <= 1.0, "details": errors}

    # ---- 指标4: RPA 触发成功率（生成 + 幂等唯一性 + mock 推送） ----
    ids = []
    for product, month in SCENARIOS:
        out = run_agent(f"请生成{product}{month}的月度成本分析报告并派发整改任务",
                        session_id=f"ev-rpa-{product}-{month}", llm=MockLLM())
        if out.get("rpa_task"):
            ids.append(out["rpa_task"]["task_id"])
    report["rpa"] = {"generated": len(ids), "success_rate": f"{len(ids)}/{len(SCENARIOS)}",
                     "unique_ids": len(set(ids)) == len(ids), "task_ids": ids}
    all_ok = all(s["pipeline_status"] == "完成" and s["guard_passed"]
                 and s["chapters_hit"] == 5 and s["placeholder_residue"] == 0
                 for s in report["scenarios"])
    all_ok = all_ok and hit["hit_rate"].startswith("6/6") and report["diff_accuracy"]["within_1pct"] \
        and report["rpa"]["generated"] == 3 and report["rpa"]["unique_ids"]
    report["overall"] = "通过" if all_ok else "存在不合格项"

    # ---- 产出《评测报告》 ----
    (ROOT / "evidence").mkdir(exist_ok=True)
    (ROOT / "evidence" / "evaluation_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = [f"# 评测报告（{report['generated_at']} 自动生成）", ""]
    lines.append(f"**总判定：{report['overall']}**")
    lines.append("")
    lines.append("## 1. 报告结构完整度（3 场景 × 5 必需章节）")
    for s in report["scenarios"]:
        lines.append(f"- {s['product']} {s['month']}：流水线 {s['pipeline_status']}，"
                     f"守卫 {'通过' if s['guard_passed'] else '未通过'}，"
                     f"章节 {s['chapters_hit']}/5，占位符残留 {s['placeholder_residue']}，图表 {s['charts']} 张")
    lines.append("")
    lines.append(f"## 2. 归因命中（对照 README 3.1 六事件标注集）")
    lines.append(f"- {hit['hit_rate']}")
    for it in hit["items"]:
        lines.append(f"- {it['id']}：{it['verdict']}（匹配 {it['matched_keywords']}，缺失 {it['missing_keywords']}）")
    lines.append("")
    lines.append("## 3. 差异计算准确率（vs 金丝雀，标准 ≤1%）")
    lines.append(f"- 12 行差异表最大相对误差 **{max_err}%** → {'达标' if max_err <= 1.0 else '超标'}")
    lines.append("")
    lines.append("## 4. RPA 触发成功率")
    lines.append(f"- 任务生成 {report['rpa']['success_rate']}，ID 唯一性 {'通过' if report['rpa']['unique_ids'] else '重复'}"
                 f"：{report['rpa']['task_ids']}")
    lines.append("")
    lines.append("## 5. 附录：评测数据（evaluation_report.json）")
    (ROOT / "evidence" / "评测报告.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(run())
