"""Deterministic intelligence agent providing managerial insights."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from statistics import mean
from typing import Any, Dict, Iterable, List

from backend.models import IntelligenceInsight


def _collect_scores(reports: Iterable[Dict[str, Any]]) -> List[float]:
    scores: List[float] = []
    for report in reports:
        compliance = report.get("compliance") or {}
        value = compliance.get("score")
        if value is None:
            continue
        try:
            scores.append(float(value))
        except (TypeError, ValueError):  # pragma: no cover - defensive
            continue
    return scores


def _collect_sectors(reports: Iterable[Dict[str, Any]]) -> Counter:
    sectors: Counter[str] = Counter()
    for report in reports:
        classification = report.get("classification") or {}
        ramo = classification.get("ramo")
        if ramo:
            sectors[ramo] += 1
    return sectors


def _collect_totals(aggregated: Dict[str, Any] | None) -> Dict[str, float]:
    if not aggregated:
        return {}
    totals = aggregated.get("totals") or {}
    output: Dict[str, float] = {}
    for key, value in totals.items():
        try:
            output[key] = float(value)
        except (TypeError, ValueError):  # pragma: no cover - resilience
            continue
    return output


async def generate_insights(
    reports: Iterable[Dict[str, Any]],
    aggregated: Dict[str, Any] | None = None,
    audits: Iterable[Dict[str, Any]] | None = None,
) -> IntelligenceInsight:
    reports_list = list(reports)
    audits = list(audits or [])
    total_docs = len(reports_list)

    summaries: List[str] = []
    if total_docs:
        summaries.append(f"{total_docs} documento(s) processado(s) até {datetime.now(timezone.utc).date().isoformat()}.")
    else:
        summaries.append("Nenhum documento disponível para análise.")

    scores = _collect_scores(reports_list)
    if scores:
        summaries.append(f"Score médio de conformidade: {mean(scores):.2f} (quanto menor, melhor).")

    sectors = _collect_sectors(reports_list)
    if sectors:
        top_sector, occurrences = sectors.most_common(1)[0]
        summaries.append(f"Segmento predominante: {top_sector} ({occurrences} documento(s)).")

    totals = _collect_totals(aggregated)

    kpis: Dict[str, float] = {
        "documents": float(total_docs),
    }
    kpis.update(totals)
    if scores:
        kpis["avgComplianceScore"] = float(mean(scores))

    recommendations: List[str] = []
    blocking = [
        issue
        for report in reports_list
        for issue in (report.get("compliance") or {}).get("inconsistencies", [])
        if (issue or {}).get("severity") == "ERROR"
    ]
    if blocking:
        recommendations.append(
            "Revise inconsistências críticas antes do fechamento fiscal (" f"{len(blocking)} ocorrência(s))."
        )
    if totals.get("vICMS", 0) > 10000:
        recommendations.append("Considere planejamento tributário para reduzir o impacto de ICMS.")
    if not recommendations:
        recommendations.append("Cenário controlado: mantenha as rotinas de conferência atuais.")

    if audits:
        severities = Counter((issue.get("severity") for audit in audits for issue in audit.get("issues", [])))
        if severities.get("ERROR"):
            recommendations.append(
                f"Auditoria identificou {severities['ERROR']} inconsistência(s) crítica(s); priorize correção imediata."
            )

    return IntelligenceInsight(
        summaries=summaries,
        kpis=kpis,
        recommendations=recommendations,
        scenario_simulations=[],
    )

