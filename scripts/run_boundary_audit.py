# -*- coding: utf-8 -*-
"""任务4 边界值审计：证据 JSON 留存。python scripts/run_boundary_audit.py"""
import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from app.core.assertions import run_all
from app.core.calc import CalculationService
from app.core.datastore import DataStore

svc = CalculationService(DataStore())
evidence = {"boundary_cases": []}

# 1) 上月缺失 → null
v = svc.mom("银黄口服液", "2026-01", "材料")
evidence["boundary_cases"].append({
    "case": "上月数据缺失(2026-01环比)", "behavior": "返回 None 标记 null（而非 0/异常）",
    "observed": v is None, "value": v})

# 2) 零基期 → 退化为绝对值差异法
orig = svc.implied_unit_consumption

def fake(product, material):
    r = orig(product, material)
    r["values"][3] = 0.0
    return r

svc.implied_unit_consumption = fake  # 实例属性直赋值，不绑定 self
w0 = svc.window_change("银黄口服液", "黄芩提取物", "2026-04", "2026-06")
svc.implied_unit_consumption = orig
evidence["boundary_cases"].append({
    "case": "成本为0(零基期)", "behavior": "变动率→None, 退化为绝对值差异法(unit_abs)",
    "observed": w0["unit_pct"] is None and w0["unit_abs"] is not None,
    "value": {"unit_pct": w0["unit_pct"], "unit_abs": w0["unit_abs"]}})

# 3) 负值告警
results = run_all(svc.ds, svc)
a13 = next(r for r in results if r["name"].startswith("A13"))
evidence["boundary_cases"].append({
    "case": "负值出现", "behavior": "A13 断言告警（正常数据零负值；异常数据在此拦下）",
    "observed": a13["ok"], "detail": a13["detail"]})

# 4) 负环比是合法结果（降级处理说明）
neg_mom = svc.mom("六味地黄胶囊", "2026-03", "材料")
evidence["boundary_cases"].append({
    "case": "负环比(合法下降)", "behavior": "正常输出，不误报",
    "observed": neg_mom is not None and neg_mom < 0, "value": round(neg_mom, 2)})

(ROOT / "evidence").mkdir(exist_ok=True)
(ROOT / "evidence" / "boundary_audit.json").write_text(
    json.dumps(evidence, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(evidence, ensure_ascii=False, indent=1))
print("证据留存: evidence/boundary_audit.json")
