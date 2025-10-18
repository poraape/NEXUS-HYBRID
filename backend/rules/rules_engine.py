"""Rule engine responsible for fiscal auditing and tax validation."""

from __future__ import annotations

import json
import re
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List

RULES_PATH = Path(__file__).with_name("rules_dictionary.json")
with RULES_PATH.open("r", encoding="utf-8") as handler:
    RULES = json.load(handler)

RULE_INDEX = {rule["code"]: rule for rule in RULES.get("rules", [])}
CFOP_SET = set(RULES.get("cfop_valid", []))
CST_MATRIX = {cfop: set(values) for cfop, values in RULES.get("cst_matrix", {}).items()}
TAX_EXPECTATIONS = {k: {tax: Decimal(str(v)) for tax, v in cfg.items()} for k, cfg in RULES.get("tax_expectations", {}).items()}
SEGMENT_MARKUP = {
    segment: {k: Decimal(str(v)) for k, v in ranges.items()} for segment, ranges in RULES.get("segments_markup", {}).items()
}
ST_SENSITIVE_CFOP = set(RULES.get("st_sensitive_cfop", []))
SEVERITY_WEIGHTS = RULES.get("severity_weights", {"ERROR": 3, "WARN": 1, "INFO": 0})
NCM_RE = re.compile(r"^\d{8}$")


def _make_inconsistency(code: str, details: Dict[str, Any] | None = None) -> Dict[str, Any]:
    rule = RULE_INDEX.get(code, {})
    payload = {
        "code": code,
        "field": rule.get("field", "unknown"),
        "severity": rule.get("severity", "INFO"),
        "message": rule.get("message", "Regra de auditoria"),
        "normative_base": rule.get("normative_base"),
    }
    if details:
        payload["details"] = details
    return payload


def _as_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0"))
    except Exception:  # pragma: no cover
        return Decimal("0")


def _infer_segment(doc: Dict[str, Any]) -> str:
    itens = (doc.get("itens") or [])
    for item in itens:
        ncm = str(item.get("ncm") or "")
        if ncm.startswith("85"):
            return "Tecnologia da Informação"
        if ncm.startswith("30") or ncm.startswith("21"):
            return "Saúde/Farma"
        if ncm.startswith("02") or ncm.startswith("16"):
            return "Alimentos"
    return "Geral"


def _validate_cfop(item: Dict[str, Any], inconsistencies: List[Dict[str, Any]]) -> None:
    cfop = str(item.get("cfop") or "").replace(".", "")
    if cfop and cfop not in CFOP_SET:
        inconsistencies.append(_make_inconsistency("CFOP_VALID", {"value": cfop}))
    cst = str(item.get("cst") or item.get("cstIcms") or item.get("cst_icms") or "")
    if cfop in CST_MATRIX and cst and cst not in CST_MATRIX[cfop]:
        inconsistencies.append(_make_inconsistency("CST_COMPATIBILITY", {"cfop": cfop, "cst": cst}))
    ncm = str(item.get("ncm") or "")
    if ncm and not NCM_RE.match(ncm):
        inconsistencies.append(_make_inconsistency("NCM_FORMAT", {"value": ncm}))


def _validate_substitution(item: Dict[str, Any], inconsistencies: List[Dict[str, Any]]) -> None:
    cfop = str(item.get("cfop") or "")
    if cfop in ST_SENSITIVE_CFOP:
        inconsistencies.append(_make_inconsistency("ST_REQUIREMENT", {"cfop": cfop}))


def _validate_taxes(doc: Dict[str, Any], inconsistencies: List[Dict[str, Any]]) -> None:
    itens = doc.get("itens") or []
    total = sum(_as_decimal(i.get("valor")) for i in itens)
    regime = (doc.get("metadata") or {}).get("regime", "simples_nacional").lower()
    expectations = TAX_EXPECTATIONS.get(regime, TAX_EXPECTATIONS["simples_nacional"])
    impostos = doc.get("impostos") or {}
    segment = _infer_segment(doc)

    def _check_tax(code: str, expected_rate: Decimal, actual_value: Any) -> None:
        expected = total * expected_rate
        actual = _as_decimal(actual_value)
        tolerance = expected * Decimal("0.05")
        if actual == 0 and expected == 0:
            return
        if (actual - expected).copy_abs() > tolerance:
            inconsistencies.append(
                _make_inconsistency(
                    code,
                    {
                        "expected": float(expected),
                        "actual": float(actual),
                        "tolerance": float(tolerance),
                        "regime": regime,
                    },
                )
            )

    _check_tax("ICMS_BASE_CALC", expectations.get("icms", Decimal("0")), impostos.get("icms"))
    _check_tax("PIS_BASE_CALC", expectations.get("pis", Decimal("0")), impostos.get("pis"))
    _check_tax("COFINS_BASE_CALC", expectations.get("cofins", Decimal("0")), impostos.get("cofins"))
    iss_min = expectations.get("iss_min", Decimal("0"))
    iss_max = expectations.get("iss_max", Decimal("0"))
    iss_value = _as_decimal(impostos.get("iss"))
    expected_iss_min = total * iss_min
    expected_iss_max = total * iss_max
    if iss_value and not (expected_iss_min <= iss_value <= expected_iss_max):
        inconsistencies.append(
            _make_inconsistency(
                "ISS_BASE_CALC",
                {
                    "expected_range": [float(expected_iss_min), float(expected_iss_max)],
                    "actual": float(iss_value),
                    "municipio": (doc.get("destinatario") or {}).get("municipio"),
                },
            )
        )
    iva_expected_rate = expectations.get("iva", Decimal("0"))
    iva_value = _as_decimal(impostos.get("iva"))
    markup_config = SEGMENT_MARKUP.get(segment, SEGMENT_MARKUP["Geral"])
    min_markup = total * markup_config["min"]
    max_markup = total * markup_config["max"]
    if iva_value and not (min_markup <= iva_value <= max_markup):
        inconsistencies.append(
            _make_inconsistency(
                "IVA_MARKUP",
                {
                    "segment": segment,
                    "expected_range": [float(min_markup), float(max_markup)],
                    "actual": float(iva_value),
                },
            )
        )


def audit_document(doc: Dict[str, Any]) -> Dict[str, Any]:
    inconsistencies: List[Dict[str, Any]] = []
    itens = doc.get("itens") or []
    for item in itens:
        _validate_cfop(item, inconsistencies)
        _validate_substitution(item, inconsistencies)
        if _as_decimal(item.get("valor")) < 0:
            inconsistencies.append(_make_inconsistency("ITEM_VALOR_NEGATIVO", {"valor": item.get("valor")}))
    _validate_taxes(doc, inconsistencies)
    score = sum(SEVERITY_WEIGHTS.get(inc.get("severity", "INFO"), 0) for inc in inconsistencies)
    return {"inconsistencies": inconsistencies, "score": score}


def validate_tax_rules(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Public helper to validate taxes directly."""
    return audit_document(doc)
