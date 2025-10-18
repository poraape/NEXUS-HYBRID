"""Gerencial agent orchestrating the hybrid pipeline with async concurrency."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles

from agents.accountant_agent import accountant_agent, compute
from agents.auditor_agent import audit
from agents.classifier_agent import classify
from agents.ocr_agent import run_ocr
from core.logger import log_event
from core.settings import settings
from services.validator import enrich_with_xai


@dataclass(slots=True)
class StageLog:
    name: str
    status: str
    started_at: float
    finished_at: Optional[float] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        duration = None
        if self.finished_at is not None:
            duration = round(self.finished_at - self.started_at, 4)
        return {
            "stage": self.name,
            "status": self.status,
            "started_at": datetime.fromtimestamp(self.started_at, tz=timezone.utc).isoformat(),
            "finished_at": datetime.fromtimestamp(self.finished_at, tz=timezone.utc).isoformat()
            if self.finished_at
            else None,
            "duration": duration,
            "details": self.details,
        }


async def _export_logs(logs: List[Dict[str, Any]]) -> None:
    if not settings.EXPORT_PROCESSING_LOG:
        return
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "documents": logs,
    }
    path: Path = settings.processing_log_file
    async with aiofiles.open(path, "w", encoding="utf-8") as fp:
        await fp.write(json.dumps(payload, ensure_ascii=False, indent=2))


async def _process_single_document(doc: Dict[str, Any], semaphore: asyncio.Semaphore) -> Dict[str, Any]:
    async with semaphore:
        document_id = doc.get("id") or str(uuid.uuid4())
        log_event("manager", "INFO", "Iniciando processamento", {"document_id": document_id})
        doc_log: Dict[str, Any] = {
            "document_id": document_id,
            "name": doc.get("name"),
            "events": [],
        }

        def append_stage(stage: StageLog) -> None:
            entry = stage.to_dict()
            doc_log["events"].append(entry)
            log_event(
                "manager",
                "DEBUG",
                f"{stage.name}::{stage.status}",
                {"document_id": document_id, **(stage.details or {})},
            )

        semaphore_inner = asyncio.Semaphore(3)

        async def _run_stage(name: str, coro, details: Optional[Dict[str, Any]] = None):
            async with semaphore_inner:
                stage = StageLog(name=name, status="running", started_at=time.time(), details=details or {})
                try:
                    result = await coro
                    stage.status = "completed"
                    return result
                except Exception as exc:  # pragma: no cover - defensive
                    stage.status = "failed"
                    stage.details = {"error": str(exc), **(stage.details or {})}
                    raise
                finally:
                    stage.finished_at = time.time()
                    append_stage(stage)

        # Stage 1 - optional OCR
        if doc.get("kind") in {"PDF", "IMAGE"}:
            ocr_result = await _run_stage("ocr", run_ocr(doc))
            doc.setdefault("data", {})["text"] = (ocr_result or {}).get("text")
        else:
            append_stage(
                StageLog(
                    name="ocr",
                    status="skipped",
                    started_at=time.time(),
                    finished_at=time.time(),
                    details={"reason": "document-type"},
                )
            )

        data = doc.get("data") or {}
        data.setdefault("metadata", {})
        data["metadata"].setdefault("regime", doc.get("regime") or "simples_nacional")
        doc["data"] = data

        audit_task = asyncio.create_task(_run_stage("auditoria", audit(doc)))
        classifier_task = asyncio.create_task(_run_stage("classificacao", classify(doc)))
        accountant_task = asyncio.create_task(_run_stage("contabilidade", compute(doc)))

        audit_result, classifier_result, accountant_result = await asyncio.gather(
            audit_task, classifier_task, accountant_task
        )

        compliance = enrich_with_xai(
            audit_result,
            context={
                "segmento": classifier_result.get("ramo"),
                "regime": accountant_result.get("regime"),
            },
        )
        source_snapshot = {
            "emitente": data.get("emitente"),
            "destinatario": data.get("destinatario"),
            "itens": data.get("itens", []),
            "impostos": data.get("impostos", {}),
        }
        report = {
            "documentId": document_id,
            "title": f"Relatório - {doc.get('name', document_id)}",
            "kpis": [
                {"label": "Itens", "value": len(data.get("itens", []))},
                {
                    "label": "Score Conformidade",
                    "value": compliance.get("score", 0),
                },
                {
                    "label": "Valor Total",
                    "value": round(sum(float(i.get("valor", 0) or 0) for i in data.get("itens", [])), 2),
                },
            ],
            "classification": classifier_result,
            "taxes": accountant_result,
            "compliance": compliance,
            "logs": doc_log["events"],
            "source": source_snapshot,
        }
        log_event("manager", "INFO", "Processamento concluído", {"document_id": document_id})
        return {"report": report, "log": doc_log}


ASYNC_BATCH_SIZE = max(1, settings.MAX_CONCURRENT_TASKS)


async def process_documents_pipeline(docs: List[Dict[str, Any]]) -> Dict[str, Any]:
    semaphore = asyncio.Semaphore(ASYNC_BATCH_SIZE)
    results = await asyncio.gather(*[_process_single_document(doc, semaphore) for doc in docs])
    reports = [r["report"] for r in results]
    logs = [r["log"] for r in results]
    aggregated = accountant_agent(reports)
    await _export_logs(logs)
    return {"reports": reports, "logs": logs, "aggregated": aggregated}
