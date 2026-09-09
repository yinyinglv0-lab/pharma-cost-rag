# -*- coding: utf-8 -*-
"""提示词架构师验收：Prompt 全量落盘、结构完整、规则对齐 v7 终版。"""
from app.agents.prompts import A0_NUMERIC_LOCK, PROMPTS, TEMPERATURE_RULE


def test_all_prompts_present():
    names = set(PROMPTS)
    for required in ["A0-数值锁定协议", "M1-1-章节规划器", "M1-2-归因段落生成器",
                     "M1-3-总结与建议", "M1-4-模板填充规则", "M2-1-看板叙事",
                     "M2-2-阈值告警规则", "M3-1-找差异总览", "M3-2-拆结构树",
                     "M3-3-拆原因归因", "M4-1-整改任务JSON", "M4-2-微信文案",
                     "M4-3-人工确认网关"]:
        assert required in names, f"缺失 Prompt: {required}"
    for p in PROMPTS.values():
        assert p["template"].strip(), f"空模板: {p}"
        assert p["role"] and p["output_format"]


def test_numeric_lock_iron_rules():
    for rule in ["铁律1", "铁律2", "铁律3", "铁律4"]:
        assert rule in A0_NUMERIC_LOCK


def test_attribution_fewshot_from_offical_example():
    t = PROMPTS["M1-2-归因段落生成器"]["template"]
    assert "不合格示例" in t and "材料成本上涨了" in t
    assert "合格示例" in t and "12.5元/kg上涨至14.0元/kg" in t


def test_rpa_schema_aligned_to_mock():
    t = PROMPTS["M4-1-整改任务JSON"]["template"]
    for field in ["task_id", "task_title", "assignee", "source", "priority",
                  "deadline", "suggestion", "notify_method", "created_at"]:
        assert field in t, f"M4-1 缺字段: {field}"
    assert "幂等" in t and "priority" in t


def test_temperature_rules_consistent():
    for name, p in PROMPTS.items():
        if "JSON" in p["output_format"] and p["temperature"] != 0.0:
            assert name == "M1-2-归因段落生成器", f"schema输出必须T=0: {name}"
    assert PROMPTS["M1-2-归因段落生成器"]["temperature"] == 0.3
    assert "temperature=0" in TEMPERATURE_RULE
