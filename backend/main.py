import asyncio
import io
import json
import mimetypes
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from fastapi import Body, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from agents.accountant_agent import compute
from agents.auditor_agent import audit
from agents.classifier_agent import classify
from agents.intelligence_agent import generate_insights
from agents.manager import process_documents_pipeline
from agents.ocr_agent import run_ocr
from core.logger import log_event
from core.settings import settings
from backend.models import (
    AccountingOutput,
    AuditIssue,
    AuditReport,
    ClassificationResult,
    Document,
    DocumentIn,
    IntelligenceInsight,
    OrchestratorRequest,
    OrchestratorResult,
)
from services.export_docx import build_docx
from services.export_html import build_html
from services.export_pdf import build_pdf
from services.export_sped import build_sped_efd
from services.parsers import parse_any_files_from_zip, parse_file
from services.validator import enrich_with_xai
from utils.aggregator import merge_results
from utils.fiscal_compare import compare_docs
from utils.progress_stream import progress_manager

app = FastAPI(title="Nexus Python Backend", version="1.2")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ReportRequest(BaseModel):
    dataset: dict


class AutomationRequest(BaseModel):
    document: Document
    audit: AuditReport | None = None
    classification: ClassificationResult | None = None


class ConsultRequest(BaseModel):
    documents: List[Document] = Field(default_factory=list)
    audits: List[AuditReport] = Field(default_factory=list)
    classifications: List[ClassificationResult] = Field(default_factory=list)
    accounting: List[AccountingOutput] = Field(default_factory=list)

@app.get("/health")
async def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "max_upload_mb": settings.MAX_UPLOAD_MB,
        "version": app.version,
    }

async def _collect_docs_from_files(files: List[UploadFile]) -> List[Dict[str, Any]]:
    docs: List[Dict[str, Any]] = []
    for file in files:
        name = file.filename or "arquivo"
        content = await file.read()
        size_mb = len(content) / 1024 / 1024
        if size_mb > settings.MAX_UPLOAD_MB:
            raise HTTPException(413, f"{name} excede limite de {settings.MAX_UPLOAD_MB} MB")

        suffix = Path(name).suffix.lower()
        mime = file.content_type or mimetypes.guess_type(name)[0] or ""

        if suffix == ".zip" or mime in {"application/zip", "application/x-zip-compressed"}:
            log_event("upload", "INFO", f"Processando ZIP: {name} ({size_mb:.2f} MB)")
            docs.extend(parse_any_files_from_zip(content))
            continue

        if suffix and suffix not in settings.ALLOWED_EXTENSIONS:
            raise HTTPException(400, f"Extensão não suportada para {name}.")
        if mime and not any(mime.startswith(prefix) for prefix in settings.ALLOWED_MIME_PREFIXES):
            raise HTTPException(400, f"MIME type não autorizado para {name}.")

        doc = parse_file(name, content, mime)
        if doc.get("kind") == "UNKNOWN":
            continue
        docs.append(doc)

    if not docs:
        raise HTTPException(422, "Nenhum arquivo válido encontrado para processamento.")

    return docs


def _decode_document_input(payload: DocumentIn) -> Dict[str, Any]:
    try:
        content = payload.decode()
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    size_mb = len(content) / 1024 / 1024
    if size_mb > settings.MAX_UPLOAD_MB:
        raise HTTPException(413, f"Arquivo excede limite de {settings.MAX_UPLOAD_MB} MB")

    mime = payload.content_type or mimetypes.guess_type(payload.filename)[0] or ""
    doc = parse_file(payload.filename, content, mime)
    if doc.get("kind") == "UNKNOWN":
        raise HTTPException(422, "Arquivo não pôde ser processado.")
    return _ensure_document_defaults(doc)


def _ensure_document_defaults(doc: Dict[str, Any]) -> Dict[str, Any]:
    data = doc.setdefault("data", {})
    if isinstance(data, dict):
        data.setdefault("metadata", {})
    return doc


def _prepare_agent_document(document: Document) -> Dict[str, Any]:
    payload = document.dict_for_agent()
    return _ensure_document_defaults(payload)


async def _run_extractor(doc: Dict[str, Any]) -> Dict[str, Any]:
    if doc.get("kind") in {"PDF", "IMAGE"} and doc.get("raw"):
        ocr_result = await run_ocr(doc)
        if ocr_result:
            data = doc.setdefault("data", {})
            if isinstance(data, dict):
                data["text"] = (ocr_result or {}).get("text")
    return doc


@app.post("/upload", response_model=Document)
async def upload_document(payload: DocumentIn) -> Document:
    doc = await _run_extractor(_decode_document_input(payload))
    return Document.model_validate(doc)


