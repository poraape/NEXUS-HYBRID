"""Pydantic models describing the public contracts of the backend."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


class DocumentParty(BaseModel):
    """Identificação de uma parte em um documento fiscal."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    nome: Optional[str] = None
    cnpj: Optional[str] = None
    ie: Optional[str] = Field(default=None, alias="inscricaoEstadual")
    municipio: Optional[str] = None
    uf: Optional[str] = None


class DocumentItem(BaseModel):
    """Item comercializado em um documento fiscal."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    codigo: Optional[str] = None
    descricao: Optional[str] = None
    ncm: Optional[str] = None
    cfop: Optional[str] = None
    cst: Optional[str] = None
    quantidade: Optional[float] = None
    valor: float = 0.0


class DocumentData(BaseModel):
    """Estrutura organizada das informações extraídas de um documento."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    emitente: Optional[DocumentParty] = None
    destinatario: Optional[DocumentParty] = None
    itens: List[DocumentItem] = Field(default_factory=list)
    impostos: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    text: Optional[str] = None


class Document(BaseModel):
    """Documento estruturado processado pelo pipeline."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    id: Optional[str] = None
    name: Optional[str] = None
    kind: Optional[str] = None
    data: DocumentData | Dict[str, Any] = Field(default_factory=dict)
    raw: Optional[bytes] = Field(default=None, exclude=True)

    def dict_for_agent(self) -> Dict[str, Any]:
        """Retorna o dicionário compatível com os agentes internos."""

        payload = self.model_dump(mode="python", exclude_none=True)
        if isinstance(self.data, DocumentData):
            payload["data"] = self.data.model_dump(mode="python", exclude_none=True)
        return payload

    def ensure_structured(self) -> Optional[DocumentData]:
        if isinstance(self.data, DocumentData):
            return self.data
        if isinstance(self.data, dict):
            try:
                return DocumentData.model_validate(self.data)
            except ValidationError:
                return None
        return None


class DocumentIn(BaseModel):
    """Entrada de um arquivo bruto para processamento."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    filename: str
    content_type: Optional[str] = Field(default=None, alias="contentType")
    byte_stream: str = Field(alias="byteStream")
    encoding: Optional[str] = "base64"

    @field_validator("encoding")
    @classmethod
    def _normalise_encoding(cls, value: Optional[str]) -> str:
        return (value or "base64").lower()

    @field_validator("byte_stream")
    @classmethod
    def _ensure_stream(cls, value: str) -> str:
        if not value:
            raise ValueError("byteStream must not be empty")
        return value

    def decode(self) -> bytes:
        import base64
        import binascii

        if self.encoding not in {"base64", "b64"}:
            raise ValueError("Unsupported encoding; expected base64")
        try:
            return base64.b64decode(self.byte_stream)
        except binascii.Error as exc:  # pragma: no cover - defensive
            raise ValueError("Invalid base64 payload") from exc


class AuditIssue(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    code: str
    field: Optional[str] = None
    severity: str = "INFO"
    message: Optional[str] = None
    normative_base: Optional[str] = Field(default=None, alias="normativeBase")
    explanation: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)


class AuditReport(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    score: float = 0
    issues: List[AuditIssue] = Field(default_factory=list)
    recommended_corrections: List[str] = Field(default_factory=list)


class ClassificationResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    tipo: str
    ramo: str
    confidence: float
    emitente: Optional[str] = None
    destinatario: Optional[str] = None
    cfop: Optional[str] = None
    ncm: Optional[str] = None


class AccountingEntry(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    debito: str
    credito: str
    valor: float
    historico: str


class AccountingOutput(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    regime: str
    competencia: str
    resumo: Dict[str, float]
    lancamentos: List[AccountingEntry] = Field(default_factory=list)


class IntelligenceInsight(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    summaries: List[str] = Field(default_factory=list)
    kpis: Dict[str, float] = Field(default_factory=dict)
    recommendations: List[str] = Field(default_factory=list)
    scenario_simulations: List[str] = Field(default_factory=list)


class PipelineDocument(BaseModel):
    """Documento aceito pelo orquestrador (bruto ou estruturado)."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    upload: Optional[DocumentIn] = None
    document: Optional[Document] = None

    @model_validator(mode="after")
    def _check_payload(self) -> "PipelineDocument":
        if not self.upload and not self.document:
            raise ValueError("Informe 'upload' ou 'document'.")
        return self


class OrchestratorRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    documents: List[PipelineDocument]
    workflow: List[str] | None = None
    async_mode: bool = Field(default=False, alias="async")


class OrchestratorResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    status: str
    job_id: Optional[str] = None
    reports: List[Dict[str, Any]] = Field(default_factory=list)
    aggregated: Dict[str, Any] = Field(default_factory=dict)
    insight: Optional[IntelligenceInsight] = None


__all__ = [
    "Document",
    "DocumentData",
    "DocumentIn",
    "DocumentItem",
    "DocumentParty",
    "AuditIssue",
    "AuditReport",
    "ClassificationResult",
    "AccountingEntry",
    "AccountingOutput",
    "IntelligenceInsight",
    "PipelineDocument",
    "OrchestratorRequest",
    "OrchestratorResult",
]

