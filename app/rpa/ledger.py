# -*- coding: utf-8 -*-
"""幂等任务台账：task_id = TASK-{YYYYMM}-{序号}，键 = 产品+根因+月份。

- 同键复用同 ID（金银花跨 4-5 月：各月同根因任务 ID 含月份，互不冲突）；
- 台账持久化到产物目录，进程重启不丢。
"""
import json
import os
import tempfile
from pathlib import Path


def _ledger_path() -> Path:
    d = Path(os.environ.get("AGENT_ARTIFACT_DIR", Path(tempfile.gettempdir()) / "pharma_agents"))
    d.mkdir(parents=True, exist_ok=True)
    return d / "rpa_ledger.json"


def _load() -> dict:
    p = _ledger_path()
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"seq": {}, "tasks": {}}


def _save(ledger: dict):
    _ledger_path().write_text(json.dumps(ledger, ensure_ascii=False, indent=1), encoding="utf-8")


def assign_task_id(product: str, root_cause: str, month: str) -> str:
    """幂等键 = 产品+根因+月份。"""
    key = f"{product}|{root_cause}|{month}"
    ledger = _load()
    if key in ledger["tasks"]:
        return ledger["tasks"][key]
    mm = month.replace("-", "")
    seq = ledger["seq"].get(mm, 0) + 1
    ledger["seq"][mm] = seq
    task_id = f"TASK-{mm}-{seq:04d}"
    ledger["tasks"][key] = task_id
    _save(ledger)
    return task_id


def ledger_state() -> dict:
    return _load()
