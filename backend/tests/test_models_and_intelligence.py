import asyncio
import base64

import pytest

from backend.agents.intelligence_agent import generate_insights
from backend.models import DocumentIn, PipelineDocument


def test_document_in_decode_roundtrip():
    content = b"nota fiscal"
    payload = DocumentIn.model_validate(
        {
            "filename": "nota.txt",
            "contentType": "text/plain",
            "byteStream": base64.b64encode(content).decode("utf-8"),
        }
    )
    assert payload.decode() == content


def test_pipeline_document_requires_payload():
    with pytest.raises(ValueError):
        PipelineDocument()


def test_generate_insights_produces_recommendations():
    reports = [
        {
            "compliance": {
                "score": 2,
                "inconsistencies": [
                    {"severity": "ERROR", "code": "ICMS_BASE_CALC", "field": "icms"}
                ],
            },
            "classification": {"ramo": "Tecnologia"},
        }
    ]
    aggregated = {"totals": {"vICMS": 12000}}
    insight = asyncio.run(generate_insights(reports, aggregated=aggregated))
    assert insight.kpis["documents"] == 1.0
    assert any("ICMS" in rec for rec in insight.recommendations)
