from typing import Dict, Any, List
import json

with open("rules/rules_dictionary.json","r",encoding="utf-8") as f:
    RULES = json.load(f)

WEIGHTS = {"ERROR":3, "WARN":1, "INFO":0}

def enrich_with_xai(compliance: Dict[str, Any]) -> Dict[str, Any]:
    rules_index = {r["code"]: r for r in RULES.get("rules", [])}
    inconsistencies = []
    for inc in compliance.get("inconsistencies", []):
        rule = rules_index.get(inc.get("code",""), {})
        inc["normativeBase"] = inc.get("normativeBase") or rule.get("normativeBase")
        inc["explanation"] = inc.get("explanation") or rule.get("message")
        inconsistencies.append(inc)
    score = sum(WEIGHTS.get(i.get("severity","INFO"),0) for i in inconsistencies)
    return {"inconsistencies": inconsistencies, "score": score}
