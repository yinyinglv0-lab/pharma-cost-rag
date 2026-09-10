# -*- coding: utf-8 -*-
"""数据完整性工程师交付：一致性守卫。

规则（v7 终版 + 四轮评审教训）：
1. 占位符残留：{{...}} 出现在草稿 → 阻断；
2. 引用角标：每个数字后 30 字符内必须有 [S/K/C] 角标；
3. 数字指纹：草稿中的数字必须出现在 fact_pack 数值集合（±0.01），否则判"疑似幻觉"；
4. [C] 角标仅当 allow_causal=True（存在图谱因果证据）时允许；
5. RPA 任务 schema 逐字段对齐 mock Pydantic（task_id/priority/deadline 格式）。
"""
import json
import re
from dataclasses import dataclass, field
from typing import List

_CITATION = re.compile(r"\[(S|K|C)\d*\]")
# 数字：排除紧跟字母后的（避免把 [S1] 角标中的序号当数字）
_NUMBER = re.compile(r"(?<![A-Za-z])-?\d+(?:\.\d+)?")
_PLACEHOLDER = re.compile(r"\{\{.*?\}\}")

RPA_SCHEMA = {
    "task_id": r"^TASK-\d{6}-\d{4}$",
    "task_title": str, "assignee": dict, "source": dict,
    "priority": {"high", "medium", "low"},
    "deadline": r"^\d{4}-\d{2}-\d{2}$",
    "suggestion": str, "notify_method": str,
    "created_at": r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$",
}
RPA_REQUIRED = {"task_id", "task_title", "assignee", "source", "priority",
                "deadline", "suggestion", "notify_method", "created_at"}


@dataclass
class GuardResult:
    passed: bool
    violations: List[str] = field(default_factory=list)


def _fact_pack_numbers(fact_pack) -> set:
    """递归收集 fact_pack 中全部浮点数（数字指纹对照集）。"""
    nums = set()
    for v in re.findall(r"-?\d+\.\d+", json.dumps(fact_pack, ensure_ascii=False)):
        nums.add(round(float(v), 2))
    return nums


def check_draft(draft_text: str, fact_pack: dict, allow_causal: bool = True) -> GuardResult:
    violations = []

    # 1. 占位符残留
    if _PLACEHOLDER.search(draft_text):
        violations.append("占位符残留: 草稿含未替换的 {{...}}")

    allowed = _fact_pack_numbers(fact_pack)

    # 2+3. 角标与数字指纹（逐数字检查）
    for m in _NUMBER.finditer(draft_text):
        num_text = m.group()
        try:
            value = round(float(num_text), 2)
        except ValueError:
            continue
        tail = draft_text[m.end():m.end() + 30]
        cited = bool(_CITATION.search(tail))
        if not cited:
            violations.append(f"无角标数字: {num_text}")
            continue
        if value not in allowed:
            violations.append(f"数字指纹不符（疑似幻觉）: {num_text}")

    # 4. [C] 角标约束
    if not allow_causal and re.search(r"\[C\d*\]", draft_text):
        violations.append("无因果证据却引用 [C] 角标")

    return GuardResult(passed=not violations, violations=violations)


def check_rpa_task(task: dict) -> GuardResult:
    violations = []
    missing = RPA_REQUIRED - set(task or {})
    if missing:
        violations.append(f"任务缺少字段: {sorted(missing)}")
        return GuardResult(False, violations)
    if not re.match(RPA_SCHEMA["task_id"], task["task_id"]):
        violations.append(f"task_id 格式非法: {task['task_id']}")
    if task["priority"] not in RPA_SCHEMA["priority"]:
        violations.append(f"priority 枚举非法: {task['priority']}")
    if not re.match(RPA_SCHEMA["deadline"], task["deadline"]):
        violations.append(f"deadline 格式非法: {task['deadline']}")
    if not re.match(RPA_SCHEMA["created_at"], task["created_at"]):
        violations.append(f"created_at 非 ISO8601: {task['created_at']}")
    if not isinstance(task["assignee"], dict) or not task["assignee"].get("name") \
            or not task["assignee"].get("department"):
        violations.append("assignee 字段缺失")
    if not isinstance(task["source"], dict) or not task["source"].get("analysis_month") \
            or not task["source"].get("product") or not task["source"].get("analysis_type") \
            or not task["source"].get("finding"):
        violations.append("source 字段缺失（analysis_type/analysis_month/product/finding 缺一不可）")
    if not task.get("suggestion"):
        violations.append("suggestion 为空（禁止无法执行的表述）")
    return GuardResult(passed=not violations, violations=violations)


def check_identity(ds, calc) -> GuardResult:
    """恒等式断言（复用阶段 1 断言库）——任何一条失败即阻断。"""
    from app.core.assertions import run_all
    results = run_all(ds, calc)
    failed = [f"{r['name']}: {r['detail']}" for r in results if not r["ok"]]
    return GuardResult(passed=not failed, violations=failed)
