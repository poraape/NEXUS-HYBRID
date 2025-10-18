# Nexus Quantum I2A2 — Hybrid Python (FastAPI + Streamlit)

Arquitetura híbrida que replica a versão Nexus (React/TS) com backend robusto e UI técnica equivalente.

## Rodar com Docker (recomendado)
```bash
docker compose up --build
```

Assim que os containers estiverem no ar, o Streamlit imprime no terminal um trecho como:

```
You can now view your Streamlit app in your browser.
  URL: http://0.0.0.0:8501
```

Abra um navegador local e acesse **http://localhost:8501** para visualizar a interface.
Os endpoints REST da API FastAPI continuam disponíveis em **http://localhost:8000/docs**.

## Rodar localmente (sem Docker)
Backend:
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload
```
Frontend:
```bash
pip install -r frontend/requirements.txt
streamlit run frontend/app.py
```

O comando acima também exibe a URL do app; abra **http://localhost:8501** no navegador para ver a UI.

## Endpoints principais (FastAPI)
- `POST /upload/zip` — recebe .zip, processa todos os arquivos e retorna reports JSON
- `POST /upload/file` — recebe arquivo único (xml/csv/xlsx/pdf/png/jpg)
- `POST /export/docx|pdf|html|sped` — exporta a partir do mesmo JSON (paridade total)

## Contrato de Dados (fonte de verdade)
```json
{
  "title": "string",
  "kpis": [{"label":"string","value":"string|number"}],
  "classification": {"tipo":"string","ramo":"string","confidence":0.0},
  "taxes": {"resumo":{"totalICMS":0,"totalPIS":0,"totalCOFINS":0,"totalISS":0,"totalIVA":0}, "lancamentos":[{"debito":"", "credito":"", "valor":0}]},
  "compliance": {
    "score": 0,
    "inconsistencies": [
      {"field":"string","code":"string","message":"string","explanation":"string","severity":"INFO|WARN|ERROR","rule_ref":"string","normativeBase":"string"}
    ]
  },
  "logs": [{"ts":"ISO","agent":"string","level":"INFO|WARN|ERROR","message":"string","meta":{}}]
}
```

## Pixel-approx & Paridade UI
- `frontend/styles/theme.css` aplica tokens e estilos equivalentes ao Nexus.
- Componentes: `components/ui_kpis.py`, `ui_tables.py`, `ui_heatmap.py`.

## SPED/EFD (Protótipo)
- Endpoint `/export/sped` gera TXT pseudo-estruturado (não-oficial).

## XAI/Validator
- `services/validator.py` enriquece inconsistências com base normativa e recalcula score.
