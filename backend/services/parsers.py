import io
import json
import mimetypes
import re
import zipfile
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import xmltodict

from core.logger import log_event
from core.settings import settings


def secure_filename(value: str) -> str:
    """Simplified secure filename implementation (Werkzeug compatible signature)."""
    if not value:
        return "document"
    value = re.sub(r"[\s]+", "_", value.strip())
    value = re.sub(r"[^A-Za-z0-9_.-]", "", value)
    value = value.lstrip(".")
    return value or "document"


def _is_allowed(name: str, mime: str) -> bool:
    suffix_ok = Path(name).suffix.lower() in settings.ALLOWED_EXTENSIONS
    mime_ok = any(mime.startswith(prefix) for prefix in settings.ALLOWED_MIME_PREFIXES if mime)
    return suffix_ok or mime_ok

def _normalize_nfe(obj: dict)->dict:
    node = obj.get("nfeProc",{}).get("NFe",{}).get("infNFe") or obj.get("NFe",{}).get("infNFe") or obj.get("infNFe") or obj
    emit = node.get("emit",{}); dest = node.get("dest",{})
    dets = node.get("det", [])
    if isinstance(dets, dict): dets = [dets]
    itens = []
    for d in dets:
        prod = d.get("prod",{})
        itens.append({
            "codigo": prod.get("cProd"),
            "descricao": prod.get("xProd"),
            "ncm": prod.get("NCM"),
            "cfop": str(prod.get("CFOP") or ""),
            "quantidade": float(prod.get("qCom") or 0),
            "valor": float(prod.get("vProd") or 0)
        })
    impostos = (node.get("total",{}) or {}).get("ICMSTot",{})
    return {
        "emitente": {"cnpj": emit.get("CNPJ"), "nome": emit.get("xNome"), "uf": (emit.get("enderEmit") or {}).get("UF")},
        "destinatario": {"cnpj": dest.get("CNPJ") or dest.get("CPF"), "nome": dest.get("xNome"), "uf": (dest.get("enderDest") or {}).get("UF")},
        "itens": itens,
        "impostos": {"icms": impostos.get("vICMS"), "pis": impostos.get("vPIS"), "cofins": impostos.get("vCOFINS")}
    }

def parse_xml(name: str, content: bytes) -> Dict[str, Any]:
    data = xmltodict.parse(content)
    return {"kind": "NFE_XML", "name": name, "data": _normalize_nfe(data)}

def parse_csv(name: str, content: bytes) -> Dict[str, Any]:
    df = pd.read_csv(io.BytesIO(content))
    return {"kind": "CSV", "name": name, "data": df.to_dict(orient="records")}

def parse_xlsx(name: str, content: bytes) -> Dict[str, Any]:
    df = pd.read_excel(io.BytesIO(content))
    return {"kind": "XLSX", "name": name, "data": df.to_dict(orient="records")}

def parse_pdf(name: str, content: bytes) -> Dict[str, Any]:
    return {"kind": "PDF", "name": name, "raw": content, "data": {"text": None}}

def parse_image(name: str, content: bytes) -> Dict[str, Any]:
    return {"kind": "IMAGE", "name": name, "raw": content}

def parse_file(name: str, content: bytes, mime: str) -> Dict[str, Any]:
    sanitized_name = secure_filename(Path(name).name)
    lname = sanitized_name.lower()
    if not _is_allowed(sanitized_name, mime):
        log_event("parser", "WARN", "Arquivo bloqueado por tipo não permitido", {"name": name, "mime": mime})
        return {"kind": "UNKNOWN", "name": sanitized_name, "raw": content}
    if lname.endswith(".xml"):
        return parse_xml(sanitized_name, content)
    if lname.endswith(".csv"):
        return parse_csv(sanitized_name, content)
    if lname.endswith(".xlsx"):
        return parse_xlsx(sanitized_name, content)
    if lname.endswith(".pdf"):
        return parse_pdf(sanitized_name, content)
    if lname.endswith(".png") or lname.endswith(".jpg") or lname.endswith(".jpeg"):
        return parse_image(sanitized_name, content)
    if "xml" in (mime or ""):
        return parse_xml(sanitized_name, content)
    if "csv" in (mime or ""):
        return parse_csv(sanitized_name, content)
    if "excel" in (mime or ""):
        return parse_xlsx(sanitized_name, content)
    if "pdf" in (mime or ""):
        return parse_pdf(sanitized_name, content)
    if "image/" in (mime or ""):
        return parse_image(sanitized_name, content)
    log_event("parser", "WARN", "Arquivo desconhecido descartado", {"name": name, "mime": mime})
    return {"kind": "UNKNOWN", "name": sanitized_name, "raw": content}

def parse_any_files_from_zip(zip_bytes: bytes) -> List[Dict[str, Any]]:
    buf = io.BytesIO(zip_bytes)
    out: List[Dict[str, Any]] = []
    with zipfile.ZipFile(buf) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            original_name = info.filename
            path = Path(original_name)
            if path.is_absolute() or ".." in path.parts:
                log_event("parser", "WARN", "Arquivo ignorado por path traversal", {"name": original_name})
                continue
            if info.file_size > settings.MAX_UPLOAD_MB * 1024 * 1024:
                log_event("parser", "WARN", "Arquivo ignorado por exceder limite individual", {"name": original_name})
                continue
            content = archive.read(info)
            mime = mimetypes.guess_type(path.name)[0] or ""
            doc = parse_file(path.name, content, mime)
            if doc["kind"] != "UNKNOWN":
                out.append(doc)
    return out
