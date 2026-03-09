import logging
from google import genai
from google.genai import types
from schemas import CreditCase, CreditDecision
import config

logger = logging.getLogger(__name__)
_client = None

def _get_client():
    global _client
    if _client is None:
        _client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _client

_SPREAD = {"AAA":50,"AA":75,"A":100,"BBB":175,"BB":300,"B":450,"D":None}


def _map_rating(score: float) -> str:
    for thr, rtg in [(88,"AAA"),(80,"AA"),(72,"A"),(62,"BBB"),(50,"BB"),(38,"B")]:
        if score >= thr: return rtg
    return "D"


def _max_limit(m) -> float:
    limits = []
    if m.revenue_yr1 and m.revenue_yr1 > 0:
        limits.append(m.revenue_yr1 * 0.25 / 100)          # Nayak Committee (lakhs→crores)
    if m.dscr and m.total_debt and m.dscr > 1.0 and m.total_debt > 0:
        limits.append((m.dscr - 1.0) * m.total_debt * 0.12 / 100)
    return round(min(limits) if limits else 5.0, 2)


async def generate_decision(case: CreditCase) -> CreditCase:
    sb   = case.score_breakdown
    m    = case.financial_metrics
    dec  = CreditDecision(risk_rating=sb.risk_rating)

    spread = _SPREAD.get(sb.risk_rating)
    if spread:
        dec.mclr_spread_bps   = spread
        dec.effective_rate_pct = round(config.BASE_MCLR + spread / 100, 2)

    max_lim = _max_limit(m)
    score   = sb.final_score

    if sb.risk_rating == "D" or score < 38:
        dec.recommendation = "DECLINE"
        dec.rejection_reasons = _rejection_reasons(case)
    elif sb.risk_rating in ("BB", "B") or score < 55:
        dec.recommendation      = "CONDITIONAL"
        dec.recommended_limit_cr = round(max_lim * 0.60, 2)
        dec.key_conditions       = _conditions(case)
    else:
        mult = {"BBB":0.75,"A":0.90,"AA":0.95,"AAA":1.0}.get(sb.risk_rating, 0.75)
        dec.recommendation      = "APPROVE"
        dec.recommended_limit_cr = round(max_lim * mult, 2)

    # Counterfactual via Gemini
    try:
        neg = [d for d in sb.score_drivers if d["direction"] == "negative"][:3]
        hi  = [f.description for f in case.risk_flags if f.severity == "HIGH"][:2]
        prompt = (f"Loan for {case.company_name}: {dec.recommendation}, "
                  f"score {score}/100 ({sb.risk_rating}).\n"
                  f"Negative drivers: {neg}\nHigh flags: {hi}\n"
                  f"In 2 sentences: (1) main reason for decision, "
                  f"(2) specific improvements to change outcome. "
                  f"Use numbers and Indian banking terms (DSCR, MCLR, NPA).")
        resp = _get_client().models.generate_content(
            model=config.GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.3))
        sb.counterfactual = resp.text.strip()
    except Exception as e:
        sb.counterfactual = sb.decision_explanation

    case.score_breakdown = sb
    case.decision        = dec
    return case


def _rejection_reasons(case: CreditCase) -> list:
    reasons = [f.description for f in case.risk_flags if f.severity == "HIGH"]
    m = case.financial_metrics
    if m.dscr and m.dscr < 0.9:
        reasons.append(f"DSCR {m.dscr} critically below 1.0 minimum threshold")
    if m.debt_to_equity and m.debt_to_equity > 5:
        reasons.append(f"Debt/Equity {m.debt_to_equity}x is unsustainably high")
    return reasons[:5]


def _conditions(case: CreditCase) -> list:
    conds = []
    m  = case.financial_metrics
    rf = case.research_findings
    pi = case.primary_insights
    if case.score_breakdown.risk_rating == "BB":
        conds.append("Additional collateral top-up required (minimum 125% coverage)")
    if m.gst_bank_ratio and m.gst_bank_ratio > 1.2:
        conds.append("GST-Bank reconciliation statement required for last 12 months")
    if rf.litigation_total_exposure_lakhs > 100:
        conds.append("Legal opinion on pending litigation required before disbursal")
    if pi.succession_plan_exists is False:
        conds.append("Key-man insurance mandatory for principal promoters")
    if m.current_ratio and m.current_ratio < 1.2:
        conds.append("Current ratio improvement plan required within 6 months")
    conds.append("Quarterly financial covenant monitoring mandatory")
    return conds[:5]
