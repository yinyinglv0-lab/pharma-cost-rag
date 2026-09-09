# -*- coding: utf-8 -*-
"""免 pytest 的阶段 5 一键检查 + 四项目演示日志：python scripts/run_phase5_checks.py"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from app.causal.engine import demo_causal, run_all_chains
from app.evaluation.engine import demo_evaluation, evaluate
from app.forecast.engine import demo_forecast
from app.simulator.engine import demo_simulator


def main():
    print("=" * 62)
    print("  阶段 5 验收：四加分项（因果引擎/What-if/命中率自评/预测+DiD）")
    print("=" * 62)

    chains = run_all_chains()
    print(f"\n[项目1 因果引擎] 六链: " + ", ".join(
        f"{c.chain_id}({c.counterfactual_unit_cost},s={c.support})" for c in chains))
    story = json.loads(demo_causal())
    print(f"  演示: {story['storyline'][:110]}...")

    sim = json.loads(demo_simulator())
    print(f"\n[项目2 What-if] 演示: {sim['storyline']}")
    print(f"  敏感度Top3: {sim['sensitivity_top3']}")

    ev = json.loads(demo_evaluation())
    print(f"\n[项目3 命中率自评] {ev['demo']}")

    fc = json.loads(demo_forecast())
    print(f"\n[项目4 预测+DiD] {fc['demo'][:120]}...")

    r = subprocess.run([sys.executable, "-m", "pytest", "tests/test_causal.py",
                        "tests/test_simulator.py", "tests/test_evaluation.py",
                        "tests/test_forecast.py", "-q"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=900)
    print("\n" + (r.stdout or "")[-200:])
    ok = r.returncode == 0
    print("-" * 62)
    print(f"  结论: {'全部通过 ✅ 阶段 5 下闸' if ok else '存在失败 ❌'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
