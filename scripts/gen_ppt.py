# -*- coding: utf-8 -*-
"""6.3 交付物：答辩 PPT（12 页，决赛用）→ evidence/答辩PPT.pptx"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pptx import Presentation
from pptx.util import Inches, Pt

ROOT = Path(__file__).parent.parent
OUT = ROOT / "evidence" / "答辩PPT.pptx"
OUT.parent.mkdir(exist_ok=True)

prs = Presentation()

SLIDES = [
    ("制药企业产品成本智能分析报告系统", ["基于 RAG 与大模型的成本智能分析 | 2026 重庆市 AI 大模型创新应用大赛"]),
    ("一、总体架构", ["四模块闭环：报告生成 → 成本看板 → 对标三步法 → RPA 整改闭环",
                     "地基：FactPack 计算层（单一事实源）+ RAG 三通道 + 多 Agent 流水线",
                     "信条：AI 不碰算术，数字零幻觉，全部可溯源"]),
    ("二、数据地基：88 项金丝雀", ["七轮独立复算的锚点数字全部固化（对标差异/三因素/摊薄/隐含单耗/阈值）",
                                   "恒等式断言库 12 条（残差<1e-9）",
                                   "任何改动 30 秒内报警——数字永远正确"]),
    ("三、RAG 知识库", ["三类知识 137 块 9 来源；PDF/Word/TXT 三格式",
                       "BM25+向量 RRF + 图谱三通道；语义模型离线可用，无网自动降级",
                       "归因查询集 6/6 命中；静态价自动过滤（I5 防线）"]),
    ("四、多 Agent 流水线", ["意图路由 → 数据 → 检索 → 写作 → 一致性守卫 → RPA",
                             "断点续跑（崩溃恢复产物字节级一致）",
                             "守卫三道闸：数字指纹 + 引用角标 + 占位符扫描"]),
    ("五、模块一 报告生成", ["101 占位符自动注册；零残留；数字与金丝雀逐位一致",
                             "趋势/瀑布/结构三图嵌入；Word + PDF 双格式",
                             "归因段落达到赛题合格示例标准（带溯源角标）"]),
    ("六、模块二 成本看板", ["ECharts 四图：趋势/瀑布/结构/热力图（54 格全矩阵校验）",
                             "阈值分层校准：旧±10%命中0条 → 新±5%命中3条（P95 自动校准）",
                             "演示：拖滑块 What-if，瀑布图恒等式实时成立"]),
    ("七、模块三 对标三步法", ["找差异 12 行 → 拆结构下钻原材料 → 拆原因 RAG 归因",
                               "一致性检验器 v7：红4 黄2 蓝1 灰1 绿4（四级判定）",
                               "连出题方标注与数据不符之处，系统都能审计出来"]),
    ("八、模块四 RPA 闭环", ["幂等台账（产品+根因+月份）；重复推送 400 被幂等承接",
                             "人工确认网关：确认前服务端任务数=0（human-in-the-loop）",
                             "预热脚本：-DONE 任务五段状态流转即时可见，演示零等待"]),
    ("九、加分项", ["因果引擎：六链反事实重算（会计恒等式），链6 诚实标注'无足迹'",
                    "What-if 数字孪生：价格滑块→BOM传导→敏感度排序",
                    "归因命中率自评 6/6（完全4+部分2）；成本预测 + DiD（双诚实警告）"]),
    ("十、方法论沉淀（七轮评审）", ["错误演化史：率/量混淆 → 指标口径混用 → 时间窗口错配 → 硬规则",
                                    "教训固化为检验器规则：方向/幅度双检验、窗口对齐、恒等式分解先行",
                                    "证据分级：红/黄/蓝/灰/绿，数字全部可现场推演"]),
    ("十一、验收总闸", ["pytest 184 passed | 统一验证 6/6 | 金丝雀 88 项全绿",
                        "报告零残留 + 差异准确率≤1% + RPA 100% + 归因 6/6",
                        "合规：公开仓库零数据文件、零 API key 泄露"]),
    ("谢谢！", ["GitHub: yinyinglv0-lab/pharma-cost-rag", "每个数字都算得出来，每条结论都查得到源头"]),
]

for title, bullets in SLIDES:
    slide = prs.slides.add_slide(prs.slide_layouts[1])
    slide.shapes.title.text = title
    body = slide.placeholders[1].text_frame
    for i, b in enumerate(bullets):
        para = body.paragraphs[0] if i == 0 else body.add_paragraph()
        para.text = b
        para.level = 0

prs.save(str(OUT))
print("已生成:", OUT)
