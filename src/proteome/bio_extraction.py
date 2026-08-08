"""生物材料知识抽取 Agent：文献证据片段 → 结构化生物材料知识。

对齐开发计划 T2.2：对 T2.1 产出的 papers[].chunk 证据片段做 LLM schema 抽取，
定义生物材料知识四元组（菌株 / 培养条件 / 蛋白家族 / 响应方向 + 证据链接），
构建 data/bio_kb.json，供 T2.3 Research Gap 识别消费。

设计原则（00-project-rules.md 4.1 / 5.3）：
1. 防幻觉三件套：schema 约束 + 原文回查 + 证据链接（对齐 exp.md 经验 13）
2. 可回退：LLM 失败降级规则式抽取（对齐 exp.md 经验 26）
3. 接口契约对齐：BioKnowledgeEntry 复用 SourceRef，to_dict/from_dict 与
   ExtractionRecord 一致（exp.md 经验 58：接口契约比字段名更重要）
4. 落盘隔离：kb_path 可配置，避免测试污染 data/（exp.md 经验 18）
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

from src.common.config import DATA_DIR
from src.common.llm import llm_available, llm_chat_json, model_name
from src.common.logging import AuditLogger
from src.extraction.schemas import SourceRef
from src.proteome.feature_engineering import PROTEIN_FAMILIES

DEFAULT_BIO_KB_PATH = DATA_DIR / 'bio_kb.json'

# 5 种酵母菌株（对齐 00-project-rules.md 5.3）
STRAINS = ('BAI', 'BAH', 'DHY210', 'CEK', 'CGD')

# 响应方向关键词映射（规则式抽取用）
RESPONSE_KEYWORDS: dict[str, list[str]] = {
    'heat_shock': ['heat shock', 'temperature', 'thermal', 'hsp'],
    'metabolic_switch': ['galactose', 'glucose', 'carbon source', 'metabolic', 'gal '],
    'oxidative_stress': ['oxidative', 'ros', 'hydrogen peroxide', 'peroxide'],
    'dna_damage': ['dna repair', 'dna damage', 'rad ', 'uv '],
    'chemical_perturbation': ['perturbation', 'drug', 'chemical stress'],
}


def _utc_now() -> str:
    """UTC 时间戳（ISO8601，秒级）。"""
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


# ---------- 生物材料 Schema ----------


class BioCondition(BaseModel):
    """培养条件（对应「合成加工条件」）。"""

    strain: str | None = Field(default=None, description='菌株（BAI/BAH/DHY210/CEK/CGD）')
    temperature: str | None = Field(
        default=None, description='温度（如 30°C / 37°C）'
    )
    carbon_source: str | None = Field(
        default=None, description='碳源（glucose / galactose）'
    )
    perturbation: str | None = Field(default=None, description='化学扰动描述')

    @field_validator('strain', mode='before')
    @classmethod
    def _coerce_strain(cls, v: Any) -> Any:
        """菌株名大写归一化（加载层宽容进，合法性校验留给下游，exp.md 经验 57）。"""
        if not isinstance(v, str):
            return None
        v = v.strip().upper()
        return v or None


class ProteinFamilyEntry(BaseModel):
    """蛋白家族表达记录。"""

    family: str = Field(description='家族键（hsp/metabolic/oxidative/dna_repair/other）')
    genes: list[str] = Field(default_factory=list, description='涉及基因（如 HSP26, GAL1）')
    response: str | None = Field(
        default=None, description='响应方向（up/down/unchanged/unknown）'
    )

    @field_validator('genes', mode='before')
    @classmethod
    def _coerce_genes(cls, v: Any) -> Any:
        """LLM 填 null 时按空列表处理。"""
        return [] if v is None else v


class BioResponse(BaseModel):
    """菌株响应（对应「材料性能」）。"""

    direction: str = Field(
        default='other', description='响应方向键（heat_shock/metabolic_switch/...）'
    )
    description: str = Field(default='', description='响应描述')
    phenotype: str | None = Field(default=None, description='表型（如 生长速率/耐热性）')


class BioKnowledgeEntry(BaseModel):
    """生物材料知识条目：菌株-条件-蛋白家族-响应 + 证据来源。

    接口契约对齐 ExtractionRecord（to_dict/from_dict/source/confidence/extracted_at），
    便于下游 Gap 识别复用（exp.md 经验 58）。
    """

    condition: BioCondition = Field(default_factory=BioCondition)
    protein_families: list[ProteinFamilyEntry] = Field(default_factory=list)
    response: BioResponse = Field(default_factory=BioResponse)
    source: SourceRef = Field(default_factory=SourceRef)
    confidence: float | None = Field(
        default=None, ge=0.0, le=1.0, description='抽取置信度 0-1'
    )
    extracted_at: str = Field(default_factory=_utc_now)

    @field_validator('protein_families', mode='before')
    @classmethod
    def _coerce_families(cls, v: Any) -> Any:
        """容忍 null。"""
        return [] if v is None else v

    @field_validator('condition', 'response', 'source', mode='before')
    @classmethod
    def _coerce_none_to_dict(cls, v: Any) -> Any:
        """LLM 填 null 时按空 dict 处理。"""
        return {} if v is None else v

    def to_dict(self) -> dict[str, Any]:
        """序列化为 JSON 兼容 dict。"""
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'BioKnowledgeEntry':
        """从 dict 反序列化，非法字段自动忽略。"""
        return cls.model_validate(data)


# ---------- 生物材料知识库 ----------


def _entry_key(entry: BioKnowledgeEntry) -> str:
    """去重键：菌株|温度|碳源|扰动|响应方向。"""
    c = entry.condition
    return '|'.join(
        [
            (c.strain or ''),
            (c.temperature or ''),
            (c.carbon_source or ''),
            (c.perturbation or ''),
            entry.response.direction,
        ]
    )


class BioKnowledgeBase:
    """生物材料知识库（JSON 存储）。"""

    def __init__(self, path: str | Path | None = None) -> None:
        """初始化。

        Args:
            path: 存储路径，默认 data/bio_kb.json。
        """
        self.path = Path(path) if path else DEFAULT_BIO_KB_PATH
        self.entries: list[BioKnowledgeEntry] = []
        if self.path.is_file():
            self._load()

    def add_entry(
        self, entry: BioKnowledgeEntry, *, evidence_id: str | None = None
    ) -> BioKnowledgeEntry:
        """添加一条知识：相同 condition+response 合并证据，否则新增。

        Args:
            entry: 抽取的知识条目。
            evidence_id: 证据 ID（doc_id），回链证据链。

        Returns:
            新增/更新后的条目。
        """
        key = _entry_key(entry)
        for existing in self.entries:
            if _entry_key(existing) == key:
                self._merge_entry(existing, entry, evidence_id)
                return existing
        if evidence_id and evidence_id not in (entry.source.doc_id or ''):
            # 新条目也记录证据 ID（写入 source.doc_id 作为主证据）
            if not entry.source.doc_id:
                entry.source.doc_id = evidence_id
        self.entries.append(entry)
        return entry

    @staticmethod
    def _merge_entry(
        target: BioKnowledgeEntry,
        new: BioKnowledgeEntry,
        evidence_id: str | None,
    ) -> None:
        """合并：蛋白家族并集 + 证据回链 + 置信度取高。"""
        existing_families = {pf.family for pf in target.protein_families}
        for pf in new.protein_families:
            if pf.family not in existing_families:
                target.protein_families.append(pf)
                existing_families.add(pf.family)
        if (new.confidence or 0) > (target.confidence or 0):
            target.confidence = new.confidence
        # 证据回链：doc_id 拼接（简化版，完整证据链在 EvidenceChain）
        if evidence_id and evidence_id not in (target.source.doc_id or ''):
            existing_doc = target.source.doc_id or ''
            target.source.doc_id = (
                f'{existing_doc};{evidence_id}' if existing_doc else evidence_id
            )

    def save(self) -> None:
        """落盘到 JSON。"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [e.model_dump() for e in self.entries]
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8'
        )

    def _load(self) -> None:
        """从 JSON 加载。"""
        try:
            payload = json.loads(self.path.read_text(encoding='utf-8'))
            self.entries = [BioKnowledgeEntry.from_dict(e) for e in payload]
        except (OSError, json.JSONDecodeError, ValueError):
            self.entries = []

    def stats(self) -> dict[str, Any]:
        """知识库统计。"""
        family_dist: dict[str, int] = {}
        direction_dist: dict[str, int] = {}
        for e in self.entries:
            for pf in e.protein_families:
                family_dist[pf.family] = family_dist.get(pf.family, 0) + 1
            direction_dist[e.response.direction] = (
                direction_dist.get(e.response.direction, 0) + 1
            )
        return {
            'n_entries': len(self.entries),
            'family_distribution': family_dist,
            'direction_distribution': direction_dist,
            'path': str(self.path),
        }

    def to_dict(self) -> dict[str, Any]:
        """完整导出（审计/评测用）。"""
        return {
            'entries': [e.model_dump() for e in self.entries],
            'stats': self.stats(),
        }


