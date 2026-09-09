# -*- coding: utf-8 -*-
"""嵌入器：离线确定性哈希嵌入（默认）+ 可选 sentence-transformers。

设计目标：演示机无网/无模型也能跑，且同输入永远同输出（可复现）。
"""
import hashlib
import math

import jieba

# 领域词——保证药材/产品名不被切碎
for _w in ["金银花", "黄芩提取物", "板蓝根", "熟地黄", "山茱萸", "山药", "泽泻", "茯苓",
           "牡丹皮", "空心胶囊", "蔗糖", "糊精", "苯甲酸钠", "纯化水", "银黄口服液",
           "板蓝根颗粒", "六味地黄胶囊", "提取收率", "制造费用", "摊薄", "环比", "同比",
           "贡献度", "处方量", "工艺路线", "灌封一体机", "胶囊填充机", "中药材市场"]:
    jieba.add_word(_w)


def tokenize(text: str) -> list:
    return [t for t in jieba.lcut(text) if t.strip() and not _is_punct(t)]


def _is_punct(t: str) -> bool:
    return all(not (ch.isalnum() or "一" <= ch <= "鿿") for ch in t)


def _h(token: str, dim: int) -> int:
    return int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16) % dim


def _sign(token: str) -> float:
    return 1.0 if int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16) % 2 == 0 else -1.0


class JiebaHashEmbedder:
    """特征哈希 + L2 归一：确定性、离线、可复现（md5 保证跨进程一致）。"""

    def __init__(self, dim: int = 512):
        self.dim = dim

    def embed(self, texts):
        out = []
        for text in texts if isinstance(texts, (list, tuple)) else [texts]:
            v = [0.0] * self.dim
            for token in tokenize(text):
                v[_h(token, self.dim)] += _sign(token)
            norm = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / norm for x in v])
        return out[0] if isinstance(texts, str) else out

    def __call__(self, input):  # chromadb EmbeddingFunction 协议
        return self.embed(input)


def best_available(dim: int = 512):
    """优先本地语义模型，不可用则哈希嵌入（演示机兜底）。"""
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("shibing624/text2vec-base-chinese")
        return SentenceTransformerEmbedder(model)
    except Exception:
        return JiebaHashEmbedder(dim)


class SentenceTransformerEmbedder:
    def __init__(self, model):
        self._model = model

    def embed(self, texts):
        if isinstance(texts, str):
            texts = [texts]
        return self._model.encode(texts, normalize_embeddings=True).tolist()

    def __call__(self, input):
        return self.embed(input)
