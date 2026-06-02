import re

try:
    from config import Colors, cprint
except Exception:
    class Colors:
        CYAN = GREEN = YELLOW = RED = RESET = ""

    def cprint(message, color=""):
        print(message)


NOT_CLEAR = "Not clearly available"

LANGUAGE_NAMES = {
    "en": "English",
    "hi": "Hindi",
    "gu": "Gujarati",
    "mixed": "Mixed language",
    "unknown": "Unknown",
}

PERSON_NAME_STOPWORDS = {
    "certificate", "resume", "curriculum", "vitae", "marksheet", "mark", "sheet",
    "invoice", "bill", "receipt", "department", "university", "school",
    "college", "institute", "total", "result", "subject", "semester",
    "course", "program", "application", "form", "information", "document",
    "policy", "claim", "insurance", "customer", "vendor", "amount",
    "date", "email", "phone", "mobile", "address", "signature", "photo",
    "overload", "unknown", "available", "clearly", "not", "candidate",
    "student", "employee", "applicant", "patient", "father", "mother",
}

NAME_LABELS = [
    "full name",
    "student name",
    "candidate name",
    "applicant name",
    "employee name",
    "policyholder name",
    "policy holder name",
    "patient name",
    "customer name",
    "person name",
    "name of student",
    "name of candidate",
    "name of applicant",
    "name",
    "father name",
    "father's name",
    "mother name",
    "mother's name",
    "नाम",
    "विद्यार्थी का नाम",
    "छात्र का नाम",
    "उम्मीदवार का नाम",
    "आवेदक का नाम",
    "पिता का नाम",
    "माता का नाम",
    "નામ",
    "વિદ્યાર્થીનું નામ",
    "વિદ્યાર્થી નુ નામ",
    "ઉમેદવારનું નામ",
    "અરજદારનું નામ",
    "પિતાનું નામ",
    "માતાનું નામ",
]

LOW_PRIORITY_NAME_LABELS = {
    "father name",
    "father's name",
    "mother name",
    "mother's name",
    "पिता का नाम",
    "माता का नाम",
    "પિતાનું નામ",
    "માતાનું નામ",
}

DOCUMENT_WORDS = {
    "certificate", "certific", "certificat", "resume", "resum", "cv",
    "biodata", "marksheet", "markshet", "mark sheet", "result",
    "grade sheet", "invoice", "invoic", "bill", "receipt", "insurance",
    "policy", "claim", "aadhaar", "aadhar", "pan", "license", "licence",
    "form", "application", "information form",
}

PROTECTED_PATTERNS = [
    r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}",
    r"\b(?:\+?91[-\s]?)?[6-9]\d{9}\b",
    r"\b[A-Z]{5}[0-9]{4}[A-Z]\b",
    r"\b\d{4}\s?\d{4}\s?\d{4}\b",
    r"\b(?:CGPA|SGPA)\s*[:\-]?\s*[0-9.]+",
    r"\b\d+(?:\.\d+)?\s*%",
    r"\b(?:INR|Rs\.?|₹)\s*[0-9,]+(?:\.\d{1,2})?\b",
    r"\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b",
    r"\b\d{1,2}[-/][A-Za-z]{3,9}[-/]\d{2,4}\b",
    r"\b[A-Z]{1,5}[-/][A-Z0-9][A-Z0-9\-/]{2,25}\b",
]


def log_indicator(event, **values):
    safe_parts = []
    for key, value in values.items():
        if value is None:
            continue
        safe_parts.append(f"{key}={value}")
    suffix = " | " + ", ".join(safe_parts) if safe_parts else ""
    cprint(f"  ADMS {event}{suffix}", Colors.CYAN)


def clean_ocr_text(text):
    raw = str(text or "").replace("\r", "\n").replace("\x00", " ")
    raw = raw.replace("â‚¹", "₹")
    lines = []
    for line in raw.splitlines():
        cleaned = re.sub(r"[ \t]+", " ", line).strip()
        cleaned = re.sub(r"([|_\-])\1{3,}", r"\1\1", cleaned)
        if cleaned:
            lines.append(cleaned)
    return "\n".join(lines).strip()


