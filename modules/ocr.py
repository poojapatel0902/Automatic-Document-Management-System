# ============================================
# MODULE 3: OCR.PY
# Image se text nikalo (Aadhar, ID cards, scanned docs)
# Uses pytesseract (primary) + EasyOCR (backup)
# ============================================

import json
import os
import re
import sys
import tempfile
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Colors, cprint, TESSERACT_PATH


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
OCR_HINT_WORDS = {
    "name", "student", "candidate", "father", "department", "email", "id",
    "enrollment", "enrolment", "registration", "program", "college", "exam",
    "marks", "statement", "stream", "seat", "result", "course", "subject",
}
NAME_LABEL_PATTERNS = (
    r"candidate'?s?\s*name",
    r"student\s*name",
    r"name\s*of\s*candidate",
)
COMMON_SURNAME_HINTS = {
    "patel", "shah", "mehta", "sharma", "singh", "parmar", "desai",
    "pandya", "trivedi", "joshi", "panchal", "prajapati", "solanki",
    "yadav", "gupta", "verma", "kumar", "chauhan", "thakor", "rawal",
    "gohil", "jain", "bhatt", "nair", "reddy", "das", "soni",
}
OCR_NAME_SKIP_WORDS = {
    "company", "here", "job", "position", "designation", "department",
    "division", "role", "email", "mail", "phone", "mobile", "contact",
    "blood", "id", "photo", "signature", "website", "www", "lorem",
    "ipsum", "sample", "gmail", "yahoo", "outlook", "hotmail", "card",
    "employee", "information", "details", "address", "barcode",
}
OCR_CONTACT_LABELS = ("id", "email", "phone", "mobile", "contact", "blood")
OCR_DEPARTMENT_LABEL_PATTERNS = (
    r"(?:department|dept|division|designation|role|job\s*position|position)\s*[:\-|]\s*([A-Za-z][A-Za-z /&.\-]+)",
)
MARKSHEET_HINT_PATTERNS = (
    r"statement\s+of\s+marks",
    r"secondary\s+sch\w*\s+certificate\s+examination",
    r"higher\s+secondary",
    r"seat\s+no",
    r"grand\s+total",
    r"percentile\s+rank",
)


# Words that act as labels at the start of a name line and should be
# stripped before evaluating whether the remaining tokens form a person name.
_SCORE_NAME_LABEL_WORDS = {
    "name", "candidate", "candidates", "student", "full",
    "employee", "of", "nameofcandidate",
}


def _correct_ocr_chars_in_name(text):
    """
    Fix common OCR character mis-reads inside extracted name strings.

    Observed confusion on Gujarat Board marksheets and similar printed docs:
      - 'oqu' → 'ooj'  (e.g. "POQUA" → "POOJA", "POQUNAM" → "POOJNAM")
        Tesseract sometimes reads the 'oj' glyph cluster as 'qu' when the
        font is slightly smeared or low-resolution.  The fix is intentionally
        scoped to the 'oqu' sequence to avoid corrupting real English words
        that contain 'qu' (e.g. "Sequel", "Unique", "Quran").
    """
    # lowercase: oqu + vowel  →  ooj + vowel
    text = re.sub(r'oqu(?=[aeiou])', 'ooj', text)
    # UPPERCASE
    text = re.sub(r'OQU(?=[AEIOU])', 'OOJ', text)
    # Mixed UPPER-lower (Poqua style)
    text = re.sub(r'(?i)oqu(?=[aeiouAEIOU])',
                  lambda m: 'OOJ' if m.group(0)[0].isupper() else 'ooj',
                  text)
    return text


def _score_ocr_text(text):
    if not text or not text.strip():
        return -1

    lowered = text.lower()
    score = len(re.findall(r"[A-Za-z0-9]", text))
    score += sum(25 for word in OCR_HINT_WORDS if word in lowered)
    score += 15 * len(re.findall(r"\b\d{4,}\b", text))
    score += 5 * len(re.findall(r"[A-Za-z]{3,}", text))
    score -= 20 * len(re.findall(r"[^\w\s]{3,}", text))
    return score


def _choose_best_ocr_result(candidates):
    best_text = ""
    best_score = -1

    for text in candidates:
        score = _score_ocr_text(text)
        if score > best_score:
            best_text = text.strip()
            best_score = score

    return best_text


def _load_image(image):
    from PIL import Image

    if isinstance(image, str):
        return Image.open(image)
    return image.copy()


def _get_resample_filter():
    from PIL import Image

    if hasattr(Image, "Resampling"):
        return Image.Resampling.LANCZOS
    return Image.LANCZOS


def _generate_ocr_variants(image):
    from PIL import ImageEnhance, ImageFilter, ImageOps

    base = image.convert("RGB")
    gray = ImageOps.autocontrast(base.convert("L"))
    high_contrast = ImageEnhance.Contrast(gray).enhance(2.4)
    sharp = high_contrast.filter(ImageFilter.SHARPEN)
    denoise = sharp.filter(ImageFilter.MedianFilter(size=3))
    binary = denoise.point(lambda p: 255 if p > 160 else 0)
    inverted_binary = ImageOps.invert(binary)

    variants = []
    resample_filter = _get_resample_filter()

    for label, variant in [
        ("base", base),
        ("sharp_gray", sharp),
        ("denoise", denoise),
        ("binary", binary),
        ("binary_invert", inverted_binary),
    ]:
        resized = variant.resize(
            (max(variant.width * 2, 1), max(variant.height * 2, 1)),
            resample_filter,
        )
        variants.append((label, resized))

    return variants


def _bbox_bounds(box):
    xs = [point[0] for point in box]
    ys = [point[1] for point in box]
    return min(xs), min(ys), max(xs), max(ys)


def _group_easyocr_rows(results):
    rows = []
    items = []

    for entry in results or []:
        if not isinstance(entry, (list, tuple)) or len(entry) < 3:
            continue

        box, text, confidence = entry[0], str(entry[1]).strip(), float(entry[2] or 0.0)
        if not text:
            continue

        x1, y1, x2, y2 = _bbox_bounds(box)
        items.append({
            "text": text,
            "confidence": confidence,
            "x1": x1,
            "y1": y1,
            "x2": x2,
            "y2": y2,
            "cy": (y1 + y2) / 2.0,
            "height": max(y2 - y1, 1),
        })

    items.sort(key=lambda item: (item["y1"], item["x1"]))

    for item in items:
        matched_row = None
        for row in rows:
            tolerance = max(16, row["height"] * 0.7, item["height"] * 0.7)
            if abs(item["cy"] - row["cy"]) <= tolerance:
                matched_row = row
                break

        if not matched_row:
            matched_row = {
                "items": [],
                "cy": item["cy"],
                "height": item["height"],
                "y1": item["y1"],
                "y2": item["y2"],
            }
            rows.append(matched_row)

        matched_row["items"].append(item)
        matched_row["cy"] = (
            sum(entry["cy"] for entry in matched_row["items"]) / len(matched_row["items"])
        )
        matched_row["height"] = max(entry["height"] for entry in matched_row["items"])
        matched_row["y1"] = min(entry["y1"] for entry in matched_row["items"])
        matched_row["y2"] = max(entry["y2"] for entry in matched_row["items"])

    finalized = []
    for row in rows:
        row_items = sorted(row["items"], key=lambda item: item["x1"])
        text = " ".join(item["text"] for item in row_items).strip()
        if not text:
            continue

        finalized.append({
            "items": row_items,
            "text": text,
            "confidence": sum(item["confidence"] for item in row_items) / len(row_items),
            "x1": min(item["x1"] for item in row_items),
            "x2": max(item["x2"] for item in row_items),
            "y1": row["y1"],
            "y2": row["y2"],
            "height": row["height"],
        })

    finalized.sort(key=lambda row: row["y1"])
    return finalized


