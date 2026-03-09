import json
import re
import logging
from google import genai
from google.genai import types
from schemas import CreditCase, FinancialMetrics
import config
from pipeline.ingestor import get_extracted_text

logger = logging.getLogger(__name__)
_client = None

def _get_client():
    global _client
    if _client is None:
        _client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _client

_EXTRACT_PROMPT = """You are a financial data extraction engine for Indian corporate lending.
Extract financial metrics from the document. All monetary values must be in INR Lakhs.
If a value is absent, use null. Yr1 = most recent year.

Return ONLY valid JSON (no markdown fences):
{{
  "revenue_yr1": <float|null>, "revenue_yr2": <float|null>, "revenue_yr3": <float|null>,
  "ebitda_yr1": <float|null>, "ebitda_yr2": <float|null>, "ebitda_yr3": <float|null>,
  "pat_yr1": <float|null>,
  "total_debt": <float|null>, "total_equity": <float|null>,
  "current_assets": <float|null>, "current_liabilities": <float|null>,
  "interest_expense": <float|null>, "depreciation": <float|null>, "capex": <float|null>,
  "extraction_confidence": "HIGH"|"MEDIUM"|"LOW",
  "caveats": "<notes>"
}}

Document type: {doc_type}
Document text:
{text}
"""


def _gemini_json(prompt: str, retries: int = 4) -> dict:
    import time
    for attempt in range(retries):
        try:
            resp = _get_client().models.generate_content(
                model=config.GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json", temperature=0.1)
            )
            raw = re.sub(r"```json\s*|\s*```", "", resp.text).strip()
            return json.loads(raw)
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "quota" in err_str.lower() or "rate" in err_str.lower():
                wait_time = (attempt + 1) * 10  # 10s, 20s, 30s, 40s
                logger.warning(f"Gemini rate limit hit (attempt {attempt+1}), waiting {wait_time}s...")
                time.sleep(wait_time)
            else:
                logger.warning(f"Gemini JSON attempt {attempt+1} failed: {e}")
                if attempt < retries - 1:
                    time.sleep(2)
    return {}


def _merge(extractions: list) -> dict:
    priority = ["annual_report", "itr", "rating_report",
                "bank_statement", "sanction_letter", "unknown"]
    extractions.sort(key=lambda x: priority.index(x.get("_src", "unknown"))
                     if x.get("_src", "unknown") in priority else len(priority))
    merged: dict = {}
    for ext in extractions:
        for k, v in ext.items():
            if not k.startswith("_") and k not in merged and v is not None:
                merged[k] = v
    return merged


def _compute_ratios(m: FinancialMetrics) -> FinancialMetrics:
    # Debt-to-equity
    try:
        if m.total_debt is not None and m.total_equity and m.total_equity > 0:
            m.debt_to_equity = round(m.total_debt / m.total_equity, 2)
    except Exception as e:
        logger.warning(f"D/E calculation failed: {e}")

    # Current ratio
    try:
        if m.current_assets is not None and m.current_liabilities and m.current_liabilities > 0:
            m.current_ratio = round(m.current_assets / m.current_liabilities, 2)
    except Exception as e:
        logger.warning(f"Current ratio calculation failed: {e}")

    # EBITDA margin
    try:
        if m.ebitda_yr1 is not None and m.revenue_yr1 and m.revenue_yr1 > 0:
            m.ebitda_margin_pct = round(m.ebitda_yr1 / m.revenue_yr1 * 100, 1)
    except Exception as e:
        logger.warning(f"EBITDA margin calculation failed: {e}")

    # Revenue CAGR
    try:
        if m.revenue_yr1 is not None and m.revenue_yr3 and m.revenue_yr3 > 0:
            m.revenue_cagr_3yr = round(((m.revenue_yr1 / m.revenue_yr3) ** (1/3) - 1) * 100, 1)
    except Exception as e:
        logger.warning(f"Revenue CAGR calculation failed: {e}")

    # Interest coverage
    try:
        if m.ebitda_yr1 and m.interest_expense and m.interest_expense > 0:
            m.interest_coverage = round(m.ebitda_yr1 / m.interest_expense, 2)
        elif m.ebitda_yr1 and m.total_debt and m.total_debt > 0:
            m.interest_coverage = round(m.ebitda_yr1 / (m.total_debt * 0.10), 2)
    except Exception as e:
        logger.warning(f"Interest coverage calculation failed: {e}")

    # DSCR
    try:
        ebitda = m.ebitda_yr1 or 0
        capex  = m.capex or 0
        interest = m.interest_expense or (m.total_debt * 0.10 if m.total_debt else 0)
        principal = (m.total_debt / 5) if m.total_debt else 0
        debt_svc = interest + principal
        if debt_svc > 0 and ebitda > 0:
            m.dscr = round((ebitda - capex) / debt_svc, 2)
    except Exception as e:
        logger.warning(f"DSCR calculation failed: {e}")

    logger.info(f"Computed ratios: DSCR={m.dscr}, D/E={m.debt_to_equity}, "
                f"CR={m.current_ratio}, EBITDA%={m.ebitda_margin_pct}, "
                f"CAGR={m.revenue_cagr_3yr}, ICR={m.interest_coverage}")
    return m


async def extract_financials(case: CreditCase) -> CreditCase:
    all_ext = []

    # Process ALL uploaded documents, not just a hardcoded priority list
    for doc_type, file_path in case.raw_documents.items():
        try:
            text = get_extracted_text(file_path)
            if len(text.strip()) < 50:
                logger.warning(f"Skipping {doc_type}: too little text ({len(text.strip())} chars)")
                continue
            logger.info(f"Sending {doc_type} to Gemini for extraction ({len(text)} chars)...")
            ext = _gemini_json(_EXTRACT_PROMPT.format(
                doc_type=doc_type, text=text[:12000]))
            if ext:
                ext["_src"] = doc_type
                all_ext.append(ext)
                logger.info(f"Extracted from {doc_type}: confidence={ext.get('extraction_confidence','?')}, "
                            f"revenue_yr1={ext.get('revenue_yr1')}, ebitda_yr1={ext.get('ebitda_yr1')}")
            else:
                logger.warning(f"Gemini returned empty extraction for {doc_type}")
        except Exception as e:
            logger.error(f"Extraction failed for {doc_type}: {e}")
            case.errors.append({"stage": "extractor",
                                 "doc_type": doc_type, "error": str(e)})

    if all_ext:
        merged = _merge(all_ext)
        logger.info(f"Merged extraction data: {json.dumps({k:v for k,v in merged.items() if not k.startswith('_')}, default=str)}")
        fm_fields = set(FinancialMetrics.model_fields.keys())
        fm_data = {k: v for k, v in merged.items()
                   if k in fm_fields and v is not None}
        case.financial_metrics = _compute_ratios(FinancialMetrics(**fm_data))
    else:
        logger.error("No financial data extracted from any document!")
        case.errors.append({"stage": "extractor",
                             "error": "No financial data extracted from any document",
                             "impact": "scoring will use defaults — results may be generic"})

    return case
