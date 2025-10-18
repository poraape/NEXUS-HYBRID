from typing import Dict, Any

CFOP_MAP = {"5101":"Venda","5102":"Venda","6102":"Venda","1102":"Compra","2102":"Compra"}

def _ramo_por_ncm(ncm:str)->str:
    if not ncm: return "Indefinido"
    if ncm.startswith("85"): return "Tecnologia da Informação"
    if ncm.startswith("21") or ncm.startswith("30"): return "Saúde/Farma"
    if ncm.startswith("02") or ncm.startswith("16"): return "Alimentos"
    return "Geral"

async def classify(doc: Dict[str, Any]) -> Dict[str, Any]:
    data = doc.get("data") or {}
    itens = data.get("itens", [])
    freq = {}
    for it in itens:
        cf = str(it.get("cfop","")).replace(".","")
        if not cf: continue
        freq[cf] = freq.get(cf,0)+1
    tipo = "Indefinido"
    if freq:
        top = max(freq, key=freq.get)
        tipo = CFOP_MAP.get(top, "Operação")
    ramo = _ramo_por_ncm((itens[0].get("ncm") if itens else "") or "")
    return {"tipo": tipo, "ramo": ramo, "confidence": 0.9 if freq else 0.5}
