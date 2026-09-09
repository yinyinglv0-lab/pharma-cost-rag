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


def best_available(corpus: list = None, dim: int = EMBED_DIM):
    """优先本地语义模型，不可用则 IDF 哈希嵌入（演示机兜底）。"""
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("shibing624/text2vec-base-chinese")
        return SentenceTransformerEmbedder(model)
    except Exception:
        return JiebaIdfHashEmbedder(corpus, dim)


class SentenceTransformerEmbedder:
    def __init__(self, model):
        self._model = model

    def embed(self, texts):
        if isinstance(texts, str):
            texts = [texts]
        return self._model.encode(texts, normalize_embeddings=True).tolist()

    def __call__(self, input):
        return self.embed(input)
