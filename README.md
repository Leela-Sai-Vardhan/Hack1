# Intelli-Credit — AI Credit Decisioning Engine

An AI-powered credit appraisal system for Indian corporate lending using Google Gemini, FastAPI, and a multi-agent research pipeline.

## Features

- **Document Ingestion**: PDF extraction (native + OCR fallback via Tesseract)
- **Financial Extraction**: Gemini AI extracts 14+ financial metrics from uploaded documents
- **GST/Bank Validation**: Automated ratio checks, DSCR, current ratio, revenue trend alerts
- **Multi-Agent Research**: Parallel DuckDuckGo + Gemini agents for news, litigation, promoter integrity, and regulatory risk
- **Primary Insights**: Site-visit observations scored by Gemini AI
- **Credit Scoring**: Weighted rule-based engine (Financial 40% | Research 35% | Primary 25%)
- **Decision Engine**: APPROVE / CONDITIONAL / DECLINE with MCLR spread and limit calculation
- **CAM Generation**: Word document using the 5Cs framework (Character, Capacity, Capital, Collateral, Conditions)

## Project Structure

```
intellicredit/
├── main.py                  # FastAPI app + REST endpoints
├── config.py                # Environment configuration
├── schemas.py               # Pydantic data models
├── database.py              # SQLite helpers
├── requirements.txt
├── .env.example
├── pipeline/
│   ├── orchestrator.py      # 8-stage pipeline runner
│   ├── ingestor.py          # PDF text extraction
│   ├── extractor.py         # Gemini financial data extraction
│   ├── gst_validator.py     # GST/bank ratio checks
│   └── scorer.py            # Credit scoring engine
├── agents/
│   └── research.py          # News, litigation, promoter, regulatory agents
├── engine/
│   ├── decision.py          # APPROVE/CONDITIONAL/DECLINE logic
│   └── cam_generator.py     # Word CAM document generator
├── static/
│   └── index.html           # Bootstrap 5 single-page UI
├── uploads/                 # Auto-created
└── outputs/                 # Auto-created (CAM documents)
```

## Setup

### 1. Clone & Install

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env and add your GEMINI_API_KEY
```

Get a free Gemini API key at: https://aistudio.google.com/app/apikey

### 3. (Optional) Install Tesseract for OCR

For scanned PDFs, install [Tesseract OCR](https://github.com/tesseract-ocr/tesseract):
- Windows: Download installer from GitHub releases
- Ubuntu: `sudo apt install tesseract-ocr`

### 4. Run

```bash
python main.py
# or
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Open: http://localhost:8000

## Usage

1. **Create a Case** — Enter company name and CIN
2. **Upload Documents** — Annual report, bank statements, GST filings, ITR etc. (PDF)
3. **Site Visit Data** — Optional: enter physical inspection observations
4. **Run AI Analysis** — Triggers all 8 pipeline stages (~2–5 minutes)
5. **View Results** — Score breakdown, risk flags, decision, ratios
6. **Download CAM** — Word document Credit Appraisal Memo

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/cases` | Create a new credit case |
| `POST` | `/api/cases/{id}/documents` | Upload a PDF document |
| `POST` | `/api/cases/{id}/primary-insights` | Save site visit data |
| `POST` | `/api/cases/{id}/analyze` | Start AI pipeline |
| `GET`  | `/api/cases/{id}/status` | Poll pipeline status |
| `GET`  | `/api/cases/{id}` | Get full case data |
| `GET`  | `/api/cases/{id}/cam` | Download CAM (.docx) |
| `GET`  | `/api/cases` | List all cases |

## Credit Score Methodology

### Score Bands → Risk Rating

| Score | Rating | Decision |
|-------|--------|----------|
| 88–100 | AAA | APPROVE (MCLR + 50bps) |
| 80–87  | AA  | APPROVE (MCLR + 75bps) |
| 72–79  | A   | APPROVE (MCLR + 100bps) |
| 62–71  | BBB | APPROVE (MCLR + 175bps) |
| 50–61  | BB  | CONDITIONAL (MCLR + 300bps) |
| 38–49  | B   | CONDITIONAL (MCLR + 450bps) |
| < 38   | D   | DECLINE |

### Scoring Weights

| Component | Weight | Key Metrics |
|-----------|--------|-------------|
| Financial Score | 40% | DSCR, D/E, Current Ratio, EBITDA Margin, Revenue CAGR, Interest Coverage, GST/Bank Ratio |
| Research Score | 35% | News risk, Litigation exposure, Promoter integrity, Regulatory risks, Sector outlook |
| Primary Insights | 25% | Site visit observations scored by Gemini AI |
