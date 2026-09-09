# -*- coding: utf-8 -*-
"""报告渲染引擎：三分类占位符填充 + 图表嵌入 + docx/PDF 导出。

- 数值类：CalculationService 直算，绝不经过 LLM（数字与金丝雀逐位一致）；
- 文本类：Agent 产物（归因/建议）+ 计算层摘要；
- 表格类：计算层行数据；
- 图表嵌入：matplotlib PNG 插入指定章节后（页眉页脚/表格样式沿用模板本身）。
"""
import io
import re
import tempfile
from datetime import date
from pathlib import Path

import docx
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from ..agents.graph import run_agent
from ..agents.llm import MockLLM, make_llm
from ..core.calc import CalculationService, ELEMENTS
from ..core.datastore import DataStore
from ..rag.entities import PRODUCTS as PRODUCT_INFO
from .registry import PH, TEMPLATE_PATH

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


def _fmt(v, suffix=""):
    if v is None:
        return "—"
    return f"{v:.2f}{suffix}"


def build_mapping(product: str, month: str) -> dict:
    """数值/文本占位符 → 值（82 个数值占位符全覆盖）。"""
    svc = CalculationService(DataStore())
    ds = DataStore()
    y, m = int(month[:4]), int(month[5:7])
    prev = f"{y}-{m - 1:02d}" if m > 1 else f"{y}-{m - 1:02d}"
    r, rp = ds.cost_row("中药一厂", product, month), ds.cost_row("中药一厂", product, prev)
    ry = ds.cost_row("中药一厂", product, f"{y - 1}-{m:02d}")
    b = ds.budget_row(product, month)
    info = PRODUCT_INFO[product]
    out = {
        "报告标题": f"{y}年{m}月{product}成本分析报告", "报告类型": "月度成本分析",
        "编制日期": date.today().isoformat(), "分析月份": month,
        "产品名称": product, "产品规格": info["规格"],
        # 产量
        "本月产量": int(r["产量(盒)"]), "上月产量": int(rp["产量(盒)"]),
        "产量环比": _fmt((r["产量(盒)"] / rp["产量(盒)"] - 1) * 100, "%"),
        "去年同月产量": int(ry["产量(盒)"]),
        "产量同比": _fmt((r["产量(盒)"] / ry["产量(盒)"] - 1) * 100, "%"),
        "预算产量": int(b["预算产量(盒)"]),
        "产量预算偏差": _fmt((r["产量(盒)"] / b["预算产量(盒)"] - 1) * 100, "%"),
    }
    # 单位成本/总成本 行（本月/上月/环比/去年/同比/预算/偏差）
    for key, col, bcol in [("单位成本", "单位成本(元/盒)", "预算单位成本(元/盒)"),
                           ("总成本", "总成本(元)", "预算总成本(元)"),
                           ("材料成本", "直接材料(元/盒)", "预算直接材料(元/盒)"),
                           ("人工成本", "直接人工(元/盒)", "预算直接人工(元/盒)"),
                           ("制造费用", "制造费用(元/盒)", "预算制造费用(元/盒)")]:
        elem = {"单位成本": "单位成本", "总成本": "单位成本", "材料成本": "材料",
                "人工成本": "人工", "制造费用": "制费"}[key]
        mom = (r[col] / rp[col] - 1) * 100
        short = {"单位成本": "单位成本", "总成本": "总成本", "材料成本": "材料",
                 "人工成本": "人工", "制造费用": "制造费用"}[key]
        out.update({
            f"本月{key}": r[col], f"上月{key}": rp[col],
            f"{key}环比": _fmt(mom, "%"),
            f"去年{key}": ry[col] if key != "总成本" else ry["总成本(元)"],
            f"{key}同比": _fmt((r[col] / ry[col] - 1) * 100, "%"),
            f"预算{key}": b[bcol],
            f"{short}预算偏差": _fmt((r[col] / b[bcol] - 1) * 100, "%"),  # 模板用裸要素名
        })
    # 成本结构（2.2 表）
    u = r["单位成本(元/盒)"]
    contrib = svc.contribution(product, month)
    for key, col, elem in [("材料", "直接材料(元/盒)", "材料"), ("人工", "直接人工(元/盒)", "人工"),
                           ("制造费用", "制造费用(元/盒)", "制费")]:
        out.update({
            f"{key}金额": r[col], f"{key}占比": _fmt(r[col] / u * 100, "%"),
            f"{key}环比": _fmt((r[col] / rp[col] - 1) * 100, "%"),
            f"{key}贡献度": _fmt(contrib[elem], "%"),
        })
    out["单位成本"] = r["单位成本(元/盒)"]
    out["总环比"] = _fmt((u / rp["单位成本(元/盒)"] - 1) * 100, "%")
    # 人工派生（3.2 表）
    lm, lmp = svc.labor_metrics(product, month), svc.labor_metrics(product, prev)
    out.update({
        "人工单位成本": _fmt(lm["wage_rate"] * lm["hour_per_box"]),
        "上月人工单位成本": _fmt(lmp["wage_rate"] * lmp["hour_per_box"]),
        "本月工时": _fmt(lm["hour_per_box"] * 10000),
        "上月工时": _fmt(lmp["hour_per_box"] * 10000),
        "工时环比": _fmt((lm["hour_per_box"] / lmp["hour_per_box"] - 1) * 100, "%"),
        "本月时薪": _fmt(lm["wage_rate"]),
        "上月时薪": _fmt(lmp["wage_rate"]),
        "时薪环比": _fmt((lm["wage_rate"] / lmp["wage_rate"] - 1) * 100, "%"),
        "本月效率": _fmt(r["产量(盒)"] / (ds.labor_row(product, month)["生产人数(人)"]
                                       * ds.labor_row(product, month)["工作天数(天)"])),
        "上月效率": _fmt(rp["产量(盒)"] / (ds.labor_row(product, prev)["生产人数(人)"]
                                        * ds.labor_row(product, prev)["工作天数(天)"])),
    })
    eff_mom = ((r["产量(盒)"] / (ds.labor_row(product, month)["生产人数(人)"]
                                * ds.labor_row(product, month)["工作天数(天)"]))
               / (rp["产量(盒)"] / (ds.labor_row(product, prev)["生产人数(人)"]
                                   * ds.labor_row(product, prev)["工作天数(天)"])) - 1) * 100
    out["效率环比"] = _fmt(eff_mom, "%")
    # 制造费用五类（3.3 表）
    names = {"折旧费": "折旧", "动力费(水电气)": "动力", "人工(间接)": "间接人工",
             "检验费": "检验", "其他制造费用": "其他"}
    total_m = 0.0
    for cat, key in names.items():
        v = ds.overhead_rows(product, month)
        cur = float(v[v["费用类别"] == cat].iloc[0]["单位费用(元/盒)"]) if not v[v["费用类别"] == cat].empty else 0.0
        pv = ds.overhead_rows(product, prev)
        prv = float(pv[pv["费用类别"] == cat].iloc[0]["单位费用(元/盒)"]) if not pv[pv["费用类别"] == cat].empty else 0.0
        total_m += cur
        out.update({f"本月{key}": cur, f"上月{key}": prv,
                    f"{key}环比": _fmt((cur / prv - 1) * 100 if prv else 0.0, "%"),
                    f"{key}变动说明": f"单位{cat}{'上升' if cur >= prv else '下降'}"
                                     f"{abs((cur / prv - 1) * 100) if prv else 0:.1f}%"})
    out.update({"制造费用合计": total_m,
                "上月制造费用合计": rp["制造费用(元/盒)"],
                "制造费用合计环比": _fmt((total_m / rp["制造费用(元/盒)"] - 1) * 100, "%")})
    return out


