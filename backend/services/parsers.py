import zipfile, io, json, xmltodict, pandas as pd
from typing import List, Dict, Any
import mimetypes

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

def parse_xml(name:str, content:bytes)->Dict[str,Any]:
    data = xmltodict.parse(content)
    return {"kind":"NFE_XML","name":name,"data":_normalize_nfe(data)}

def parse_csv(name:str, content:bytes)->Dict[str,Any]:
    df = pd.read_csv(io.BytesIO(content))
    return {"kind":"CSV","name":name,"data": df.to_dict(orient="records")}

def parse_xlsx(name:str, content:bytes)->Dict[str,Any]:
    df = pd.read_excel(io.BytesIO(content))
    return {"kind":"XLSX","name":name,"data": df.to_dict(orient="records")}

def parse_pdf(name:str, content:bytes)->Dict[str,Any]:
    return {"kind":"PDF","name":name,"raw": content, "data": {"text": None}}

def parse_image(name:str, content:bytes)->Dict[str,Any]:
    return {"kind":"IMAGE","name":name,"raw": content}

def parse_file(name:str, content:bytes, mime:str)->Dict[str,Any]:
    lname = name.lower()
    if lname.endswith(".xml"): return parse_xml(name, content)
    if lname.endswith(".csv"): return parse_csv(name, content)
    if lname.endswith(".xlsx"): return parse_xlsx(name, content)
    if lname.endswith(".pdf"): return parse_pdf(name, content)
    if lname.endswith(".png") or lname.endswith(".jpg") or lname.endswith(".jpeg"): return parse_image(name, content)
    if "xml" in (mime or ""): return parse_xml(name, content)
    if "csv" in (mime or ""): return parse_csv(name, content)
    if "excel" in (mime or ""): return parse_xlsx(name, content)
    if "pdf" in (mime or ""): return parse_pdf(name, content)
    if "image/" in (mime or ""): return parse_image(name, content)
    return {"kind":"UNKNOWN","name":name, "raw": content}

def parse_any_files_from_zip(zip_bytes: bytes)->List[Dict[str,Any]]:
    buf = io.BytesIO(zip_bytes)
    z = zipfile.ZipFile(buf)
    out = []
    for info in z.infolist():
        if info.is_dir(): continue
        name = info.filename
        content = z.read(info)
        doc = parse_file(name, content, mimetypes.guess_type(name)[0] or "")
        if doc["kind"] != "UNKNOWN":
            out.append(doc)
    return out
