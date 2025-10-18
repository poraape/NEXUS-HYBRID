"""SPED/EFD export with XMLSchema validation."""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Iterable
from xml.etree.ElementTree import Element, SubElement, tostring

from xmlschema import XMLSchema

from core.settings import settings

SCHEMA_PATH = Path(__file__).with_name("schemas").joinpath("sped_efd_schema.xsd")
SCHEMA = XMLSchema(str(SCHEMA_PATH))


def _append_kpis(parent: Element, kpis: Iterable[Dict[str, str]]) -> None:
    if not kpis:
        return
    kpi_root = SubElement(parent, "KPIs")
    for kpi in kpis:
        node = SubElement(kpi_root, "KPI")
        SubElement(node, "Label").text = str(kpi.get("label", ""))
        SubElement(node, "Valor").text = str(kpi.get("value", ""))


def _append_inconsistencies(parent: Element, inconsistencies: Iterable[Dict[str, str]]) -> None:
    inconsistencies = list(inconsistencies or [])
    if not inconsistencies:
        return
    inc_root = SubElement(parent, "Inconsistencias")
    for inc in inconsistencies:
        node = SubElement(inc_root, "Inconsistencia")
        SubElement(node, "Codigo").text = inc.get("code", "")
        SubElement(node, "Campo").text = inc.get("field", "")
        SubElement(node, "Severidade").text = inc.get("severity", "INFO")
        SubElement(node, "Mensagem").text = inc.get("message", "")


def _append_entries(parent: Element, entries: Iterable[Dict[str, str]]) -> None:
    entries = list(entries or [])
    if not entries:
        return
    entries_root = SubElement(parent, "Lancamentos")
    for entry in entries:
        node = SubElement(entries_root, "Lancamento")
        SubElement(node, "Debito").text = str(entry.get("debito", ""))
        SubElement(node, "Credito").text = str(entry.get("credito", ""))
        SubElement(node, "Valor").text = f"{float(entry.get('valor', 0)):.2f}"
        if entry.get("historico"):
            SubElement(node, "Historico").text = entry.get("historico")


def build_sped_efd(dataset: Dict[str, Any]):
    if not settings.ENABLE_SPED_EXPORT:
        raise ValueError("Exportação SPED desabilitada nas configurações")
    root = Element("EFD")
    identification = SubElement(root, "Identificacao")
    SubElement(identification, "Titulo").text = dataset.get("title", "Relatorio Fiscal")
    SubElement(identification, "GeradoEm").text = datetime.now(timezone.utc).isoformat()

    _append_kpis(root, dataset.get("kpis", []))
    compliance = dataset.get("compliance", {})
    _append_inconsistencies(root, compliance.get("inconsistencies", []))
    taxes = dataset.get("taxes", {})
    entries = taxes.get("lancamentos") or dataset.get("lancamentos", [])
    _append_entries(root, entries)

    xml_bytes = tostring(root, encoding="utf-8", xml_declaration=True)
    SCHEMA.validate(BytesIO(xml_bytes))
    filename = "sped_efd_validado.xml"
    return xml_bytes, filename
