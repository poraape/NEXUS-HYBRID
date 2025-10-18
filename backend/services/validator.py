from typing import Any, Dict

import json

from services.ai_bridge import build_explanations

with open("rules/rules_dictionary.json", "r", encoding="utf-8") as f:
    RULES = json.load(f)

WEIGHTS = RULES.get("severity_weights", {"ERROR": 3, "WARN": 1, "INFO": 0})


def enrich_with_xai(compliance: Dict[str, Any], context: Dict[str, Any] | None = None) -> Dict[str, Any]:
    rules_index = {r["code"]: r for r in RULES.get("rules", [])}
    inconsistencies = []
    for inc in compliance.get("inconsistencies", []):
        rule = rules_index.get(inc.get("code", ""), {})
        inc["normative_base"] = inc.get("normative_base") or rule.get("normative_base")
        inc["message"] = inc.get("message") or rule.get("message")
        inconsistencies.append(inc)
    context = context or {}
    explanations = build_explanations(inconsistencies, context)
    for inc in inconsistencies:
        code = inc.get("code", "UNKNOWN")
        inc["explanation"] = explanations.get(code, inc.get("message"))
    score = sum(WEIGHTS.get(i.get("severity", "INFO"), 0) for i in inconsistencies)
    return {"inconsistencies": inconsistencies, "score": score}