@app.post("/validate", response_model=AuditReport)
async def validate_document(document: Document) -> AuditReport:
    agent_doc = _prepare_agent_document(document)
    compliance = await audit(agent_doc)
    context = {}
    data = agent_doc.get("data") or {}
    if isinstance(data, dict):
        metadata = data.get("metadata") or {}
        context = {
            "regime": metadata.get("regime"),
            "segmento": metadata.get("segmento"),
        }
    enriched = enrich_with_xai(compliance, context=context)
    issues = [AuditIssue.model_validate(issue) for issue in enriched.get("inconsistencies", [])]
    corrections = [
        f"Revisar {issue.field or 'campo'} ({issue.code})"
        for issue in issues
        if issue.severity.upper() in {"WARN", "ERROR"}
    ]
    return AuditReport(
        score=float(enriched.get("score") or 0),
        issues=issues,
        recommended_corrections=sorted(set(corrections)),
    )


@app.post("/classify", response_model=ClassificationResult)
async def classify_document(document: Document) -> ClassificationResult:
    agent_doc = _prepare_agent_document(document)
    result = await classify(agent_doc)
    return ClassificationResult.model_validate(result)


@app.post("/automate", response_model=AccountingOutput)
async def automate_document(payload: AutomationRequest) -> AccountingOutput:
    agent_doc = _prepare_agent_document(payload.document)
    result = await compute(agent_doc)
    return AccountingOutput.model_validate(result)


@app.post("/consult", response_model=IntelligenceInsight)
async def consult_insights(payload: ConsultRequest) -> IntelligenceInsight:
    reports: List[Dict[str, Any]] = []
    for index, document in enumerate(payload.documents):
        base = _prepare_agent_document(document)
        report: Dict[str, Any] = {
            "documentId": base.get("id") or base.get("name"),
            "title": base.get("name"),
            "source": base.get("data"),
        }
        if index < len(payload.audits):
            audit_report = payload.audits[index]
            report["compliance"] = {
                "score": audit_report.score,
                "inconsistencies": [
                    issue.model_dump(mode="python", exclude_none=True) for issue in audit_report.issues
                ],
            }
        if index < len(payload.classifications):
            report["classification"] = payload.classifications[index].model_dump(
                mode="python", exclude_none=True
            )
        if index < len(payload.accounting):
            report["taxes"] = payload.accounting[index].model_dump(mode="python", exclude_none=True)
        reports.append(report)

    aggregated_totals: Dict[str, float] = {}
    for accounting in payload.accounting:
        for key, value in accounting.resumo.items():
            try:
                aggregated_totals[key] = aggregated_totals.get(key, 0.0) + float(value)
            except (TypeError, ValueError):  # pragma: no cover - resilience
                continue

    aggregated_payload = {"totals": aggregated_totals}
    audit_payloads = [audit.model_dump(mode="python", exclude_none=True) for audit in payload.audits]
    return await generate_insights(reports, aggregated=aggregated_payload, audits=audit_payloads)


@app.post("/orchestrate", response_model=OrchestratorResult)
async def orchestrate(payload: OrchestratorRequest) -> OrchestratorResult:
    docs: List[Dict[str, Any]] = []
    for entry in payload.documents:
        if entry.upload is not None:
            docs.append(await _run_extractor(_decode_document_input(entry.upload)))
            continue
        assert entry.document is not None
        doc = _prepare_agent_document(entry.document)
        if doc.get("kind") in {"PDF", "IMAGE"} and not doc.get("raw"):
            doc["kind"] = f"{doc['kind']}_STRUCTURED"
        docs.append(doc)

    if payload.async_mode:
        job_id = str(uuid.uuid4())
        await progress_manager.create_job(job_id)
        asyncio.create_task(_run_pipeline_job(job_id, docs))
        return OrchestratorResult(status="accepted", job_id=job_id, reports=[], aggregated={})

    result = await process_documents_pipeline(docs)
    insight = await generate_insights(result.get("reports", []), aggregated=result.get("aggregated"))
    return OrchestratorResult(
        status="completed",
        reports=result.get("reports", []),
        aggregated=result.get("aggregated", {}),
        insight=insight,
    )


@app.post("/upload/zip")
async def upload_zip(file: UploadFile = File(...)):
    name = file.filename or "upload.zip"
    content = await file.read()
    size_mb = len(content)/1024/1024
    if size_mb > settings.MAX_UPLOAD_MB:
        raise HTTPException(413, f"Arquivo excede limite de {settings.MAX_UPLOAD_MB} MB")
    mt = mimetypes.guess_type(name)[0] or "application/octet-stream"
    if not (name.lower().endswith(".zip") or mt in ("application/zip","application/x-zip-compressed")):
        raise HTTPException(400, "Apenas .zip permitido neste endpoint.")
    log_event("upload", "INFO", f"ZIP recebido: {name} ({size_mb:.2f} MB)")
    docs = parse_any_files_from_zip(content)
    if not docs:
        raise HTTPException(422, "Nenhum arquivo válido encontrado no ZIP.")
    result = await process_documents_pipeline(docs)
    return JSONResponse(result)

