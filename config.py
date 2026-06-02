# ============================================
# CONFIG.PY — Central Configuration File
# Sabhi settings ek jagah!
# ============================================

import os
import sys

# ---- PATHS ----
BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR    = os.path.join(BASE_DIR, "output")
SAMPLE_DIR    = os.path.join(BASE_DIR, "sample_docs")
LOG_DIR       = os.path.join(BASE_DIR, "logs")

# Auto-create directories
for d in [OUTPUT_DIR, SAMPLE_DIR, LOG_DIR]:
    os.makedirs(d, exist_ok=True)


def load_env_file(path=None):
    """
    Load simple KEY=VALUE pairs from .env without requiring extra packages.
    Existing system environment values are kept unchanged.
    """
    env_path = path or os.path.join(BASE_DIR, ".env")
    if not os.path.exists(env_path):
        return

    with open(env_path, "r", encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                os.environ.setdefault(key, value)


load_env_file()

# ---- SUPPORTED FILE TYPES ----
SUPPORTED_FORMATS = {
    "document" : [".docx", ".txt"],
    "spreadsheet": [".xlsx", ".xls"],
    "pdf"      : [".pdf"],
    "image"    : [".jpg", ".jpeg", ".png", ".bmp", ".tiff"],
}

ALL_SUPPORTED = [ext for exts in SUPPORTED_FORMATS.values() for ext in exts]

# ---- OCR SETTINGS ----
TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"  # Windows
# TESSERACT_PATH = "/usr/bin/tesseract"  # Linux/Mac

# ---- TRANSLATION SETTINGS ----
DEFAULT_TARGET_LANGUAGE = "en"   # Always translate TO English
SUPPORTED_LANGUAGES = {
    "en": "English",
    "hi": "Hindi",
    "gu": "Gujarati",
    "mr": "Marathi",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
    "zh": "Chinese",
    "ar": "Arabic",
    "ja": "Japanese",
}

# ---- NLP FIELDS TO EXTRACT ----
EXTRACT_FIELDS = [
    "first_name",
    "surname",
    "father_name",
    "unique_id",
    "dob",
    "department",
    "email",
    "phone",
]

# ---- SUMMARIZATION ----
SUMMARY_SENTENCES = 3   # How many sentences in summary

# ---- COLORS for terminal output ----
class Colors:
    GREEN  = "\033[92m"
    RED    = "\033[91m"
    YELLOW = "\033[93m"
    BLUE   = "\033[94m"
    CYAN   = "\033[96m"
    BOLD   = "\033[1m"
    RESET  = "\033[0m"

def cprint(msg, color=Colors.RESET):
    text = f"{color}{msg}{Colors.RESET}"
    try:
        print(text)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "utf-8"
        safe_text = text.encode(encoding, errors="replace").decode(encoding, errors="replace")
        print(safe_text)
