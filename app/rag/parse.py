# -*- coding: utf-8 -*-
"""PDF 解析与知识块构建（2.1 + 2.2）。

- 配方文档按章节切（处方量/折算/成本参考分块）；
- 工艺文档按工序/参数节切；
- 设备清单表格转结构化实体（见 entities.py），文档按节切块供引用；
- GMP 按章切；
- 行情/行业基准从 DataStore 生成"行业知识"块（type=行情价/行业基准）。

元数据（I5）：type + 文档版本 + 页码 + 时效标签；type=处方参考价 的块
forbid_current_numbers=True——写作层与检索层双重禁引为当期数字。
"""
import re
import unicodedata
from pathlib import Path

from pypdf import PdfReader

from ..core.datastore import DataStore

# ---------------- 文档配置 ----------------
# 章节标题：一、二、… / 第X章 / N.N 后必须跟汉字（排除"1.5h""10.2±0.2ml"等表格单元格行）
_SECTION_SPLIT = re.compile(
    r"^(?:[一二三四五六七八九十]+、|第[一二三四五六七八九十]+章|\d+\.\d+\s*[一-鿿])")

_NOISE_LINES = {"国家市场监督管理总局规章", "卫生部发布", "X"}

PDF_CFG = [
    {"file": "产品配方文档_银黄口服液.pdf", "doc_id": "PF-YH",
     "version": "V2.0", "effective": "2025-01-01", "kind": "配方"},
    {"file": "产品配方文档_板蓝根颗粒.pdf", "doc_id": "PF-BLG",
     "version": "V1.5", "effective": "2025-03-01", "kind": "配方"},
    {"file": "产品配方文档_六味地黄胶囊.pdf", "doc_id": "PF-LW",
     "version": "V2.2", "effective": "2025-06-01", "kind": "配方"},
    {"file": "生产工艺文档_中药一厂.pdf", "doc_id": "MFG",
     "version": "V3.0", "effective": "2025-06-01", "kind": "工艺"},
    {"file": "车间设备清单_中药一厂.pdf", "doc_id": "EQP",
     "version": "V2.1", "effective": "2026-03-15", "kind": "设备"},
    {"file": "GMP法规核心摘要_2010修订版.pdf", "doc_id": "GMP-S",
     "version": "2010修订版摘要", "effective": "2011-03-01", "kind": "GMP"},
    {"file": "药品生产质量管理规范GMP.pdf", "doc_id": "GMP-F",
     "version": "2010修订版全文", "effective": "2011-03-01", "kind": "GMP"},
]

# 文档上下文（注入索引文本，不污染引用原文；弥补表格类正文产品名出现频率低的问题）
_DOC_CONTEXT = {
    "PF-YH": "银黄口服液 产品配方", "PF-BLG": "板蓝根颗粒 产品配方",
    "PF-LW": "六味地黄胶囊 产品配方", "MFG": "中药一厂 生产工艺",
    "EQP": "中药一厂 车间设备清单", "GMP-S": "GMP法规核心摘要",
    "GMP-F": "药品生产质量管理规范GMP全文",
}

# 类型判定：按标题关键词依次匹配（顺序敏感）
_TYPE_RULES = [
    (r"成本参考|物料成本波动", "处方参考价", True),   # 静态价格，禁引为当期数字
    (r"处方|折算", "处方量", False),
    (r"工艺参数|收率|成本影响|对成本的影响", "工艺参数", False),
    (r"工艺流程|生产工艺", "工艺路线", False),
    (r"工时|人工分配", "工艺工时", False),
    (r"公用工程", "公用工程", False),
    (r"设备利用率", "设备台账", False),
    (r"维修历史|维修", "维修事件", False),
    (r"设备|折旧", "设备台账", False),
    (r"变更记录", "变更记录", False),
    (r"基本信息|功能主治", "产品信息", False),
    (r"工厂概况|概况", "工厂信息", False),
]


def _type_of(title: str, kind: str):
    if kind == "GMP":
        return "GMP要求", False
    for pattern, t, forbid in _TYPE_RULES:
        if re.search(pattern, title):
            return t, forbid
    return "其他", False


def _clean(text: str) -> str:
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln and ln not in _NOISE_LINES
             and not re.fullmatch(r"-\s*\d+\s*-", ln)]
    out = " ".join(lines)
    out = re.sub(r"\s+", " ", out).strip()
    return out