def _line_text_from_easyocr_results(results):
    rows = _group_easyocr_rows(results)
    return "\n".join(row["text"] for row in rows if row["text"].strip())


def _is_name_label_line(text):
    lowered = re.sub(r"\s+", " ", text.lower())
    return any(re.search(pattern, lowered, re.IGNORECASE) for pattern in NAME_LABEL_PATTERNS)


def _is_labelish_token(text):
    normalized = re.sub(r"[^a-z]", "", text.lower())
    return normalized in {
        "candidate", "candidates", "student", "name", "nameofcandidate",
    }


def _clean_name_candidate(text):
    cleaned = re.sub(r"\s+", " ", text or "").strip(" :-|")
    for pattern in NAME_LABEL_PATTERNS:
        cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)

    parts = [
        part.upper()
        for part in re.findall(r"[A-Za-z][A-Za-z'.-]*", cleaned)
        if len(part) >= 2
    ]
    label_words = {"candidate", "student", "name", "of"}
    parts = [part for part in parts if part.lower() not in label_words]

    if len(parts) < 2:
        return ""

    return _correct_ocr_chars_in_name(" ".join(parts))


def _score_name_candidate(candidate, confidence=0.0):
    parts = re.findall(r"[A-Za-z][A-Za-z'.-]*", candidate or "")
    if len(parts) < 2 or len(parts) > 5:
        return -1

    lowered = [part.lower() for part in parts]
    if any(word in OCR_HINT_WORDS for word in lowered):
        return -1

    score = 40 + sum(len(part) for part in parts)
    if len(parts) >= 3:
        score += 20
    if lowered[0] in COMMON_SURNAME_HINTS:
        score += 20
    if all(part.isalpha() for part in parts):
        score += 10
    score += int(max(confidence, 0.0) * 25)
    return score


def _select_best_name_candidate(candidates):
    best_name = ""
    best_score = -1

    for candidate in candidates:
        name = candidate.get("name", "")
        score = candidate.get("score", -1)
        if name and score > best_score:
            best_name = name
            best_score = score

    return best_name


def _extract_name_candidates_from_rows(rows):
    candidates = []

    for index, row in enumerate(rows):
        row_text = row["text"]
        confidence = row.get("confidence", 0.0)

        if _is_name_label_line(row_text):
            same_row_candidate = _clean_name_candidate(row_text)
            score = _score_name_candidate(same_row_candidate, confidence)
            if same_row_candidate and score >= 0:
                candidates.append({"name": same_row_candidate, "score": score + 25})

            if index + 1 < len(rows):
                next_row_candidate = _clean_name_candidate(rows[index + 1]["text"])
                next_score = _score_name_candidate(
                    next_row_candidate,
                    rows[index + 1].get("confidence", 0.0),
                )
                if next_row_candidate and next_score >= 0:
                    candidates.append({"name": next_row_candidate, "score": next_score + 10})

        fallback_candidate = _clean_name_candidate(row_text)
        fallback_score = _score_name_candidate(fallback_candidate, confidence)
        if fallback_candidate and fallback_score >= 0 and row_text.upper() == row_text:
            candidates.append({"name": fallback_candidate, "score": fallback_score})

    return candidates


def _extract_crop_name_candidate(reader, variant, row):
    import numpy as np

    label_right_edges = [
        item["x2"]
        for item in row.get("items", [])
        if _is_labelish_token(item["text"])
    ]

    left = int(min(label_right_edges) + 4) if label_right_edges else int(variant.width * 0.18)
    top = max(int(row["y1"] - row["height"] * 0.8), 0)
    bottom = min(int(row["y2"] + row["height"] * 0.8), variant.height)
    left = max(min(left, variant.width - 1), 0)

    if bottom <= top or left >= variant.width - 1:
        return ""

    crop = variant.crop((left, top, variant.width, bottom))
    crop_results = reader.readtext(
        np.array(crop),
        detail=1,
        paragraph=False,
        allowlist="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz ",
    )
    crop_text = _line_text_from_easyocr_results(crop_results)
    return _clean_name_candidate(crop_text)


def _extract_structured_name_hint(reader, variant):
    import numpy as np

    results = reader.readtext(np.array(variant), detail=1, paragraph=False)
    rows = _group_easyocr_rows(results)
    candidates = _extract_name_candidates_from_rows(rows)

    for row in rows:
        if not _is_name_label_line(row["text"]):
            continue

        cropped_candidate = _extract_crop_name_candidate(reader, variant, row)
        cropped_score = _score_name_candidate(cropped_candidate, row.get("confidence", 0.0))
        if cropped_candidate and cropped_score >= 0:
            candidates.append({"name": cropped_candidate, "score": cropped_score + 35})

    return _line_text_from_easyocr_results(results), _select_best_name_candidate(candidates)


# ============================================
# PRIMARY OCR — Pytesseract
# ============================================

def perform_ocr_pytesseract(image):
    """
    Pytesseract se OCR karo
    image = PIL Image object ya file path (string)
    """
    try:
        import pytesseract

        # Tesseract path set karo (Windows ke liye)
        if os.name == "nt" and os.path.exists(TESSERACT_PATH):
            pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

        # File path diya hai? Open karo
        image = _load_image(image)
        attempts = []

        # Image enhance karo (better OCR accuracy)
        for _, variant in _generate_ocr_variants(image):
            for lang, config in [
                ("eng+hin", "--psm 6 --oem 3"),
                ("eng+hin", "--psm 11 --oem 3"),
                ("eng", "--psm 6"),
                ("eng", "--psm 11"),
            ]:
                try:
                    text = pytesseract.image_to_string(
                        variant,
                        lang=lang,
                        config=config,
                    )
                except Exception:
                    text = ""
                if text.strip():
                    attempts.append(text)

        # Multiple languages support — English + Hindi + Gujarati
        # lang string: "eng+hin+guj"
        text = _choose_best_ocr_result(attempts)

        if text.strip():
            cprint(f"  ✅ Pytesseract OCR: {len(text)} chars found", Colors.GREEN)
            return text.strip()

        cprint("  Pytesseract found no text", Colors.YELLOW)
        return ""
        if False:

            cprint("  ⚠️  Pytesseract found no text", Colors.YELLOW)
            return ""

    except ImportError:
        cprint("  ⚠️  pytesseract not installed", Colors.YELLOW)
        return ""
    except Exception as e:
        cprint(f"  ❌ Pytesseract Error: {e}", Colors.RED)
        return ""


# ============================================
# BACKUP OCR — EasyOCR (Better for Hindi/Regional)
# ============================================