def detect_language(text):
    if not text or not str(text).strip():
        return "unknown"

    devanagari = sum(1 for char in text if "\u0900" <= char <= "\u097F")
    gujarati = sum(1 for char in text if "\u0A80" <= char <= "\u0AFF")
    latin = sum(1 for char in text if ("A" <= char <= "Z") or ("a" <= char <= "z"))
    script_total = devanagari + gujarati + latin

    if script_total == 0:
        return "unknown"

    has_hi = devanagari / script_total >= 0.08
    has_gu = gujarati / script_total >= 0.08
    has_en = latin / script_total >= 0.20

    if (has_hi or has_gu) and has_en:
        return "mixed"
    if has_hi and has_gu:
        return "mixed"
    if has_hi:
        return "hi"
    if has_gu:
        return "gu"
    return "en"


def _protect_values(text):
    protected = {}
    output = str(text or "")

    for pattern in PROTECTED_PATTERNS:
        for match in list(re.finditer(pattern, output, re.I)):
            value = match.group(0)
            if value in protected.values():
                continue
            placeholder = f"ZXQPROTECT{len(protected)}QXZ"
            protected[placeholder] = value
            output = output.replace(value, placeholder, 1)

    return output, protected


def _restore_values(text, protected):
    output = str(text or "")
    for placeholder, value in protected.items():
        output = output.replace(placeholder, value)
        output = output.replace(placeholder.lower(), value)
        output = re.sub(re.escape(placeholder).replace("\\ ", r"\s*"), value, output, flags=re.I)
    return output


def translate_to_english(text, detected_language=None):
    cleaned = clean_ocr_text(text)
    language = detected_language or detect_language(cleaned)

    if not cleaned:
        return "", True, ""
    if language in {"en", "unknown"}:
        return cleaned, True, ""

    protected_text, protected = _protect_values(cleaned)
    try:
        from deep_translator import GoogleTranslator

        translator = GoogleTranslator(source="auto", target="en")
        chunks = []
        current = []
        current_len = 0
        for line in protected_text.splitlines():
            line_len = len(line) + 1
            if current and current_len + line_len > 4300:
                chunks.append("\n".join(current))
                current = []
                current_len = 0
            current.append(line)
            current_len += line_len
        if current:
            chunks.append("\n".join(current))

        translated_chunks = []
        for chunk in chunks:
            translated = translator.translate(chunk)
            if translated:
                translated_chunks.append(translated)

        translated_text = clean_ocr_text("\n".join(translated_chunks))
        translated_text = _restore_values(translated_text, protected)
        if translated_text and re.search(r"[A-Za-z]", translated_text):
            return translated_text, True, ""
    except Exception as exc:
        return cleaned, False, f"Translation not clearly available: {exc}"

    return cleaned, False, "Translation not clearly available"


def process_multilingual_text(extracted_text):
    original = clean_ocr_text(extracted_text)
    language = detect_language(original)
    english, success, warning = translate_to_english(original, language)
    log_indicator(
        "multilingual",
        text_length=len(original),
        language=language,
        translated=bool(success and english != original),
    )
    return {
        "original_text": original,
        "english_text": english or original,
        "detected_language": language,
        "translation_success": success,
        "translation_warning": warning,
    }


INDEPENDENT_VOWELS = {
    "अ": "a", "आ": "aa", "इ": "i", "ई": "ee", "उ": "u", "ऊ": "oo",
    "ऋ": "ri", "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au",
    "અ": "a", "આ": "aa", "ઇ": "i", "ઈ": "ee", "ઉ": "u", "ઊ": "oo",
    "ઋ": "ri", "એ": "e", "ઐ": "ai", "ઓ": "o", "ઔ": "au",
}

CONSONANTS = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n",
    "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "ny",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n",
    "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "f", "ब": "b", "भ": "bh", "म": "m",
    "य": "y", "र": "r", "ल": "l", "व": "v",
    "श": "sh", "ष": "sh", "स": "s", "ह": "h", "ळ": "l",
    "ક": "k", "ખ": "kh", "ગ": "g", "ઘ": "gh", "ઙ": "n",
    "ચ": "ch", "છ": "chh", "જ": "j", "ઝ": "jh", "ઞ": "ny",
    "ટ": "t", "ઠ": "th", "ડ": "d", "ઢ": "dh", "ણ": "n",
    "ત": "t", "થ": "th", "દ": "d", "ધ": "dh", "ન": "n",
    "પ": "p", "ફ": "f", "બ": "b", "ભ": "bh", "મ": "m",
    "ય": "y", "ર": "r", "લ": "l", "વ": "v",
    "શ": "sh", "ષ": "sh", "સ": "s", "હ": "h", "ળ": "l",
}

