import asyncio
import json
import re
import logging
from google import genai
from google.genai import types
import config
import database
from schemas import CreditCase

logger = logging.getLogger(__name__)
_client = None

def _get_client():
    global _client
    if _client is None:
        _client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _client


async def _score_primary_insights(case: CreditCase) -> CreditCase:
    pi = case.primary_insights
    obs = []
    if pi.capacity_utilization_observed_pct is not None:
        obs.append(f"Capacity observed {pi.capacity_utilization_observed_pct}% "
                   f"vs reported {pi.capacity_utilization_reported_pct or 'unknown'}%")
    if pi.machinery_condition:
        obs.append(f"Machinery: {pi.machinery_condition}")
    if pi.management_response_quality:
        obs.append(f"Mgmt response: {pi.management_response_quality}")
    if pi.succession_plan_exists is not None:
        obs.append(f"Succession plan: {'present' if pi.succession_plan_exists else 'absent'}")
    if pi.additional_observations:
        obs.append(pi.additional_observations)

    if not obs:
        pi.ai_score_adjustment = 0
        pi.ai_adjustment_reason = "No primary insights provided."
        case.primary_insights = pi
        return case

    import time
    for attempt in range(3):
        try:
            resp = _get_client().models.generate_content(
                model=config.GEMINI_MODEL,
                contents=(
                    f"Senior Indian credit analyst. Score these site-visit observations "
                    f"for {case.company_name}:\n{chr(10).join(obs)}\n\n"
                    f"Return JSON only: "
                    f'{{ "score_adjustment": <int -25 to +10>, "reason": "<one sentence>" }}'
                ),
                config=types.GenerateContentConfig(
                    response_mime_type="application/json", temperature=0.1)
            )
            result = json.loads(re.sub(r"```json\s*|\s*```", "", resp.text).strip())
            pi.ai_score_adjustment  = int(result.get("score_adjustment", 0))
            pi.ai_adjustment_reason = result.get("reason", "")
            break
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "quota" in err_str.lower():
                wait_time = (attempt + 1) * 10
                logger.warning(f"Primary insights rate limited (attempt {attempt+1}), waiting {wait_time}s...")
                time.sleep(wait_time)
            else:
                logger.error(f"Primary insight scoring failed: {e}")
                pi.ai_score_adjustment  = 0
                pi.ai_adjustment_reason = "Could not process primary insights."
                break

    case.primary_insights = pi
    return case


async def run_pipeline(case: CreditCase) -> CreditCase:
    from pipeline.ingestor    import ingest_documents
    from pipeline.extractor   import extract_financials
    from pipeline.gst_validator import run_gst_bank_checks
    from agents.research      import run_all_research_agents
    from pipeline.scorer      import compute_all_scores
    from engine.decision      import generate_decision
    from engine.cam_generator import generate_cam

    async def stage(name: str, fn, *args):
        nonlocal case
        case.pipeline_stage = name
        database.save_case(case)
        logger.info(f"▶ Stage: {name}")
        try:
            result = fn(*args)
            case = await result if asyncio.iscoroutine(result) else result
        except Exception as e:
            logger.error(f"Stage {name} error: {e}", exc_info=True)
            case.errors.append({"stage": name, "error": str(e)})
        return case

    await stage("INGESTING",         ingest_documents,          case)
    await stage("EXTRACTING",        extract_financials,         case)
    await stage("VALIDATING",        run_gst_bank_checks,        case)
    await stage("RESEARCHING",       run_all_research_agents,    case)
    await stage("PRIMARY_INSIGHTS",  _score_primary_insights,    case)
    await stage("SCORING",           compute_all_scores,         case)
    await stage("DECIDING",          generate_decision,          case)
    await stage("GENERATING_CAM",    generate_cam,               case)

    case.pipeline_stage = "COMPLETE"
    database.save_case(case)
    logger.info(f"✅ Pipeline complete for {case.case_id}")
    return case