def perform_ocr_easyocr(image_path, languages=["en", "hi"]):
    """
    EasyOCR se OCR karo — Hindi/Regional languages ke liye better!
    """
    try:
        import easyocr

        cprint("  🔍 EasyOCR loading (first time takes 1-2 min)...", Colors.CYAN)
        reader = easyocr.Reader(languages, gpu=False)
        image = _load_image(image_path)
        attempts = []
        structured_name_candidates = []

        for _, variant in _generate_ocr_variants(image):
            try:
                text, structured_name = _extract_structured_name_hint(reader, variant)
            except Exception:
                text = ""
                structured_name = ""
            if text.strip():
                attempts.append(text)
            if structured_name:
                structured_name_candidates.append({
                    "name": structured_name,
                    "score": _score_name_candidate(structured_name, 1.0),
                })

        text = _choose_best_ocr_result(attempts)
        best_name = _select_best_name_candidate(structured_name_candidates)
        if best_name and best_name.lower() not in text.lower():
            cprint(f"  Name hint recovered: {best_name}", Colors.CYAN)
            text = f"Candidate Name: {best_name}\n{text}".strip()
        if text.strip():
            cprint(f"  ✅ EasyOCR: {len(text)} chars found", Colors.GREEN)
            return text.strip()
        else:
            cprint("  ⚠️  EasyOCR found no text", Colors.YELLOW)
            return ""

    except ImportError:
        cprint("  ⚠️  easyocr not installed", Colors.YELLOW)
        return ""
    except Exception as e:
        cprint(f"  ❌ EasyOCR Error: {e}", Colors.RED)
        return ""


# ============================================
# MAIN FUNCTION — Image file se text nikalo
# ============================================

def extract_from_image(file_path):
    """
    ⭐ MAIN OCR FUNCTION ⭐
    Image file do → Text milega
    Pehle Pytesseract try karo, phir EasyOCR
    """
    cprint(f"\n  🖼️  OCR Processing: {os.path.basename(file_path)}", Colors.CYAN)

    if not os.path.exists(file_path):
        cprint(f"  ❌ Image not found: {file_path}", Colors.RED)
        return ""

    # Method 1: Pytesseract
    text = perform_ocr_pytesseract(file_path)

    # Method 2: EasyOCR as backup
    if not text or len(text) < 20:
        cprint("  🔄 Trying EasyOCR as backup...", Colors.YELLOW)
        text = perform_ocr_easyocr(file_path)

    # Method 3: Basic fallback — just return filename info
    if not text:
        cprint("  ⚠️  OCR could not read image. Check Tesseract installation.", Colors.YELLOW)
        text = f"[Image file: {os.path.basename(file_path)} - OCR text extraction failed]"

    return text


def perform_ocr_on_image(pil_image):
    """
    PIL Image object pe OCR karo (PDF pages ke liye)
    """
    return perform_ocr_pytesseract(pil_image)


def _extract_text_for_analysis(document):
    """
    Accepts either an image/PIL object or a supported document path.
    """
    if isinstance(document, str):
        if not os.path.exists(document):
            return ""

        ext = os.path.splitext(document)[1].lower()
        if ext in IMAGE_EXTENSIONS:
            return extract_from_image(document)

        from modules.ingestion import route_to_extractor
        return route_to_extractor(document)

    return perform_ocr_on_image(document)


# ============================================
# FIX 2: Suspicious OCR value guard
# Agar value single char / only special chars /
# clearly garbage ho toh "Not Found" return karo
# instead of showing wrong data.
# ============================================

def _is_suspicious_ocr_value(value):
    """
    Returns True if value looks like OCR garbage —
    single char, only dashes/special chars, or too short.
    Used to suppress bad field values rather than show wrong data.
    """
    if not value or value == "Not Found":
        return True
    # Remove all separators/whitespace and check remaining length
    stripped = re.sub(r"[\s\-\—\–|:.]", "", value)
    if len(stripped) <= 1:
        return True
    # Only special / non-alphanumeric characters
    if re.fullmatch(r"[^A-Za-z0-9]+", value.strip()):
        return True
    return False


def _is_suspicious_ocr_value_strict(value):
    if not value or value == "Not Found":
        return True

    text = str(value).strip()
    stripped = re.sub(r"[\s\-|:._,/\\]+", "", text)
    if len(stripped) <= 1:
        return True
    if re.fullmatch(r"[^A-Za-z0-9]+", text):
        return True
    if text.lower() in {"na", "n/a", "none", "null", "nil", "ee"}:
        return True
    return False


def _normalize_field(value):
    if value is None:
        return "Not Found"

    if isinstance(value, dict):
        value = value.get("value")

    text = re.sub(r"\s+", " ", str(value)).strip(" \n\r\t|:-")
    if not text:
        return "Not Found"

    # FIX 2: Suppress single-char / garbage OCR values
    if _is_suspicious_ocr_value_strict(text):
        return "Not Found"

    return text


def _normalize_summary(summary):
    if not summary:
        return "Not Found"

    cleaned = _normalize_field(summary)
    if "ocr text extraction failed" in cleaned.lower():
        return "Not Found"

    if cleaned in {
        "Empty/Invalid document.",
        "Document is too short to summarize.",
        "Insufficient text for summarization.",
    }:
        return "Not Found"

    return cleaned


def _shorten_text(text, limit=220):
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."


def _clean_marksheet_capture(value):
    text = re.sub(r"\s+", " ", str(value or "")).strip(" |:-")
    text = re.sub(r"\s*([./-])\s*", r"\1", text)
    return text


def _normalize_marksheet_text(text):
    return re.sub(r"[|]+", " ", text or "").replace("\r", "\n")


def _iter_clean_lines(text):
    return [
        _clean_marksheet_capture(line)
        for line in re.split(r"[\r\n]+", _normalize_marksheet_text(text))
        if _clean_marksheet_capture(line)
    ]


def _clean_marksheet_numeric_fragment(value):
    cleaned = _clean_marksheet_capture(value)
    cleaned = re.sub(r"(?<=\d)\s+(?=\d)", "", cleaned)
    cleaned = re.sub(r"(?<=\d)\s+(?=[./-])", "", cleaned)
    cleaned = re.sub(r"(?<=[./-])\s+(?=\d)", "", cleaned)
    return cleaned


def _is_valid_marksheet_field_value(field_name, value):
    cleaned = _clean_marksheet_capture(value)
    if not cleaned or cleaned == "Not Found":
        return False
    if _is_suspicious_ocr_value_strict(cleaned):
        return False

    digits = re.sub(r"\D", "", cleaned)
    letters = re.sub(r"[^A-Za-z]", "", cleaned)
    lowered = cleaned.lower()

    if field_name == "month_year_of_exam":
        return bool(
            re.search(
                r"\b(?:jan|feb|mar|march|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*[-/ ]?\d{4}\b",
                lowered,
                re.IGNORECASE,
            )
        )
    if field_name == "seat_no":
        compact = re.sub(r"[\s\-]", "", cleaned)
        return len(compact) >= 6 and len(digits) >= 5
    if field_name == "centre_number":
        return 3 <= len(digits) <= 6
    if field_name == "school_index_no":
        return len(digits) >= 4
    if field_name == "statement_no":
        return len(digits) >= 4
    if field_name == "grand_total":
        return 2 <= len(digits) <= 4
    if field_name == "grade":
        return bool(re.fullmatch(r"[A-D][12]|[A-E]", cleaned.upper()))
    if field_name == "percentile_rank":
        return bool(re.fullmatch(r"\d{2,3}(?:\.\d{1,3})?", cleaned))
    if field_name == "result_status":
        return lowered in {"pass", "fail", "qualified for secondary school certificate"}

    return bool(digits or letters)


def _extract_labeled_marksheet_value(text, label_pattern, field_name, value_pattern=None):
    lines = _iter_clean_lines(text)
    fallback_pattern = value_pattern or r"([A-Za-z0-9][A-Za-z0-9 ./-]{1,40})"

    for index, line in enumerate(lines):
        if not re.search(label_pattern, line, re.IGNORECASE):
            continue

        same_line_match = re.search(
            rf"{label_pattern}\s*[:\-|]?\s*{fallback_pattern}",
            line,
            re.IGNORECASE,
        )
        if same_line_match:
            candidate = _clean_marksheet_numeric_fragment(same_line_match.group(1))
            if _is_valid_marksheet_field_value(field_name, candidate):
                return candidate

        for next_line in lines[index + 1:index + 3]:
            candidate = _clean_marksheet_numeric_fragment(next_line)
            if _is_valid_marksheet_field_value(field_name, candidate):
                return candidate

    return ""


