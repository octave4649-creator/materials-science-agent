"""Sci-Base 语料索引构建器：JSONL → BM25 索引落盘。

数据源（02-literature-data-sources.md 第 2 节）：Sci-Base material 子集
（HF `opendatalab/Sci-Base` config="material"，CC-BY-4.0），字段含
abstract/author/content_list/doi/is_oa/sci_category/title。

构建策略（两级）：
1. 本地 JSONL：`build_from_jsonl` 从已有 JSONL（每行一个 doc）构建索引
   —— 无网络依赖，测试/离线可用
2. HuggingFace 流式：`stream_from_hf` 用 datasets 流式拉取 material 子集
   前 N 条转 JSONL —— 需装 datasets + 网络，可选

落盘：data/cache/scibase/scibase_index.json（路径可配置，落盘隔离 exp 经验 18）。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from src.common.config import CACHE_DIR
from src.common.logging import AuditLogger
from src.rag.bm25_index import BM25Index

DEFAULT_INDEX_PATH = CACHE_DIR / "scibase" / "scibase_index.json"
DEFAULT_JSONL_PATH = CACHE_DIR / "scibase" / "scibase_material.jsonl"


@dataclass
class IndexStats:
    """索引构建统计（审计与日志）。"""

    n_docs: int = 0  # 有效文档数
    n_skipped: int = 0  # 跳过文档数（无 doc_id 或无可检索文本）
    vocab: int = 0  # 词项数
    output_path: str | None = None  # 索引落盘路径


class ScibaseIndexer:
    """Sci-Base 语料索引构建器。"""

    def __init__(
        self,
        *,
        output_path: str | Path | None = None,
        logger: AuditLogger | None = None,
    ) -> None:
        """初始化。

        参数:
            output_path: 索引落盘路径（默认 data/cache/scibase/scibase_index.json）
            logger: 审计日志器（默认 scibase_indexer 专用）
        """
        self.output_path = Path(output_path) if output_path else DEFAULT_INDEX_PATH
        self.logger = logger or AuditLogger("scibase_indexer")

    # ---------- 主入口 ----------

    def build_from_jsonl(
        self, jsonl_path: str | Path, *, limit: int | None = None
    ) -> IndexStats:
        """从本地 JSONL 构建索引并落盘。

        参数:
            jsonl_path: JSONL 文件（每行一个 doc，字段对齐 Sci-Base 子集）
            limit: 最多构建文档数（None 表示全部）

        返回:
            IndexStats（文档数/跳过数/词项数/落盘路径）。
        """
        p = Path(jsonl_path)
        if not p.exists():
            self.logger.log(
                "build_from_jsonl", "error", input_summary={"path": str(p)}
            )
            return IndexStats()
        index = BM25Index()
        n_skipped = 0
        n_total = 0
        with self.logger.step(
            "build_index", input_summary={"path": str(p), "limit": limit}
        ):
            for raw in self._iter_jsonl(p, limit):
                n_total += 1
                doc = self._normalize_doc(raw)
                if doc is None:
                    n_skipped += 1
                    continue
                index.docs[doc["doc_id"]] = doc
            # 用归一化后的 doc 列表构建词频表（build 会按 doc_id 去重）
            index.build(list(index.docs.values()))
            index.save(self.output_path)
        stats = IndexStats(
            n_docs=index.n_docs,
            n_skipped=n_skipped,
            vocab=len(index.doc_freqs),
            output_path=str(self.output_path),
        )
        self.logger.log(
            "build_index_done",
            "success",
            output_summary={
                "n_total": n_total,
                **stats.__dict__,
            },
        )
        return stats

    @staticmethod
    def _iter_jsonl(path: Path, limit: int | None) -> Iterator[dict[str, Any]]:
        """逐行读取 JSONL（容错：坏行跳过，exp 经验 57 加载层宽容进）。"""
        count = 0
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
                count += 1
                if limit is not None and count >= limit:
                    return

    @staticmethod
    def _normalize_doc(raw: dict[str, Any]) -> dict[str, Any] | None:
        """Sci-Base 行 → 索引文档（doc_id 取 doi 兜底 sha 值）。"""
        doc_id = str(raw.get("doc_id") or raw.get("doi") or raw.get("sha256") or "")
        if not doc_id:
            return None
        title = str(raw.get("title") or "").strip()
        abstract = str(raw.get("abstract") or "").strip()
        content = raw.get("content_list")
        if isinstance(content, (list, dict)):
            content = _flatten_content(content)
        if not (title or abstract or content):
            return None
        year = raw.get("publication_published_year") or raw.get("year")
        return {
            "doc_id": doc_id,
            "doi": raw.get("doi"),
            "title": title,
            "abstract": abstract,
            "content": str(content) if content else None,
            "year": int(year) if str(year).isdigit() else None,
            "sci_category": raw.get("sci_category"),
        }

    # ---------- 检索产物构建（离线真实语料） ----------

    def build_from_retrieval(
        self, retrieval_paths: list[str | Path], *, limit: int | None = None
    ) -> IndexStats:
        """从本地 Sciverse 检索产物聚合真实文献构建索引并落盘。

        离线降级路径（对齐 exp 经验 26/47）：HF 网络受限时，用本地已有的
        Sciverse 检索产物（results/retrieval_*.json，含 doc_id/title/doi/
        chunk 证据片段）作为真实语料，让 RAG 从「测试文档」升级为真实文献。
        多文件按 doc_id 去重；缺失/损坏文件跳过不中断。

        参数:
            retrieval_paths: 检索产物 JSON 文件列表
            limit: 最多构建文档数（None 表示全部）

        返回:
            IndexStats（文档数/跳过数/词项数/落盘路径）。
        """
        index = BM25Index()
        n_skipped = 0
        n_total = 0
        seen: set[str] = set()
        with self.logger.step(
            "build_from_retrieval",
            input_summary={"paths": [str(p) for p in retrieval_paths], "limit": limit},
        ):
            for path in retrieval_paths:
                p = Path(path)
                if not p.exists():
                    n_skipped += 1
                    self.logger.log(
                        "retrieval_missing", "degraded", input_summary={"path": str(p)}
                    )
                    continue
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    n_skipped += 1
                    self.logger.log(
                        "retrieval_bad_json",
                        "degraded",
                        input_summary={"path": str(p)},
                        error=str(exc)[:200],
                    )
                    continue
                for paper in data.get("papers", []):
                    if limit is not None and n_total >= limit:
                        break
                    n_total += 1
                    doc = self._normalize_retrieval_paper(paper)
                    if doc is None or doc["doc_id"] in seen:
                        if doc is None:
                            n_skipped += 1
                        continue
                    seen.add(doc["doc_id"])
                    index.docs[doc["doc_id"]] = doc
                if limit is not None and n_total >= limit:
                    break
            index.build(list(index.docs.values()))
            index.save(self.output_path)
        stats = IndexStats(
            n_docs=index.n_docs,
            n_skipped=n_skipped,
            vocab=len(index.doc_freqs),
            output_path=str(self.output_path),
        )
        self.logger.log(
            "build_from_retrieval_done",
            "success",
            output_summary={
                "n_total": n_total,
                **stats.__dict__,
            },
        )
        return stats

    @staticmethod
    def _normalize_retrieval_paper(
        paper: dict[str, Any],
    ) -> dict[str, Any] | None:
        """检索产物论文 → 索引文档（chunk 作为 content 证据片段）。"""
        doc_id = str(paper.get("doc_id") or paper.get("unique_id") or "")
        if not doc_id:
            return None
        title = str(paper.get("title") or "").strip()
        chunk = str(paper.get("chunk") or "").strip()
        if not (title or chunk):
            return None
        year = paper.get("year")
        return {
            "doc_id": doc_id,
            "doi": paper.get("doi"),
            "title": title,
            "abstract": "",
            "content": chunk or None,
            "year": int(year) if str(year).isdigit() else None,
            "sci_category": "sciverse-retrieval",
        }

    # ---------- HuggingFace 流式（可选） ----------

    @classmethod
    def stream_from_hf(
        cls, output_path: str | Path | None = None, limit: int = 1000
    ) -> Path:
        """用 datasets 流式拉取 Sci-Base material 子集前 limit 条 → JSONL。

        依赖：`datasets` 包（未安装时抛清晰 ImportError）+ 网络。
        输出：JSONL（每行一个 doc，字段对齐 HF 原始字段，供 build_from_jsonl 消费）。

        参数:
            output_path: JSONL 落盘路径（默认 data/cache/scibase/scibase_material.jsonl）
            limit: 拉取条数上限

        返回:
            JSONL 落盘路径。
        """
        out = Path(output_path) if output_path else DEFAULT_JSONL_PATH
        try:
            from datasets import load_dataset  # 可选依赖
        except ImportError as exc:  # pragma: no cover - 依赖缺失路径
            raise ImportError(
                "stream_from_hf 需要安装 datasets 包：pip install datasets\n"
                "或改用本地 JSONL：run_scibase_index.py --jsonl <path>"
            ) from exc
        out.parent.mkdir(parents=True, exist_ok=True)
        ds = load_dataset(
            "opendatalab/Sci-Base", "material", split="train", streaming=True
        )
        with out.open("w", encoding="utf-8") as fh:
            for i, row in enumerate(ds):
                if i >= limit:
                    break
                fh.write(json.dumps(dict(row), ensure_ascii=False) + "\n")
        return out


def _flatten_content(content: list[Any] | dict[str, Any]) -> str:
    """content_list（结构化正文）→ 纯文本（合并 text 字段）。"""
    parts: list[str] = []
    for item in content if isinstance(content, list) else [content]:
        if isinstance(item, dict):
            text = item.get("text")
            if text:
                parts.append(str(text))
        elif isinstance(item, str):
            parts.append(item)
    return "\n".join(parts)
