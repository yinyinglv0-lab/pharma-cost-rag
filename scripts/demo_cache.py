# -*- coding: utf-8 -*-
"""6.2 演示工程：3 场景预生成缓存（秒开）+ 降级模式标注。"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from app.agents.graph import run_agent
from app.agents.llm import MockLLM, make_llm
from app.report.render import build_report

CACHE_DIR = Path(__file__).parent.parent / "demo_cache"
SCENARIOS = [("银黄口服液", "2026-05"), ("板蓝根颗粒", "2026-02"), ("六味地黄胶囊", "2026-03")]


def warm_cache(llm=None) -> list:
    """预生成三场景（报告 docx + 流水线产物），返回耗时记录。"""
    CACHE_DIR.mkdir(exist_ok=True)
    log = []
    for product, month in SCENARIOS:
        t0 = time.time()
        out = run_agent(f"请生成{product}{month}的月度成本分析报告",
                        session_id=f"cache-{product}-{month}", llm=llm or make_llm())
        data = build_report(product, month, draft=out["draft"], rpa_task=out["rpa_task"],
                            llm=llm or make_llm(), charts=True)
        key = f"{product}-{month}"
        (CACHE_DIR / f"{key}.docx").write_bytes(data)
        (CACHE_DIR / f"{key}.json").write_text(
            json.dumps({"product": product, "month": month, "status": out["status"],
                        "guard": out["guard"], "rpa_task": out["rpa_task"],
                        "warnings": out["warnings"]}, ensure_ascii=False, indent=1),
            encoding="utf-8")
        log.append({"scenario": key, "seconds": round(time.time() - t0, 2)})
    return log


def load_cached(product: str, month: str, llm=None) -> dict:
    """秒开缓存：命中→返回缓存（标注演示模式）；未命中→现场生成（真实演示）。"""
    key = f"{product}-{month}"
    docx_path, meta_path = CACHE_DIR / f"{key}.docx", CACHE_DIR / f"{key}.json"
    if docx_path.exists() and meta_path.exists():
        return {"product": product, "month": month, "mode": "演示模式(预生成缓存)",
                "docx": docx_path.read_bytes(),
                "meta": json.loads(meta_path.read_text(encoding="utf-8"))}
    out = run_agent(f"请生成{product}{month}的月度成本分析报告",
                    session_id=f"live-{product}-{month}", llm=llm or make_llm())
    data = build_report(product, month, draft=out["draft"], rpa_task=out["rpa_task"],
                        llm=llm or make_llm(), charts=True)
    return {"product": product, "month": month, "mode": "现场生成(真实流水线)",
            "docx": data, "meta": {"status": out["status"], "guard": out["guard"],
                                   "rpa_task": out["rpa_task"]}}


if __name__ == "__main__":
    log = warm_cache()
    print("预热完成:", log)
    t0 = time.time()
    hit = load_cached("银黄口服液", "2026-05")
    print(f"缓存秒开: {hit['mode']}, {len(hit['docx']) // 1024}KB, "
          f"{time.time() - t0:.2f}s")