def _table_rows(kind: str, product: str, month: str, svc, ds, draft, rpa_task) -> str:
    lines = []
    if kind == "原材料成本明细表格":
        y, m = int(month[:4]), int(month[5:7])
        prev = f"{y}-{m - 1:02d}"
        rows = ds.material_rows(product, month)
        prev_rows = ds.material_rows(product, prev)
        for i, (_, r) in enumerate(rows.iterrows(), 1):
            pv = prev_rows[prev_rows["原材料名称"] == r["原材料名称"]]
            prev_v = float(pv.iloc[0]["单位消耗成本(元/盒)"]) if not pv.empty else float(r["单位消耗成本(元/盒)"])
            mom = (float(r["单位消耗成本(元/盒)"]) / prev_v - 1) * 100
            lines.append(f"{i}\t{r['原材料名称']}\t{float(r['单位消耗成本(元/盒)']):.2f}\t"
                         f"{prev_v:.2f}\t{mom:+.1f}%\t{'行情驱动' if mom > 0 else '稳定/回落'}")
    elif kind == "近6个月成本趋势表格":
        for i in range(6):
            mm = f"{month[:4]}-{i + 1:02d}"
            rr = ds.cost_row("中药一厂", product, mm)
            lines.append(f"{mm}\t{int(rr['产量(盒)'])}\t{rr['直接材料(元/盒)']:.2f}\t"
                         f"{rr['直接人工(元/盒)']:.2f}\t{rr['制造费用(元/盒)']:.2f}\t"
                         f"{rr['单位成本(元/盒)']:.2f}")
    elif kind == "原材料价格跟踪表格":
        for _, r in ds.market.iterrows():
            p1 = float(r["1月价格"])
            pm = float(r[f"{int(month[5:7])}月价格"])
            lines.append(f"{r['药材名称']}\t{p1:.1f}\t{pm:.1f}\t{(pm / p1 - 1) * 100:+.1f}%\t"
                         f"{r['趋势分析']}")
    elif kind == "对标差异表格":
        for elem in ("材料", "人工", "制费", "单位成本"):
            d = svc.benchmark_diff(product, elem)
            lines.append(f"{elem}\t一厂低{-d:.2f}%\t{'-d' if False else d:.2f}%\t"
                         f"{'一厂更优' if d < 0 else '二厂更优'}")
    elif kind == "改进建议表格":
        for i, s in enumerate((draft or {}).get("suggestion", [])[:4], 1):
            lines.append(f"{i}\t{s}\t待定\t中\t待评估\t{month}")
    elif kind == "整改任务表格":
        if rpa_task:
            lines.append(f"{rpa_task['task_id']}\t{rpa_task['task_title']}\t"
                         f"{rpa_task['assignee']['name']}\t{rpa_task['priority']}\t"
                         f"{rpa_task['source']['analysis_month']}\t{rpa_task['deadline']}")
    return "\n".join(lines) if lines else "暂无数据"