def _looks_like_marksheet_document(text="", entities=None):
    if isinstance(entities, dict) and entities.get("doc_type") == "marksheet":
        return True

    collapsed = re.sub(r"\s+", " ", text or "").strip().lower()
    if not collapsed:
        return False

    matches = sum(
        1
        for pattern in MARKSHEET_HINT_PATTERNS
        if re.search(pattern, collapsed, re.IGNORECASE)
    )
    return matches >= 2 or "statement of marks" in collapsed


def _extract_marksheet_exam_name(text):
    collapsed = re.sub(r"\s+", " ", text or "").strip()
    if not collapsed:
        return ""

    patterns = [
        r"has\s+acquired\s+following\s+grade\s+in\s+the\s+([A-Za-z][A-Za-z ]{10,120}?examination)\b",
        r"\b(secondary\s+sch\w*\s+certificate\s+examination)\b",
        r"\b(higher\s+secondary\s+certificate\s+examination)\b",
        r"\b(statement\s+of\s+marks)\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, collapsed, re.IGNORECASE)
        if match:
            return re.sub(r"\s+", " ", match.group(1)).strip(" .|:-")

    return ""


def _extract_marksheet_header_fields(text):
    fields = {}

    labeled_extractors = [
        ("month_year_of_exam", r"(?:month\s*&?\s*year(?:\s*of\s*(?:exam|the exam))?|month\s*year\s*of\s*exam)", r"([A-Za-z]{3,10}\s*[-/ ]\s*\d{4})"),
        ("seat_no", r"seat\s*no", r"([A-Z0-9][A-Z0-9\- ]{4,20})"),
        ("centre_number", r"(?:centre|center)\s*number", r"(\d{3,6})"),
        ("school_index_no", r"school\s*index\s*no", r"([0-9][0-9 ./-]{3,20})"),
        ("statement_no", r"(?:statement\s*no|sr\.?\s*no\.?\s*of\s*statement)", r"([A-Z0-9][A-Z0-9\- ]{3,20})"),
    ]
    for field_name, label_pattern, value_pattern in labeled_extractors:
        value = _extract_labeled_marksheet_value(text, label_pattern, field_name, value_pattern)
        if value:
            fields[field_name] = value

    if len(fields) >= 5:
        return fields

    lines = _iter_clean_lines(text)
    month_pattern = r"\b(?:jan|feb|mar|march|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s*[-/ ]\s*\d{4}\b"

    for index, line in enumerate(lines):
        if not re.search(month_pattern, line, re.IGNORECASE):
            continue

        values = [line]
        for next_line in lines[index + 1:index + 8]:
            if re.search(r"(?:subject|marks obtained|name of the subject|grand total|performance|percentile|grade)", next_line, re.IGNORECASE):
                break

            compact = _clean_marksheet_numeric_fragment(next_line)
            if not compact or not re.search(r"[A-Za-z0-9]", compact):
                continue

            values.append(compact)
            if len(values) >= 5:
                break

        if len(values) >= 5:
            candidate_fields = {
                "month_year_of_exam": values[0],
                "seat_no": values[1],
                "centre_number": values[2],
                "school_index_no": values[3],
                "statement_no": values[4],
            }
            for key, candidate in candidate_fields.items():
                if _is_valid_marksheet_field_value(key, candidate):
                    fields.setdefault(key, candidate)
            break

    return fields


def _extract_marksheet_grand_total(text):
    value = _extract_labeled_marksheet_value(
        text,
        r"(?:grand\s*total|total)",
        "grand_total",
        r"(\d{2,4})",
    )
    if value:
        return value
    return ""


def _extract_marksheet_result_status(text):
    value = _extract_labeled_marksheet_value(
        text,
        r"(?:result\s*status|result)",
        "result_status",
        r"(qualified\s+for\s+secondary\s+school\s+certificate|pass|fail)",
    )
    if value and _is_valid_marksheet_field_value("result_status", value):
        return value.upper()

    collapsed = _clean_marksheet_capture(text).lower()
    if re.search(r"\bpassed\s+this\s+exam\b", collapsed, re.IGNORECASE):
        return "PASS"
    return ""


def _extract_marksheet_percentile(text):
    value = _extract_labeled_marksheet_value(
        text,
        r"(?:percentile(?:\s*rank)?|perce\w*)",
        "percentile_rank",
        r"(\d{2,3}\s*[.,]\s*\d{1,3})",
    )
    if value:
        return value.replace(",", ".")
    return ""


def _extract_marksheet_final_grade(text):
    value = _extract_labeled_marksheet_value(
        text,
        r"\bgrade\b",
        "grade",
        r"([A-D][12]|[A-E])",
    )
    if value:
        return value.upper()

    matches = re.findall(r"\b([A-D][12]|[A-E])\b", text or "", re.IGNORECASE)
    for match in reversed(matches):
        if _is_valid_marksheet_field_value("grade", match):
            return match.upper()
    return ""


def _extract_marksheet_display_name(text, full_name, entities=None):
    collapsed = re.sub(r"\s+", " ", text or "").strip()
    if collapsed:
        match = re.search(
            r"this\s+is\s+to\s+certify\s+that\s+([A-Za-z][A-Za-z ]{3,80}?)\s+has\s+acquired\s+following\s+grade",
            collapsed,
            re.IGNORECASE,
        )
        if match:
            captured = _normalize_field(match.group(1))
            if captured != "Not Found":
                # FIX 1: Apply OCR char correction on marksheet name
                return _correct_ocr_chars_in_name(captured)

    lines = _iter_ocr_lines(text)
    for index, line in enumerate(lines):
        if not re.search(r"(?:certify\s+that|his\s+is\s+to\s+certify\s+that)", line, re.IGNORECASE):
            continue

        collected = []
        for next_line in lines[index + 1:index + 5]:
            if re.search(r"has\s+acquired\s+following\s+grade", next_line, re.IGNORECASE):
                break

            words = re.findall(r"[A-Za-z][A-Za-z'.-]*", next_line)
            if not words:
                continue

            upper_like = next_line.upper() == next_line or sum(
                1 for word in words if word.isupper()
            ) >= max(len(words) - 1, 1)
            if upper_like:
                collected.append(" ".join(words))

        if collected:
            captured = _normalize_field(" ".join(collected))
            if captured != "Not Found":
                # FIX 1: Apply OCR char correction on marksheet name
                return _correct_ocr_chars_in_name(captured)

    normalized_name = _normalize_field(full_name)
    if normalized_name != "Not Found":
        # FIX 1: Apply OCR char correction on marksheet name
        return _correct_ocr_chars_in_name(normalized_name)

    if isinstance(entities, dict):
        parts = [
            _normalize_field(entities.get("surname")),
            _normalize_field(entities.get("first_name")),
            _normalize_field(entities.get("father_name")),
        ]
        parts = [part for part in parts if part != "Not Found"]
        if parts:
            # FIX 1: Apply OCR char correction on marksheet name
            return _correct_ocr_chars_in_name(" ".join(parts))

    return "Not Found"


def _build_marksheet_summary(text, full_name, entities=None):
    exam_name = _extract_marksheet_exam_name(text)
    display_name = _extract_marksheet_display_name(text, full_name, entities=entities)
    parts = ["Certificate"]

    if display_name != "Not Found" and exam_name:
        parts.append(
            f"Name: {display_name.upper()} has acquired following grade in the {exam_name}"
        )
    elif display_name != "Not Found":
        parts.append(f"Name: {display_name.upper()}")

    if exam_name:
        parts.append(f"Field: {exam_name}")

    if len(parts) == 1:
        return "Not Found"

    return _shorten_text(" | ".join(parts), limit=220)


def _iter_ocr_lines(text):
    lines = []
    for raw_line in re.split(r"[\r\n]+", text or ""):
        cleaned = re.sub(r"\s+", " ", str(raw_line)).strip(" \t|:-")
        if cleaned:
            lines.append(cleaned)
    return lines


def _clean_text_candidate(value):
    words = re.findall(r"[A-Za-z][A-Za-z/&.\-]*", value or "")
    return " ".join(words).strip()


def _score_name_line(line, next_lines):
    if not line:
        return -1

    if re.search(r"[@\d]", line):
        return -1

    parts = re.findall(r"[A-Za-z][A-Za-z'.-]*", line)

    # Strip leading label tokens (e.g. "Name", "Candidate", "Student") so that
    # a line like "Name: Rahul Sharma" is not rejected because "name" appears
    # in OCR_HINT_WORDS.  We only strip from the front; a label word sitting
    # inside actual name tokens is still disqualifying.
    while parts and parts[0].lower() in _SCORE_NAME_LABEL_WORDS:
        parts = parts[1:]

    if len(parts) < 2 or len(parts) > 4:
        return -1

    lowered = [part.lower() for part in parts]
    # Only OCR_NAME_SKIP_WORDS disqualify now; label/hint words have already
    # been stripped from the front above.
    if any(word in OCR_NAME_SKIP_WORDS for word in lowered):
        return -1

    score = 40
    if len(parts) == 2:
        score += 35
    elif len(parts) == 3:
        score += 15

    if line.upper() == line:
        score += 15
    elif line.title() == line:
        score += 10

    nearby_text = " ".join(next_lines).lower()
    if any(label in nearby_text for label in OCR_CONTACT_LABELS):
        score += 35
    if any(word in COMMON_SURNAME_HINTS for word in lowered):
        score += 10

    return score


def _extract_best_name_line(text):
    lines = _iter_ocr_lines(text)
    best_name = ""
    best_score = -1

    for index, line in enumerate(lines):
        score = _score_name_line(line, lines[index + 1:index + 4])
        if score > best_score:
            best_name = line
            best_score = score

    if best_score < 60:
        return ""

    return _correct_ocr_chars_in_name(_clean_text_candidate(best_name))


def _extract_email_hint(text):
    for line in _iter_ocr_lines(text):
        normalized = re.sub(r"\s*@\s*", "@", line)
        normalized = re.sub(r"\s*\.\s*", ".", normalized)
        match = re.search(r"([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})", normalized)
        if match:
            return match.group(1)
    return ""


def _extract_phone_hint(text):
    lines = _iter_ocr_lines(text)

    for line in lines:
        if not re.search(r"(?:phone|mobile|contact|tel)", line, re.IGNORECASE):
            continue

        match = re.search(r"(\+?\d[\d\s\-]{7,}\d)", line)
        if not match:
            continue

        candidate = re.sub(r"\s+", " ", match.group(1)).strip()
        if len(re.sub(r"\D", "", candidate)) >= 10:
            return candidate

    for line in lines:
        match = re.search(r"(\+?\d[\d\s\-]{9,}\d)", line)
        if not match:
            continue

        candidate = re.sub(r"\s+", " ", match.group(1)).strip()
        if len(re.sub(r"\D", "", candidate)) >= 10:
            return candidate

    return ""


def _clean_department_hint(value):
    cleaned = _clean_text_candidate(value)
    if not cleaned:
        return ""

    lowered = cleaned.lower()
    if any(word in lowered for word in ("company", "lorem", "ipsum", "signature", "website")):
        return ""

    return " ".join(part.capitalize() for part in cleaned.split())


def _extract_department_hint(text, full_name=""):
    lines = _iter_ocr_lines(text)

    for line in lines:
        for pattern in OCR_DEPARTMENT_LABEL_PATTERNS:
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                candidate = _clean_department_hint(match.group(1))
                if candidate:
                    return candidate

    if full_name:
        normalized_name = re.sub(r"\s+", " ", full_name).strip().lower()
        for index, line in enumerate(lines):
            if re.sub(r"\s+", " ", line).strip().lower() != normalized_name:
                continue

            if index + 1 >= len(lines):
                break

            next_line = lines[index + 1]
            if re.search(r"(?:id|blood|email|phone|mobile|contact)", next_line, re.IGNORECASE):
                break

            candidate = _clean_department_hint(next_line)
            if candidate:
                return candidate

    for line in lines:
        if re.fullmatch(r"(?i)(?:job\s*position|designation|department|role)", line.strip()):
            return " ".join(part.capitalize() for part in line.split())

    return ""


def _extract_ocr_field_hints(text):
    hints = {}
    full_name = _extract_best_name_line(text)
    if full_name:
        first_name, middle_name, last_name = split_person_name(full_name)
        hints["full_name"] = full_name
        hints["first_name"] = first_name
        hints["middle_name"] = middle_name
        hints["last_name"] = last_name

    email = _extract_email_hint(text)
    if email:
        hints["email"] = email

    phone = _extract_phone_hint(text)
    if phone:
        hints["phone"] = phone

    department = _extract_department_hint(text, hints.get("full_name", ""))
    if department:
        hints["department"] = department

    return hints


def split_person_name(full_name):
    """
    Split a full name into first, middle, and last name.
    Missing parts are returned as "Not Found".
    """
    if not full_name or full_name == "Not Found":
        return "Not Found", "Not Found", "Not Found"

    cleaned = re.sub(
        r"\b(?:mr|mrs|ms|miss|dr|prof|sir|shri|smt)\.?\b",
        " ",
        full_name,
        flags=re.IGNORECASE,
    )
    parts = re.findall(r"[A-Za-z][A-Za-z'.-]*", cleaned)

    if not parts:
        return "Not Found", "Not Found", "Not Found"
    if len(parts) == 1:
        return parts[0].title(), "Not Found", "Not Found"
    if len(parts) == 2:
        return parts[0].title(), "Not Found", parts[1].title()

    first_name = parts[0].title()
    middle_name = " ".join(p.title() for p in parts[1:-1]) or "Not Found"
    last_name = parts[-1].title()
    return first_name, middle_name, last_name


def split_marksheet_name(full_name):
    """
    Marksheet names often appear as:
    SURNAME FIRSTNAME FATHERNAME
    """
    if not full_name or full_name == "Not Found":
        return "Not Found", "Not Found", "Not Found"

    parts = re.findall(r"[A-Za-z][A-Za-z'.-]*", full_name)
    parts = [part.title() for part in parts if len(part) >= 2]

    if len(parts) >= 3:
        first_name = parts[1]
        middle_name = " ".join(parts[2:]) or "Not Found"
        last_name = parts[0]
        return first_name, middle_name, last_name

    if len(parts) == 2:
        return parts[1], "Not Found", parts[0]

    return split_person_name(full_name)


def _has_marksheet_name_order(full_name):
    parts = re.findall(r"[A-Za-z][A-Za-z'.-]*", full_name or "")
    return len(parts) >= 3


def _extract_full_name_candidate(text, entities, ocr_hints=None):
    patterns = [
        r"(?:^|\n|\|)\s*(?:full\s*name|employee\s*name|candidate\s*name|student\s*name|passenger\s*name)\s*[:\-|]\s*([A-Za-z][A-Za-z .'-]+)",
        r"(?:^|\n|\|)\s*name\s*[:\-|]\s*([A-Za-z][A-Za-z .'-]+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = _normalize_field(match.group(1))
            if value != "Not Found":
                return _correct_ocr_chars_in_name(value)

    if ocr_hints and ocr_hints.get("full_name"):
        return _correct_ocr_chars_in_name(ocr_hints["full_name"])

    if isinstance(entities, dict) and entities.get("doc_type") == "marksheet":
        ordered_parts = [
            _normalize_field(entities.get("surname")),
            _normalize_field(entities.get("first_name")),
            _normalize_field(entities.get("father_name")),
        ]
        ordered_parts = [part for part in ordered_parts if part != "Not Found"]
        if ordered_parts:
            return " ".join(ordered_parts)

    parts = [
        _normalize_field(entities.get("first_name")),
        _normalize_field(entities.get("surname")),
    ]
    parts = [part for part in parts if part != "Not Found"]
    return " ".join(parts) if parts else "Not Found"


def build_requested_fields_result(text, entities, summary, include_extended=True):
    """
    Normalize extracted data into the requested JSON shape.
    """
    translated_text = entities.get("_translated") or ""
    is_marksheet_document = _looks_like_marksheet_document(
        text or translated_text,
        entities=entities,
    )
    if is_marksheet_document:
        source_text = text or translated_text or ""
    else:
        source_text = translated_text or text or ""
    ocr_hints = _extract_ocr_field_hints(text or source_text)
    full_name = _extract_full_name_candidate(source_text, entities, ocr_hints=ocr_hints)
    if is_marksheet_document and _has_marksheet_name_order(full_name):
        first_name, middle_name, last_name = split_marksheet_name(full_name)
    else:
        first_name, middle_name, last_name = split_person_name(full_name)

    if first_name == "Not Found" and ocr_hints.get("first_name"):
        first_name = ocr_hints["first_name"]
    if middle_name == "Not Found" and ocr_hints.get("middle_name"):
        middle_name = ocr_hints["middle_name"]
    if last_name == "Not Found" and ocr_hints.get("last_name"):
        last_name = ocr_hints["last_name"]

    result = {
        "first_name": first_name,
        "middle_name": middle_name,
        "last_name": last_name,
    }

    if include_extended:
        result.update({
            "father_name": _normalize_field(entities.get("father_name")),
            "department": _normalize_field(entities.get("department") or ocr_hints.get("department")),
            "email": _normalize_field(entities.get("email") or ocr_hints.get("email")),
            "phone": _normalize_field(entities.get("phone") or ocr_hints.get("phone")),
            "id": _normalize_field((entities.get("unique_id") or {}).get("value")),
        })

        if is_marksheet_document:
            header_fields = _extract_marksheet_header_fields(source_text)
            result_status = _extract_marksheet_result_status(source_text)
            grand_total = _extract_marksheet_grand_total(source_text)
            final_grade = _extract_marksheet_final_grade(source_text)
            percentile_rank = _extract_marksheet_percentile(source_text)
            exam_name = _extract_marksheet_exam_name(source_text)
            display_name = _extract_marksheet_display_name(
                source_text,
                full_name,
                entities=entities,
            )

            if display_name != "Not Found":
                result["full_name"] = display_name.upper()
            if exam_name:
                result["exam_name"] = exam_name
            if header_fields.get("month_year_of_exam"):
                result["month_year_of_exam"] = header_fields["month_year_of_exam"]
            if header_fields.get("seat_no"):
                result["seat_no"] = header_fields["seat_no"]
            if header_fields.get("centre_number"):
                result["centre_number"] = header_fields["centre_number"]
            if header_fields.get("school_index_no"):
                result["school_index_no"] = header_fields["school_index_no"]
            if header_fields.get("statement_no"):
                result["statement_no"] = header_fields["statement_no"]
            if grand_total:
                result["grand_total"] = grand_total
            if final_grade:
                result["grade"] = final_grade
            if percentile_rank:
                result["percentile_rank"] = percentile_rank
            if result_status:
                result["result_status"] = result_status

    normalized_summary = _normalize_summary(summary)
    if normalized_summary == "Not Found" and is_marksheet_document:
        normalized_summary = _build_marksheet_summary(
            source_text,
            full_name,
            entities=entities,
        )

    result["summary"] = normalized_summary
    return result


def extract_requested_fields(document, include_extended=True):
    """
    High-level helper for image/document analysis.

    Returns either:
    - minimal JSON-compatible fields: first_name, middle_name, last_name, summary
    - or the extended set including father_name, department, email, phone, and id
    """
    from modules.nlp_parser import extract_entities
    from modules.summarizer import summarize_document

    text = _extract_text_for_analysis(document)
    if not text or "OCR text extraction failed" in text:
        return build_requested_fields_result("", {}, "", include_extended=include_extended)

    entities = extract_entities(text)
    summary_source = entities.get("_translated") or text
    summary = summarize_document(summary_source)

    return build_requested_fields_result(
        text,
        entities,
        summary,
        include_extended=include_extended,
    )


def extract_requested_fields_json(document, include_extended=True):
    """
    Returns the extracted result as a JSON string.
    """
    result = extract_requested_fields(document, include_extended=include_extended)
    return json.dumps(result, indent=2, ensure_ascii=False)


# ============================================
# CREATE SAMPLE AADHAR-LIKE IMAGE FOR TESTING
# ============================================

def create_sample_id_image(output_path):
    """
    Test ke liye ek fake ID card image banao
    """
    try:
        from PIL import Image, ImageDraw, ImageFont

        # White background
        img  = Image.new("RGB", (600, 350), color="white")
        draw = ImageDraw.Draw(img)

        # Draw border
        draw.rectangle([10, 10, 590, 340], outline="navy", width=3)
        draw.rectangle([10, 10, 590, 60], fill="navy")

        # Header
        draw.text((200, 25), "GOVERNMENT ID CARD", fill="white")
        draw.text((220, 45), "India", fill="white")

        # Photo placeholder
        draw.rectangle([30, 80, 150, 200], outline="gray", width=2)
        draw.text((55, 130), "PHOTO", fill="gray")

        # Details
        details = [
            ("First Name:", "Pooja"),
            ("Surname:", "Patel"),
            ("Father's Name:", "Bhadhreshkumar Patel"),
            ("Date of Birth:", "15-Aug-1995"),
            ("ID Number:", "1234 5678 9012"),
            ("Address:", "Bilimora, Gujarat - 396321"),
        ]

        y = 85
        for label, value in details:
            draw.text((170, y), label,  fill="navy")
            draw.text((310, y), value,  fill="black")
            y += 28

        img.save(output_path)
        cprint(f"  ✅ Sample ID image created: {output_path}", Colors.GREEN)
        return True

    except Exception as e:
        cprint(f"  ❌ Image creation error: {e}", Colors.RED)
        return False


def _ui_clean_display_value(value):
    return re.sub(r"\s+", " ", str(value or "")).strip(" |:-")


def _ui_iter_clean_lines(text):
    lines = []
    for raw_line in re.split(r"[\r\n]+", text or ""):
        cleaned = _ui_clean_display_value(raw_line)
        if cleaned:
            lines.append(cleaned)
    return lines


def _ui_clean_marksheet_capture(value):
    text = _ui_clean_display_value(value)
    text = re.sub(r"\s*([./-])\s*", r"\1", text)
    return text


def _ui_clean_marksheet_numeric_fragment(value):
    cleaned = _ui_clean_marksheet_capture(value)
    cleaned = re.sub(r"(?<=\d)\s+(?=\d)", "", cleaned)
    cleaned = re.sub(r"(?<=\d)\s+(?=[./-])", "", cleaned)
    cleaned = re.sub(r"(?<=[./-])\s+(?=\d)", "", cleaned)
    return cleaned


def _ui_is_valid_marksheet_field_value(field_name, value):
    cleaned = _ui_clean_marksheet_capture(value)
    if not cleaned:
        return False

    digits = re.sub(r"\D", "", cleaned)
    lowered = cleaned.lower()

    if field_name == "month_year_of_exam":
        return bool(
            re.search(
                r"\b(?:jan|feb|mar|march|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*[-/ ]?\d{4}\b",
                lowered,
                re.IGNORECASE,
            )
        )
    if field_name == "seat_no":
        compact = re.sub(r"[\s\-]", "", cleaned)
        return len(compact) >= 6 and len(digits) >= 5
    if field_name == "centre_number":
        return 3 <= len(digits) <= 6
    if field_name == "school_index_no":
        return bool(re.fullmatch(r"\d{1,3}[./-]\d{3,5}", cleaned))
    if field_name == "statement_no":
        return len(digits) >= 4
    if field_name == "grand_total":
        return bool(re.fullmatch(r"\d{2,4}", cleaned))
    if field_name == "grade":
        return bool(re.fullmatch(r"[A-D][12]", cleaned.upper()))
    if field_name == "percentile_rank":
        return bool(re.fullmatch(r"\d{2,3}(?:\.\d{1,3})?", cleaned))
    if field_name == "result_status":
        return lowered in {"pass", "fail", "qualified for secondary school certificate", "e.q.c."}

    return bool(re.search(r"[A-Za-z0-9]", cleaned))


def _ui_extract_labeled_marksheet_value(text, label_pattern, field_name, value_pattern=None):
    lines = _ui_iter_clean_lines(text)
    fallback_pattern = value_pattern or r"([A-Za-z0-9][A-Za-z0-9 ./-]{1,40})"

    for index, line in enumerate(lines):
        if not re.search(label_pattern, line, re.IGNORECASE):
            continue

        same_line_match = re.search(
            rf"{label_pattern}\s*[:\-|]?\s*{fallback_pattern}",
            line,
            re.IGNORECASE,
        )
        if same_line_match:
            candidate = _ui_clean_marksheet_numeric_fragment(same_line_match.group(1))
            if _ui_is_valid_marksheet_field_value(field_name, candidate):
                return candidate

        for next_line in lines[index + 1:index + 3]:
            candidate = _ui_clean_marksheet_numeric_fragment(next_line)
            if _ui_is_valid_marksheet_field_value(field_name, candidate):
                return candidate

    return ""


def _ui_looks_like_marksheet_text(text):
    lowered = _ui_clean_display_value(text).lower()
    hints = [
        "statement of marks",
        "seat no",
        "grand total of marks obtained",
        "percentile",
        "secondary school certificate",
        "month & year of the exam",
    ]
    return sum(1 for hint in hints if hint in lowered) >= 2


def _ui_extract_marksheet_full_name(text, details=None):
    collapsed = _ui_clean_display_value(text)
    direct = re.search(
        r"this\s+is\s+to\s+certify\s+that\s+([A-Za-z][A-Za-z ]{3,80}?)\s+has\s+acquired\s+following\s+grade",
        collapsed,
        re.IGNORECASE,
    )
    if direct:
        return _correct_ocr_chars_in_name(_ui_clean_display_value(direct.group(1)))

    lines = _ui_iter_clean_lines(text)
    for index, line in enumerate(lines):
        if not re.search(r"(?:this\s+is\s+to\s+certify\s+that|c\s*his\s+is\s+to\s+certify\s+that)", line, re.IGNORECASE):
            continue

        captured_parts = []
        for next_line in lines[index + 1:index + 5]:
            if re.search(r"has\s+acquired\s+following\s+grade", next_line, re.IGNORECASE):
                break

            words = re.findall(r"[A-Za-z][A-Za-z'.-]*", next_line)
            if not words:
                continue

            upper_like = next_line.upper() == next_line or sum(
                1 for word in words if word.isupper()
            ) >= max(len(words) - 1, 1)
            if upper_like:
                captured_parts.append(" ".join(words))

        if captured_parts:
            return _correct_ocr_chars_in_name(_ui_clean_display_value(" ".join(captured_parts)))

    if details:
        parts = []
        for key in ["Surname", "First Name", "Father's Name"]:
            value = details.get(key, "Not Found")
            if value != "Not Found":
                parts.append(value)
        if parts:
            return _correct_ocr_chars_in_name(_ui_clean_display_value(" ".join(parts)))

    return ""


def _ui_extract_marksheet_exam_name(text):
    def _normalize_exam_name(value):
        cleaned = _ui_clean_display_value(value)
        normalized = re.sub(r"\s+", " ", cleaned).strip()

        if re.search(
            r"\bsecondary\s+sch\w*(?:\s+\w{1,3})?\s+certificate\s+examination\b",
            normalized,
            re.IGNORECASE,
        ):
            return "Secondary School Certificate Examination"

        if re.search(
            r"\bhigher\s+secondary\s+certificate\s+examination\b",
            normalized,
            re.IGNORECASE,
        ):
            return "Higher Secondary Certificate Examination"

        return cleaned

    collapsed = _ui_clean_display_value(text)
    patterns = [
        r"has\s+acquired\s+following\s+grade\s+in\s+the\s+([A-Za-z][A-Za-z ]{10,120}?examination)\b",
        r"\b(secondary\s+sch\w*\s+certificate\s+examination)\b",
        r"\b(higher\s+secondary\s+certificate\s+examination)\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, collapsed, re.IGNORECASE)
        if match:
            return _normalize_exam_name(match.group(1))

    return ""


def _ui_extract_marksheet_header_fields(text):
    fields = {}

    labeled_extractors = [
        ("month_year_of_exam", r"(?:month\s*&?\s*year(?:\s*of\s*(?:exam|the exam))?|month\s*year\s*of\s*exam)", r"([A-Za-z]{3,10}\s*[-/ ]\s*\d{4})"),
        ("seat_no", r"seat\s*no", r"([A-Z0-9][A-Z0-9\- ]{4,20})"),
        ("centre_number", r"(?:centre|center)\s*number", r"(\d{3,6})"),
        ("school_index_no", r"school\s*index\s*no", r"([0-9][0-9 ./-]{3,20})"),
        ("statement_no", r"(?:statement\s*no|sr\.?\s*no\.?\s*of\s*statement)", r"([A-Z0-9][A-Z0-9\- ]{3,20})"),
    ]
    for field_name, label_pattern, value_pattern in labeled_extractors:
        value = _ui_extract_labeled_marksheet_value(text, label_pattern, field_name, value_pattern)
        if value:
            fields[field_name] = value

    if len(fields) >= 5:
        return fields

    lines = _ui_iter_clean_lines(text)
    month_pattern = r"\b(?:jan|feb|mar|march|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s*[-/ ]\s*\d{4}\b"

    for index, line in enumerate(lines):
        if not re.search(month_pattern, line, re.IGNORECASE):
            continue

        values = [line]
        for next_line in lines[index + 1:index + 8]:
            if re.search(r"(?:subject|marks obtained|name of the subject|grand total|performance|percentile|grade)", next_line, re.IGNORECASE):
                break

            compact = _ui_clean_marksheet_numeric_fragment(next_line)
            if not compact or not re.search(r"[A-Za-z0-9]", compact):
                continue

            values.append(compact)
            if len(values) >= 5:
                break

        if len(values) >= 5:
            candidate_fields = {
                "month_year_of_exam": values[0],
                "seat_no": values[1],
                "centre_number": values[2],
                "school_index_no": values[3],
                "statement_no": values[4],
            }
            for key, candidate in candidate_fields.items():
                if _ui_is_valid_marksheet_field_value(key, candidate):
                    fields.setdefault(key, candidate)
            break

    return fields


def _ui_extract_marksheet_grand_total(text):
    lines = _ui_iter_clean_lines(text)
    prioritized_patterns = [
        r"(?:obtained\s*marks|total\s*marks\s*obtained)\s*[:\-]?\s*(\d{2,4})\b",
        r"(?:grand\s*total(?:\s*of\s*marks\s*obtained)?)\s*[:\-]?\s*(\d{2,4})\b",
        r"(?:theory\s*total\s*on\s*which\s*grade\s*is\s*calculated)\s*[:\-]?\s*(\d{2,4})\s*/\s*\d{2,4}\b",
        r"(?:total\s*marks)\s*[:\-]?\s*(\d{2,4})\b",
    ]

    for line in lines:
        for pattern in prioritized_patterns:
            match = re.search(pattern, line, re.IGNORECASE)
            if not match:
                continue

            candidate = _ui_clean_marksheet_numeric_fragment(match.group(1))
            if _ui_is_valid_marksheet_field_value("grand_total", candidate):
                return candidate

    flat = _ui_clean_display_value(text)
    for pattern in prioritized_patterns:
        match = re.search(pattern, flat, re.IGNORECASE)
        if not match:
            continue

        candidate = _ui_clean_marksheet_numeric_fragment(match.group(1))
        if _ui_is_valid_marksheet_field_value("grand_total", candidate):
            return candidate

    return ""


def _ui_extract_marksheet_result_status(text):
    value = _ui_extract_labeled_marksheet_value(
        text,
        r"(?:result\s*status|result)",
        "result_status",
        r"(qualified\s+for\s+secondary\s+school\s+certificate|pass|fail|e\.q\.c\.)",
    )
    if value and _ui_is_valid_marksheet_field_value("result_status", value):
        return _ui_clean_display_value(value).upper()

    collapsed = _ui_clean_display_value(text).lower()
    if re.search(r"\bpassed\s+this\s+exam\b", collapsed, re.IGNORECASE):
        return "PASS"
    return ""


def _ui_extract_marksheet_percentile(text):
    value = _ui_extract_labeled_marksheet_value(
        text,
        r"(?:percentile(?:\s*rank)?|perce\w*)",
        "percentile_rank",
        r"(\d{2,3}\s*[.,]\s*\d{1,3})",
    )
    if value:
        return value.replace(",", ".")
    return ""


def _ui_extract_marksheet_final_grade(text):
    overall_patterns = [
        r"(?:over\s*all\s*grade|overall\s*grade)\s*[:\-]?\s*([A-D][12])\b",
    ]
    for pattern in overall_patterns:
        match = re.search(pattern, text or "", re.IGNORECASE)
        if match:
            grade = match.group(1).upper()
            if _ui_is_valid_marksheet_field_value("grade", grade):
                return grade

    value = _ui_extract_labeled_marksheet_value(
        text,
        r"\bgrade\b",
        "grade",
        r"([A-D][12])",
    )
    if value:
        return value.upper()

    matches = re.findall(r"\b([A-D][12])\b", text or "", re.IGNORECASE)
    for match in reversed(matches):
        if _ui_is_valid_marksheet_field_value("grade", match):
            return match.upper()
    return ""


def _ui_build_marksheet_summary(raw_text, details):
    full_name = _ui_extract_marksheet_full_name(raw_text, details=details)
    exam_name = _ui_extract_marksheet_exam_name(raw_text)

    parts = ["Certificate"]
    if full_name and exam_name:
        parts.append(f"Name: {full_name.upper()} has acquired following grade in the {exam_name}")
    elif full_name:
        parts.append(f"Name: {full_name.upper()}")

    if exam_name:
        parts.append(f"Field: {exam_name}")

    return " | ".join(parts) if len(parts) > 1 else ""


def _ui_build_marksheet_additional_info(raw_text, details):
    extra = {}
    full_name = _ui_extract_marksheet_full_name(raw_text, details=details)
    exam_name = _ui_extract_marksheet_exam_name(raw_text)
    header_fields = _ui_extract_marksheet_header_fields(raw_text)
    result_status = _ui_extract_marksheet_result_status(raw_text)
    grand_total = _ui_extract_marksheet_grand_total(raw_text)
    final_grade = _ui_extract_marksheet_final_grade(raw_text)
    percentile_rank = _ui_extract_marksheet_percentile(raw_text)

    if full_name:
        extra["full_name"] = full_name.upper()
    if exam_name:
        extra["exam_name"] = exam_name

    for key in [
        "month_year_of_exam",
        "seat_no",
        "centre_number",
        "school_index_no",
    ]:
        value = header_fields.get(key)
        if value:
            extra[key] = value

    if grand_total:
        extra["grand_total"] = grand_total
    if final_grade:
        extra["grade"] = final_grade
    if percentile_rank:
        extra["percentile_rank"] = percentile_rank
    if result_status:
        extra["result_status"] = result_status

    existing_extra = details.get("extra", {}) or {}
    for key, value in existing_extra.items():
        if key == "statement_no":
            continue
        if value and key not in extra:
            extra[key] = value

    return extra


def prepare_display_details(details, raw_text, doc_summary):
    prepared = dict(details or {})
    display_doc_type = prepared.get("doc_type", "generic")
    display_summary = doc_summary
    display_extra = dict(prepared.get("extra", {}) or {})

    if _ui_looks_like_marksheet_text(raw_text):
        display_doc_type = "marksheet"
        full_name = _ui_extract_marksheet_full_name(raw_text, details=prepared)
        name_parts = [part.title() for part in re.findall(r"[A-Za-z][A-Za-z'.-]*", full_name)]
        header_fields = _ui_extract_marksheet_header_fields(raw_text)
        exam_name = _ui_extract_marksheet_exam_name(raw_text)

        if len(name_parts) >= 3:
            prepared["Surname"] = name_parts[0]
            prepared["First Name"] = name_parts[1]
            prepared["Father's Name"] = " ".join(name_parts[2:])

        if prepared.get("Department") == "Not Found" and exam_name:
            prepared["Department"] = exam_name

        if prepared.get("ID") == "Not Found" and header_fields.get("seat_no"):
            prepared["ID"] = header_fields["seat_no"]
            prepared["ID_Type"] = "Seat No"

        marksheet_summary = _ui_build_marksheet_summary(raw_text, prepared)
        if marksheet_summary:
            display_summary = marksheet_summary
        display_extra = _ui_build_marksheet_additional_info(raw_text, prepared)

    prepared["extra"] = display_extra
    return prepared, display_doc_type, display_summary


# ============================================
# DIRECT TEST
# ============================================
if __name__ == "__main__":
    sample_path = "../sample_docs/sample_id_card.png"
    os.makedirs("../sample_docs", exist_ok=True)

    print("Creating sample ID card image...")
    create_sample_id_image(sample_path)

    print("\nRunning OCR on sample image...")
    text = extract_from_image(sample_path)
    print("\nExtracted Text:")
    print(text)

    print("\nStructured Output:")
    print(extract_requested_fields_json(sample_path))