@app.post("/upload/file")
async def upload_file(file: UploadFile = File(...)):
    content = await file.read()
    size_mb = len(content)/1024/1024
    if size_mb > settings.MAX_UPLOAD_MB:
        raise HTTPException(413, f"Arquivo excede limite de {settings.MAX_UPLOAD_MB} MB")
    suffix = Path(file.filename or "").suffix.lower()
    mime = file.content_type or ""
    if suffix and suffix not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(400, "Extensão não suportada para processamento.")
    if mime and not any(mime.startswith(prefix) for prefix in settings.ALLOWED_MIME_PREFIXES):
        raise HTTPException(400, "MIME type não autorizado.")
    doc = parse_file(file.filename, content, mime)
    result = await process_documents_pipeline([doc])
    return JSONResponse(result)


@app.post("/upload/multiple")
async def upload_multiple(files: List[UploadFile] = File(...)):
    if not files:
        raise HTTPException(400, "Nenhum arquivo enviado.")

    docs = await _collect_docs_from_files(files)

    result = await process_documents_pipeline(docs)
    aggregated = merge_results(result.get("reports", []))
    return JSONResponse({**result, "aggregated": aggregated})


@app.post("/compare-incremental")
async def compare_incremental(payload: Dict[str, Dict[str, Dict[str, float]]]):
    previous = (payload or {}).get("previous") or {}
    current = (payload or {}).get("current") or {}

    previous_totals = previous.get("totals") or {}
    current_totals = current.get("totals") or {}

    keys = set(current_totals) | set(previous_totals)
    differences = {
        key: float(current_totals.get(key) or 0) - float(previous_totals.get(key) or 0)
        for key in keys
    }

    return JSONResponse(content={"differences": differences})


@app.post("/interdoc/compare")
async def interdoc_compare(payload: Dict[str, Any] = Body(...)):
    docs = (payload or {}).get("docs") or []
    result = compare_docs(docs)
    return JSONResponse(content={"status": "ok", "result": result})


@app.post("/export/docx")
async def export_docx(payload: ReportRequest):
    buf, filename = build_docx(payload.dataset)
    return StreamingResponse(io.BytesIO(buf), media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                             headers={"Content-Disposition": f"attachment; filename={filename}"})

@app.post("/export/pdf")
async def export_pdf(payload: ReportRequest):
    buf, filename = build_pdf(payload.dataset)
    return StreamingResponse(io.BytesIO(buf), media_type="application/pdf",
                             headers={"Content-Disposition": f"attachment; filename={filename}"})

@app.post("/export/html")
async def export_html(payload: ReportRequest):
    html, filename = build_html(payload.dataset)
    return StreamingResponse(io.BytesIO(html.encode("utf-8")), media_type="text/html",
                             headers={"Content-Disposition": f"attachment; filename={filename}"})

@app.post("/export/sped")
async def export_sped(payload: ReportRequest):
    buf, filename = build_sped_efd(payload.dataset)
    return StreamingResponse(io.BytesIO(buf), media_type="text/plain",
                             headers={"Content-Disposition": f"attachment; filename={filename}"})


async def _run_pipeline_job(job_id: str, docs: List[Dict[str, Any]]) -> None:
    async def _callback(event: Dict[str, Any]) -> None:
        await progress_manager.publish(job_id, event)

    await progress_manager.publish(
        job_id,
        {
            "type": "job",
            "job_id": job_id,
            "status": "started",
            "total_documents": len(docs),
        },
    )

    try:
        result = await process_documents_pipeline(
            docs,
            progress_callback=_callback,
            job_id=job_id,
        )
        payload = {"status": "completed", **result}
        await progress_manager.publish(
            job_id,
            {
                "type": "job",
                "job_id": job_id,
                "status": "completed",
                "result": payload,
            },
        )
        progress_manager.set_result(job_id, payload)
    except Exception as exc:  # pragma: no cover - defensive
        log_event("pipeline", "ERROR", "Job falhou", {"job_id": job_id, "error": str(exc)})
        await progress_manager.publish(
            job_id,
            {
                "type": "job",
                "job_id": job_id,
                "status": "failed",
                "error": str(exc),
            },
        )
        progress_manager.set_result(job_id, {"status": "failed", "error": str(exc)})
    finally:
        await progress_manager.finalize(job_id)


@app.post("/pipeline/jobs")
async def create_pipeline_job(files: List[UploadFile] = File(...)):
    if not files:
        raise HTTPException(400, "Nenhum arquivo enviado.")

    docs = await _collect_docs_from_files(files)
    job_id = str(uuid.uuid4())
    await progress_manager.create_job(job_id)
    asyncio.create_task(_run_pipeline_job(job_id, docs))
    return JSONResponse({"job_id": job_id})


@app.get("/pipeline/jobs/{job_id}")
async def get_pipeline_job(job_id: str):
    result = progress_manager.get_result(job_id)
    if result is None:
        raise HTTPException(404, "Resultado ainda não disponível ou job inexistente.")
    return JSONResponse(result)


@app.get("/pipeline/jobs/{job_id}/stream")
async def stream_pipeline_job(job_id: str):
    queue = await progress_manager.subscribe(job_id)
    if queue is None:
        raise HTTPException(404, "Job inexistente.")

    async def event_generator():
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        finally:
            await progress_manager.discard(job_id, queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