def _split_sections(page_texts):
    """按章节标题行精确切片（行偏移定位，杜绝"整页并入"）。"""
    lines = []                      # (line, page, offset)
    offset = 0
    for pg, text in page_texts:
        for ln in text.splitlines():
            lines.append((ln, pg, offset))
            offset += len(ln) + 1
    starts = []
    for i, (ln, pg, off) in enumerate(lines):
        s = ln.strip()
        if _SECTION_SPLIT.match(s) and len(s) <= 40:
            starts.append((i, pg, off, s))
    sections = []
    for k, (i, pg, off, title) in enumerate(starts):
        end_off = starts[k + 1][2] if k + 1 < len(starts) else None
        body = "\n".join(ln for ln, p, o in lines
                         if o >= off and (end_off is None or o < end_off))
        end_pg = starts[k + 1][1] if k + 1 < len(starts) else page_texts[-1][0]
        text = _clean(body)
        if len(text) < 30:
            continue  # 标题壳块（正文在 2.1/2.2 等子节里），丢弃避免空证据
        sections.append({"title": title, "page": pg, "end_page": end_pg,
                         "text": text})
    if not sections:
        return [{"title": "（卷首）", "page": page_texts[0][0],
                 "end_page": page_texts[-1][0],
                 "text": _clean("\n".join(t for _, t in page_texts))}]
    return sections


def _pages_of(path: Path):
    reader = PdfReader(str(path))
    pages = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        # NFKC：把康熙部首/兼容字符（⼀⼆三、⼯、⽅…）归一为标准汉字，
        # 否则章节正则与 jieba 分词都会错位
        pages.append((i + 1, unicodedata.normalize("NFKC", text)))
    return pages


_MAX_CHUNK = 900   # 长节滑窗切分阈值（字符）
_WIN_SIZE = 700
_WIN_OVERLAP = 150


def _window_split(text: str):
    """超长节按滑窗切分（GMP 全文等），避免长块统治 BM25/向量打分。"""
    if len(text) <= _MAX_CHUNK:
        return [text]
    out = []
    start = 0
    while start < len(text):
        seg = text[start:start + _WIN_SIZE]
        out.append(seg)
        if start + _WIN_SIZE >= len(text):
            break
        start += _WIN_SIZE - _WIN_OVERLAP
    return out


def build_document_chunks(base_dir=None) -> list:
    """返回全部 PDF 知识块（含元数据）。"""
    import app.core.datastore as d
    base = Path(base_dir) if base_dir else Path(d.DEFAULT_DATA_BASE)
    ds = DataStore(base)
    kb_dir = base / "03_制药知识文档"
    chunks = []
    for cfg in PDF_CFG:
        pages = _pages_of(kb_dir / cfg["file"])
        sections = _split_sections(pages)
        for i, sec in enumerate(sections):
            ctype, forbid = _type_of(sec["title"], cfg["kind"])
            for w, seg in enumerate(_window_split(sec["text"])):
                chunks.append({
                    "chunk_id": f"{cfg['doc_id']}-{i:03d}" + (f"-w{w}" if len(_window_split(sec['text'])) > 1 else ""),
                    "source": cfg["file"],
                    "page": sec["page"],
                    "doc_version": cfg["version"],
                    "effective_date": cfg["effective"],
                    "type": ctype,
                    "temporal": "static",
                    "forbid_current_numbers": forbid,
                    "title": sec["title"],
                    "context": _DOC_CONTEXT.get(cfg["doc_id"], ""),
                    "text": seg,
                })
    chunks.extend(_csv_knowledge_chunks(ds))
    return chunks


def _csv_knowledge_chunks(ds: DataStore) -> list:
    """行情/行业基准 → 行业知识块（数字事实仍由 DataStore 出，此处只供引用佐证）。"""
    out = []
    for _, r in ds.market.iterrows():
        prices = "、".join(f"{m}月{float(r[f'{m}月价格']):g}元/kg"
                           for m in range(1, 7))
        text = (f"{r['药材名称']}（{r['规格等级']}，{r['价格来源']}）2026上半年价格：{prices}。"
                f"趋势：{r['趋势分析']}")
        out.append({
            "chunk_id": f"MKT-{r['药材名称']}",
            "source": "药材市场价格行情_2026年上半年.csv",
            "page": None, "doc_version": "V1.1", "effective_date": "2026-08-16",
            "type": "行情价", "temporal": "2026-H1", "forbid_current_numbers": False,
            "title": f"行情·{r['药材名称']}", "context": f"{r['药材名称']} 药材市场行情",
            "text": text,
        })
    for _, r in ds.benchmark.iterrows():
        text = (f"{r['产品类别']}｜{r['指标']}：行业P25 {r['行业P25']}、P50 {r['行业P50']}、"
                f"P75 {r['行业P75']}；本厂水平 {r['本厂水平(中药一厂)']}；评价：{r['对标评价']}")
        out.append({
            "chunk_id": f"BNM-{r['产品类别']}-{r['指标']}",
            "source": "行业成本基准数据_2026.csv",
            "page": None, "doc_version": "V1.1", "effective_date": "2026-08-16",
            "type": "行业基准", "temporal": "2026-H1", "forbid_current_numbers": False,
            "title": f"行业基准·{r['产品类别']}·{r['指标']}", "context": f"{r['产品类别']} 行业成本基准",
            "text": text,
        })
    return out
