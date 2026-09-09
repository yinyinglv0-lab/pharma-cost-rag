# -*- coding: utf-8 -*-
"""模板占位符注册表：由解析交付模板 .docx 自动生成（零手写），并做类型三分类。

赛题 5.1.1：识别固定章节标题和动态占位符（如 {{产品名称}}、{{本月材料成本}}、{{环比变动率}}）。
类型三分类（M1-4）：
- 数值类：结构化替换（fact_pack/计算层查表），绝不经过 LLM；
- 文本类：Agent 产物填入（归因段落/总结建议）；
- 表格类：计算层生成行数据渲染；
- 引用类：知识库来源清单。
"""
import re
from pathlib import Path

import docx

TEMPLATE_PATH = Path(
    r"D:\23生信-团日活动（学习雷锋）\重庆比赛AI\创灵境_考题模拟数据0816\创灵境_考题模拟数据"
    r"\04_报告模板\月度成本分析报告模板.docx"
)
PH = re.compile(r"\{\{(.*?)\}\}")

# 表格类关键词（模板中占位符名含"表格"即表格类）
_TABLE_KW = ["表格", "清单", "跟踪"]
# 文本类关键词
_TEXT_KW = ["分析文本", "排查分析", "拆解", "亮点", "问题", "说明", "标题", "类型", "日期",
            "编号", "告警描述", "趋势", "引用"]
# 其余默认数值类（占比/环比/偏差/金额等均走计算层）


def _classify(name: str) -> str:
    if any(k in name for k in _TABLE_KW):
        return "表格"
    if any(k in name for k in _TEXT_KW):
        return "文本"
    return "数值"


def parse_template(template_path=None) -> dict:
    """解析模板 → 占位符注册表 {name: kind}（覆盖段落与表格单元格）。"""
    path = Path(template_path) if template_path else TEMPLATE_PATH
    d = docx.Document(str(path))
    found = {}
    for par in d.paragraphs:
        for m in PH.finditer(par.text):
            found.setdefault(m.group(1), _classify(m.group(1)))
    for table in d.tables:
        for row in table.rows:
            for cell in row.cells:
                for par in cell.paragraphs:
                    for m in PH.finditer(par.text):
                        found.setdefault(m.group(1), _classify(m.group(1)))
    return found


def registry(template_path=None) -> dict:
    return parse_template(template_path)