VOWEL_SIGNS = {
    "ा": "aa", "ि": "i", "ी": "ee", "ु": "u", "ू": "oo", "ृ": "ri",
    "े": "e", "ै": "ai", "ो": "o", "ौ": "au",
    "ા": "aa", "િ": "i", "ી": "ee", "ુ": "u", "ૂ": "oo", "ૃ": "ri",
    "ે": "e", "ૈ": "ai", "ો": "o", "ૌ": "au",
}

SIGNS = {
    "ं": "n", "ँ": "n", "ः": "h",
    "ં": "n", "ઁ": "n", "ઃ": "h",
}

VIRAMAS = {"्", "્"}


def contains_indic_script(text):
    return bool(re.search(r"[\u0900-\u097F\u0A80-\u0AFF]", str(text or "")))


def _cleanup_romanized_word(word):
    cleaned = re.sub(r"[^a-zA-Z.'-]", "", str(word or "")).lower()
    if not cleaned:
        return ""

    replacements = {
        "poojaa": "pooja",
        "pujaa": "pooja",
        "puja": "pooja",
        "shaha": "shah",
        "patela": "patel",
        "rahula": "rahul",
        "raahula": "rahul",
        "raahul": "rahul",
        "kumara": "kumar",
        "deepaka": "deepak",
        "hardika": "hardik",
    }
    if cleaned in replacements:
        return replacements[cleaned].title()

    if cleaned.endswith("aa") and len(cleaned) > 3:
        cleaned = cleaned[:-1]
    elif (
        cleaned.endswith("a")
        and len(cleaned) > 4
        and not cleaned.endswith(("ja", "ha", "ma", "ta", "ya", "na", "sha"))
    ):
        cleaned = cleaned[:-1]

    return cleaned.title()


def _romanize_indic_text(text):
    output = []
    index = 0
    text = str(text or "")

    while index < len(text):
        char = text[index]

        if char in INDEPENDENT_VOWELS:
            output.append(INDEPENDENT_VOWELS[char])
            index += 1
            continue

        if char in CONSONANTS:
            suffix = "a"
            next_index = index + 1
            if next_index < len(text):
                next_char = text[next_index]
                if next_char in VOWEL_SIGNS:
                    suffix = VOWEL_SIGNS[next_char]
                    index += 1
                elif next_char in VIRAMAS:
                    suffix = ""
                    index += 1
            output.append(CONSONANTS[char] + suffix)
            index += 1
            continue

        if char in SIGNS:
            output.append(SIGNS[char])
            index += 1
            continue

        output.append(char)
        index += 1

    rough = re.sub(r"\s+", " ", "".join(output)).strip()
    words = []
    for word in rough.split():
        if re.search(r"[A-Za-z]", word):
            cleaned = _cleanup_romanized_word(word)
            if cleaned:
                words.append(cleaned)
    return " ".join(words).strip()


def _clean_name_text(name_text):
    value = re.sub(r"\s+", " ", str(name_text or "")).strip(" :-|,.;")
    value = re.sub(r"\b(?:mr|mrs|ms|miss|dr|prof|shri|smt)\.?\b", " ", value, flags=re.I)
    value = re.sub(r"\s+", " ", value).strip(" :-|,.;")
    return value


def _title_case_name(value):
    words = re.findall(r"[A-Za-z][A-Za-z.'-]*", str(value or ""))
    titled = []
    for word in words:
        if word.isupper() or word.islower():
            titled.append(word.title())
        else:
            titled.append(word[0].upper() + word[1:])
    return " ".join(titled).strip()


def validate_person_name(name_text, require_two_words=True):
    name = _title_case_name(name_text)
    if not name or name == NOT_CLEAR:
        return "", 0

    words = re.findall(r"[A-Za-z][A-Za-z.'-]*", name)
    if require_two_words and len(words) < 2:
        return "", 0
    if len(words) < 1 or len(words) > 5:
        return "", 0
    if any(len(word) < 2 for word in words):
        return "", 0

    lowered_words = [word.lower().strip(".") for word in words]
    if any(word in PERSON_NAME_STOPWORDS for word in lowered_words):
        return "", 0
    if any(word in DOCUMENT_WORDS for word in lowered_words):
        return "", 0
    if re.search(r"[@\d_]", name):
        return "", 0

    score = 55 + min(len(words), 4) * 8
    if len(words) in {2, 3}:
        score += 12
    if all(word[0].isupper() for word in words):
        score += 8
    return name, min(score, 95)


def transliterate_name_to_english(name_text):
    cleaned = _clean_name_text(name_text)
    if not cleaned:
        return NOT_CLEAR

    if contains_indic_script(cleaned):
        cleaned = _romanize_indic_text(cleaned)
    else:
        cleaned = _title_case_name(cleaned)

    name, confidence = validate_person_name(cleaned, require_two_words=False)
    if not name or confidence < 55:
        return NOT_CLEAR
    return name


