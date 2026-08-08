"""真实可用的在线流水线 API（FastAPI 后端）。

定位（用户需求「把真正可以使用的部署到 demo 中」）：
赛事组在 Web 页自由输入研究问题 → 后端真实运行六阶段流水线：
    检索（Sci-Base BM25 本地索引优先 + Sciverse 在线可选）
  → 抽取（LLM schema 约束 / 规则式降级）
  → Gap 识别（覆盖率 + 矛盾 + LLM 推理）
  → 搜索算法 × LLM（GA/SR/MCTS/BO 三角色）
  → 数据库验证（oracle 真值表本地降级，OQMD 服务器不可达）
  → 证据链审计（全阶段产物汇总）
每阶段实时更新 job 进度，前端轮询展示，最终返回完整产物 JSON。

部署形态（腾讯云 Lighthouse，2 核 / 3.5Gi 内存）：
- 不安装 langgraph / pymatgen / mp-api（重依赖省内存），后端手动顺序编排
- 训练好的资产随仓库上传：data/cache/scibase/scibase_index.json（BM25 索引）、
  results/oracle/oracle_truth_*.json（12 母体 OQMD 验证真值表）
- 在线能力按凭据自动升级：SCIVERSE_API_TOKEN → 在线语义检索；
  DEEPSEEK_API_KEY → LLM 三角色/抽取/Gap 推理

用法（本地开发）:
    uvicorn scripts.run_live_api:app --host 127.0.0.1 --port 8000
或:  python scripts/run_live_api.py

接口:
    POST /api/run             {question, domain?, top_k?, algo?, use_llm?} -> {job_id}
    GET  /api/jobs/{job_id}   -> {status, stage, message, progress, result?}
    GET  /api/jobs            -> 任务列表（摘要）
"""

from __future__ import annotations

import json
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# 允许直接 `python scripts/run_live_api.py` 运行
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from src.common.config import PROJECT_ROOT  # noqa: E402
from src.common.llm import llm_available, model_name  # noqa: E402

# 训练好的资产路径（随仓库上传）
DEFAULT_INDEX_PATH = PROJECT_ROOT / "data" / "cache" / "scibase" / "scibase_index.json"
ORACLE_DIR = PROJECT_ROOT / "results" / "oracle"

# 任务工作目录（每 job 独立，避免并发文件冲突）
LIVE_DIR = PROJECT_ROOT / "results" / "live"
JOBS_DIR = LIVE_DIR / "jobs"

# 六阶段（对齐 demo-pipeline 演示页）
STAGES = ("retrieve", "extract", "gap", "search", "verify", "audit")

# 单机资源有限：最多 2 个并发任务，其余排队
MAX_WORKERS = 2
_SEM = threading.Semaphore(MAX_WORKERS)

# 领域 → 覆盖分析阈值（min_evidence）
_DOMAIN_MIN_EVIDENCE = {"thermoelectric": 1, "materials": 1, "battery": 1, "catalysis": 1}


@dataclass
class Job:
    """一个在线流水线任务（内存态，单进程 demo 够用）。"""

    job_id: str
    question: str
    domain: str = "materials"
    top_k: int = 8
    algo: str = "ga"
    use_llm: bool = True
    status: str = "queued"  # queued / running / done / failed
    stage: str = ""  # 当前阶段（STAGES 之一或空）
    message: str = ""  # 阶段说明（前端展示）
    progress: float = 0.0  # 0-1 总进度
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    result: dict[str, Any] | None = None
    error: str | None = None


JOBS: dict[str, Job] = {}
JOBS_LOCK = threading.Lock()

