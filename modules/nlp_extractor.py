# ============================================================
# MODULE 3: NLP_EXTRACTOR.PY
# Text se naam aur unique ID nikalo (hierarchical matching)
# First Name + Surname + Father/Middle Name + Unique ID
# ============================================================

import os
import re
from typing import Optional


FIRST_NAME_PATTERNS = [
    r"first\s*name\s*[:\-\|]\s*([A-Za-z]+)",
    r"given\s*name\s*[:\-\|]\s*([A-Za-z]+)",
    r"employee\s+name\s*[:\-\|]\s*([A-Za-z]+)",
]

SURNAME_PATTERNS = [
    r"surname\s*[:\-\|]\s*([A-Za-z]+)",
    r"last\s*name\s*[:\-\|]\s*([A-Za-z]+)",
    r"family\s*name\s*[:\-\|]\s*([A-Za-z]+)",
]

FATHER_NAME_PATTERNS = [
    r"father'?s?\s*name\s*[:\-\|]\s*([A-Za-z ]+)",
    r"middle\s*name\s*[:\-\|]\s*([A-Za-z ]+)",
    r"s/o\s*[:\-]?\s*([A-Za-z ]+)",
    r"d/o\s*[:\-]?\s*([A-Za-z ]+)",
    r"father\s*[:\-\|]\s*([A-Za-z ]+)",
]

UNIQUE_ID_PATTERNS = [
    (r"(?:enrol(?:l)?ment(?:\s*/\s*pg)?(?:\s*registration)?\s*(?:no|number)?|registration\s*no)\s*[:\-\|]?\s*([A-Z0-9\-]{8,20})\b", "Enrollment No"),
    (r"(?:seat\s*no)\s*[:\-\|]?\s*([A-Z0-9][A-Z0-9\- ]{3,20})\b", "Seat No"),
    (r"(?:statement\s*no|sr\.?\s*no\.?\s*of\s*statement)\s*[:\-\|]?\s*([A-Z0-9\-]{4,20})\b", "Statement No"),
    (r"\b(\d{4}\s?\d{4}\s?\d{4})\b", "Aadhar"),
    (r"\b([A-Z]{5}[0-9]{4}[A-Z])\b", "PAN"),
    (r"\bemployee\s*id\s*[:\-\|]\s*([A-Z0-9\-]+)\b", "Employee ID"),
    (r"\bemp\s*id\s*[:\-\|]\s*([A-Z0-9\-]+)\b", "Employee ID"),
    (r"\bid\s*[:\-\|]\s*([A-Z0-9\-]+)\b", "Employee ID"),
    (r"\b([A-Z]{2,4}-\d{3,6})\b", "Employee ID"),
]

MARKSHEET_HINT_WORDS = {
    "student name",
    "candidate name",
    "candidate's name",
    "statement of marks",
    "seat no",
    "enrolment",
    "enrollment",
    "school index",
    "statement no",
    "percentile",
    "grade",
    "higher secondary certificate examination",
}

GENERIC_NAME_BLOCK_WORDS = {
    "item", "amount", "total", "subtotal", "qty", "quantity", "price", "rate",
    "description", "product", "service", "gst", "tax", "taxable", "balance",
    "bill", "invoice", "order", "unit", "value", "table", "date",
}

PERSON_CONTEXT_HINTS = (
    "@", "email", "phone", "mobile", "contact", "linkedin.com", "github.com",
    "summary", "education", "experience", "projects", "resume", "curriculum vitae",
    "department", "employee id", "father's name", "date of birth", "dob",
)


def _correct_ocr_chars_in_name(text):
    """
    Fix common OCR character mis-reads inside name strings.
    Example: POQUA -> POOJA
    """
    if not text:
        return text

    text = re.sub(r"oqu(?=[aeiou])", "ooj", text)
    text = re.sub(r"OQU(?=[AEIOU])", "OOJ", text)
    text = re.sub(
        r"(?i)oqu(?=[aeiouAEIOU])",
        lambda m: "OOJ" if m.group(0)[0].isupper() else "ooj",
        text,
    )
    return text


