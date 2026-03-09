import uuid
import os
import logging
from datetime import datetime
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import aiofiles

import config
import database
from schemas import CreditCase, CreateCaseRequest, PrimaryInsightRequest, PrimaryInsights
from pipeline.orchestrator import run_pipeline
from pipeline.ingestor import classify_document

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s"
)
logger = logging.getLogger(__name__)

database.init_db()

app = FastAPI(title="Intelli-Credit API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def root():
    return FileResponse("static/index.html")


@app.post("/api/cases", summary="Create a new credit case")
async def create_case(req: CreateCaseRequest):
    case = CreditCase(
        case_id=str(uuid.uuid4()),
        company_name=req.company_name,
        company_cin=req.company_cin,
        credit_officer_id=req.credit_officer_id,
        created_at=datetime.now().isoformat(),
    )
    database.save_case(case)
    return {"case_id": case.case_id, "message": "Case created"}


@app.post("/api/cases/{case_id}/documents", summary="Upload a document")
async def upload_document(
    case_id: str,
    file: UploadFile = File(...),
    doc_type: str = Form(default="unknown"),
):
    case = database.get_case(case_id)
    if not case:
        raise HTTPException(404, "Case not found")

    classified = classify_document(file.filename or "", doc_type)
    dest = os.path.join(config.UPLOAD_DIR,
                        f"{case_id}_{classified}_{file.filename}")
    async with aiofiles.open(dest, "wb") as f:
        await f.write(await file.read())

    case.raw_documents[classified] = dest
    database.save_case(case)
    return {"doc_type": classified, "file": dest}


@app.post("/api/cases/{case_id}/primary-insights")
async def add_primary_insights(case_id: str, insights: PrimaryInsightRequest):
    case = database.get_case(case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    case.primary_insights = PrimaryInsights(**insights.model_dump())
    database.save_case(case)
    return {"message": "Primary insights saved"}


@app.post("/api/cases/{case_id}/analyze", summary="Start AI analysis pipeline")
async def analyze_case(case_id: str, background_tasks: BackgroundTasks):
    case = database.get_case(case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    if case.pipeline_stage not in ("CREATED", "COMPLETE", "ERROR"):
        return {"message": f"Already running: {case.pipeline_stage}"}
    background_tasks.add_task(_pipeline_task, case_id)
    return {"message": "Analysis started", "case_id": case_id}


async def _pipeline_task(case_id: str):
    case = database.get_case(case_id)
    if not case:
        return
    try:
        await run_pipeline(case)
    except Exception as e:
        logger.error(f"Pipeline failed for {case_id}: {e}")
        case = database.get_case(case_id)
        if case:
            case.pipeline_stage = "ERROR"
            case.errors.append({"stage": "pipeline", "error": str(e)})
            database.save_case(case)


@app.get("/api/cases/{case_id}/status")
async def get_status(case_id: str):
    case = database.get_case(case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    return {
        "case_id":   case_id,
        "stage":     case.pipeline_stage,
        "errors":    case.errors,
        "has_cam":   bool(case.cam_path and os.path.exists(case.cam_path)),
    }


@app.get("/api/cases/{case_id}")
async def get_case(case_id: str):
    case = database.get_case(case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    return case.model_dump()


@app.get("/api/cases/{case_id}/cam", summary="Download CAM document")
async def download_cam(case_id: str):
    case = database.get_case(case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    if not case.cam_path or not os.path.exists(case.cam_path):
        raise HTTPException(404, "CAM not yet generated — run analysis first")
    return FileResponse(
        case.cam_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=os.path.basename(case.cam_path),
    )


@app.get("/api/cases")
async def list_cases():
    return database.list_cases()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
