from typing import List, Dict, Any
from agents.ocr_agent import run_ocr
from agents.auditor_agent import audit
from agents.classifier_agent import classify
from agents.accountant_agent import compute
from services.validator import enrich_with_xai

async def process_documents_pipeline(docs: List[Dict[str, Any]])->Dict[str, Any]:
    reports = []
    for doc in docs:
        kind = doc.get("kind")
        if kind in ("PDF","IMAGE"):
            ocr = await run_ocr(doc)
            doc["data"] = {"text": ocr.get("text","")}
        audit_res = await audit(doc)
        cls_res = await classify(doc)
        acc_res = await compute(doc)
        report = {
            "title": f"Relatório - {doc.get('name')}",
            "kpis": [
                {"label":"Itens", "value": len(doc.get("data",{}).get("itens", []))},
                {"label":"Score Conformidade (↓ melhor)", "value": audit_res.get("score",0)},
                {"label":"Valor ICMS (calc.)", "value": acc_res.get("resumo",{}).get("totalICMS",0)}
            ],
            "classification": cls_res,
            "taxes": {"resumo": acc_res.get("resumo",{}), "lancamentos": acc_res.get("lancamentos",[])},
            "compliance": enrich_with_xai(audit_res),
            "logs": []
        }
        reports.append(report)
    return {"reports": reports}
