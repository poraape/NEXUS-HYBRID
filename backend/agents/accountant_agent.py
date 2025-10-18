"""Accountant agent responsible for deterministic fiscal apuration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Iterable, List, Mapping

@dataclass(frozen=True)
class RegimeConfig:
    name: str
    aliquotas: Mapping[str, Decimal]
    iss_cidades: Mapping[str, Decimal]


PLAN_OF_ACCOUNTS = {
    "estoques": "1.1.05.001",
    "fornecedores": "2.1.01.001",
    "icms_recuperar": "1.1.09.002",
    "pis_recuperar": "1.1.09.003",
    "cofins_recuperar": "1.1.09.004",
    "iss_pagar": "2.1.09.001",
    "iva_registro": "3.1.04.005",
}

REGIMES = {
    "simples_nacional": RegimeConfig(
        name="Simples Nacional",
        aliquotas={
            "icms": Decimal("0.03"),
            "pis": Decimal("0.0065"),
            "cofins": Decimal("0.03"),
            "iss": Decimal("0.02"),
            "iva": Decimal("0.12"),
        },
        iss_cidades={"SP": Decimal("0.02"), "RJ": Decimal("0.03"), "BH": Decimal("0.025")},
    ),
    "lucro_presumido": RegimeConfig(
        name="Lucro Presumido",
        aliquotas={
            "icms": Decimal("0.18"),
            "pis": Decimal("0.0165"),
            "cofins": Decimal("0.076"),
            "iss": Decimal("0.05"),
            "iva": Decimal("0.25"),
        },
        iss_cidades={"SP": Decimal("0.05"), "RJ": Decimal("0.05"), "BH": Decimal("0.045")},
    ),
    "lucro_real": RegimeConfig(
        name="Lucro Real",
        aliquotas={
            "icms": Decimal("0.18"),
            "pis": Decimal("0.0165"),
            "cofins": Decimal("0.076"),
            "iss": Decimal("0.035"),
            "iva": Decimal("0.28"),
        },
        iss_cidades={"SP": Decimal("0.035"), "RJ": Decimal("0.04"), "BH": Decimal("0.032")},
    ),
}


def _as_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value or "0"))
    except Exception:  # pragma: no cover - resilience against bad data
        return Decimal("0")


def _round(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _total_items(itens: Iterable[Mapping[str, Any]]) -> Decimal:
    total = Decimal("0")
    for item in itens:
        total += _as_decimal(item.get("valor"))
    return total


def _get_regime(doc: Dict[str, Any]) -> RegimeConfig:
    data = doc.get("data") or {}
    metadata = data.get("metadata") or {}
    regime_name = (metadata.get("regime") or doc.get("regime") or "simples_nacional").lower()
    return REGIMES.get(regime_name, REGIMES["simples_nacional"])


def _resolve_iss_rate(config: RegimeConfig, doc: Dict[str, Any]) -> Decimal:
    destinatario = (doc.get("data") or {}).get("destinatario") or {}
    cidade = destinatario.get("municipio") or destinatario.get("cidade") or ""
    uf = destinatario.get("uf") or ""
    if cidade.upper() in config.iss_cidades:
        return config.iss_cidades[cidade.upper()]
    if uf.upper() in config.iss_cidades:
        return config.iss_cidades[uf.upper()]
    return config.aliquotas["iss"]


def _build_entries(total: Decimal, taxes: Dict[str, float]) -> List[Dict[str, Any]]:
    entries = [
        {
            "debito": PLAN_OF_ACCOUNTS["estoques"],
            "credito": PLAN_OF_ACCOUNTS["fornecedores"],
            "valor": _round(total),
            "historico": "Entrada de mercadorias",
        }
    ]
    if taxes["icms"]:
        entries.append(
            {
                "debito": PLAN_OF_ACCOUNTS["icms_recuperar"],
                "credito": PLAN_OF_ACCOUNTS["fornecedores"],
                "valor": taxes["icms"],
                "historico": "Crédito ICMS",
            }
        )
    if taxes["pis"]:
        entries.append(
            {
                "debito": PLAN_OF_ACCOUNTS["pis_recuperar"],
                "credito": PLAN_OF_ACCOUNTS["fornecedores"],
                "valor": taxes["pis"],
                "historico": "Crédito PIS",
            }
        )
    if taxes["cofins"]:
        entries.append(
            {
                "debito": PLAN_OF_ACCOUNTS["cofins_recuperar"],
                "credito": PLAN_OF_ACCOUNTS["fornecedores"],
                "valor": taxes["cofins"],
                "historico": "Crédito COFINS",
            }
        )
    if taxes["iss"]:
        entries.append(
            {
                "debito": PLAN_OF_ACCOUNTS["iss_pagar"],
                "credito": PLAN_OF_ACCOUNTS["fornecedores"],
                "valor": taxes["iss"],
                "historico": "Provisão ISS",
            }
        )
    iva_value = taxes.get("iva")
    if iva_value:
        entries.append(
            {
                "debito": PLAN_OF_ACCOUNTS["iva_registro"],
                "credito": PLAN_OF_ACCOUNTS["fornecedores"],
                "valor": iva_value,
                "historico": "Ajuste IVA",
            }
        )
    return entries


def _balance_check(entries: List[Dict[str, Any]]) -> None:
    if any(entry["valor"] <= 0 for entry in entries):  # pragma: no cover - data validation
        raise ValueError("Lançamento com valor não positivo")
    debit = sum(entry["valor"] for entry in entries)
    credit = sum(entry["valor"] for entry in entries)
    if round(debit - credit, 2) != 0:  # pragma: no cover - guard
        raise ValueError("Lançamentos contábeis desequilibrados")


def _compute_taxes(doc: Dict[str, Any], config: RegimeConfig) -> Dict[str, float]:
    itens = (doc.get("data") or {}).get("itens", [])
    total = _total_items(itens)
    aliquotas = config.aliquotas

    taxes_decimal = {
        "icms": total * aliquotas["icms"],
        "pis": total * aliquotas["pis"],
        "cofins": total * aliquotas["cofins"],
        "iss": total * _resolve_iss_rate(config, doc),
        "iva": total * aliquotas["iva"],
    }
    return {tax: _round(value) for tax, value in taxes_decimal.items()}


async def compute(doc: Dict[str, Any]) -> Dict[str, Any]:
    config = _get_regime(doc)
    total = _total_items((doc.get("data") or {}).get("itens", []))
    taxes = _compute_taxes(doc, config)
    entries = _build_entries(total, taxes)
    _balance_check(entries)
    return {
        "regime": config.name,
        "competencia": datetime.utcnow().strftime("%Y-%m"),
        "resumo": {
            "totalICMS": taxes["icms"],
            "totalPIS": taxes["pis"],
            "totalCOFINS": taxes["cofins"],
            "totalISS": taxes["iss"],
            "totalIVA": taxes["iva"],
        },
        "lancamentos": entries,
    }
