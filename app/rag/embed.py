# -*- coding: utf-8 -*-
"""嵌入器：离线确定性 IDF 加权哈希嵌入（默认）+ 可选 sentence-transformers。

设计目标：演示机无网/无模型也能跑，且同输入永远同输出（可复现，md5 跨进程一致）。

v2（评审修复 P1-1）：
- IDF 加权——罕见领域词（金银花/收率/摊薄）权重大、停用词权重≈0，
  抑制"83% 桶碰撞"下的噪声累积；
- dim 提升到 8192，词表 3079 → 碰撞率约 17%（断言 < 25%）。
"""
import hashlib
import math
import os
from collections import Counter

import jieba

EMBED_DIM = 8192

# 领域词——保证药材/产品名不被切碎
_DOMAIN_WORDS = ["金银花", "黄芩提取物", "板蓝根", "熟地黄", "山茱萸", "山药", "泽泻", "茯苓",
                 "牡丹皮", "空心胶囊", "蔗糖", "糊精", "苯甲酸钠", "纯化水", "银黄口服液",
                 "板蓝根颗粒", "六味地黄胶囊", "提取收率", "制造费用", "摊薄", "环比", "同比",
                 "贡献度", "处方量", "工艺路线", "灌封一体机", "胶囊填充机", "中药材市场"]
for _w in _DOMAIN_WORDS:
    jieba.add_word(_w)


def add_domain_word(word: str):
    jieba.add_word(word)


def tokenize(text: str) -> list:
    return [t for t in jieba.lcut(text) if t.strip() and not _is_punct(t)]


def _is_punct(t: str) -> bool:
    return all(not (ch.isalnum() or "一" <= ch <= "鿿") for ch in t)


def _h(token: str, dim: int) -> int:
    return int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16) % dim


def _sign(token: str) -> float:
    return 1.0 if int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16) % 2 == 0 else -1.0


class JiebaIdfHashEmbedder:
    """IDF 加权特征哈希 + L2 归一：确定性、离线、可复现。"""

    def __init__(self, corpus: list = None, dim: int = EMBED_DIM):
        self.dim = dim
        self._idf: dict = {}
        if corpus:
            self._fit(corpus)

    def _fit(self, texts):
        dfs = Counter()
        n = 0
        for t in texts:
            n += 1
            for w in set(tokenize(t)):
                dfs[w] += 1
        self._idf = {w: math.log((n + 1) / (c + 1)) + 1.0 for w, c in dfs.items()}

    def embed(self, texts):
        if isinstance(texts, str):
            texts = [texts]
        out = []
        for text in texts:
            v = [0.0] * self.dim
            for token in tokenize(text):
                v[_h(token, self.dim)] += _sign(token) * self._idf.get(token, 1.0)
            norm = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / norm for x in v])
        return out

    def __call__(self, input):  # 兼容旧调用
        return self.embed(input)

    # ---- chromadb 新版 EmbeddingFunction 协议 ----
    is_legacy = False

    def name(self):
        return "jieba-idf-hash"

    def embed_query(self, input):
        return self.embed(input)

    def embed_documents(self, input):
        return self.embed(input)


# 兼容旧名
JiebaHashEmbedder = JiebaIdfHashEmbedder


def _resolve_model_name():
    """模型解析顺序：环境变量 → ModelScope 本地缓存（国内可达）→ HF 默认名（离线不可达时哈希兜底接管）。

    在 auto_embedder 调用时动态解析——模型晚于模块导入才下载完成也能被探测到。
    """
    env = os.environ.get("RAG_EMBED_MODEL")
    if env:
        return env
    from pathlib import Path
    root = Path.home() / ".cache/modelscope/models"
    for cand in ("iic--nlp_gte_sentence-embedding_chinese-small",
                 "iic--nlp_gte_sentence-embedding_chinese-base"):
        snap = root / cand / "snapshots"
        if snap.exists():
            latest = sorted(snap.iterdir())
            if latest:
                return str(latest[-1])
    for cand in ("nlp_gte_sentence-embedding_chinese-small", "nlp_gte_sentence-embedding_chinese-base",
                 "text2vec-base-chinese"):
        for prefix in (Path.home() / ".cache/modelscope/hub/models/iic",
                       Path.home() / ".cache/huggingface/hub/models--shibing624"):
            p = prefix / cand
            if p.exists():
                return str(p)
    return "shibing624/text2vec-base-chinese"


class SentenceTransformerEmbedder:
    """本地语义模型（GTE/text2vec 中文句向量，可离线使用，满足 6.1"语义检索"本义）。

    available 类标记：成功实例化即置 True，供测试/文档判断当前生效的嵌入路径。
    """
    available = False

    def __init__(self, model, corpus=None, model_name: str = ""):
        self._model = model
        self.model_name = model_name
        SentenceTransformerEmbedder.available = True

    # ---- chromadb 新版 EmbeddingFunction 协议 ----
    is_legacy = False

    def name(self):
        return "st-" + os.path.basename(self.model_name)

    def embed_query(self, input):
        return self.embed(input)

    def embed_documents(self, input):
        return self.embed(input)

    def embed(self, texts):
        if isinstance(texts, str):
            texts = [texts]
        return self._model.encode(texts, normalize_embeddings=True).tolist()

    def __call__(self, input):
        return self.embed(input)


def auto_embedder(corpus: list = None):
    """合规默认（缺口 2 修复）：优先本地语义模型；未安装/加载失败/无网时兜底 IDF 哈希。

    - RAG_EMBED_FORCE=hash 强制兜底（CI/演示机确定性）；
    - RAG_EMBED_MODEL 覆盖模型名/本地路径；
    - HF_ENDPOINT=https://hf-mirror.com 可加速 HF 下载（国内推荐 ModelScope，见 README）。
    """
    if os.environ.get("RAG_EMBED_FORCE") == "hash":
        return JiebaIdfHashEmbedder(corpus)
    try:
        from sentence_transformers import SentenceTransformer
        name = _resolve_model_name()
        model = SentenceTransformer(name)
        return SentenceTransformerEmbedder(model, corpus, model_name=name)
    except Exception as e:  # 记录兜底原因，便于诊断（不做静默降级）
        import warnings
        warnings.warn(f"语义模型不可用，降级 IDF 哈希嵌入: {type(e).__name__}: {e}")
        return JiebaIdfHashEmbedder(corpus)


def best_available(corpus: list = None, dim: int = EMBED_DIM):
    """兼容旧名：等同 auto_embedder。"""
    return auto_embedder(corpus)
