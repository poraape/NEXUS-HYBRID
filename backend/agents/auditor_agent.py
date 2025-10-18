from typing import Any, Dict

from rules.rules_engine import audit_document


async def audit(doc: Dict[str, Any]) -> Dict[str, Any]:
    data = doc.get("data") or {}
    payload = {
        "itens": data.get("itens", []),
        "impostos": data.get("impostos", {}),
        "metadata": data.get("metadata", {}),
        "destinatario": data.get("destinatario", {}),
    }
    return audit_document(payload)
