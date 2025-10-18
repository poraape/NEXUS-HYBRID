"""Fiscal classifier powered by spaCy with persistent feedback."""

from __future__ import annotations

import asyncio
import hashlib
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

import spacy
from spacy.pipeline import EntityRuler

from core.logger import log_event
from core.settings import settings

CFOP_OPERATION_MAP = {
    "1101": "Compra",
    "1102": "Compra",
    "2101": "Compra",
    "2102": "Compra",
    "5101": "Venda",
    "5102": "Venda",
    "6101": "Venda",
    "6102": "Venda",
    "1202": "Devolução",
    "2202": "Devolução",
    "5201": "Remessa",
    "6201": "Remessa",
}

NCM_BRANCHES = {
    "85": "Tecnologia da Informação",
    "30": "Saúde/Farma",
    "21": "Saúde/Farma",
    "02": "Alimentos",
    "16": "Alimentos",
}

try:  # pragma: no cover - loading external model can fail in CI
    NLP = spacy.load("pt_core_news_sm")
except Exception:  # fallback to simple rule-based pipeline
    NLP = spacy.blank("pt")
    ruler = NLP.add_pipe("entity_ruler", config={"validate": True})
    ruler.add_patterns(
        [
            {"label": "CFOP", "pattern": "CFOP"},
            {"label": "NCM", "pattern": "NCM"},
            {"label": "CST", "pattern": "CST"},
            {"label": "EMITENTE", "pattern": "emitente"},
            {"label": "DESTINATARIO", "pattern": "destinatário"},
        ]
    )
else:
    if "entity_ruler" not in NLP.pipe_names:
        ruler = NLP.add_pipe("entity_ruler")
        ruler.add_patterns(
            [
                {"label": "CFOP", "pattern": "CFOP"},
                {"label": "NCM", "pattern": "NCM"},
                {"label": "CST", "pattern": "CST"},
                {"label": "EMITENTE", "pattern": "emitente"},
                {"label": "DESTINATARIO", "pattern": "destinatário"},
            ]
        )


class FeedbackRepository:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._ensure()

    def _ensure(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS classification_feedback (
                    doc_hash TEXT PRIMARY KEY,
                    tipo TEXT,
                    ramo TEXT,
                    confidence REAL,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _hash(self, key: str) -> str:
        return hashlib.sha256(key.encode("utf-8")).hexdigest()

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        doc_hash = self._hash(key)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT tipo, ramo, confidence FROM classification_feedback WHERE doc_hash = ?",
                (doc_hash,),
            ).fetchone()
            if not row:
                return None
            return {"tipo": row["tipo"], "ramo": row["ramo"], "confidence": row["confidence"]}

    def save(self, key: str, tipo: str, ramo: str, confidence: float) -> None:
        doc_hash = self._hash(key)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO classification_feedback (doc_hash, tipo, ramo, confidence)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(doc_hash) DO UPDATE SET
                    tipo = excluded.tipo,
                    ramo = excluded.ramo,
                    confidence = excluded.confidence,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (doc_hash, tipo, ramo, confidence),
            )


REPOSITORY = FeedbackRepository(settings.DB_PATH)


def _build_context(doc: Dict[str, Any]) -> Tuple[str, str, str, str]:
    data = doc.get("data") or {}
    emitente = (data.get("emitente") or {}).get("nome") or ""
    destinatario = (data.get("destinatario") or {}).get("nome") or ""
    cfop = ""
    cst = ""
    ncm = ""
    for item in data.get("itens", []):
        if not cfop:
            cfop = str(item.get("cfop") or "").replace(".", "")
        if not cst:
            cst = str(item.get("cst") or item.get("cst_icms") or item.get("cstIcms") or "")
        if not ncm:
            ncm = str(item.get("ncm") or "")
    return emitente, destinatario, cfop, ncm


def _branch_from_ncm(ncm: str) -> str:
    if not ncm:
        return "Indefinido"
    prefix = ncm[:2]
    return NCM_BRANCHES.get(prefix, "Geral")


def _operation_from_cfop(cfop: str) -> str:
    if not cfop:
        return "Operação"
    return CFOP_OPERATION_MAP.get(cfop, "Operação")


def _document_key(doc: Dict[str, Any], emitente: str, destinatario: str) -> str:
    base = doc.get("name") or "documento"
    return f"{emitente}|{destinatario}|{base}"


def _predict_entities(text: str) -> Dict[str, str]:
    doc = NLP(text)
    result: Dict[str, str] = {}
    for ent in doc.ents:
        result[ent.label_] = ent.text
    return result


def _confidence(items: Iterable[Any], overrides: bool) -> float:
    base = 0.75 + min(len(list(items)), 5) * 0.02
    return min(0.99 if overrides else base, 0.99)


def _classify_sync(doc: Dict[str, Any]) -> Dict[str, Any]:
    emitente, destinatario, cfop, ncm = _build_context(doc)
    raw_text_segments = []
    if emitente:
        raw_text_segments.append(f"Emitente: {emitente}")
    if destinatario:
        raw_text_segments.append(f"Destinatário: {destinatario}")
    itens = (doc.get("data") or {}).get("itens", [])
    for item in itens:
        raw_text_segments.append(
            f"Produto {item.get('descricao', '')} CFOP {item.get('cfop', '')} NCM {item.get('ncm', '')} CST {item.get('cst', '')}"
        )
    text = "\n".join(raw_text_segments)
    entities = _predict_entities(text)
    cfop = cfop or entities.get("CFOP", "").strip()
    ncm = ncm or entities.get("NCM", "").strip()
    ramo = _branch_from_ncm(ncm)
    tipo = _operation_from_cfop(cfop)
    overrides = False
    key = _document_key(doc, emitente, destinatario)
    stored = REPOSITORY.get(key)
    if stored:
        tipo = stored["tipo"]
        ramo = stored["ramo"]
        overrides = True
    feedback_payload = (doc.get("feedback") or {}).get("classification")
    if feedback_payload:
        tipo = feedback_payload.get("tipo", tipo)
        ramo = feedback_payload.get("ramo", ramo)
        overrides = True
        REPOSITORY.save(key, tipo, ramo, 0.99)
        log_event("classifier", "INFO", "Feedback de classificação aplicado", {"document": key})
    confidence = _confidence(itens, overrides)
    result = {
        "emitente": emitente or entities.get("EMITENTE", ""),
        "destinatario": destinatario or entities.get("DESTINATARIO", ""),
        "cfop": cfop,
        "ncm": ncm,
        "tipo": tipo,
        "ramo": ramo,
        "confidence": confidence,
    }
    if not stored and not feedback_payload:
        REPOSITORY.save(key, tipo, ramo, confidence)
    return result


async def classify(doc: Dict[str, Any]) -> Dict[str, Any]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _classify_sync, doc)
