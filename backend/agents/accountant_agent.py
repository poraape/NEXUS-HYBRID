from typing import Dict, Any

def _sum(v):
    try: return float(v or 0)
    except: return 0.0

async def compute(doc: Dict[str, Any]) -> Dict[str, Any]:
    data = doc.get("data") or {}
    itens = data.get("itens", [])
    total = sum(_sum(i.get("valor")) for i in itens)
    taxes = {
        "totalICMS": round(total * 0.18, 2),
        "totalPIS": round(total * 0.0165, 2),
        "totalCOFINS": round(total * 0.076, 2),
        "totalISS": 0.0,
        "totalIVA": 0.0
    }
    entries = [
        {"debito":"ESTOQUES", "credito":"FORNECEDORES", "valor": round(total,2)},
        {"debito":"ICMS A RECUPERAR", "credito":"FORNECEDORES", "valor": taxes["totalICMS"]},
    ]
    return {"resumo": taxes, "lancamentos": entries}
