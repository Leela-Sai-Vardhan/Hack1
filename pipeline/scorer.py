import logging
from schemas import CreditCase, ScoreBreakdown

logger = logging.getLogger(__name__)

# (feature, weight, [(threshold, score)...], higher_is_better, description)
_RULES = [
    ("dscr",              20, [(2.0,100),(1.5,85),(1.2,70),(1.0,50),(0.8,25),(0.0,5)],  True,  "Debt Service Coverage Ratio"),
    ("debt_to_equity",    15, [(1.0,100),(2.0,80),(3.0,60),(4.0,35),(5.0,10),(99,0)],   False, "Debt-to-Equity Ratio"),
    ("current_ratio",     10, [(2.0,100),(1.5,85),(1.2,65),(1.0,40),(0.5,15),(0.0,5)],  True,  "Current Ratio"),
    ("ebitda_margin_pct", 15, [(20,100),(15,80),(10,60),(5,35),(0,10),(-99,0)],          True,  "EBITDA Margin %"),
    ("revenue_cagr_3yr",  10, [(20,100),(15,80),(10,65),(5,45),(0,25),(-99,5)],          True,  "3-Year Revenue CAGR %"),
    ("interest_coverage", 10, [(5.0,100),(3.0,80),(2.0,60),(1.5,40),(1.0,20),(0.0,0)],  True,  "Interest Coverage Ratio"),
    ("gst_bank_ratio",    10, [],                                                        None,  "GST / Bank Ratio"),
    ("bounce_rate",        5, [(0.0,100),(0.02,80),(0.05,50),(0.10,20),(1.0,0)],         False, "Cheque Bounce Rate"),
    ("od_utilization_pct", 5, [(0.5,100),(0.7,75),(0.85,50),(0.95,25),(1.0,0)],          False, "OD Utilisation %"),
]
_TOTAL_WEIGHT = sum(r[1] for r in _RULES)


def _band_score(value: float, bands: list, higher: bool) -> float:
    if higher:
        for thr, sc in sorted(bands, reverse=True):
            if value >= thr: return float(sc)
        return float(bands[-1][1])
    else:
        for thr, sc in sorted(bands):
            if value <= thr: return float(sc)
        return float(bands[-1][1])


def _gst_bank_score(ratio: float) -> float:
    if 0.85 <= ratio <= 1.15: return 100.0
    if 0.75 <= ratio < 0.85 or 1.15 < ratio <= 1.30: return 70.0
    if 1.30 < ratio <= 1.50: return 35.0
    if ratio > 1.50: return 10.0
    return 40.0


def _financial_score(m, has_docs: bool) -> tuple:
    weighted_sum = 0.0
    drivers = []
    ratios_used = {}

    for (feat, wt, bands, hib, desc) in _RULES:
        value = getattr(m, feat, None)
        ratios_used[feat] = value

        if value is None:
            # If no documents uploaded: use neutral 50 (truly unknown)
            # If documents uploaded but metric not found: mild penalty (35)
            sub = 50.0 if not has_docs else 35.0
        elif feat == "gst_bank_ratio":
            sub = _gst_bank_score(value)
        else:
            sub = _band_score(value, bands, hib)

        impact = (sub - 50) * wt / _TOTAL_WEIGHT
        weighted_sum += sub * (wt / _TOTAL_WEIGHT)
        drivers.append({
            "feature": feat,
            "description": desc,
            "value": f"{value:.3f}" if value is not None else "not extracted",
            "sub_score": round(sub, 1),
            "weight": wt,
            "impact": round(impact, 2),
            "direction": "positive" if impact > 0 else ("negative" if impact < 0 else "neutral"),
        })

    drivers.sort(key=lambda x: abs(x["impact"]), reverse=True)
    return round(weighted_sum, 1), drivers, ratios_used


def _research_score(findings, risk_flags) -> float:
    score = 100.0
    score -= {"HIGH": 30, "MEDIUM": 15, "LOW": 0, "UNKNOWN": 5}.get(findings.news_risk_level, 5)

    exp = findings.litigation_total_exposure_lakhs
    score -= 30 if exp > 500 else (15 if exp > 100 else (5 if exp > 0 else 0))

    score = score * 0.60 + findings.promoter_integrity_score * 0.40
    score -= len(findings.regulatory_risks) * 5
    score += {"POSITIVE": 5, "NEUTRAL": 0, "NEGATIVE": -10}.get(findings.sector_outlook, 0)
    score -= sum(5 for f in risk_flags
                 if f.severity == "HIGH" and f.source in
                 ["news_agent", "litigation_agent", "promoter_agent"])
    return max(0.0, min(100.0, round(score, 1)))


def _map_rating(score: float) -> str:
    for thr, rtg in [(88,"AAA"),(80,"AA"),(72,"A"),(62,"BBB"),(50,"BB"),(38,"B")]:
        if score >= thr: return rtg
    return "D"


def compute_all_scores(case: CreditCase) -> CreditCase:
    has_docs = bool(case.raw_documents)
    fin_score, drivers, ratios = _financial_score(case.financial_metrics, has_docs)
    res_score = _research_score(case.research_findings, case.risk_flags)

    pi_base = 70 + (case.primary_insights.ai_score_adjustment * 2)
    primary_score = max(0.0, min(100.0, float(pi_base)))

    final = fin_score * 0.40 + res_score * 0.35 + primary_score * 0.25

    # Hard overrides
    high_flags = [f for f in case.risk_flags if f.severity == "HIGH"]
    if len(high_flags) >= 3:
        final = min(final, 38.0)
    if any("insolvency" in f.description.lower() for f in case.risk_flags):
        final = min(final, 25.0)

    rating = _map_rating(final)

    # Human-readable explanation
    neg = [d for d in drivers if d["direction"] == "negative"][:3]
    pos = [d for d in drivers if d["direction"] == "positive"][:2]
    expl_lines = [f"Financial {fin_score}/100 | Research {res_score}/100 | Primary {primary_score}/100"]
    expl_lines += [f"  ✗ {d['description']}: {d['value']} (–{abs(d['impact']):.1f}pts)" for d in neg]
    expl_lines += [f"  ✓ {d['description']}: {d['value']} (+{d['impact']:.1f}pts)" for d in pos]

    case.score_breakdown = ScoreBreakdown(
        financial_score=fin_score,
        research_score=res_score,
        primary_insight_score=primary_score,
        final_score=round(final, 1),
        risk_rating=rating,
        score_drivers=drivers,
        financial_ratios_used={k: v for k, v in ratios.items() if v is not None},
        decision_explanation="\n".join(expl_lines),
    )
    return case
