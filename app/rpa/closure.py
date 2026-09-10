# -*- coding: utf-8 -*-
"""闭环回写（交付级）：系统自维护"任务→状态→后续月份指标变化"关联表。

- mock 服务无回写接口——整改是否见效由系统自己对后续月份指标做 DiD 估计；
- 关联表持久化到产物目录（closure_ledger.json），前端/答辩可展示"整改效果追踪"。
"""
import json
import os
import tempfile
from pathlib import Path

from ..forecast.engine import did_effect


def _path() -> Path:
    d = Path(os.environ.get("AGENT_ARTIFACT_DIR", Path(tempfile.gettempdir()) / "pharma_agents"))
    d.mkdir(parents=True, exist_ok=True)
    return d / "closure_ledger.json"


def _load() -> dict:
    p = _path()
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"records": []}


def record_closure(task: dict, target: str = "材料", control: str = "人工") -> dict:
    """任务完成 → 计算目标要素后续月份环比 vs 对照要素环比 → 记录净效应。"""
    ledger = _load()
    rec = {
        "task_id": task.get("task_id"),
        "task_title": task.get("task_title"),
        "product": (task.get("source") or {}).get("product"),
        "task_month": (task.get("source") or {}).get("analysis_month"),
        "status": "completed",
    }
    try:
        d = did_effect(rec["product"], target=target, control=control)
        rec.update({"target_mom_pct": d.target_mom_pct, "control_mom_pct": d.control_mom_pct,
                    "net_effect_pct": d.net_effect_pct, "warnings": d.warnings})
    except Exception as e:
        rec["error"] = str(e)
    ledger["records"] = [r for r in ledger["records"] if r["task_id"] != rec["task_id"]] + [rec]
    _path().write_text(json.dumps(ledger, ensure_ascii=False, indent=1), encoding="utf-8")
    return rec


def closure_records() -> list:
    return _load()["records"]