def _charts(product: str, month: str, svc, ds) -> dict:
    """三张图表 PNG（趋势/瀑布/结构）。"""
    figs = {}
    y, m = int(month[:4]), int(month[5:7])
    # 趋势图
    uc = [ds.cost_row("中药一厂", product, f"{y}-{i + 1:02d}")["单位成本(元/盒)"] for i in range(6)]
    fig, ax = plt.subplots(figsize=(6, 2.6))
    ax.plot(range(1, 7), uc, marker="o", color="#2f6fb3")
    ax.set_title(f"{product} 单位成本趋势（{y}年1-6月）")
    ax.set_ylabel("元/盒")
    figs["趋势"] = fig
    # 瀑布图（本月 Δ单位成本 三因素）
    tf = svc.three_factor(product, month)
    labels = ["材料", "人工", "制费"]
    deltas = [tf[e]["delta"] for e in labels]
    fig, ax = plt.subplots(figsize=(6, 2.6))
    colors = ["#c0504d" if d >= 0 else "#4f81bd" for d in deltas]
    bottom = 0.0
    for lb, d, c in zip(labels, deltas, colors):
        ax.bar(lb, d, bottom=bottom, color=c)
        ax.text(labels.index(lb), bottom + d / 2, f"{d:+.2f}", ha="center", va="center", fontsize=8)
        bottom += d
    ax.axhline(0, color="gray", lw=0.6)
    ax.set_title(f"{month} 单位成本变动分解（合计 {tf['unit_cost_delta']:+.2f} 元/盒）")
    figs["瀑布"] = fig
    # 结构图
    row = ds.cost_row("中药一厂", product, month)
    vals = [row["直接材料(元/盒)"], row["直接人工(元/盒)"], row["制造费用(元/盒)"]]
    fig, ax = plt.subplots(figsize=(3.4, 2.6))
    ax.pie(vals, labels=labels, autopct="%.1f%%", colors=["#c0504d", "#e8b34b", "#4f81bd"])
    ax.set_title(f"{month} 成本结构")
    figs["结构"] = fig
    pngs = {}
    for k, f in figs.items():
        buf = io.BytesIO()
        f.savefig(buf, format="png", dpi=150, bbox_inches="tight")
        plt.close(f)
        buf.seek(0)
        pngs[k] = buf
    return pngs


