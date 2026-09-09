# -*- coding: utf-8 -*-
"""四模块 Web 界面（Streamlit）：报告生成 / 成本看板 / 对标审计 / RPA 闭环。

启动: streamlit run frontend/app.py
ECharts 渲染走本地 assets/echarts.min.js（离线可用，无 CDN 依赖）。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from app.agents.graph import run_agent
from app.agents.llm import make_llm
from app.benchmark.checker import audit
from app.benchmark.steps import step1_find, step3_cause
from app.core.calc import PRODUCTS
from app.dashboard.calibration import build_calibration
from app.dashboard.charts import CHART_BUILDERS
from app.report.render import build_report
from app.rpa.client import RPAClient
from app.rpa.gateway import Gateway

st.set_page_config(page_title="制药企业成本智能分析系统", layout="wide")

ASSETS = Path(__file__).parent / "assets"


def echarts(option: dict, height: int = 360):
    js = (ASSETS / "echarts.min.js").read_text(encoding="utf-8")
    html = f"""<div id="c" style="width:100%;height:{height}px"></div>
<script>{js}</script>
<script>
var chart = echarts.init(document.getElementById('c'));
chart.setOption({json.dumps(option, ensure_ascii=False)});
</script>"""
    components.html(html, height=height + 20)


LEVEL_COLOR = {"红": "#d9534f", "黄": "#f0ad4e", "蓝": "#5bc0de", "灰": "#9aa0a6", "绿": "#5cb85c"}

tab1, tab2, tab3, tab4 = st.tabs(["📄 报告生成", "📊 成本看板", "🔍 对标审计", "🤖 RPA 整改闭环"])

# ---------------- 模块一 ----------------
with tab1:
    st.header("智能成本分析报告生成")
    col1, col2 = st.columns(2)
    product = col1.selectbox("产品", PRODUCTS)
    # 环比计算需上月数据 → 月份从 02 起（01 无上年12月数据）
    month = col2.selectbox("月份", [f"2026-{m:02d}" for m in range(2, 7)])
    if st.button("生成报告（含归因 + 图表嵌入）", type="primary"):
        with st.spinner("流水线运行中（意图路由→数据→检索→写作→守卫→RPA任务）..."):
            out = run_agent(f"请生成{product}{month}的月度成本分析报告",
                            session_id=f"ui-{product}-{month}", llm=make_llm())
            if out["status"] != "完成":
                st.error(f"流水线状态: {out['status']} {out.get('warnings')}")
            else:
                docx_bytes = build_report(product, month, draft=out["draft"],
                                          rpa_task=out["rpa_task"], llm=make_llm())
                st.success(f"报告生成完成（守卫通过，数字全部可溯源）")
                st.download_button("下载 Word 报告", docx_bytes,
                                   file_name=f"{product}{month}成本分析报告.docx",
                                   mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
                st.markdown("**归因草稿（守卫通过）**")
                st.write(out["draft"])
                st.caption(f"任务: {out['rpa_task']['task_id']}（待模块四确认推送）")

# ---------------- 模块二 ----------------
with tab2:
    st.header("单品成本看板")
    p2 = st.selectbox("产品", PRODUCTS, key="dash_product")
    m2 = st.selectbox("月份", [f"2026-{m:02d}" for m in range(2, 7)], key="dash_month")
    cols = st.columns(2)
    with cols[0]:
        echarts(CHART_BUILDERS["趋势"](p2))
    with cols[1]:
        echarts(CHART_BUILDERS["结构"](p2, m2))
    st.subheader("成本变动分解（瀑布图）")
    echarts(CHART_BUILDERS["瀑布"](p2, m2))
    st.subheader("要素×产品×月份（热力图）")
    echarts(CHART_BUILDERS["热力图"](), height=420)
    st.subheader("阈值分层校准（附录自动生成）")
    cal = build_calibration()
    st.table(pd.DataFrame([{"层级": k, "P95(%)": v["p95"], "校准阈值": f"±{v['band']}%", "样本": v["样本"]}
                           for k, v in cal["table"].items()]))
    st.caption(cal["appendix"])
    st.markdown("**新旧阈值对比演示**：" +
                f"旧规则 ±10% 命中 {len(cal['old_rule_alerts'])} 条 → 新规则命中 {len(cal['new_rule_alerts'])} 条（示例: {cal['demo']}）")

# ---------------- 模块三 ----------------
with tab3:
    st.header("对标分析三步法 + 一致性检验器 v7")
    p3 = st.selectbox("产品", PRODUCTS, key="bench_product")
    st.subheader("第一步 找差异")
    step1 = step1_find()
    st.dataframe(pd.DataFrame(step1["rows"]))
    st.subheader("第三步 拆原因（RAG+知识归因）")
    cause = step3_cause(p3)
    st.write(cause["attribution"])
    with st.expander("检索证据（可溯源）"):
        for e in cause["evidence"][:5]:
            st.caption(f"[{e['type']}] {e['source']} · {e['chunk_id']}")
    st.subheader("一致性检验器 v7（叙述-数据审计，四级判定）")
    rep = audit()
    for it in rep["items"]:
        color = LEVEL_COLOR.get(it["level"], "#888")
        st.markdown(
            f"<span style='color:{color};font-weight:bold'>[{it['level']}]</span> "
            f"{it['id']} {it['hypothesis']} —— <b>{it['verdict']}</b><br>"
            f"<small>证据: {it['evidence']}</small>", unsafe_allow_html=True)
    st.info("判定汇总: " + rep["summary"])

# ---------------- 模块四 ----------------
with tab4:
    st.header("RPA 整改任务闭环")
    gw = Gateway()
    client = RPAClient()
    st.caption(f"RPA 服务: {client.base_url} — 健康: {'✅' if client.health() else '❌ 未启动（先运行 mock_rpa_server.py）'}")
    if st.button("从分析结论生成待确认任务", type="primary"):
        out = run_agent("请生成银黄口服液2026-05成本分析报告并派发整改任务",
                        session_id="ui-rpa", llm=make_llm())
        if out.get("rpa_task"):
            gw.enqueue([out["rpa_task"]])
            st.success(f"已入待确认清单: {out['rpa_task']['task_id']}（人工确认后才推送）")
    if gw.pending:
        st.subheader("待人工确认（human-in-the-loop）")
        for item in list(gw.pending):
            t, rv = item["task"], item["review"]
            c1, c2 = st.columns([4, 1])
            c1.write(f"**{t['task_id']}** {t['task_title']}（风险: {rv['risk']}）")
            if c2.button(f"确认推送 {t['task_id'][-4:]}", key=t["task_id"]):
                res = gw.confirm(t["task_id"])
                st.write("推送结果:", res)
                st.rerun()
    board = gw.board()
    st.subheader("任务追踪看板")
    st.write(f"待确认 {board['pending']} / 已推送 {board['sent']} / 服务端状态分布 {board['status_count']}")
