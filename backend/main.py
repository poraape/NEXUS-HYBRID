import asyncio
import io
import json
import mimetypes
import uuid
from pathlib import Path

from fastapi import Body, FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from typing import Any, Dict, List
from core.settings import settings
from core.logger import log_event
from services.parsers import parse_any_files_from_zip, parse_file
from utils.aggregator import merge_results
from utils.fiscal_compare import compare_docs
from agents.manager import process_documents_pipeline
from services.export_docx import build_docx
from services.export_pdf import build_pdf
from services.export_html import build_html
from services.export_sped import build_sped_efd
from utils.progress_stream import progress_manager

app = FastAPI(title="Nexus Python Backend", version="1.1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ReportRequest(BaseModel):
    dataset: dict

@app.get("/health")
async def health():
    return {"status":"ok","ts":"2025-10-18T11:13:15.030344","max_upload_mb": settings.MAX_UPLOAD_MB}

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
