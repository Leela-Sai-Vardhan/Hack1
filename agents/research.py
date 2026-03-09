import asyncio
import json
import re
import logging
from typing import List
from google import genai
from google.genai import types
from schemas import CreditCase, RiskFlag
import config

logger = logging.getLogger(__name__)
_client = None

def _get_client():
    global _client
    if _client is None:
        _client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _client


def _ddg(query: str, n: int = 5) -> List[dict]:
    """DuckDuckGo search — free, no API key needed."""
    try:
        # Try new package name first, then fall back to old
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
        return list(DDGS().text(query, max_results=n))
    except Exception as e:
        logger.warning(f"DDG search failed for '{query}': {e}")
        return []


def _gemini(prompt: str) -> dict:
    import time
    for attempt in range(3):
        try:
            resp = _get_client().models.generate_content(
                model=config.GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json", temperature=0.15))
            return json.loads(re.sub(r"```json\s*|\s*```", "", resp.text).strip())
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "quota" in err_str.lower() or "rate" in err_str.lower():
                wait_time = (attempt + 1) * 10
                logger.warning(f"Gemini rate limit (attempt {attempt+1}), waiting {wait_time}s...")
                time.sleep(wait_time)
            else:
                logger.error(f"Gemini research call failed: {e}")
                if attempt < 2:
                    time.sleep(2)
    return {}


async def _news_agent(company: str) -> dict:
    queries = [
        f"{company} fraud default NPA India",
        f"{company} news 2024 2025",
        f"{company} NCLT insolvency India",
    ]
    snippets = []
    for q in queries:
        for r in _ddg(q, 4):
            snippets.append(f"Title: {r.get('title','')}\nSnippet: {r.get('body','')[:300]}")

    logger.info(f"News agent: {len(snippets)} snippets found for '{company}'")

    # Always call Gemini — even with no snippets it can reason about the company
    news_context = "\n---\n".join(snippets[:15]) if snippets else "No web results found."
    result = _gemini(f"""You are a credit risk analyst. Analyze the Indian company '{company}' for credit risk.
Web search results (may be empty — use your knowledge if so):
{news_context}

Instructions:
- If no web results, use your knowledge about this company and Indian market context
- Be specific to this company, not generic
- Infer the sector from company name/context

Return JSON only:
{{"risk_level":"HIGH"|"MEDIUM"|"LOW","summary":"2-3 specific sentences about {company}","critical_findings":["specific finding 1","specific finding 2"],"sector":"inferred sector name"}}""")

    return {
        "news_summary": result.get("summary", f"No significant negative news found for {company}."),
        "news_risk_level": result.get("risk_level", "LOW"),
        "critical_findings": result.get("critical_findings", []),
        "sector": result.get("sector", ""),
    }


async def _litigation_agent(company: str) -> dict:
    snippets = []
    for q in [f"{company} NCLT insolvency case India",
              f"{company} court case legal dispute DRT"]:
        for r in _ddg(q, 3):
            snippets.append(f"{r.get('title','')}: {r.get('body','')[:250]}")

    logger.info(f"Litigation agent: {len(snippets)} snippets found for '{company}'")
    lit_context = "\n---\n".join(snippets[:10]) if snippets else "No web results found."

    result = _gemini(f"""You are a legal risk analyst for Indian credit. Analyze litigation risk for '{company}'.
Web search results (use your knowledge if empty):
{lit_context}

Return JSON only:
{{"cases":[{{"type":"NCLT/Civil/DRT","description":"brief description","amount_lakhs":0,"status":"pending/resolved"}}],
  "total_exposure_lakhs":0,"has_insolvency":false}}""")

    cases = result.get("cases", [])
    if result.get("has_insolvency") and not any(
            "insolvency" in c.get("type","").lower() for c in cases):
        cases.append({"type":"NCLT/Insolvency","description":"Insolvency proceedings detected",
                      "amount_lakhs":0,"status":"pending"})
    return {
        "litigation_cases": cases,
        "litigation_total_exposure_lakhs": float(result.get("total_exposure_lakhs", 0)),
    }


async def _promoter_agent(company: str) -> dict:
    snippets = []
    for q in [f"{company} promoter director fraud default",
              f"{company} management ED PMLA case"]:
        for r in _ddg(q, 3):
            snippets.append(f"{r.get('title','')}: {r.get('body','')[:200]}")

    logger.info(f"Promoter agent: {len(snippets)} snippets found for '{company}'")
    prom_context = "\n---\n".join(snippets[:8]) if snippets else "No web results found."

    result = _gemini(f"""You are a promoter integrity analyst. Assess the promoters/directors of Indian company '{company}'.
Web search results (use your knowledge if empty):
{prom_context}

Return JSON only:
{{"integrity_score":65,"flags":["specific concern if any"],"has_din_issues":false,"has_pmla_cases":false}}""")

    score = result.get("integrity_score", 65)
    flags = result.get("flags", [])
    if result.get("has_din_issues"):
        score = min(score, 40)
        flags.insert(0, "Possible DIN disqualification / director issues found")
    if result.get("has_pmla_cases"):
        score = min(score, 30)
        flags.insert(0, "PMLA / ED case references found in public domain")
    return {"promoter_integrity_score": max(0, min(100, score)),
            "promoter_flags": flags[:5]}


async def _regulatory_agent(sector: str) -> dict:
    if not sector:
        return {"regulatory_risks": [], "sector_outlook": "NEUTRAL"}
    snippets = [f"{r.get('title','')}: {r.get('body','')[:200]}"
                for r in _ddg(f"RBI SEBI {sector} India regulations 2025 NPA", 3)]
    if not snippets:
        return {"regulatory_risks": [], "sector_outlook": "NEUTRAL"}
    result = _gemini(f"""Regulatory risks for {sector} sector in India.
Sources:
{"---".join(snippets[:5])}

Return JSON:
{{"regulatory_risks":["r1","r2"],"sector_outlook":"POSITIVE"|"NEUTRAL"|"NEGATIVE"}}""")
    return {"regulatory_risks": result.get("regulatory_risks", [])[:3],
            "sector_outlook": result.get("sector_outlook", "NEUTRAL")}


async def run_all_research_agents(case: CreditCase) -> CreditCase:
    import time
    cname = case.company_name
    sector = case.research_findings.sector or ""

    # Run agents SEQUENTIALLY with delays to avoid Gemini rate limits
    logger.info(f"Starting research agents for '{cname}'...")

    try:
        news_r = await _news_agent(cname)
    except Exception as e:
        logger.error(f"News agent error: {e}")
        news_r = e

    time.sleep(3)  # Delay between API calls

    try:
        lit_r = await _litigation_agent(cname)
    except Exception as e:
        logger.error(f"Litigation agent error: {e}")
        lit_r = e

    time.sleep(3)

    try:
        prom_r = await _promoter_agent(cname)
    except Exception as e:
        logger.error(f"Promoter agent error: {e}")
        prom_r = e

    time.sleep(3)

    # Use sector from news agent if available
    if isinstance(news_r, dict) and news_r.get("sector"):
        sector = news_r["sector"]

    try:
        reg_r = await _regulatory_agent(sector)
    except Exception as e:
        logger.error(f"Regulatory agent error: {e}")
        reg_r = e

    rf = case.research_findings

    if isinstance(news_r, dict):
        rf.news_summary     = news_r.get("news_summary", rf.news_summary)
        rf.news_risk_level  = news_r.get("news_risk_level", rf.news_risk_level)
        rf.sector           = news_r.get("sector", rf.sector)
        for finding in news_r.get("critical_findings", []):
            sev = "HIGH" if any(kw in finding.lower() for kw in
                                ["fraud","default","scam","insolvency"]) else "MEDIUM"
            case.risk_flags.append(RiskFlag(severity=sev, source="news_agent",
                                            description=finding))

    if isinstance(lit_r, dict):
        rf.litigation_cases = lit_r.get("litigation_cases", [])
        rf.litigation_total_exposure_lakhs = lit_r.get("litigation_total_exposure_lakhs", 0.0)
        exp = rf.litigation_total_exposure_lakhs
        if exp > 500:
            case.risk_flags.append(RiskFlag(severity="HIGH", source="litigation_agent",
                description=f"Total litigation exposure ₹{exp:.0f}L across "
                            f"{len(rf.litigation_cases)} cases.",
                supporting_data={"cases": rf.litigation_cases[:3]}))
        elif exp > 100:
            case.risk_flags.append(RiskFlag(severity="MEDIUM", source="litigation_agent",
                description=f"Litigation exposure ₹{exp:.0f}L."))
        if any("insolvency" in c.get("type","").lower() for c in rf.litigation_cases):
            case.risk_flags.append(RiskFlag(severity="HIGH", source="litigation_agent",
                description="Active NCLT / Insolvency proceedings detected."))

    if isinstance(prom_r, dict):
        rf.promoter_integrity_score = prom_r.get("promoter_integrity_score", rf.promoter_integrity_score)
        rf.promoter_flags           = prom_r.get("promoter_flags", [])
        if rf.promoter_integrity_score < 40:
            case.risk_flags.append(RiskFlag(severity="HIGH", source="promoter_agent",
                description=f"Low promoter integrity score ({rf.promoter_integrity_score}/100). "
                            f"{'; '.join(rf.promoter_flags[:2])}"))

    if isinstance(reg_r, dict):
        rf.regulatory_risks = reg_r.get("regulatory_risks", [])
        rf.sector_outlook   = reg_r.get("sector_outlook", "NEUTRAL")

    case.research_findings = rf
    return case