# ---------- 抽取 Agent ----------

_LLM_SYSTEM_PROMPT = """你是生物材料（酵母蛋白质组学）文献信息抽取助手。
从给定的文献片段中抽取结构化生物材料知识，严格输出 JSON 对象，不要输出任何解释。

JSON 结构（生物材料知识四元组）：
{
  "condition": {
    "strain": "菌株名（BAI/BAH/DHY210/CEK/CGD 之一，未提及填 null）",
    "temperature": "温度（如 30°C / 37°C，未提及填 null）",
    "carbon_source": "碳源（glucose / galactose，未提及填 null）",
    "perturbation": "化学扰动描述，未提及填 null"
  },
  "protein_families": [
    {"family": "hsp|metabolic|oxidative|dna_repair|other",
     "genes": ["基因名列表"],
     "response": "up|down|unchanged|unknown"}
  ],
  "response": {
    "direction": "响应方向键（heat_shock/metabolic_switch/oxidative_stress/"
                 "dna_damage/chemical_perturbation/other）",
    "description": "响应描述（一句话）",
    "phenotype": "表型（如 生长速率变化/耐热性，未提及填 null）"
  },
  "source": {"doi": "DOI", "page": "页码", "paragraph": "段落定位"}
}

硬性要求：
1. 只抽取片段中明确提到的信息，严禁编造（防幻觉）
2. 菌株名/基因名必须原文出现；响应方向必须基于原文证据
3. 未提及的字段填 null 或空数组
4. "confidence" 字段：0-1，反映信息完整度
"""


