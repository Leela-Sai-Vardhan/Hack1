import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyDwT9RVxI0xUoExGlUk-tyDQbwVLX85Pvo")
GEMINI_MODEL   = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
DATABASE_PATH  = os.getenv("DATABASE_PATH", "intellicredit.db")
OUTPUT_DIR     = os.getenv("OUTPUT_DIR", "outputs")
UPLOAD_DIR     = os.getenv("UPLOAD_DIR", "uploads")
BASE_MCLR      = float(os.getenv("BASE_MCLR", "9.0"))

for d in [OUTPUT_DIR, UPLOAD_DIR, "static"]:
    os.makedirs(d, exist_ok=True)