def _strip_label_from_line(line, label):
    escaped = re.escape(label)
    value = re.sub(rf"^.*?{escaped}\s*(?:\([^)]*\))?\s*[:：\-|]?\s*", "", line, flags=re.I)
    value = re.sub(r"^[\]\)\}:：\-| ]+", "", value)
    return value.strip(" :-|,.;")


def _candidate_from_text(value):
    value = _clean_name_text(value)
    value = re.split(
        r"\b(?:date|dob|id|roll|enrollment|department|course|class|semester|email|phone|mobile|address)\b",
        value,
        maxsplit=1,
        flags=re.I,
    )[0]
    value = re.sub(r"\d+", " ", value)
    value = re.sub(r"[^A-Za-z\u0900-\u097F\u0A80-\u0AFF .'’-]", " ", value)
    return re.sub(r"\s+", " ", value).strip(" :-|,.;")


def _add_name_candidate(candidates, raw_value, base_score, source):
    candidate = _candidate_from_text(raw_value)
    if not candidate:
        return
    candidate = transliterate_name_to_english(candidate)
    if candidate == NOT_CLEAR:
        return
    name, validation_score = validate_person_name(candidate, require_two_words=True)
    if not name:
        return
    score = min(100, int((base_score + validation_score) / 2))
    candidates.append({"name": name, "confidence": score, "source": source})


def extract_person_name(original_text, english_text="", document_type=""):
    candidates = []
    sources = [
        ("original", clean_ocr_text(original_text)),
        ("english", clean_ocr_text(english_text)),
    ]

    for source_name, source_text in sources:
        if not source_text:
            continue
        lines = [line.strip() for line in source_text.splitlines() if line.strip()]
        for index, line in enumerate(lines[:140]):
            lowered = line.lower()
            for label in NAME_LABELS:
                label_lower = label.lower()
                if label_lower not in lowered and label not in line:
                    continue

                value = _strip_label_from_line(line, label)
                priority = 74 if label_lower in LOW_PRIORITY_NAME_LABELS or label in LOW_PRIORITY_NAME_LABELS else 90
                _add_name_candidate(candidates, value, priority, f"{source_name}:{label}")

                for next_line in lines[index + 1:index + 3]:
                    if re.search(r"[:：]", next_line) and not contains_indic_script(next_line):
                        break
                    _add_name_candidate(candidates, next_line, priority - 8, f"{source_name}:{label}:next")

        flat = re.sub(r"\s+", " ", source_text)
        phrase_patterns = [
            r"(?:certify that|this is to certify that)\s+(?:mr|mrs|ms|miss|dr)?\.?\s*([A-Za-z][A-Za-z .'-]{3,80})\s+(?:has|for|successfully|is|was)\b",
            r"\bresume\s+of\s+([A-Za-z][A-Za-z .'-]{3,80})\b",
            r"\b(?:awarded to|presented to|issued to)\s+([A-Za-z][A-Za-z .'-]{3,80})\b",
        ]
        for pattern in phrase_patterns:
            match = re.search(pattern, flat, re.I)
            if match:
                _add_name_candidate(candidates, match.group(1), 82, f"{source_name}:phrase")

    if not candidates:
        return {"name": NOT_CLEAR, "confidence": 0, "source": "none"}

    candidates.sort(key=lambda item: item["confidence"], reverse=True)
    best = candidates[0]
    if best["confidence"] < 70:
        return {"name": NOT_CLEAR, "confidence": best["confidence"], "source": best["source"]}
    return best


def is_weak_summary(summary):
    text = re.sub(r"\s+", " ", str(summary or "")).strip()
    lowered = text.lower()
    if not text:
        return True
    if len(text) < 45:
        return True
    if re.fullmatch(r"[a-z]{3,12}", lowered):
        return True
    if any(fragment in lowered for fragment in ["certificate of certific", "resume of overload", "document contains details"]):
        return True
    if lowered in {"not found", NOT_CLEAR.lower()}:
        return True
    return False


def summary_confidence(summary, english_text):
    if is_weak_summary(summary):
        return 25
    score = 55
    if len(str(english_text or "")) > 250:
        score += 15
    if re.search(r"\b(name|id|email|phone|cgpa|sgpa|amount|date|skills|education|policy|invoice)\b", summary or "", re.I):
        score += 15
    if len(str(summary or "")) > 120:
        score += 10
    return min(score, 95)
