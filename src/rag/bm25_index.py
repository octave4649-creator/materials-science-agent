"""BM25 检索索引（纯 Python，无第三方依赖）。

对齐项目先例（exp 经验 38：SR 纯 Python 实现）：Sci-Base local search 的
本地索引采用手写 BM25，避免引入外部向量库依赖，保证离线可构建、可复现。

BM25 公式（Okapi）：
    score(d, q) = Σ IDF(t) * tf(t,d) * (k1+1) / (tf(t,d) + k1 * (1 - b + b * dl/avgdl))
    IDF(t) = ln(1 + (N - df(t) + 0.5) / (df(t) + 0.5))

用法：
    index = BM25Index()
    index.build(docs)          # docs: list[dict]（doc_id/title/abstract/content/...）
    hits = index.search(query, top_k=5)
    index.save(path); index.load(path)
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# 文档统一字段（对齐 Sci-Base 字段：title/abstract/content/doi/sci_category）
_DOC_FIELDS = ("doc_id", "doi", "title", "abstract", "content", "year", "sci_category")

# 分词：英文/数字词（>=2 字符或纯数字串）或连续中文片段（>=2 字）
_TOKEN_RE = re.compile(r"[a-z0-9]{2,}|[0-9]+|[\u4e00-\u9fff]{2,}")
# 中文连续片段（bigram 切分用）
_CN_ONLY_RE = re.compile(r"^[\u4e00-\u9fff]+$")

_K1 = 1.5  # BM25 词频饱和参数
_B = 0.75  # 文档长度归一化参数


def _cn_bigrams(seg: str) -> list[str]:
    """中文片段 bigram 切分：'热电材料' → ['热电','电材','材料']。

    连续中文整体分词会导致查询词无法命中子串（如 '热电' vs '热电材料'），
    bigram 保证中英文混合检索的召回。
    """
    if len(seg) <= 2:
        return [seg]
    return [seg[i : i + 2] for i in range(len(seg) - 1)]


def tokenize(text: str) -> list[str]:
    """文本分词：小写 + 英文/数字词 + 中文 bigram。"""
    if not text:
        return []
    tokens: list[str] = []
    for match in _TOKEN_RE.findall(text.lower()):
        if _CN_ONLY_RE.match(match):
            tokens.extend(_cn_bigrams(match))
        else:
            tokens.append(match)
    return tokens


@dataclass
class RagHit:
    """单条检索命中。"""

    doc_id: str
    score: float
    title: str = ""
    abstract: str = ""
    doi: str | None = None
    year: int | None = None
    sci_category: str | None = None
    snippet: str = ""  # 命中片段（取标题/摘要）

    def to_dict(self) -> dict[str, Any]:
        """序列化为 dict（落盘/审计）。"""
        return {
            "doc_id": self.doc_id,
            "score": round(self.score, 6),
            "title": self.title,
            "abstract": self.abstract,
            "doi": self.doi,
            "year": self.year,
            "sci_category": self.sci_category,
            "snippet": self.snippet,
        }


@dataclass
class BM25Index:
    """BM25 检索索引。

    属性:
        docs: 文档元数据（doc_id → 字段）
        doc_freqs: 词项 → 出现文档数 df
        doc_tfs: doc_id → 词项 → 词频 tf
        doc_lengths: doc_id → 文档长度（词数）
        avg_dl: 平均文档长度
        k1/b: BM25 参数
    """

    docs: dict[str, dict[str, Any]] = field(default_factory=dict)
    doc_freqs: dict[str, int] = field(default_factory=dict)
    doc_tfs: dict[str, dict[str, int]] = field(default_factory=dict)
    doc_lengths: dict[str, int] = field(default_factory=dict)
    avg_dl: float = 0.0
    k1: float = _K1
    b: float = _B

    # ---------- 构建 ----------

    def build(self, docs: list[dict[str, Any]]) -> None:
        """从文档列表构建倒排索引。

        参数:
            docs: 每项含 doc_id 与可检索文本字段（title/abstract/content）。
        """
        self.docs = {}
        self.doc_freqs = {}
        self.doc_tfs = {}
        self.doc_lengths = {}
        total_len = 0
        for raw in docs:
            doc_id = str(raw.get("doc_id") or raw.get("doi") or "")
            if not doc_id:
                continue
            text = self._doc_text(raw)
            tokens = tokenize(text)
            if not tokens:
                continue
            tf: dict[str, int] = {}
            for tok in tokens:
                tf[tok] = tf.get(tok, 0) + 1
            self.docs[doc_id] = {k: raw.get(k) for k in _DOC_FIELDS if k in raw}
            self.docs[doc_id]["doc_id"] = doc_id
            self.doc_tfs[doc_id] = tf
            self.doc_lengths[doc_id] = len(tokens)
            total_len += len(tokens)
            for tok in tf:
                self.doc_freqs[tok] = self.doc_freqs.get(tok, 0) + 1
        n = len(self.doc_lengths)
        self.avg_dl = total_len / n if n else 0.0

    @staticmethod
    def _doc_text(raw: dict[str, Any]) -> str:
        """拼接文档可检索文本（title + abstract + content）。"""
        parts = [
            str(raw.get("title") or ""),
            str(raw.get("abstract") or ""),
            str(raw.get("content") or ""),
        ]
        return "\n".join(p for p in parts if p)

    # ---------- 检索 ----------

    def search(self, query: str, top_k: int = 5) -> list[RagHit]:
        """BM25 检索：返回按相关度降序的命中列表。"""
        if not self.docs or not query:
            return []
        query_tokens = tokenize(query)
        if not query_tokens:
            return []
        n = len(self.doc_lengths)
        scores: dict[str, float] = {}
        for tok in set(query_tokens):
            df = self.doc_freqs.get(tok, 0)
            if df == 0:
                continue
            idf = math.log(1.0 + (n - df + 0.5) / (df + 0.5))
            for doc_id, tf_map in self.doc_tfs.items():
                tf = tf_map.get(tok, 0)
                if tf == 0:
                    continue
                dl = self.doc_lengths.get(doc_id, 0)
                norm = 1.0 - self.b + self.b * dl / self.avg_dl if self.avg_dl else 1.0
                scores[doc_id] = scores.get(doc_id, 0.0) + (
                    idf * tf * (self.k1 + 1) / (tf + self.k1 * norm)
                )
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:top_k]
        return [self._to_hit(doc_id, score) for doc_id, score in ranked]

    def _to_hit(self, doc_id: str, score: float) -> RagHit:
        """构造命中：附带命中片段（标题优先，缺省取摘要前 200 字）。"""
        meta = self.docs.get(doc_id, {})
        title = str(meta.get("title") or "")
        abstract = str(meta.get("abstract") or "")
        snippet = title or (abstract[:200] + ("…" if len(abstract) > 200 else ""))
        return RagHit(
            doc_id=doc_id,
            score=score,
            title=title,
            abstract=abstract,
            doi=meta.get("doi"),
            year=meta.get("year"),
            sci_category=meta.get("sci_category"),
            snippet=snippet,
        )

    # ---------- 持久化 ----------

    def save(self, path: str | Path) -> None:
        """索引落盘（JSON）：词项 df 表 + 文档字段 + 词频表 + 长度表。"""
        payload = {
            "k1": self.k1,
            "b": self.b,
            "avg_dl": self.avg_dl,
            "docs": self.docs,
            "doc_freqs": self.doc_freqs,
            "doc_tfs": self.doc_tfs,
            "doc_lengths": self.doc_lengths,
        }
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "BM25Index":
        """从磁盘加载索引；文件缺失返回空索引（降级不抛错）。"""
        p = Path(path)
        if not p.exists():
            return cls()
        payload = json.loads(p.read_text(encoding="utf-8"))
        return cls(
            docs=payload.get("docs", {}),
            doc_freqs=payload.get("doc_freqs", {}),
            doc_tfs=payload.get("doc_tfs", {}),
            doc_lengths=payload.get("doc_lengths", {}),
            avg_dl=payload.get("avg_dl", 0.0),
            k1=payload.get("k1", _K1),
            b=payload.get("b", _B),
        )

    @property
    def n_docs(self) -> int:
        """索引文档数。"""
        return len(self.docs)