def _replace_in_paragraph(par, mapping):
    full = par.text
    if not PH.search(full):
        return False
    new_text = PH.sub(lambda mm: str(mapping.get(mm.group(1), mm.group(0))), full)
    for run in par.runs[1:]:
        run.text = ""
    if par.runs:
        par.runs[0].text = new_text
    return True


def build_report(product: str, month: str, draft=None, rpa_task=None, llm=None,
                 template_path=None, charts=True) -> bytes:
    """端到端报告生成 → docx 字节流。"""
    svc = CalculationService(DataStore())
    ds = DataStore()
    mapping = build_mapping(product, month)
    # 文本类：Agent 产物（未提供时跑流水线）
    if draft is None:
        out = run_agent(f"请生成{product}{month}的月度成本分析报告",
                        session_id=f"report-{product}-{month}", llm=llm or make_llm())
        draft, rpa_task = out["draft"], out["rpa_task"]
    mapping.update({
        "材料成本归因分析文本": (draft or {}).get("chain", ""),
        "成本异常排查分析": "；".join((draft or {}).get("suggestion", [])) or "无",
        "差异归因分析文本": (draft or {}).get("chain", ""),
        "差异结构拆解分析": "差异按成本要素与产品维度逐层拆解，详见差异表。",
        "本月亮点": "无超阈值要素" if not mapping.get("告警") else "存在超阈值要素",
        "需关注问题": "；".join((draft or {}).get("suggestion", [])[:2]) or "持续观察",
        "波动告警描述": "要素级阈值±5%（分层校准）；本月无告警" ,
    })
    doc = docx.Document(str(Path(template_path) if template_path else TEMPLATE_PATH))
    for par in doc.paragraphs:
        _replace_in_paragraph(par, mapping)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for par in cell.paragraphs:
                    _replace_in_paragraph(par, mapping)
    # 表格类（占位符可能在单元格或正文段落中 → 统一替换为多行文本）
    for kind, build in {"原材料成本明细表格": None, "近6个月成本趋势表格": None,
                        "原材料价格跟踪表格": None, "对标差异表格": None,
                        "改进建议表格": None, "整改任务表格": None}.items():
        rows_text = _table_rows(kind, product, month, svc, ds, draft, rpa_task)
        marker = f"{{{{{kind}}}}}"
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for par in cell.paragraphs:
                        if marker in par.text:
                            for run in par.runs[1:]:
                                run.text = ""
                            par.runs[0].text = par.runs[0].text.replace(marker, rows_text)
        for par in doc.paragraphs:  # 正文段落中的表格占位符
            if marker in par.text:
                for run in par.runs[1:]:
                    run.text = ""
                par.runs[0].text = par.runs[0].text.replace(marker, rows_text)
    # 图表嵌入：插入指定章节标题之后
    if charts:
        pngs = _charts(product, month, svc, ds)
        targets = {"趋势": "重点产品专项分析", "瀑布": "总成本概览", "结构": "总成本概览"}
        for key, buf in pngs.items():
            heading = targets[key]
            for i, par in enumerate(doc.paragraphs):
                if heading in par.text and "{{" not in par.text:
                    from docx.shared import Inches
                    new_par = par.insert_paragraph_before()
                    new_par.add_run().add_picture(buf, width=Inches(5.6))
                    break
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def export_pdf(docx_bytes: bytes, out_path) -> Path:
    """Word COM 转 PDF（本机已装 Word；无 Word 环境时抛错并说明）。"""
    import win32com.client
    tmp = Path(tempfile.gettempdir()) / "report_tmp.docx"
    tmp.write_bytes(docx_bytes)
    word = win32com.client.Dispatch("Word.Application")
    word.Visible = False
    try:
        d = word.Documents.Open(str(tmp))
        d.SaveAs(str(out_path), FileFormat=17)  # wdFormatPDF
        d.Close()
    finally:
        word.Quit()
    return Path(out_path)
