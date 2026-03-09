from pydantic import BaseModel
from typing import Optional, List, Dict, Any


class RiskFlag(BaseModel):
    severity: str = "LOW"          # HIGH | MEDIUM | LOW
    source: str = ""
    description: str = ""
    supporting_data: Dict[str, Any] = {}


class FinancialMetrics(BaseModel):
    # Revenue in INR Lakhs
    revenue_yr1: Optional[float] = None
    revenue_yr2: Optional[float] = None
    revenue_yr3: Optional[float] = None
    ebitda_yr1: Optional[float] = None
    ebitda_yr2: Optional[float] = None
    ebitda_yr3: Optional[float] = None
    pat_yr1: Optional[float] = None
    total_debt: Optional[float] = None
    total_equity: Optional[float] = None
    current_assets: Optional[float] = None
    current_liabilities: Optional[float] = None
    interest_expense: Optional[float] = None
    depreciation: Optional[float] = None
    capex: Optional[float] = None
    # Computed ratios
    dscr: Optional[float] = None
    debt_to_equity: Optional[float] = None
    current_ratio: Optional[float] = None
    ebitda_margin_pct: Optional[float] = None
    revenue_cagr_3yr: Optional[float] = None
    interest_coverage: Optional[float] = None
    # GST signals
    gst_bank_ratio: Optional[float] = None
    itc_mismatch_pct: Optional[float] = None
    circular_trade_score: int = 0
    # Banking behaviour
    bounce_rate: Optional[float] = None
    od_utilization_pct: Optional[float] = None
    extraction_confidence: str = "LOW"
    caveats: str = ""


class ResearchFindings(BaseModel):
    news_summary: str = "Research not yet performed."
    news_risk_level: str = "UNKNOWN"   # HIGH | MEDIUM | LOW | UNKNOWN
    litigation_cases: List[Dict] = []
    litigation_total_exposure_lakhs: float = 0.0
    promoter_integrity_score: int = 60
    promoter_flags: List[str] = []
    regulatory_risks: List[str] = []
    sector_outlook: str = "NEUTRAL"    # POSITIVE | NEUTRAL | NEGATIVE
    sector: str = ""


class PrimaryInsights(BaseModel):
    capacity_utilization_observed_pct: Optional[float] = None
    capacity_utilization_reported_pct: Optional[float] = None
    worker_count_observed: Optional[int] = None
    inventory_condition: Optional[str] = None
    machinery_condition: Optional[str] = None
    succession_plan_exists: Optional[bool] = None
    promoter_skin_in_game: Optional[str] = None
    management_response_quality: Optional[str] = None
    additional_observations: str = ""
    ai_score_adjustment: int = 0
    ai_adjustment_reason: str = ""


class ScoreBreakdown(BaseModel):
    financial_score: float = 0.0
    research_score: float = 0.0
    primary_insight_score: float = 70.0
    final_score: float = 0.0
    risk_rating: str = "UNRATED"
    score_drivers: List[Dict] = []
    financial_ratios_used: Dict[str, Any] = {}
    counterfactual: str = ""
    decision_explanation: str = ""


class CreditDecision(BaseModel):
    recommendation: str = "PENDING"   # APPROVE | CONDITIONAL | DECLINE
    recommended_limit_cr: Optional[float] = None
    risk_rating: str = "UNRATED"
    mclr_spread_bps: int = 0
    effective_rate_pct: float = 0.0
    key_conditions: List[str] = []
    rejection_reasons: List[str] = []


class CreditCase(BaseModel):
    case_id: str
    company_name: str
    company_cin: str = ""
    credit_officer_id: str = "officer_001"
    created_at: str = ""
    pipeline_stage: str = "CREATED"
    errors: List[Dict] = []
    raw_documents: Dict[str, str] = {}   # doc_type -> file_path
    financial_metrics: FinancialMetrics = FinancialMetrics()
    research_findings: ResearchFindings = ResearchFindings()
    primary_insights: PrimaryInsights = PrimaryInsights()
    risk_flags: List[RiskFlag] = []
    score_breakdown: ScoreBreakdown = ScoreBreakdown()
    decision: CreditDecision = CreditDecision()
    cam_path: Optional[str] = None


# ── API Request models ────────────────────────────────────────────────────────
class CreateCaseRequest(BaseModel):
    company_name: str
    company_cin: str = ""
    credit_officer_id: str = "officer_001"


class PrimaryInsightRequest(BaseModel):
    capacity_utilization_observed_pct: Optional[float] = None
    capacity_utilization_reported_pct: Optional[float] = None
    worker_count_observed: Optional[int] = None
    inventory_condition: Optional[str] = None
    machinery_condition: Optional[str] = None
    succession_plan_exists: Optional[bool] = None
    promoter_skin_in_game: Optional[str] = None
    management_response_quality: Optional[str] = None
    additional_observations: str = ""
