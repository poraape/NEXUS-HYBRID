# Nexus Hybrid — FastAPI + Streamlit

Plataforma híbrida FastAPI/Streamlit preparada para o Desafio Final I2A2 com orquestração assíncrona, agentes especializados e exportações fiscais validadas.

## Arquitetura

```
frontend/          # Streamlit (UX técnica, dashboards e simuladores)
backend/
  ├─ main.py       # FastAPI, uploads seguros e endpoints de exportação
  ├─ agents/       # OCR, Auditor, Classifier (spaCy), Accountant, Manager
  ├─ services/     # Parsers, exports (DOCX/PDF/HTML/SPED), AI bridge
  ├─ rules/        # Motor fiscal e dicionário normativo
  └─ core/         # Configurações (.env) e logger estruturado
```

* **Orquestração paralela:** `agents/manager.py` utiliza `asyncio` com controle de concorrência, gera `logs/processing_log.json` em formato JSON e consolida XAI.
* **Agentes dedicados:**
  * `ocr_agent` (PyMuPDF + Tesseract).
  * `auditor_agent` + `rules_engine` com cobertura CFOP/CST/ICMS/PIS/COFINS/ISS/IVA/ST.
  * `classifier_agent` (spaCy `pt_core_news_sm` + feedback persistido em SQLite).
  * `accountant_agent` com cálculo determinístico por regime e lançamentos balanceados.
* **Explicabilidade:** `services/ai_bridge.py` gera explicações locais (ou Gemini/OpenAI quando configurado).
* **Segurança:** uploads com `secure_filename`, bloqueio path traversal, MIME whitelist e limites configuráveis via `.env`.

## Requisitos

### Backend
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload
```

### Frontend
```bash
pip install -r frontend/requirements.txt
streamlit run frontend/app.py
```

### Docker (full stack)
```bash
docker compose up --build
# UI: http://localhost:8501
# API: http://localhost:8000/docs
```

## Configuração (.env)

Copie `.env.example` para `.env` na raiz e ajuste conforme necessário:

```
MAX_UPLOAD_MB=200
DATA_PATH=./data
LOG_DIR=./logs
DB_PATH=./data/learning.db
GEMINI_API_KEY=
OPENAI_API_KEY=
OFFLINE_MODE=true
EXPORT_PROCESSING_LOG=true
ENABLE_SPED_EXPORT=true
```

## Fluxo operacional

1. **Upload seguro** (`/upload/zip` ou `/upload/file`): sanitização, parser multi-formato (XML, CSV, XLSX, PDF, imagens) e logs em tempo real na interface Streamlit.
2. **Pipeline assíncrono:** Manager aciona OCR → Auditor → Classifier → Accountant em paralelo e grava eventos com timestamps.
3. **Dashboards e simulações:** Página `03_dashboards.py` consolida KPIs, heatmaps Plotly/Altair e logs estruturados.
4. **Exportações:** `/export/docx|pdf|html|sped` geram relatórios; o SPED/EFD é validado via XMLSchema oficial simplificado (`backend/services/schemas/sped_efd_schema.xsd`).
5. **XAI fiscal:** inconsistências retornam com base normativa, tolerâncias e explicações contextualizadas.

## Contrato de dados

```json
{
  "title": "string",
  "documentId": "uuid",
  "kpis": [{"label": "string", "value": "string|number"}],
  "classification": {"tipo": "string", "ramo": "string", "confidence": 0.0},
  "taxes": {
    "regime": "Simples Nacional | Lucro Presumido | Lucro Real",
    "resumo": {"totalICMS": 0, "totalPIS": 0, "totalCOFINS": 0, "totalISS": 0, "totalIVA": 0},
    "lancamentos": [{"debito": "", "credito": "", "valor": 0, "historico": ""}]
  },
  "compliance": {
    "score": 0,
    "inconsistencies": [
      {
        "code": "string",
        "field": "string",
        "severity": "INFO|WARN|ERROR",
        "message": "string",
        "normative_base": "string",
        "explanation": "string",
        "details": {"expected": 0, "actual": 0}
      }
    ]
  },
  "logs": [{"stage": "ocr", "status": "completed", "duration": 0.0, "started_at": "ISO"}],
  "source": {"emitente": {}, "destinatario": {}, "itens": []}
}
```

## Integração com IA

* **Modo offline:** defina `OFFLINE_MODE=true` para gerar explicações determinísticas.
* **Gemini/OpenAI:** configure `GEMINI_API_KEY` ou `OPENAI_API_KEY` para habilitar respostas contextuais via `services/ai_bridge.py`.

## Testes e validação

* `backend/rules/rules_engine.validate_tax_rules` cobre ICMS, PIS, COFINS, ISS, IVA, CFOP, CST e ST.
* Logs estruturados persistidos em `logs/processing_log.json` quando `EXPORT_PROCESSING_LOG=true`.
* Exportação SPED validada com `xmlschema` antes do download.

## Referências adicionais

* Dashboards (`frontend/pages/03_dashboards.py`) usam Plotly e Altair com componentes reutilizáveis (`components/ui_heatmap.py`).
* Feedback fiscal persistido em SQLite (`data/learning.db`) para aprendizado incremental.
