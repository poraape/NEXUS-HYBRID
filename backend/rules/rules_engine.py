import re, json
from typing import Dict, Any

with open("rules/rules_dictionary.json","r",encoding="utf-8") as f:
    RULES = json.load(f)

CFOP_SET = set(RULES.get("cfopValid", []))
NCM_RE = re.compile(r"^\d{8}$")

def audit_document(doc: Dict[str, Any]) -> Dict[str, Any]:
    inconsistencies = []

    for item in doc.get("itens", []):
        # CFOP
        cfop = str(item.get("cfop","")).replace(".","")
        if cfop and cfop not in CFOP_SET:
            inconsistencies.append({
                "field":"cfop","code":"CFOP_VALID","message":"CFOP não esperado para operação",
                "severity":"ERROR","rule_ref":"CFOP_VALID","normativeBase":"RICMS-SP Art. 33"
            })
        # NCM
        ncm = str(item.get("ncm",""))
        if ncm and not NCM_RE.match(ncm):
            inconsistencies.append({
                "field":"ncm","code":"NCM_FORMAT","message":"NCM não possui 8 dígitos",
                "severity":"WARN","rule_ref":"NCM_FORMAT","normativeBase":"TIPI 2022"
            })
        # Valor
        try:
            v = float(item.get("valor") or 0)
            if v < 0:
                inconsistencies.append({
                    "field":"valor","code":"VALOR_NEGATIVO","message":"Valor do item negativo",
                    "severity":"ERROR","rule_ref":"VALOR_NEGATIVO","normativeBase":"Princípios contábeis"
                })
        except:
            pass
    score = sum(3 if r["severity"]=="ERROR" else 1 for r in inconsistencies)
    return {"inconsistencies": inconsistencies, "score": score}