def _clean_capture(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip(" |:-")


def _looks_like_marksheet(text: str) -> bool:
    lowered = (text or "").lower()
    return any(word in lowered for word in MARKSHEET_HINT_WORDS)


def _has_person_context(text: str) -> bool:
    lowered = (text or "").lower()
    return any(hint in lowered for hint in PERSON_CONTEXT_HINTS)


def _is_safe_generic_name_pair(first_name: str, surname: str, text: str) -> bool:
    first_clean = re.sub(r"[^A-Za-z]", "", first_name or "")
    surname_clean = re.sub(r"[^A-Za-z]", "", surname or "")
    if len(first_clean) < 2 or len(surname_clean) < 2:
        return False
    if first_clean.lower() in GENERIC_NAME_BLOCK_WORDS:
        return False
    if surname_clean.lower() in GENERIC_NAME_BLOCK_WORDS:
        return False
    if not _has_person_context(text):
        return False
    return True


def _capture_labeled_value(text: str, label_pattern: str, stop_patterns: list[str]) -> str:
    lines = [line.strip() for line in re.split(r"[\r\n]+", text or "") if line.strip()]

    for index, line in enumerate(lines):
        if not re.search(label_pattern, line, re.I):
            continue

        current = re.sub(label_pattern, "", line, flags=re.I).strip(" :-|")
        parts = [current] if current else []

        for next_line in lines[index + 1:index + 4]:
            if any(re.search(stop_pattern, next_line, re.I) for stop_pattern in stop_patterns):
                break
            parts.append(next_line)

        candidate = _clean_capture(" ".join(parts))
        if not candidate:
            continue

        for stop_pattern in stop_patterns:
            stop_match = re.search(rf"\b{stop_pattern}\b", candidate, re.I)
            if stop_match:
                candidate = _clean_capture(candidate[:stop_match.start()])

        if candidate:
            return candidate

    return ""


def _split_marksheet_name(name_text: str):
    parts = [
        _correct_ocr_chars_in_name(part.capitalize())
        for part in re.findall(r"[A-Za-z]+", name_text or "")
        if len(part) >= 2
    ]
    if len(parts) >= 3 and not any(part.lower() in GENERIC_NAME_BLOCK_WORDS for part in parts):
        return parts[1], parts[0], " ".join(parts[2:])
    return None, None, None


def _extract_marksheet_name(text: str):
    stop_patterns = [
        r"program\s*name",
        r"college\s*name",
        r"exam\s*name",
        r"seat\s*no",
        r"result\s*declared",
        r"enrol(?:l)?ment",
        r"registration\s*no",
        r"course\s*code",
        r"sgpa",
        r"cgpa",
        r"stream",
        r"school\s*index",
        r"statement\s*no",
        r"percentile",
        r"grade",
    ]

    for label_pattern in [
        r"student\s*name",
        r"candidate'?s?\s*name",
        r"name\s*of\s*candidate",
        r"full\s*name",
    ]:
        captured = _capture_labeled_value(text, label_pattern, stop_patterns)
        if captured:
            return _split_marksheet_name(captured)

    flat = re.sub(r"\s+", " ", text or "")
    direct_match = re.search(
        r"(?:^|[|])\s*(?:full\s*name|name)\s*[:\-|]\s*([A-Z][A-Z ]{5,80})(?=\s+(?:exam\s*name|month|seat\s*no|centre|school\s*index|statement\s*no|grade|percentile)\b|$)",
        flat,
        re.I,
    )
    if direct_match:
        return _split_marksheet_name(direct_match.group(1))

    return None, None, None


def extract_entities(text: str) -> dict:
    """
    Text se structured entities nikalo.
    """
    print("\n  NLP ENTITY EXTRACTION")
    print("  " + "-" * 45)

    entities = {
        "first_name": None,
        "surname": None,
        "father_name": None,
        "unique_id": None,
        "id_type": None,
        "email": None,
        "department": None,
        "confidence": {},
    }

    if _looks_like_marksheet(text):
        first_name, surname, father_name = _extract_marksheet_name(text)
        if first_name:
            entities["first_name"] = first_name
            entities["confidence"]["first_name"] = "marksheet_name"
        if surname:
            entities["surname"] = surname
            entities["confidence"]["surname"] = "marksheet_name"
        if father_name:
            entities["father_name"] = father_name
            entities["confidence"]["father_name"] = "marksheet_name"

    if not entities["first_name"]:
        entities["first_name"], entities["confidence"]["first_name"] = _match_first(
            FIRST_NAME_PATTERNS,
            text,
        )

    if not entities["surname"]:
        entities["surname"], entities["confidence"]["surname"] = _match_first(
            SURNAME_PATTERNS,
            text,
        )

    if not entities["father_name"]:
        entities["father_name"], entities["confidence"]["father_name"] = _match_first_group(
            FATHER_NAME_PATTERNS,
            text,
        )

    if not entities["surname"]:
        fallback_first, fallback_surname, fallback_pattern = _extract_two_part_name(text)
        if fallback_surname and (
            not entities["first_name"] or entities["first_name"].lower() == fallback_first.lower()
        ):
            entities["first_name"] = fallback_first
            entities["surname"] = fallback_surname
            if not entities["confidence"].get("first_name"):
                entities["confidence"]["first_name"] = fallback_pattern
            entities["confidence"]["surname"] = fallback_pattern

    entities["unique_id"], entities["id_type"] = _extract_unique_id(text)

    email_match = re.search(r"[\w\.\+\-]+@[\w\-]+\.[a-z]{2,}", text or "", re.I)
    if email_match:
        entities["email"] = email_match.group(0).strip()

    dept_match = re.search(
        r"department\s*[:\-\|]\s*(.+?)[\n\r\|]",
        text or "",
        re.IGNORECASE,
    )
    if dept_match:
        entities["department"] = dept_match.group(1).strip()

    _print_entities(entities)
    return entities


def _match_first(patterns: list, text: str):
    for pattern in patterns:
        match = re.search(pattern, text or "", re.IGNORECASE | re.MULTILINE)
        if match:
            val = match.group(1).strip().split()[0]
            val = re.sub(r"[^A-Za-z]", "", val)
            if len(val) >= 2 and val.lower() not in GENERIC_NAME_BLOCK_WORDS:
                return _correct_ocr_chars_in_name(val.capitalize()), pattern
    return None, None


def _match_first_group(patterns: list, text: str):
    for pattern in patterns:
        match = re.search(pattern, text or "", re.IGNORECASE | re.MULTILINE)
        if match:
            val = match.group(1).strip()
            val = re.split(r"[\|\n\r]", val)[0].strip()
            val = re.sub(r"\s+", " ", val)
            if len(val) >= 2 and all(
                word.lower() not in GENERIC_NAME_BLOCK_WORDS
                for word in re.findall(r"[A-Za-z]+", val)
            ):
                return _correct_ocr_chars_in_name(val.title()), pattern
    return None, None


def _extract_two_part_name(text: str):
    patterns = [
        r"(?:^|\n|\|)\s*(?:full\s*name|employee\s*name|candidate\s*name|student\s*name)\s*[:\-\|]\s*([A-Za-z]+)\s+([A-Za-z]+)(?:\s|$)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text or "", re.IGNORECASE | re.MULTILINE)
        if not match:
            continue

        first_name = re.sub(r"[^A-Za-z]", "", match.group(1) or "")
        surname = re.sub(r"[^A-Za-z]", "", match.group(2) or "")
        if _is_safe_generic_name_pair(first_name, surname, text):
            return (
                _correct_ocr_chars_in_name(first_name.capitalize()),
                _correct_ocr_chars_in_name(surname.capitalize()),
                pattern,
            )

    return None, None, None


def _extract_unique_id(text: str):
    for pattern, id_type in UNIQUE_ID_PATTERNS:
        match = re.search(pattern, text or "", re.IGNORECASE)
        if match:
            uid = _clean_capture(match.group(1))
            if len(re.sub(r"[^A-Za-z0-9]", "", uid)) >= 4:
                print(f"  {id_type} found: {uid}")
                return uid, id_type
    return None, None


def _print_entities(e: dict):
    print("  " + "=" * 45)
    print(f"  First Name  : {e['first_name'] or 'Not found'}")
    print(f"  Surname     : {e['surname'] or 'Not found'}")
    print(f"  Father Name : {e['father_name'] or 'Not found'}")
    print(f"  Unique ID   : {e['unique_id'] or 'Not found'}")
    print(f"  ID Type     : {e['id_type'] or ''}")
    print(f"  Email       : {e['email'] or ''}")
    print(f"  Department  : {e['department'] or ''}")
    print("  " + "=" * 45)


def match_with_database(entities: dict, db_path: str = "users.db") -> Optional[tuple]:
    """
    Extracted entities ko database se match karo.
    Hierarchical: First Name + Surname + Father Name
    """
    import sqlite3

    if not entities.get("first_name"):
        print("  Cannot match - First Name missing!")
        return None

    if not os.path.exists(db_path):
        print(f"  Database not found: {db_path}")
        return None

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    fn = entities["first_name"]
    sn = entities.get("surname")
    dad = entities.get("father_name")

    print("\n  DATABASE MATCHING")
    print("  " + "-" * 45)

    cursor.execute(
        "SELECT * FROM users WHERE LOWER(first_name) = LOWER(?)",
        (fn,),
    )
    rows = cursor.fetchall()
    print(f"  Step 1 - First Name '{fn}': {len(rows)} match(es)")

    if len(rows) == 1:
        conn.close()
        return rows[0]

    if len(rows) == 0:
        conn.close()
        print(f"  No one found with first name '{fn}'")
        return None

    if sn:
        cursor.execute(
            """
            SELECT * FROM users
            WHERE LOWER(first_name) = LOWER(?)
            AND   LOWER(surname)    = LOWER(?)
            """,
            (fn, sn),
        )
        rows = cursor.fetchall()
        print(f"  Step 2 - Surname '{sn}': {len(rows)} match(es)")

        if len(rows) == 1:
            conn.close()
            return rows[0]

    if dad:
        first_word = dad.split()[0]
        cursor.execute(
            """
            SELECT * FROM users
            WHERE LOWER(first_name)  = LOWER(?)
            AND   LOWER(surname)     = LOWER(?)
            AND   LOWER(father_name) LIKE LOWER(?)
            """,
            (fn, sn or fn, f"%{first_word}%"),
        )
        rows = cursor.fetchall()
        print(f"  Step 3 - Father '{dad}': {len(rows)} match(es)")

        if len(rows) >= 1:
            conn.close()
            return rows[0]

    conn.close()
    print("  Could not uniquely identify person")
    return None
