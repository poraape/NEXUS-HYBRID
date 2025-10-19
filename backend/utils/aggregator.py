from __future__ import annotations

from typing import Any, Dict, Iterable, List


def _to_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return 0.0


def merge_results(reports: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    docs: List[Dict[str, Any]] = []
    totals = {"vNF": 0.0, "vProd": 0.0, "vICMS": 0.0, "vPIS": 0.0, "vCOFINS": 0.0}

    for report in reports:
        source = report.get("source") or {}
        itens = source.get("itens") or []
        valor_produtos = sum(_to_float(item.get("valor")) for item in itens)
        totals["vProd"] += valor_produtos
        totals["vNF"] += valor_produtos

        taxes_resumo = ((report.get("taxes") or {}).get("resumo") or {})
        totals["vICMS"] += _to_float(taxes_resumo.get("totalICMS"))
        totals["vPIS"] += _to_float(taxes_resumo.get("totalPIS"))
        totals["vCOFINS"] += _to_float(taxes_resumo.get("totalCOFINS"))

        docs.append(
            {
                "documentId": report.get("documentId"),
                "title": report.get("title"),
                "valorProdutos": valor_produtos,
                "score": (report.get("compliance") or {}).get("score"),
            }
        )

    return {"docs": docs, "totals": totals}