@dataclass
class BioExtractionStats:
    """抽取统计（审计与评测用）。"""

    n_papers: int = 0
    n_entries: int = 0
    n_llm: int = 0
    n_rule: int = 0
    n_verify_fail: int = 0
    n_merged: int = 0
    model: str | None = None


@dataclass
class BioExtractionResult:
    """抽取结果：知识库 + 统计。"""

    knowledge_base: BioKnowledgeBase
    stats: BioExtractionStats = field(default_factory=BioExtractionStats)


class BioExtractionAgent:
    """生物材料知识抽取 Agent。"""

    def __init__(
        self,
        *,
        kb_path: str | Path | None = None,
        logger: AuditLogger | None = None,
    ) -> None:
        """初始化。

        Args:
            kb_path: 知识库落库路径（默认 data/bio_kb.json）。
            logger: 审计日志器。
        """
        self.kb = BioKnowledgeBase(path=kb_path)
        self.logger = logger or AuditLogger('bio_extraction_agent')

    # ---------- 核心流程 ----------

    def run(
        self, retrieval_json: str | Path | dict[str, Any]
    ) -> BioExtractionResult:
        """执行抽取：读取 T2.1 检索输出 → 抽取 → 校验 → 落库。

        Args:
            retrieval_json: T2.1 输出（JSON 文件路径或 dict，含 papers[].chunk）。

        Returns:
            BioExtractionResult（知识库 + 统计）。
        """
        data = self._load_retrieval(retrieval_json)
        papers = data.get('papers', [])
        stats = BioExtractionStats(
            n_papers=len(papers),
            model=model_name() if llm_available() else None,
        )
        self.logger.log(
            'extract_start',
            'success',
            input_summary={'n_papers': len(papers)},
        )
        n_before = len(self.kb.entries)
        for paper in papers:
            entry = self._extract_paper(paper, stats)
            if entry is not None:
                self.kb.add_entry(entry, evidence_id=paper.get('doc_id'))
        stats.n_merged = len(self.kb.entries) - n_before - stats.n_entries
        stats.n_entries = len(self.kb.entries) - n_before
        self.kb.save()
        self.logger.log(
            'extract_done',
            'success',
            output_summary={
                'n_entries': stats.n_entries,
                'n_llm': stats.n_llm,
                'n_rule': stats.n_rule,
                'n_verify_fail': stats.n_verify_fail,
                'kb_path': str(self.kb.path),
            },
        )
        return BioExtractionResult(knowledge_base=self.kb, stats=stats)

    # ---------- 单篇抽取 ----------

    def _extract_paper(
        self, paper: dict[str, Any], stats: BioExtractionStats
    ) -> BioKnowledgeEntry | None:
        """对单篇文献抽取一条知识条目（取 chunk 证据片段为输入）。"""
        text = paper.get('chunk') or ''
        if not text:
            return None
        doc_id = paper.get('doc_id')
        doi = paper.get('doi')
        page = paper.get('page_no')

        used_llm = False
        if llm_available():
            try:
                raw = llm_chat_json(_LLM_SYSTEM_PROMPT, self._user_prompt(text))
                entry = self._parse_llm_output(
                    raw, doc_id=doc_id, doi=doi, page=page
                )
                used_llm = True
            except Exception as exc:  # LLM 任意失败 → 规则式降级
                self.logger.log(
                    'extract_llm_fallback',
                    'degraded',
                    input_summary={'doc_id': doc_id},
                    output_summary={'reason': str(exc)[:200]},
                )
                entry = self._rule_extract(text, doc_id=doc_id)
        else:
            entry = self._rule_extract(text, doc_id=doc_id)

        if entry is None:
            return None
        if used_llm:
            stats.n_llm += 1
        else:
            stats.n_rule += 1
        # 回查防幻觉：菌株名/基因名/响应关键词至少一个在原文出现
        if not self._verify_against_source(entry, text):
            stats.n_verify_fail += 1
            return None
        return entry

    @staticmethod
    def _user_prompt(text: str) -> str:
        """构造抽取提示（含原文片段，控制长度）。"""
        snippet = text if len(text) <= 6000 else text[:6000]
        return f'请从以下生物材料文献片段中抽取酵母蛋白质组学知识：\n\n{snippet}'

    def _parse_llm_output(
        self,
        raw: dict[str, Any],
        *,
        doc_id: str | None,
        doi: str | None,
        page: Any,
    ) -> BioKnowledgeEntry | None:
        """LLM 输出 → BioKnowledgeEntry（schema 校验 + 来源注入）。"""
        if not raw or 'condition' not in raw:
            return None
        # 注入权威来源（防 LLM 编造来源字段，对齐 exp.md 经验 13）
        raw['source'] = {
            'doi': doi or raw.get('source', {}).get('doi'),
            'page': str(page) if page is not None else raw.get('source', {}).get('page'),
            'doc_id': doc_id,
        }
        try:
            return BioKnowledgeEntry.from_dict(raw)
        except Exception:
            return None

    @staticmethod
    def _verify_against_source(entry: BioKnowledgeEntry, text: str) -> bool:
        """回查防幻觉：菌株名 / 基因名 / 响应关键词至少一个在原文出现。

        生物材料版回查（区别于无机材料的化学式子串匹配）：
        - 菌株名（BAI/BAH/...）在原文 → 通过
        - 蛋白家族涉及的基因名（HSP26/GAL1/...）至少一个在原文 → 通过
        - 响应方向关键词（heat shock/galactose/...）在原文 → 通过
        - 都不命中 → 判为幻觉，丢弃
        """
        text_lower = text.lower()
        # 1. 菌株名
        if entry.condition.strain and entry.condition.strain.lower() in text_lower:
            return True
        # 2. 基因名
        for pf in entry.protein_families:
            for gene in pf.genes:
                if gene and gene.lower() in text_lower:
                    return True
        # 3. 响应方向关键词
        keywords = RESPONSE_KEYWORDS.get(entry.response.direction, [])
        if any(kw in text_lower for kw in keywords):
            return True
        return False

    # ---------- 规则式降级抽取 ----------

    def _rule_extract(
        self, text: str, *, doc_id: str | None
    ) -> BioKnowledgeEntry | None:
        """规则式抽取（降级路径）：正则匹配菌株/温度/碳源/基因名/响应方向。"""
        text_lower = text.lower()

        # 1. 菌株名
        strain = None
        for s in STRAINS:
            if re.search(rf'\b{re.escape(s)}\b', text):
                strain = s
                break

        # 2. 温度
        temperature = None
        temp_match = re.search(r'\b(30|37)\s*[°]?\s*[Cc]\b', text)
        if temp_match:
            temperature = f'{temp_match.group(1)}°C'

        # 3. 碳源
        carbon_source = None
        if 'galactose' in text_lower:
            carbon_source = 'galactose'
        elif 'glucose' in text_lower:
            carbon_source = 'glucose'

        # 4. 蛋白家族：遍历 PROTEIN_FAMILIES 找原文命中的基因
        families: list[ProteinFamilyEntry] = []
        for family, genes in PROTEIN_FAMILIES.items():
            hit_genes = [g for g in genes if g.lower() in text_lower]
            if hit_genes:
                families.append(
                    ProteinFamilyEntry(
                        family=family, genes=hit_genes, response='unknown'
                    )
                )

        # 5. 响应方向
        direction = 'other'
        for dir_key, keywords in RESPONSE_KEYWORDS.items():
            if any(kw in text_lower for kw in keywords):
                direction = dir_key
                break

        # 至少有菌株或基因命中才算有效抽取
        if not strain and not families:
            return None

        return BioKnowledgeEntry(
            condition=BioCondition(
                strain=strain,
                temperature=temperature,
                carbon_source=carbon_source,
            ),
            protein_families=families,
            response=BioResponse(
                direction=direction,
                description='规则式抽取（降级）',
            ),
            source=SourceRef(doc_id=doc_id),
            confidence=0.5,  # 规则式抽取置信度固定 0.5
        )

    # ---------- 输入加载 ----------

    @staticmethod
    def _load_retrieval(
        retrieval_json: str | Path | dict[str, Any]
    ) -> dict[str, Any]:
        """加载 T2.1 输出（路径或 dict）。"""
        if isinstance(retrieval_json, dict):
            return retrieval_json
        path = Path(retrieval_json)
        return json.loads(path.read_text(encoding='utf-8'))
