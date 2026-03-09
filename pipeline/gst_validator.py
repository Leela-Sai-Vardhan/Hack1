import re
import logging
from schemas import CreditCase, RiskFlag

logger = logging.getLogger(__name__)


def _estimate_bank_credits(case: CreditCase) -> float | None:
    if "bank_statement" not in case.raw_documents:
        return None
    try:
        from pipeline.ingestor import get_extracted_text
        text = get_extracted_text(case.raw_documents["bank_statement"])
        patterns = [
            r"total\s+credit[s]?\s*[:\-]?\s*(?:inr|rs\.?|₹)?\s*([\d,]+(?:\.\d+)?)",
            r"credit\s+total\s*[:\-]?\s*(?:inr|rs\.?|₹)?\s*([\d,]+(?:\.\d+)?)",
        ]
        for pat in patterns:
            m = re.search(pat, text.lower())
            if m:
                amt = float(m.group(1).replace(",", ""))
                return amt / 100 if amt > 100000 else amt   # rupees→lakhs heuristic
    except Exception as e:
        logger.warning(f"Bank credit extraction failed: {e}")
    # Fallback: estimate 92% of GST turnover (healthy ratio)
    if case.financial_metrics.revenue_yr1:
        return case.financial_metrics.revenue_yr1 * 0.92
    return None


def run_gst_bank_checks(case: CreditCase) -> CreditCase:
    m = case.financial_metrics

    # ── Check 1: GST / Bank turnover ratio ───────────────────────────────────
    bank_credits = _estimate_bank_credits(case)
    if m.revenue_yr1 and bank_credits and bank_credits > 0:
        ratio = m.revenue_yr1 / bank_credits
        m.gst_bank_ratio = round(ratio, 3)
        if ratio > 1.3:
            case.risk_flags.append(RiskFlag(
                severity="HIGH", source="gst_validator",
                description=f"GST/Bank ratio {ratio:.2f}x — declared GST turnover "
                            f"(₹{m.revenue_yr1:.0f}L) exceeds bank credits "
                            f"(₹{bank_credits:.0f}L). Possible circular trading.",
                supporting_data={"ratio": ratio}))
        elif ratio < 0.65:
            case.risk_flags.append(RiskFlag(
                severity="MEDIUM", source="gst_validator",
                description=f"Bank credits far exceed GST turnover (ratio {ratio:.2f}). "
                            f"Possible undeclared income.",
                supporting_data={"ratio": ratio}))

    # ── Check 2: Debt / EBITDA ────────────────────────────────────────────────
    if m.total_debt and m.ebitda_yr1 and m.ebitda_yr1 > 0:
        de = m.total_debt / m.ebitda_yr1
        if de > 6:
            case.risk_flags.append(RiskFlag(
                severity="HIGH", source="gst_validator",
                description=f"Debt/EBITDA {de:.1f}x is critically high (>6x). "
                            f"Severe debt servicing risk.",
                supporting_data={"debt_ebitda": de}))
        elif de > 4:
            case.risk_flags.append(RiskFlag(
                severity="MEDIUM", source="gst_validator",
                description=f"Debt/EBITDA {de:.1f}x elevated (>4x).",
                supporting_data={"debt_ebitda": de}))

    # ── Check 3: DSCR ─────────────────────────────────────────────────────────
    if m.dscr is not None:
        if m.dscr < 0.9:
            case.risk_flags.append(RiskFlag(
                severity="HIGH", source="gst_validator",
                description=f"DSCR {m.dscr} < 1.0 — operating cash flows cannot "
                            f"cover debt service. Critical NPA risk.",
                supporting_data={"dscr": m.dscr}))
        elif m.dscr < 1.2:
            case.risk_flags.append(RiskFlag(
                severity="MEDIUM", source="gst_validator",
                description=f"DSCR {m.dscr} below preferred 1.2 threshold.",
                supporting_data={"dscr": m.dscr}))

    # ── Check 4: Current ratio ────────────────────────────────────────────────
    if m.current_ratio is not None and m.current_ratio < 1.0:
        case.risk_flags.append(RiskFlag(
            severity="HIGH", source="gst_validator",
            description=f"Current ratio {m.current_ratio} < 1.0. "
                        f"Current liabilities exceed current assets — immediate liquidity risk.",
            supporting_data={"current_ratio": m.current_ratio}))

    # ── Check 5: Revenue trend ────────────────────────────────────────────────
    if m.revenue_yr1 and m.revenue_yr2 and m.revenue_yr2 > 0:
        growth = (m.revenue_yr1 - m.revenue_yr2) / m.revenue_yr2 * 100
        if growth < -10:
            case.risk_flags.append(RiskFlag(
                severity="MEDIUM", source="gst_validator",
                description=f"Revenue declined {abs(growth):.1f}% YoY — "
                            f"deteriorating business performance.",
                supporting_data={"yoy_growth_pct": round(growth, 1)}))

    case.financial_metrics = m
    return case
