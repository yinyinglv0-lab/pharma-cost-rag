# -*- coding: utf-8 -*-
"""6.3 交付物：技术方案文档（架构图/RAG流程/Prompt设计/模板解析/API文档）→ docx。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from docx import Document
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor

ROOT = Path(__file__).parent.parent
OUT = ROOT / "evidence" / "技术方案文档.docx"
OUT.parent.mkdir(exist_ok=True)

doc = Document()
normal = doc.styles["Normal"]
normal.font.name = "Calibri"
normal.font.size = Pt(10.5)
normal.element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
for h, s in [("Heading 1", 15), ("Heading 2", 12.5), ("Heading 3", 11)]:
    st = doc.styles[h]
    st.font.color.rgb = RGBColor(0, 0, 0)
    st.font.size = Pt(s)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), "微软雅黑")


def h1(t): doc.add_heading(t, level=1)
def h2(t): doc.add_heading(t, level=2)
def p(t): doc.add_paragraph(t)
def code(t):
    para = doc.add_paragraph()
    run = para.add_run(t)
    run.font.name = "Consolas"
    para.paragraph_format.left_indent = Pt(18)


doc.add_heading("制药企业产品成本智能分析报告系统 · 技术方案文档", 0)
p("（2026年第二届重庆市AI大模型创新应用大赛 · 企业出题赛道）")

h1("一、系统架构")
code("""[前端 Streamlit 四页签] 报告生成 / 成本看板 / 对标审计 / RPA闭环
        │
[多Agent编排 LangGraph] 意图路由→数据Agent→检索Agent→写作Agent→一致性守卫→执行Agent
        │                    │              │               │
[计算层 FactPack]      [RAG三通道]      [守卫]           [RPA]
 CalculationService   BM25+向量+图谱   数字指纹/角标     幂等台账/确认网关
 (金丝雀88项断言)     (RRF融合)        恒等式断言        (mock集成)
""")

h1("二、RAG 流程")
h2("2.1 文档切分")
p("7 份 PDF + Word/TXT 统一管线：NFKC+部首补充区归一 → 章节正则精确切片 → 句边界滑窗（700/150）。"
  "共 137 块 / 9 来源 / 14 类 type 元数据（版本/页码/时效）。")
h2("2.2 向量化")
p("本地语义模型 GTE-small（512维，ModelScope 国内获取，离线可用）；无网自动降级 IDF 哈希嵌入"
  "（确定性、带告警）。")
h2("2.3 检索策略")
p("BM25(0.3)+向量(0.7) RRF 加权融合 + 查询感知类型权重（GMP 全文仅合规查询纳入）+ 图谱通道证据"
  "（实体锚定→多跳路径）。数值敏感查询自动过滤静态价块（I5 纵深防御）。")

h1("三、Prompt 设计（13 个，全量落盘 app/agents/prompts.py）")
p("A0 数值锁定协议（铁律1-4：数字只引用 fact_pack、禁自行计算、必带角标、无证据不下结论）"
  "前置注入所有 LLM 调用；M1-2 归因生成器嵌入赛题合格/不合格 few-shot；M4-1 整改任务 schema "
  "逐字段对齐 mock Pydantic（幂等键=产品+根因+月份）；温度规则：schema 输出=0、叙述字段=0.3。")

h1("四、模板解析")
p("占位符注册表由解析交付模板 .docx 自动生成（101 个：数值81/文本14/表格6），零手写。"
  "三分类填充：数值类=计算层查表（82 项全覆盖）、文本类=Agent 产物、表格类=计算层行数据；"
  "matplotlib 图表嵌入指定章节；导出前占位符残留扫描阻断；Word COM 转 PDF。")

h1("五、模块 API 文档")
h2("5.1 检索门面")
code("retrieve(query, top_k=5, filter_forbidden=True) -> EvidenceBundle\n"
     "PharmaKnowledgeRetriever(BaseRetriever).invoke(query) -> List[Document]")
h2("5.2 报告生成")
code("build_report(product, month, draft, rpa_task, charts=True) -> docx bytes\n"
     "export_pdf(docx_bytes, out_path) -> pdf path")
h2("5.3 对标与审计")
code("step1_find() / step2_struct(product) / step3_cause(product)\n"
     "audit() -> {items, counts, summary}   # 一致性检验器 v7: 红4黄2蓝1灰1绿4")
h2("5.4 RPA")
code("RPAClient.push_task(task)  # 幂等: 重复400被承接为 duplicate=True\n"
     "Gateway.enqueue/confirm      # 人工确认后才推送\n"
     "assign_task_id(product, root, month)  # 幂等台账")

h1("六、一致性与验收")
p("数字金丝雀 88 项 + 恒等式断言 12 条 + 一致性检验器 12 假设 + 全量 pytest 184 项；"
  "统一验证入口 validate_phase3.py 六步全 PASS。")

doc.save(str(OUT))
print("已生成:", OUT)
