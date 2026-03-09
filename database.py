import sqlite3
import logging
from typing import Optional, List
from schemas import CreditCase
import config

logger = logging.getLogger(__name__)


def init_db():
    conn = sqlite3.connect(config.DATABASE_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS cases (
        case_id       TEXT PRIMARY KEY,
        company_name  TEXT NOT NULL,
        created_at    TEXT,
        pipeline_stage TEXT,
        data          TEXT NOT NULL
    )""")
    conn.commit()
    conn.close()
    logger.info("Database initialised")


def save_case(case: CreditCase):
    try:
        conn = sqlite3.connect(config.DATABASE_PATH)
        c = conn.cursor()
        c.execute(
            "INSERT OR REPLACE INTO cases VALUES (?, ?, ?, ?, ?)",
            (case.case_id, case.company_name, case.created_at,
             case.pipeline_stage, case.model_dump_json())
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Failed to save case {case.case_id}: {e}")


def get_case(case_id: str) -> Optional[CreditCase]:
    try:
        conn = sqlite3.connect(config.DATABASE_PATH)
        c = conn.cursor()
        c.execute("SELECT data FROM cases WHERE case_id = ?", (case_id,))
        row = c.fetchone()
        conn.close()
        if row:
            return CreditCase.model_validate_json(row[0])
    except Exception as e:
        logger.error(f"Failed to get case {case_id}: {e}")
    return None


def list_cases() -> List[dict]:
    try:
        conn = sqlite3.connect(config.DATABASE_PATH)
        c = conn.cursor()
        c.execute("""SELECT case_id, company_name, created_at, pipeline_stage
                     FROM cases ORDER BY created_at DESC LIMIT 100""")
        rows = c.fetchall()
        conn.close()
        return [{"case_id": r[0], "company_name": r[1],
                 "created_at": r[2], "stage": r[3]} for r in rows]
    except Exception as e:
        logger.error(f"Failed to list cases: {e}")
        return []
