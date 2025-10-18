"""Utilities for inter-document fiscal comparisons."""
from __future__ import annotations

from typing import Any, Dict, List

FISCAL_KEYS = [
    "cfop",
    "cst",
    "ncm",
    "regime",
    "aliquota_icms",
    "aliquota_pis",
    "aliquota_cofins",
]

TOTAL_KEYS = ["vNF", "vProd", "vICMS", "vPIS", "vCOFINS"]


def _norm(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().upper()


def compare_docs(docs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compare normalized fiscal documents and highlight discrepancies."""
    discrepancies: List[Dict[str, Any]] = []
    summary: Dict[str, Dict[str, int]] = {
        "by_cfop": {},
        "by_ncm": {},
        "by_cst": {},
    }

    for doc in docs:
        cfop = _norm(doc.get("cfop"))
        ncm = _norm(doc.get("ncm"))
        cst = _norm(doc.get("cst"))

        summary["by_cfop"][cfop] = summary["by_cfop"].get(cfop, 0) + 1
        summary["by_ncm"][ncm] = summary["by_ncm"].get(ncm, 0) + 1
        summary["by_cst"][cst] = summary["by_cst"].get(cst, 0) + 1

    total_docs = len(docs)
    for i in range(total_docs):
        for j in range(i + 1, total_docs):
            a = docs[i]
            b = docs[j]
            diffs: Dict[str, Any] = {}

            for key in FISCAL_KEYS:
                aval = _norm(a.get(key))
                bval = _norm(b.get(key))
                if aval and bval and aval != bval:
                    diffs[key] = {"a": aval, "b": bval}

            for key in TOTAL_KEYS:
                aval = float(a.get(key) or 0.0)
                bval = float(b.get(key) or 0.0)
                if abs(aval - bval) > 1e-6:
                    diffs[key] = {"a": aval, "b": bval, "delta": bval - aval}

            if diffs:
                discrepancies.append(
                    {
                        "a_source": a.get("source"),
                        "b_source": b.get("source"),
                        "a_emitente": a.get("emitente"),
                        "b_emitente": b.get("emitente"),
                        "diffs": diffs,
                    }
                )

    insights: List[str] = []
    if any("cfop" in item["diffs"] for item in discrepancies):
        insights.append(
            "Divergências de CFOP detectadas entre documentos — revisar classificação operacional."
        )
    if any("cst" in item["diffs"] for item in discrepancies):
        insights.append(
            "CST conflitante entre documentos semelhantes — verificar regime e tributação aplicável."
        )
    if any("ncm" in item["diffs"] for item in discrepancies):
        insights.append(
            "NCM divergente para itens aparentados — investigar cadastro do produto."
        )

    return {
        "summary": summary,
        "discrepancies": discrepancies,
        "insights": insights,
    }
