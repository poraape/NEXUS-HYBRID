from typing import Dict, Any
from rules.rules_engine import audit_document

async def audit(doc: Dict[str, Any]) -> Dict[str, Any]:
    data = doc.get("data") or {}
    return audit_document({"itens": data.get("itens", [])})
