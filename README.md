# IntelliCredit — AI-Powered Credit Decisioning Prototype

## 🚀 Overview
IntelliCredit is an end-to-end AI-powered credit appraisal and decisioning prototype designed to automate and augment the SME and corporate lending process. The prototype leverages the Gemini API and modular processing workflows to ingest documents, extract financial metrics, conduct web-based due diligence, calculate synthetic scores, and ultimately generate a comprehensive Credit Appraisal Memo (CAM).

## ✨ Key Features & Functionality
- **Document Ingestion & Classification**: Upload financial documents which are automatically classified and stored against the specified credit case.
- **Automated Financial Extraction**: Uses AI to extract key financial ratios (DSCR, Debt-to-Equity, Current Ratio, EBITDA Margin, etc.) and calculate baseline risk scores.
- **GST & Bank Statement Validation**: Reconciles reported financial metrics against auxiliary datasets (GST returns and bank statement ratios) for consistency checking.
- **Web Research Agents**: Autonomous agents gather real-time data on promoter integrity, sectoral outlook, regulatory risks, and pending litigation (via news sentiment and rule-based tracking).
- **Primary Insight Scoring**: Adjusts algorithmic baseline scores based on qualitative, real-world inputs (e.g., site visit observations, succession planning, machinery condition, management quality).
- **Automated Decision Engine**: Based on credit grading (AAA to D), automatically recommends **APPROVE**, **CONDITIONAL**, or **DECLINE**, along with recommended limits (via Nayak Committee turnover method and DSCR) and MCLR-linked pricing adjustments.
- **Counterfactual Explanations**: Gemini generates a concise two-sentence narrative explaining exactly *why* the decision was made, and what specific improvements would change the outcome. 
- **CAM Document Generation**: Automatically writes and exports a detailed, fully-formatted Word document (CAM) covering the "Five Cs of Credit" (Character, Capacity, Capital, Collateral, Conditions).

## 🛠️ Technical Architecture

### Backend Layer
- **Framework**: FastAPI (Python) running asynchronously on Uvicorn.
- **Pipeline Orchestrator**: An asynchronous task pipeline managing the entire logical flow (`INGESTING` ➔ `EXTRACTING` ➔ `VALIDATING` ➔ `RESEARCHING` ➔ `PRIMARY_INSIGHTS` ➔ `SCORING` ➔ `DECIDING` ➔ `GENERATING_CAM`).
- **AI Integration**: Google GenAI SDK is heavily utilized for extraction mapping, unstructured sentiment analysis, qualitative scoring, and CAM document generation.

### Frontend Layer
- **Interface**: A vanilla HTML/CSS dashboard interface designed directly on top of the backend (served via `StaticFiles`). It is built for speed, simplicity, and clear visualization of complex credit metrics.
- **Visuals**: Features a dark-on-light professional theme with dedicated color-coded score rings (Good/Warn/Bad), dynamic progress badges, ratio cards, dynamic driver bars, and a structured breakdown of risk flags.

### Data Layer
- **Database**: Standard relational database structure initialized via a lightweight `database.py`.
- **Domain Modeling**: Deeply typed Pydantic schemas map out the complex entities logically: `CreditCase`, `FinancialMetrics`, `ResearchFindings`, `PrimaryInsights`, and `ScoreBreakdown`.

## 📦 Tools & Methods Used
- **Runtime Environment**: Python 3.13, FastAPI, Pydantic, aiofiles
- **AI/LLM**: Google GenAI endpoints for reasoning tasks (structured JSON generation, text formatting, contextual risk grading).
- **Document Generation**: `python-docx` for dynamically creating the CAM .docx report with customized shading and text alignments.
- **Frontend Stack**: HTML5, custom CSS layout handling, Javascript (Vanilla), Bootstrap Icons for lightweight scalable UI icons.
- **Methodology**: Multi-step reasoning pipeline combining traditional deterministic banking covenants overlaid with flexible, natural-language AI capability.

## 🌟 Real-World Applications & Scalability
- **Rapid TAT (Turnaround Time)**: This prototype highlights how corporate loan decisioning times can be reduced from weeks to mere hours by shifting the manual grunt work (data entry, initial ratio calculations, CAM drafting) entirely to the machine.
- **Process Scalability**: The asynchronous pipeline handles multiple distinct requests at the same time and provides isolated steps. In the real world, this structure easily allows dropping in external data provider APIs (e.g., CIBIL integration, Experian API, targeted MCA registry scraping) without rewriting the core engine.
- **Consistency & Objectivity**: Standardizes risk decisions across branches, directly tying pricing (MCLR spread limits) to mathematically verifiable and AI-summarized qualitative flags.
- **Auditability via Explainability**: Unlike opaque ML models or pure scoring formulas, credit committees read synthesized, factual justifications in the explanation narratives and counterfactual improvement markers directly constructed by the model. 