app = FastAPI(
    title="材料科学文献驱动的科学发现智能体 · 在线流水线",
    version="1.0",
    description="真实可用的六阶段流水线：检索 → 抽取 → Gap → 搜索×LLM → 验证 → 审计",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 本地开发：静态托管 docs/（部署时 nginx 负责静态，此处仅为本地联调提供页面）
_DOCS_DIR = PROJECT_ROOT / "docs"
if _DOCS_DIR.exists():
    app.mount("/demo", StaticFiles(directory=str(_DOCS_DIR)), name="demo")


class RunRequest(BaseModel):
    """运行请求：研究问题必填，其余可选。"""

    question: str = Field(..., description="研究问题（自由输入）")
    domain: str = Field(
        "materials", description="调研领域（thermoelectric/materials/battery/catalysis）"
    )
    top_k: int = Field(8, ge=1, le=30, description="单阶段检索 top_k")
    algo: str = Field("ga", description="搜索算法（ga/sr/mcts/bo）")
    use_llm: bool = Field(True, description="是否启用 LLM（抽取/Gap/搜索三角色）")


def _job_dict(job: Job) -> dict[str, Any]:
    """Job → 前端可读 dict（不含内部锁）。"""
    return {
        "job_id": job.job_id,
        "question": job.question,
        "domain": job.domain,
        "top_k": job.top_k,
        "algo": job.algo,
        "use_llm": job.use_llm,
        "status": job.status,
        "stage": job.stage,
        "message": job.message,
        "progress": job.progress,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "result": job.result,
        "error": job.error,
    }


def _set_stage(job: Job, stage: str, message: str, progress: float) -> None:
    """更新 job 阶段与进度（线程安全）。"""
    with JOBS_LOCK:
        job.stage = stage
        job.message = message
        job.progress = progress
        job.updated_at = time.time()


def _set_done(job: Job, result: dict[str, Any]) -> None:
    with JOBS_LOCK:
        job.status = "done"
        job.stage = "audit"
        job.message = "流水线完成"
        job.progress = 1.0
        job.result = result
        job.updated_at = time.time()


def _set_failed(job: Job, error: str) -> None:
    with JOBS_LOCK:
        job.status = "failed"
        job.message = "流水线失败"
        job.error = error[:2000]
        job.updated_at = time.time()


# ---------- 六阶段实现 ----------


def _stage_retrieve(job: Job, work_dir: Path) -> dict[str, Any]:
    """阶段 1 检索：本地 BM25 优先 + Sciverse 在线可选，合并去重。"""
    _set_stage(job, "retrieve", "检索中：Sci-Base 本地 BM25 索引（训练好的模型）", 0.10)
    from src.rag.rag_tool import RagRetrievalTool

    rag = RagRetrievalTool()
    rag_papers = rag.search_papers(job.question, top_k=job.top_k)
    sources = ["scibase"]
    online_papers: list[dict[str, Any]] = []

    # Sciverse 在线（可选升级：配置 token 后自动启用）
    from src.common.config import sciverse_token

    if sciverse_token():
        try:
            _set_stage(job, "retrieve", "检索中：Sciverse 在线语义检索（已配置 token）", 0.14)
            from src.agent.retrieval_agent import RetrievalAgent

            online = RetrievalAgent().run_sync(job.question, top_k=job.top_k)
            online_papers = online.papers
            sources.append("sciverse")
        except Exception as exc:  # 在线失败降级，不中断
            job.message += f"（在线检索降级: {str(exc)[:120]}）"

    # 合并去重（doc_id/unique_id/title）
    papers: list[dict[str, Any]] = []
    seen: set[str] = set()
    for p in rag_papers + online_papers:
        key = (
            f"doc:{p.get('doc_id')}"
            or f"uid:{p.get('unique_id')}"
            or f"title:{str(p.get('title', '')).strip().lower()}"
        )
        if key in seen:
            continue
        seen.add(key)
        papers.append(p)

    # 落盘检索产物（供后续阶段与审计复用）
    retrieval = {"query": job.question, "papers": papers, "sources": sources}
    (work_dir / "retrieval.json").write_text(
        json.dumps(retrieval, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return retrieval


def _stage_extract(job: Job, work_dir: Path, retrieval: dict[str, Any]) -> dict[str, Any]:
    """阶段 2 抽取：LLM schema 约束抽取，失败规则式降级。"""
    papers = retrieval.get("papers", [])
    if not papers:
        _set_stage(job, "extract", "抽取中：无文献可抽取", 0.25)
        return {"n_papers": 0, "n_records": 0, "records": [], "mode": "skipped"}
    _set_stage(job, "extract", "抽取中：LLM schema 约束抽取（防幻觉）", 0.24)
    from src.agent.extraction_agent import ExtractionAgent

    kb_path = work_dir / "knowledge_base.json"
    agent = ExtractionAgent(kb_path=kb_path)
    result = agent.run(retrieval)
    kb_dict = result.knowledge_base.to_dict()
    records = [
        {
            "formula": e.get("normalized_formula")
            or e.get("record", {}).get("material", {}).get("formula"),
            "confidence": e.get("record", {}).get("confidence"),
            "evidence_ids": e.get("evidence_ids", []),
        }
        for e in kb_dict.get("entries", [])
    ]
    return {
        "n_papers": result.stats.n_papers,
        "n_records": result.stats.n_records,
        "n_llm": result.stats.n_llm,
        "n_rule": result.stats.n_rule,
        "n_merged": result.stats.n_merged,
        "mode": "llm" if result.stats.n_llm else "rule",
        "records_preview": records[:5],
    }


def _stage_gap(job: Job, work_dir: Path) -> dict[str, Any]:
    """阶段 3 Gap 识别：覆盖率 + 矛盾 + LLM 推理（Sciverse 回查关闭保稳）。"""
    _set_stage(job, "gap", "Gap 识别中：覆盖率分析 + 矛盾检测 + LLM 推理", 0.45)
    from src.agent.gap_agent import GapAgent

    kb_path = work_dir / "knowledge_base.json"
    gaps_path = work_dir / "gaps.json"
    agent = GapAgent(kb_path=kb_path, output_path=gaps_path)
    min_ev = _DOMAIN_MIN_EVIDENCE.get(job.domain, 1)
    result = agent.run_sync(domain=job.domain, min_evidence=min_ev, max_gaps=10, verify=False)
    gaps = [
        {
            "statement": g.statement,
            "gap_type": g.gap_type,
            "formulas": g.formulas,
            "rationale": g.rationale,
            "confidence": g.confidence,
        }
        for g in result.report.gaps
    ]
    return {
        "n_gaps": len(gaps),
        "n_coverage": result.stats.n_coverage,
        "n_contradiction": result.stats.n_contradiction,
        "n_llm": result.stats.n_llm,
        "gaps": gaps,
    }


def _stage_search(job: Job, work_dir: Path, gap_result: dict[str, Any]) -> dict[str, Any]:
    """阶段 4 搜索算法 × LLM：对 Gap 清单执行 GA/SR/MCTS/BO 三角色搜索。"""
    if not gap_result.get("gaps"):
        _set_stage(job, "search", "搜索跳过：无 Gap 种子", 0.60)
        return {"algo": job.algo, "n_findings": 0, "findings": []}
    _set_stage(job, "search", f"搜索中：{job.algo.upper()} × LLM 三角色（种子→评估→剪枝）", 0.55)
    from src.agent.search_agent import SearchAgent

    gaps_path = work_dir / "gaps.json"
    out_dir = work_dir / "findings"
    agent = SearchAgent(gaps_path=gaps_path, output_dir=out_dir)
    results = agent.run(
        top_n=min(2, gap_result.get("n_gaps", 0)),
        generations=3,
        pop_size=8,
        use_llm=job.use_llm,
        domain=job.domain,
        algo=job.algo,
    )
    findings = []
    for res in results:
        f = res.finding
        findings.append(
            {
                "relation": f.relation,
                "hypothesis": f.hypothesis,
                "novelty": f.novelty,
                "confidence": f.confidence,
                "mechanism": f.mechanism,
                "gap_statement": f.gap_statement,
                "top_candidates": [c.to_dict() for c in f.top_candidates[:5]],
                "llm_calls": f.search_log.llm_calls,
                "llm_failures": f.search_log.llm_failures,
                "used_llm": f.search_log.used_llm,
            }
        )
    return {
        "algo": job.algo,
        "n_findings": len(findings),
        "llm_on": llm_available(),
        "model": model_name() if llm_available() else None,
        "findings": findings,
    }


def _stage_verify(job: Job, work_dir: Path, search_result: dict[str, Any]) -> dict[str, Any]:
    """阶段 5 数据库验证：oracle 真值表本地降级（OQMD 服务器不可达）。"""
    _set_stage(job, "verify", "验证中：OQMD oracle 真值表交叉验证（本地降级）", 0.80)
    # 加载最新 oracle 真值表（训练好的模型资产）
    truth: dict[str, str] = {}
    meta: dict[str, Any] = {}
    if ORACLE_DIR.exists():
        files = sorted(ORACLE_DIR.glob("oracle_truth_*.json"))
        if files:
            data = json.loads(files[-1].read_text(encoding="utf-8"))
            meta = {
                "generated_at": data.get("generated_at"),
                "n_hosts": data.get("n_hosts"),
                "source": data.get("source"),
            }
            for r in data.get("results", []):
                truth[str(r.get("host", "")).strip()] = r.get("verdict", "未知")
                truth[str(r.get("candidate_formula", "")).strip()] = r.get("verdict", "未知")

    verdicts: list[dict[str, Any]] = []
    n_known = n_novel = n_unknown = 0
    for f in search_result.get("findings", []):
        for cand in f.get("top_candidates", []):
            host = str(cand.get("host", ""))
            formula = str(cand.get("formula", ""))
            verdict = truth.get(host) or truth.get(formula) or "未知"
            if verdict == "已知":
                n_known += 1
            elif verdict == "新知":
                n_novel += 1
            else:
                n_unknown += 1
            verdicts.append(
                {
                    "host": host,
                    "formula": formula,
                    "verdict": verdict,
                    "relation": f.get("relation", ""),
                }
            )
    return {
        "mode": "oracle_truth_local",
        "oracle_meta": meta,
        "n_known": n_known,
        "n_novel": n_novel,
        "n_unknown": n_unknown,
        "verdicts": verdicts[:20],
    }


def _stage_audit(job: Job, work_dir: Path, stages: dict[str, Any]) -> dict[str, Any]:
    """阶段 6 证据链审计：汇总六阶段产物，输出可审计 JSON。"""
    _set_stage(job, "audit", "审计中：汇总证据链与调用记录", 0.95)
    retrieval = stages["retrieve"]
    papers_audit = [
        {
            "title": p.get("title", "")[:80],
            "doi": p.get("doi"),
            "source": p.get("source", "scibase"),
            "score": p.get("score"),
        }
        for p in retrieval.get("papers", [])
    ]
    return {
        "question": job.question,
        "domain": job.domain,
        "algo": job.algo,
        "llm_on": job.use_llm and llm_available(),
        "model": model_name() if (job.use_llm and llm_available()) else None,
        "n_papers": len(papers_audit),
        "papers": papers_audit[:15],
        "extract": stages["extract"],
        "gap": stages["gap"],
        "search": stages["search"],
        "verify": stages["verify"],
        "audit_trail": [{"stage": s, "ts": time.strftime("%H:%M:%S")} for s in STAGES],
    }


def _run_pipeline(job: Job) -> None:
    """六阶段流水线主入口（worker 线程执行）。"""
    try:
        with JOBS_LOCK:
            job.status = "running"
            job.updated_at = time.time()
        work_dir = JOBS_DIR / job.job_id
        work_dir.mkdir(parents=True, exist_ok=True)

        stages: dict[str, Any] = {}
        stages["retrieve"] = _stage_retrieve(job, work_dir)
        stages["extract"] = _stage_extract(job, work_dir, stages["retrieve"])
        stages["gap"] = _stage_gap(job, work_dir)
        stages["search"] = _stage_search(job, work_dir, stages["gap"])
        stages["verify"] = _stage_verify(job, work_dir, stages["search"])
        audit = _stage_audit(job, work_dir, stages)

        # 落盘完整产物
        (work_dir / "result.json").write_text(
            json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        _set_done(job, audit)
    except Exception as exc:  # 防御：任何阶段异常都不拖垮服务
        import traceback

        _set_failed(job, f"{exc}\n{traceback.format_exc()[-800:]}")


# ---------- HTTP 接口 ----------


@app.get("/api/health")
def health() -> dict[str, Any]:
    """健康检查（含环境状态）。"""
    return {
        "status": "ok",
        "llm_available": llm_available(),
        "model": model_name() if llm_available() else None,
        "index_ready": DEFAULT_INDEX_PATH.exists(),
        "oracle_ready": (
            len(list(ORACLE_DIR.glob("oracle_truth_*.json"))) > 0 if ORACLE_DIR.exists() else False
        ),
    }


@app.post("/api/run")
def run_pipeline(req: RunRequest) -> dict[str, Any]:
    """提交研究问题，启动六阶段流水线。"""
    question = req.question.strip()
    if not question:
        return {"error": "研究问题不能为空"}
    job = Job(
        job_id=uuid.uuid4().hex[:12],
        question=question,
        domain=req.domain,
        top_k=req.top_k,
        algo=req.algo,
        use_llm=req.use_llm,
    )
    with JOBS_LOCK:
        JOBS[job.job_id] = job

    def _worker() -> None:
        with _SEM:
            _run_pipeline(job)

    threading.Thread(target=_worker, daemon=True).start()
    return {"job_id": job.job_id, "status": job.status}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    """查询任务状态（前端轮询）。"""
    job = JOBS.get(job_id)
    if job is None:
        return {"error": "job 不存在"}
    return _job_dict(job)


@app.get("/api/jobs")
def list_jobs() -> dict[str, Any]:
    """任务列表（摘要，按创建时间倒序）。"""
    jobs = sorted(JOBS.values(), key=lambda j: j.created_at, reverse=True)
    return {
        "jobs": [
            {
                "job_id": j.job_id,
                "question": j.question,
                "status": j.status,
                "stage": j.stage,
                "progress": j.progress,
                "created_at": j.created_at,
            }
            for j in jobs[:20]
        ]
    }


def main() -> None:
    """直接运行（开发用）。"""
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
