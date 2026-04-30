# # ============================================
# # MODULE 4: NLP_PARSER.PY
# # Entity Extraction — Names, IDs, DOB, etc.
# # Uses: Regex (always works) + spaCy (optional)
# # ============================================

# import re
# import os
# import sys
# sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# from config import Colors, cprint


# # ============================================
# # PART A — REGEX PATTERNS (Core Logic)
# # ============================================

# # Pattern dictionary — easy to extend!
# PATTERNS = {
#     # Names
#     "first_name"  : [
#         r"(?i)first\s*name\s*[:\-]\s*([A-Za-z]+)",
#         r"(?i)name\s*[:\-]\s*([A-Za-z]+)",
#         r"(?i)employee\s*name\s*[:\-]\s*([A-Za-z]+)",
#         r"(?i)candidate\s*name\s*[:\-]\s*([A-Za-z]+)",
#     ],
#     "surname"     : [
#         r"(?i)sur\s*name\s*[:\-]\s*([A-Za-z]+)",
#         r"(?i)last\s*name\s*[:\-]\s*([A-Za-z]+)",
#         r"(?i)family\s*name\s*[:\-]\s*([A-Za-z]+)",
#     ],
#     "father_name" : [
#         r"(?i)father'?s?\s*name\s*[:\-]\s*(.+?)(?:\n|$)",
#         r"(?i)parent\s*name\s*[:\-]\s*(.+?)(?:\n|$)",
#         r"(?i)s/o\s*[:\-]?\s*(.+?)(?:\n|$)",
#         r"(?i)d/o\s*[:\-]?\s*(.+?)(?:\n|$)",
#     ],

#     # IDs
#     "aadhar_no"   : [r"\b(\d{4}\s?\d{4}\s?\d{4})\b"],
#     "pan_no"      : [r"\b([A-Z]{5}[0-9]{4}[A-Z]{1})\b"],
#     "employee_id" : [
#         r"(?i)employee\s*id\s*[:\-]\s*([A-Z0-9\-]+)",
#         r"(?i)emp\s*id\s*[:\-]\s*([A-Z0-9\-]+)",
#         r"(?i)staff\s*id\s*[:\-]\s*([A-Z0-9\-]+)",
#     ],

#     # Other Fields
#     "dob"         : [
#         r"(?i)(?:dob|date\s*of\s*birth|born)\s*[:\-]?\s*(\d{1,2}[-/]\w+[-/]\d{2,4})",
#         r"(?i)(?:dob|date\s*of\s*birth)\s*[:\-]?\s*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
#     ],
#     "email"       : [r"\b([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)\b"],
#     "phone"       : [
#         r"\b([6-9]\d{9})\b",
#         r"\b(\+91[-\s]?\d{10})\b",
#     ],
#     "department"  : [
#         r"(?i)department\s*[:\-]\s*(.+?)(?:\n|$)",
#         r"(?i)dept\s*[:\-]\s*(.+?)(?:\n|$)",
#         r"(?i)division\s*[:\-]\s*(.+?)(?:\n|$)",
#     ],
# }


# def extract_with_regex(text, field):
#     """
#     Ek field ke liye regex se value nikalo
#     Multiple patterns try karta hai — pehla match return karta hai
#     """
#     patterns = PATTERNS.get(field, [])

#     for pattern in patterns:
#         match = re.search(pattern, text)
#         if match:
#             value = match.group(1).strip()
#             # Clean up extra whitespace/newlines
#             value = re.sub(r'\s+', ' ', value).strip()
#             return value

#     return None


# # ============================================
# # PART B — UNIQUE ID DETECTOR
# # ============================================

# def find_unique_id(text):
#     """
#     Document mein koi bhi unique ID dhundo
#     Priority: Aadhar > PAN > Employee ID
#     Returns: (id_type, id_value)
#     """
#     # Aadhar — 12 digit number
#     aadhar = extract_with_regex(text, "aadhar_no")
#     if aadhar:
#         return "Aadhar", aadhar

#     # PAN — ABCDE1234F format
#     pan = extract_with_regex(text, "pan_no")
#     if pan:
#         return "PAN", pan

#     # Employee ID
#     emp_id = extract_with_regex(text, "employee_id")
#     if emp_id:
#         return "Employee ID", emp_id

#     # Any number that looks like an ID (fallback)
#     id_match = re.search(r"(?i)(?:id|no|number|#)\s*[:\-]?\s*([A-Z0-9\-]{4,15})", text)
#     if id_match:
#         return "ID", id_match.group(1).strip()

#     return "Unknown", None


# # ============================================
# # PART C — spaCy NER (Optional Enhancement)
# # ============================================

# def extract_with_spacy(text):
#     """
#     spaCy ke Named Entity Recognition se names nikalo
#     Fallback if regex doesn't find names
#     """
#     try:
#         import spacy

#         # Load model — English model
#         try:
#             nlp = spacy.load("en_core_web_sm")
#         except OSError:
#             # Auto download if not found
#             cprint("  📦 spaCy model download ho raha hai...", Colors.YELLOW)
#             os.system("python -m spacy download en_core_web_sm")
#             nlp = spacy.load("en_core_web_sm")

#         doc    = nlp(text[:5000])  # Limit text for performance
#         people = [ent.text for ent in doc.ents if ent.label_ == "PERSON"]

#         return people

#     except ImportError:
#         return []
#     except Exception:
#         return []


# # ============================================
# # PART D — MASTER EXTRACTION FUNCTION
# # ============================================

# def extract_entities(text):
#     """
#     ⭐ MAIN ENTITY EXTRACTION FUNCTION ⭐
#     Text do → Saari information structured dict mein milegi

#     Returns dict with:
#     - first_name, surname, father_name
#     - unique_id (type + value)
#     - dob, email, phone, department
#     - all_names (from spaCy)
#     """
#     cprint("\n  🧠 Extracting Entities from text...", Colors.CYAN)

#     result = {
#         "first_name"  : None,
#         "surname"     : None,
#         "father_name" : None,
#         "unique_id"   : {"type": None, "value": None},
#         "dob"         : None,
#         "email"       : None,
#         "phone"       : None,
#         "department"  : None,
#         "all_names"   : [],
#     }

#     # --- Extract each field with regex ---
#     for field in ["first_name", "surname", "father_name", "dob", "email", "phone", "department"]:
#         value = extract_with_regex(text, field)
#         if value:
#             result[field] = value

#     # --- Unique ID ---
#     id_type, id_val = find_unique_id(text)
#     result["unique_id"] = {"type": id_type, "value": id_val}

#     # --- spaCy enhancement for names ---
#     if not result["first_name"] or not result["surname"]:
#         spacy_names = extract_with_spacy(text)
#         result["all_names"] = spacy_names

#         # Use spaCy names as fallback
#         if spacy_names and not result["first_name"]:
#             name_parts = spacy_names[0].split()
#             if len(name_parts) >= 1:
#                 result["first_name"] = name_parts[0]
#             if len(name_parts) >= 2:
#                 result["surname"]    = name_parts[-1]

#     # --- Clean up None values ---
#     for key, val in result.items():
#         if isinstance(val, str):
#             result[key] = val.strip() if val else None

#     cprint(f"  ✅ Entities extracted!", Colors.GREEN)
#     return result


# # ============================================
# # PART E — PRINT RESULT (Pretty format)
# # ============================================

# def print_entities(entities):
#     """
#     Extracted entities sundar format mein print karo
#     """
#     uid = entities.get("unique_id", {})

#     print(f"""
# ╔══════════════════════════════════════════════╗
# ║         📋 EXTRACTED INFORMATION             ║
# ╠══════════════════════════════════════════════╣
# ║  First Name   : {str(entities.get('first_name')  or '❌ Not found'):<29}║
# ║  Surname      : {str(entities.get('surname')     or '❌ Not found'):<29}║
# ║  Father Name  : {str(entities.get('father_name') or '❌ Not found'):<29}║
# ║  Unique ID    : {str(uid.get('type','?') + ': ' + str(uid.get('value','Not found'))):<29}║
# ║  Date of Birth: {str(entities.get('dob')         or '❌ Not found'):<29}║
# ║  Email        : {str(entities.get('email')       or '❌ Not found'):<29}║
# ║  Phone        : {str(entities.get('phone')       or '❌ Not found'):<29}║
# ║  Department   : {str(entities.get('department')  or '❌ Not found'):<29}║
# ╚══════════════════════════════════════════════╝""")


# # ============================================
# # DIRECT TEST
# # ============================================
# if __name__ == "__main__":
#     # Test with sample text
#     sample_text = """
#     Employee Information Form

#     First Name: Pooja
#     Surname: Patel
#     Father's Name: Bhadhreshkumar Patel
#     Date of Birth: 15-Aug-1995
#     Employee ID: DEV-402
#     Department: Software Development
#     Email: pooja.patel@gmail.com
#     Phone: 9876501234
#     """

#     print("Testing NLP Parser with sample text...")
#     entities = extract_entities(sample_text)
#     print_entities(entities)

# ============================================
# MODULE 4: NLP_PARSER.PY
# Entity Extraction — Names, IDs, DOB, etc.
# Upgraded with Translation & Smart Fallback
# ============================================

# ============================================
# MODULE 4: NLP_PARSER.PY
# Entity Extraction — Names, IDs, DOB, etc.
# Upgraded with Translation, Smart Fallback & DYNAMIC EXTRACTION
# ============================================

# ============================================
# MODULE 4: NLP_PARSER.PY  — FIXED VERSION
# Handles: Employee Form, Certificate,
#          Internship Report, Train Ticket,
#          Hindi/Gujarati documents
# ============================================

import re
import os
import sys
from deep_translator import GoogleTranslator

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from config import Colors, cprint
except ImportError:
    class Colors: CYAN = GREEN = YELLOW = RED = BOLD = RESET = ""
    def cprint(t, c=""): print(t)


# ============================================
# OCR CHAR CORRECTION — Fix common OCR mis-reads in names
# e.g. "POQUA" → "POOJA", "Poqua" → "Pooja"
# ============================================

def _correct_ocr_chars_in_name(text):
    """
    Fix common OCR character mis-reads inside name strings.
    'oqu' followed by a vowel → 'ooj'
    e.g. POQUA → POOJA, Poqua → Pooja
    """
    if not text:
        return text
    # lowercase
    text = re.sub(r'oqu(?=[aeiou])', 'ooj', text)
    # UPPERCASE
    text = re.sub(r'OQU(?=[AEIOU])', 'OOJ', text)
    # Mixed case
    text = re.sub(
        r'(?i)oqu(?=[aeiouAEIOU])',
        lambda m: 'OOJ' if m.group(0)[0].isupper() else 'ooj',
        text,
    )
    return text


# ============================================
# WORDS THAT ARE NEVER A PERSON'S NAME
# ============================================
SKIP_TITLE_WORDS = {
    "internship","completion","certificate","report","form","resume","cv",
    "profile","details","document","information","declaration","abstract",
    "acknowledgement","introduction","conclusion","chapter","appendix",
    "director","manager","managing","head","officer","president","chairman",
    "sincerely","regards","yours","truly","faithfully","subject","date",
    "dear","sir","madam","respected","university","institute","college",
    "department","division","technology","engineering","science","commerce",
    "sparks","ideas","pavitrasoft","qrious","mbit","cvm","irctc","railways",
    "general","waiting","confirmed","class","quota","sitting","second",
    "booked","arrival","departure","train","ticket","reservation","slip",
    "electronic","normal","user","payment","details","passenger","invoice",
    "item","amount","total","subtotal","qty","quantity","price","rate",
    "description","product","service","gst","tax","taxable","balance",
    "bill","invoice","order","unit","value","table",
}

# Designations — agar kisi ke baad yeh aaye toh woh person SIGNATORY hai, recipient nahi
DESIGNATION_WORDS = {
    "director","manager","ceo","cto","coo","president","chairman","founder",
    "head","officer","principal","dean","professor","dr","mr","mrs","ms",
    "guide","mentor","supervisor","coordinator","authorized","signature",
}

GENERIC_NAME_BLOCK_WORDS = {
    "item", "amount", "total", "subtotal", "qty", "quantity", "price", "rate",
    "description", "product", "service", "gst", "tax", "taxable", "balance",
    "bill", "invoice", "order", "unit", "value", "table", "date",
    "id", "email", "phone", "mobile", "department", "form",
}

PERSON_CONTEXT_HINTS = (
    "@", "email", "phone", "mobile", "contact", "linkedin.com", "github.com",
    "summary", "education", "experience", "projects", "resume", "curriculum vitae",
    "department", "employee id", "father's name", "date of birth", "dob",
)


def _has_person_context(text):
    lowered = (text or "").lower()
    return any(hint in lowered for hint in PERSON_CONTEXT_HINTS)


def _is_safe_generic_name_words(words, text, line_index=0):
    if not (2 <= len(words) <= 3):
        return False
    if not all(word.isalpha() for word in words):
        return False
    if any(len(word) < 2 for word in words):
        return False

    lowered = [word.lower() for word in words]
    if any(word in SKIP_TITLE_WORDS for word in lowered):
        return False
    if any(word in GENERIC_NAME_BLOCK_WORDS for word in lowered):
        return False
    if line_index > 5:
        return False
    if not _has_person_context(text):
        return False

    return True


def _clean_capture(value):
    return re.sub(r"\s+", " ", str(value or "")).strip(" |:-")


MULTILINGUAL_LABEL_PATTERNS = {
    "first_name": [
        r"first\s*name",
        r"given\s*name",
        r"પ્રથમ\s*નામ",
        r"નામ",
        r"प्रथम\s*नाम",
        r"पहला\s*नाम",
        r"पहले\s*नाम",
    ],
    "surname": [
        r"surname",
        r"sur\s*name",
        r"last\s*name",
        r"family\s*name",
        r"અટક",
        r"સરનેમ",
        r"ઉપનામ",
        r"અંતિમ\s*નામ",
        r"उपनाम",
        r"सरनेम",
        r"अंतिम\s*नाम",
    ],
    "father_name": [
        r"father'?s?\s*name",
        r"father\s*name",
        r"middle\s*name",
        r"પિતાનું\s*નામ",
        r"\bપિતા\b",
        r"पिता\s*का\s*नाम",
        r"\bपिता\b",
        r"मध्य\s*नाम",
    ],
    "full_name": [
        r"full\s*name",
        r"candidate'?s?\s*name",
        r"student\s*name",
        r"પૂર્ણ\s*નામ",
        r"સંપૂર્ણ\s*નામ",
        r"विद्यार्थी\s*का\s*नाम",
        r"पूरा\s*नाम",
        r"पूर्ण\s*नाम",
    ],
    "department": [
        r"department",
        r"dept",
        r"division",
        r"વિભાગ",
        r"विभाग",
    ],
    "employee_id": [
        r"employee\s*id",
        r"emp\s*id",
        r"staff\s*id",
        r"\bid\b",
        r"આઈડી",
        r"आईडी",
        r"आई\.डी",
    ],
}

MULTILINGUAL_FORM_HINTS = [
    r"માહિતી\s*ફોર્મ",
    r"जानकारी\s*फॉर्म",
    r"सूचना\s*फॉर्म",
    r"information\s*form",
]

INDIC_INDEPENDENT_VOWELS = {
    "अ": "a", "आ": "aa", "इ": "i", "ई": "i", "उ": "u", "ऊ": "u",
    "ऋ": "ri", "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au",
    "અ": "a", "આ": "aa", "ઇ": "i", "ઈ": "i", "ઉ": "u", "ઊ": "u",
    "ઋ": "ri", "એ": "e", "ઐ": "ai", "ઓ": "o", "ઔ": "au",
}

INDIC_CONSONANTS = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n",
    "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "ny",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n",
    "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "f", "ब": "b", "भ": "bh", "म": "m",
    "य": "y", "र": "r", "ल": "l", "व": "v",
    "श": "sh", "ष": "sh", "स": "s", "ह": "h", "ळ": "l",
    "क़": "q", "फ़": "f", "ज़": "z", "ड़": "d", "ढ़": "dh",
    "ક": "k", "ખ": "kh", "ગ": "g", "ઘ": "gh", "ઙ": "n",
    "ચ": "ch", "છ": "chh", "જ": "j", "ઝ": "jh", "ઞ": "ny",
    "ટ": "t", "ઠ": "th", "ડ": "d", "ઢ": "dh", "ણ": "n",
    "ત": "t", "થ": "th", "દ": "d", "ધ": "dh", "ન": "n",
    "પ": "p", "ફ": "f", "બ": "b", "ભ": "bh", "મ": "m",
    "ય": "y", "ર": "r", "લ": "l", "વ": "v",
    "શ": "sh", "ષ": "sh", "સ": "s", "હ": "h", "ળ": "l",
}

INDIC_VOWEL_SIGNS = {
    "ा": "aa", "ि": "i", "ी": "i", "ु": "u", "ू": "u", "ृ": "ri",
    "े": "e", "ै": "ai", "ो": "o", "ौ": "au",
    "ા": "aa", "િ": "i", "ી": "i", "ુ": "u", "ૂ": "u", "ૃ": "ri",
    "ે": "e", "ૈ": "ai", "ો": "o", "ૌ": "au",
}

INDIC_SIGNS = {
    "ं": "n", "ँ": "n", "ः": "h",
    "ં": "n", "ઁ": "n", "ઃ": "h",
}

INDIC_VIRAMAS = {"्", "્"}


def _contains_indic_script(text):
    return bool(re.search(r"[\u0900-\u097F\u0A80-\u0AFF]", text or ""))


def _cleanup_transliterated_word(word):
    cleaned = str(word or "").lower()
    cleaned = cleaned.replace("aai", "ai").replace("ee", "i").replace("oo", "u")
    cleaned = cleaned.replace("aa", "a")
    cleaned = cleaned.replace("ii", "i").replace("uu", "u")
    cleaned = re.sub(r"yya\b", "ya", cleaned)
    cleaned = re.sub(r"([a-z])haa\b", r"\1ha", cleaned)
    if len(cleaned) > 5 and re.search(r"(ika|aka|uka|ega|oga|aka|sha|bha|dha|tha|ka|ga|da|ta|na|pa|ba|ma|la|ra|sa|ha)\b", cleaned):
        cleaned = re.sub(r"a\b", "", cleaned)
    return cleaned.title()


def _romanize_indic_text(text):
    if not _contains_indic_script(text):
        return _clean_capture(text)

    output = []
    index = 0
    text = str(text or "")

    while index < len(text):
        char = text[index]

        if char in INDIC_INDEPENDENT_VOWELS:
            output.append(INDIC_INDEPENDENT_VOWELS[char])
            index += 1
            continue

        if char in INDIC_CONSONANTS:
            piece = INDIC_CONSONANTS[char]
            next_index = index + 1
            suffix = "a"

            if next_index < len(text):
                next_char = text[next_index]
                if next_char in INDIC_VOWEL_SIGNS:
                    suffix = INDIC_VOWEL_SIGNS[next_char]
                    index += 1
                elif next_char in INDIC_VIRAMAS:
                    suffix = ""
                    index += 1

            output.append(piece + suffix)
            index += 1
            continue

        if char in INDIC_SIGNS:
            output.append(INDIC_SIGNS[char])
            index += 1
            continue

        output.append(char)
        index += 1

    transliterated = re.sub(r"\s+", " ", "".join(output)).strip()
    words = [
        _cleanup_transliterated_word(word) if re.search(r"[A-Za-z]", word) else word
        for word in transliterated.split()
    ]
    return " ".join(words).strip()


def _translate_value_to_english(value):
    cleaned = _clean_capture(value)
    if not cleaned:
        return ""
    if not _contains_indic_script(cleaned):
        return cleaned

    try:
        translated = GoogleTranslator(source="auto", target="en").translate(cleaned)
        translated = _clean_capture(translated)
        if translated and re.search(r"[A-Za-z]", translated):
            return translated
    except Exception:
        pass

    return _romanize_indic_text(cleaned)


def _extract_multilingual_line_value(lines, label_patterns):
    label_union = "|".join(f"(?:{pattern})" for pattern in label_patterns)

    for index, line in enumerate(lines):
        if not re.search(label_union, line, re.I):
            continue

        candidate = re.sub(
            rf".*?(?:{label_union})(?:\s*\([^)]*\))?\s*[:：\-|]?\s*",
            "",
            line,
            flags=re.I,
        ).strip(" |:-")
        candidate = re.sub(r"^\([^)]*\)\s*", "", candidate).strip(" |:-")
        candidate = re.sub(r"^[\)\]\}\s:：\-|]+", "", candidate).strip(" |:-")

        if not candidate and index + 1 < len(lines):
            candidate = lines[index + 1].strip(" |:-")

        if candidate:
            return candidate

    return ""


def _extract_multilingual_labeled_fields(text):
    lines = [line.strip() for line in re.split(r"[\r\n]+", text or "") if line.strip()]
    extracted = {}

    for field_name, patterns in MULTILINGUAL_LABEL_PATTERNS.items():
        value = _extract_multilingual_line_value(lines, patterns)
        if not value:
            continue

        if field_name in {"first_name", "surname", "father_name", "full_name", "department"}:
            value = _translate_value_to_english(value)
        else:
            value = _clean_capture(value)

        if value:
            extracted[field_name] = value

    email_match = re.search(r"[\w\.\+\-]+@[\w\-]+\.[a-z]{2,}", text or "", re.I)
    if email_match:
        extracted["email"] = email_match.group(0).strip()

    phone_match = re.search(r"(?:\+?\d[\d\-\s]{8,}\d)", text or "")
    if phone_match:
        digits_only = re.sub(r"\D", "", phone_match.group(0))
        if len(digits_only) >= 10:
            extracted["phone"] = digits_only[-10:]

    id_value = _extract_multilingual_line_value(lines, MULTILINGUAL_LABEL_PATTERNS["employee_id"])
    if id_value:
        id_value = _clean_capture(id_value)
        id_match = re.search(r"[A-Z0-9][A-Z0-9\-]{3,25}", id_value, re.I)
        if id_match:
            extracted["employee_id"] = id_match.group(0).upper()

    surname = extracted.get("surname")
    father_name = extracted.get("father_name")
    if surname and father_name:
        lowered_father = father_name.lower().strip()
        lowered_surname = surname.lower().strip()
        if lowered_father.endswith(" " + lowered_surname):
            extracted["father_name"] = father_name[: -len(surname)].strip()

    return extracted


def _build_multilingual_english_hint_text(raw_text):
    hints = _extract_multilingual_labeled_fields(raw_text)
    lines = []

    if hints:
        lines.append("Information Form")
    if hints.get("first_name"):
        lines.append(f"First Name: {hints['first_name']}")
    if hints.get("surname"):
        lines.append(f"Surname: {hints['surname']}")
    if hints.get("father_name"):
        lines.append(f"Father's Name: {hints['father_name']}")
    if hints.get("full_name"):
        lines.append(f"Full Name: {hints['full_name']}")
    if hints.get("employee_id"):
        lines.append(f"Employee ID: {hints['employee_id']}")
    if hints.get("department"):
        lines.append(f"Department: {hints['department']}")
    if hints.get("email"):
        lines.append(f"Email: {hints['email']}")
    if hints.get("phone"):
        lines.append(f"Phone: {hints['phone']}")

    return "\n".join(lines).strip()


def _normalize_marksheet_text(text):
    return re.sub(r"[|]+", " ", text or "").replace("\r", "\n")


def _is_noise_text(value):
    cleaned = _clean_capture(value)
    if not cleaned:
        return True
    if cleaned in {"()", "[]", "{}", "-", "--", "_"}:
        return True
    if not re.search(r"[A-Za-z0-9]", cleaned):
        return True

    lowered = cleaned.lower()
    noise_words = {
        "whatsapp", "image", "photo", "scan", "camera", "screenshot",
        "score", "scores", "sores", "at", "pm", "am", "eg", "e.g",
    }
    return lowered in noise_words


def _is_valid_name_value(value):
    if _is_noise_text(value):
        return False

    words = re.findall(r"[A-Za-z]+", str(value))
    if not words:
        return False
    if any(len(word) < 2 for word in words):
        return False
    if any(word.lower() in SKIP_TITLE_WORDS for word in words):
        return False
    return True


def _is_valid_department_value(value):
    if _is_noise_text(value):
        return False

    cleaned = _clean_capture(value)
    if len(cleaned) < 3:
        return False
    if re.fullmatch(r"[\W_]+", cleaned):
        return False
    return True


def _is_valid_id_value(value):
    if _is_noise_text(value):
        return False

    cleaned = _clean_capture(value)
    if len(cleaned) < 4:
        return False
    if not re.search(r"\d", cleaned):
        return False
    if not re.fullmatch(r"[A-Za-z0-9\- ]{4,25}", cleaned):
        return False
    return True


def _sanitize_extracted(extracted):
    cleaned = dict(extracted or {})

    for key in ["first_name", "surname", "father_name"]:
        value = cleaned.get(key)
        if value and not _is_valid_name_value(value):
            cleaned.pop(key, None)

    department = cleaned.get("department")
    if department and not _is_valid_department_value(department):
        cleaned.pop("department", None)

    employee_id = cleaned.get("employee_id")
    if employee_id and not _is_valid_id_value(employee_id):
        cleaned.pop("employee_id", None)

    unique_id = cleaned.get("unique_id")
    if isinstance(unique_id, dict) and not _is_valid_id_value(unique_id.get("value")):
        cleaned.pop("unique_id", None)

    return cleaned


def _capture_labeled_value(text, label_pattern, stop_patterns):
    normalized = _normalize_marksheet_text(text)
    lines = [line.strip() for line in normalized.split("\n") if line.strip()]

    def trim_at_stop(value):
        cleaned = str(value or "")
        for stop_pattern in stop_patterns:
            match = re.search(rf"\b{stop_pattern}\b", cleaned, re.I)
            if match:
                cleaned = cleaned[:match.start()]
        return _clean_capture(cleaned)

    def word_count(value):
        return len(re.findall(r"[A-Za-z]+", value or ""))

    for index, line in enumerate(lines):
        if not re.search(label_pattern, line, re.I):
            continue

        candidate_parts = []
        direct_candidate = ""
        current = re.sub(label_pattern, "", line, flags=re.I).strip(" :-|")
        if current:
            direct_candidate = trim_at_stop(current)
            candidate_parts.append(current)

        for next_line in lines[index + 1:index + 4]:
            if any(re.search(stop_pattern, next_line, re.I) for stop_pattern in stop_patterns):
                break
            candidate_parts.append(next_line)

        candidate = trim_at_stop(" ".join(candidate_parts))
        if direct_candidate and candidate:
            if (
                candidate.lower().startswith(direct_candidate.lower())
                and word_count(candidate) > word_count(direct_candidate)
            ):
                return candidate
            return direct_candidate
        if candidate:
            return candidate
        if direct_candidate:
            return direct_candidate

    flat = re.sub(r"\s+", " ", normalized)
    stop_union = "|".join(f"(?:{pattern})" for pattern in stop_patterns)
    pattern = rf"{label_pattern}\s*[:\-|]?\s*(.+?)(?=\s+(?:{stop_union})\b|$)"
    match = re.search(pattern, flat, re.I)
    if match:
        return trim_at_stop(match.group(1))

    return ""


def _split_student_name(name_text):
    parts = [
        _correct_ocr_chars_in_name(part.title())
        for part in re.findall(r"[A-Za-z]+", name_text or "")
        if part.lower() not in SKIP_TITLE_WORDS
    ]
    if not parts:
        return {}

    while parts and len(parts[-1]) < 2:
        parts.pop()

    if len(parts) < 3:
        return {}

    if any(part.lower() in GENERIC_NAME_BLOCK_WORDS for part in parts):
        return {}

    return {
        "surname": parts[0],
        "first_name": parts[1],
        "father_name": " ".join(parts[2:]),
    }


def _extract_marksheet_name(text):
    stop_patterns = [
        r"college\s*name", r"program\s*name", r"exam\s*name",
        r"seat\s*no", r"sp\s*id", r"result\s*declared",
        r"enrol(?:l)?ment", r"registration\s*no", r"course\s*code",
        r"sgpa", r"cgpa", r"\bresult\b", r"s\.?\s*i\.?\s*d\.?\s*no",
        r"sid\s*no", r"sr\.?\s*no", r"stream",
    ]

    for label_pattern in [
        r"student\s*name",
        r"candidate'?s?\s*name",
        r"name\s*of\s*candidate",
        r"full\s*name",
    ]:
        candidate = _capture_labeled_value(text, label_pattern, stop_patterns)
        if candidate:
            return _split_student_name(candidate)

    flat = re.sub(r"\s+", " ", _normalize_marksheet_text(text))
    direct_match = re.search(
        r"(?:^|[|])\s*(?:full\s*name|name)\s*[:\-|]\s*([A-Z][A-Z ]{5,80})(?=\s+(?:exam\s*name|month|seat\s*no|centre|school\s*index|statement\s*no|grade|percentile)\b|$)",
        flat,
        re.I,
    )
    if direct_match:
        return _split_student_name(direct_match.group(1))

    normalized = _normalize_marksheet_text(text)
    lines = [line.strip() for line in normalized.split("\n") if line.strip()]
    for line in lines:
        words = re.findall(r"[A-Za-z]+", line)
        if len(words) < 2 or len(words) > 4:
            continue
        if any(word.lower() in SKIP_TITLE_WORDS for word in words):
            continue
        if not all(len(word) >= 2 for word in words):
            continue
        if line.upper() != line:
            continue
        return _split_student_name(" ".join(words))

    return {}


def _extract_marksheet_program(text):
    stop_patterns = [
        r"student\s*name", r"college\s*name", r"exam\s*name",
        r"seat\s*no", r"sp\s*id", r"result\s*declared",
        r"enrol(?:l)?ment", r"registration\s*no",
    ]
    return _capture_labeled_value(text, r"program\s*name", stop_patterns)


def _extract_marksheet_stream(text):
    match = re.search(r"\b(science|commerce|general|arts)\s+stream\b", text or "", re.I)
    if match:
        return f"{match.group(1).upper()} STREAM"
    return ""


def _extract_marksheet_department(program_name):
    if not program_name:
        return ""

    parenthetical = re.findall(r"\(([^()]+)\)", program_name)
    if parenthetical:
        return _clean_capture(max(parenthetical, key=len)).strip("()")

    branch_matches = [
        _clean_capture(match).strip("()")
        for match in re.findall(
            r"([A-Za-z/& ]{3,}(?:engineering|technology|science|commerce|management|application))",
            program_name,
            re.I,
        )
    ]
    preferred = [
        match for match in branch_matches
        if match.lower() not in {
            "bachelor of technology",
            "master of technology",
            "bachelor of engineering",
            "master of engineering",
        }
    ]
    if preferred:
        engineering_first = sorted(
            preferred,
            key=lambda value: ("engineering" not in value.lower(), -len(value)),
        )
        return engineering_first[0]

    cleaned = _clean_capture(program_name)
    prefixes = [
        "bachelor of technology",
        "master of technology",
        "bachelor of engineering",
        "master of engineering",
    ]
    lowered = cleaned.lower()
    for prefix in prefixes:
        if lowered.startswith(prefix):
            remainder = _clean_capture(cleaned[len(prefix):])
            if remainder:
                return remainder

    return cleaned


def _extract_marksheet_id(text):
    normalized = _normalize_marksheet_text(text)
    flat = re.sub(r"\s+", " ", normalized)

    id_patterns = [
        (
            r"(?:s\.?\s*i\.?\s*d\.?\s*no\.?|sid\s*no\.?|student\s*id)\s*[:\-|]?\s*([A-Z0-9\-]{4,20})",
            "S.I.D. No",
        ),
        (
            r"(?:enrol(?:l)?ment(?:\s*/\s*pg)?(?:\s*registration)?\s*(?:no|number)?|registration\s*no)\s*[:\-|]?\s*([A-Z0-9\-]{8,20})",
            "Enrollment No",
        ),
        (r"(?:seat\s*no)\s*[:\-|]?\s*([A-Z0-9][A-Z0-9\- ]{3,20})", "Seat No"),
        (r"(?:sp\s*id)\s*[:\-|]?\s*([A-Z0-9\-]{4,20})", "SP ID"),
        (r"(?:sr\.?\s*no\.?\s*of\s*statement|statement\s*no)\s*[:\-|]?\s*([A-Z0-9\-]{4,20})", "Statement No"),
    ]
    for pattern, id_type in id_patterns:
        match = re.search(pattern, flat, re.I)
        if match:
            value = _clean_capture(match.group(1))
            if _is_valid_id_value(value):
                return {"type": id_type, "value": value}

    long_numbers = re.findall(r"\b\d{10,20}\b", flat)
    if long_numbers:
        best = max(long_numbers, key=len)
        return {"type": "Enrollment No", "value": best}

    return None


def parse_marksheet(text):
    result = {}
    flat = re.sub(r"\s+", " ", _normalize_marksheet_text(text))

    name_fields = _extract_marksheet_name(text)
    if name_fields:
        result.update(name_fields)

    program_name = _extract_marksheet_program(text)
    if program_name:
        result["department"] = _extract_marksheet_department(program_name)
        result["program_name"] = program_name

    if not result.get("department"):
        stream = _extract_marksheet_stream(text)
        if stream:
            result["department"] = stream
            result["stream"] = stream

    college_name = _capture_labeled_value(
        text,
        r"college\s*name",
        [
            r"enrol(?:l)?ment", r"registration\s*no", r"result\s*declared",
            r"sp\s*id", r"seat\s*no", r"course\s*code", r"sgpa", r"cgpa",
        ],
    )
    if college_name:
        result["college_name"] = college_name

    exam_name = _capture_labeled_value(
        text,
        r"exam\s*name",
        [
            r"program\s*name", r"student\s*name", r"college\s*name",
            r"seat\s*no", r"result\s*declared",
        ],
    )
    if exam_name:
        result["exam_name"] = exam_name

    unique_id = _extract_marksheet_id(text)
    if unique_id:
        result["unique_id"] = unique_id

    declared_match = re.search(
        r"(?:result\s*declared\s*on\s*date|result\s*declared\s*on)\s*[:\-|]?\s*([A-Za-z0-9:.\- ]+?)(?=\s+(?:sp\s*id|course\s*code|sgpa|cgpa|result)\b|$)",
        flat,
        re.I,
    )
    if declared_match:
        result["result_declared_on"] = _clean_capture(declared_match.group(1))

    sgpa_match = re.search(r"\bsgpa\s*[:\-|]?\s*([0-9.]+)", flat, re.I)
    if sgpa_match:
        result["sgpa"] = sgpa_match.group(1)

    cgpa_match = re.search(r"\bcgpa\s*[:\-|]?\s*([0-9.]+)", flat, re.I)
    if cgpa_match:
        result["cgpa"] = cgpa_match.group(1)

    result_match = re.search(r"\bresult\s*[:\-|]?\s*(pass|fail)\b", flat, re.I)
    if result_match:
        result["result_status"] = result_match.group(1).upper()
    elif re.search(r"\bpassed\s+this\s+exam\b", flat, re.I):
        result["result_status"] = "PASS"

    return result


def _enforce_marksheet_name_order(extracted, text):
    cleaned = dict(extracted or {})
    ordered = _extract_marksheet_name(text)
    if not ordered:
        return cleaned

    for key in ["surname", "first_name", "father_name"]:
        value = ordered.get(key)
        if value:
            cleaned[key] = value

    return cleaned


def _prefer_raw_marksheet_names(raw_text, extracted):
    cleaned = dict(extracted or {})
    raw_name_fields = _extract_marksheet_name(raw_text or "")

    for key in ["surname", "first_name", "father_name"]:
        value = raw_name_fields.get(key)
        if value:
            cleaned[key] = value

    return cleaned


# ============================================
# PART A — DOCUMENT TYPE DETECTOR
# ============================================
def detect_doc_type(text):
    """
    Document ka type pehchano — iske hisaab se extraction strategy change hogi
    Returns: 'certificate' | 'ticket' | 'employee_form' | 'report' | 'generic'
    """
    t = text.lower()

    if any(w in t for w in ["certify that","completion certificate","internship certificate",
                             "this is to certify","successfully completed"]):
        return "certificate"

    if any(w in t for w in ["pnr","passenger details","irctc","reservation slip",
                             "booking status","train no","waitlist","wl/"]):
        return "ticket"

    if any(w in t for w in ["first name:","surname:","employee id:","emp id:",
                             "father's name:","date of birth:"]):
        return "employee_form"

    if any(w in t for w in ["internship report","industrial report","submitted by",
                             "table of contents","chapter","abstract"]):
        return "report"

    if any(w in t for w in [
        "student name", "candidate's name", "candidate name", "program name",
        "seat no", "enrolment", "enrollment", "result declared", "sgpa",
        "cgpa", "statement of marks", "higher secondary certificate examination",
        "s.i.d. no", "sid no", "science stream", "commerce stream",
        "month & year of the exam",
    ]):
        return "marksheet"

    return "generic"


# ============================================
# PART B — STRATEGY 1: LABELED FIELDS
# Works for: Employee Forms, Structured Docs
# ============================================
def extract_labeled_fields(text):
    """
    'First Name: Pooja' → Pooja
    'Surname: Patel'    → Patel
    """
    result = {}

    patterns = {
        "first_name"  : r"(?:first\s*name|given\s*name)\s*[:\-|]\s*([A-Za-z]+)",
        "surname"     : r"(?:sur\s*name|last\s*name|family\s*name)\s*[:\-|]\s*([A-Za-z]+)",
        "father_name" : r"(?:father'?s?\s*name|s/o|d/o)\s*[:\-|]\s*([A-Za-z ]+?)(?:\n|$|\|)",
        "dob"         : r"(?:dob|date\s*of\s*birth)\s*[:\-]?\s*(\d{1,2}[-/]\w+[-/]\d{2,4})",
        "email"       : r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)",
        "phone"       : r"\b([6-9]\d{9})\b",
        "department"  : r"(?:department|dept|division)\s*[:\-|]\s*([A-Za-z /&]+?)(?:\n|$)",
        "employee_id" : r"(?:employee\s*id|emp\s*id|staff\s*id)\s*[:\-|]\s*([A-Z0-9\-]+)",
    }

    for field, pattern in patterns.items():
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            val = m.group(1).strip()
            val = re.sub(r'\s+', ' ', val)
            # FIX: Apply OCR correction on name fields
            if field in ("first_name", "surname", "father_name"):
                val = _correct_ocr_chars_in_name(val)
            result[field] = val

    if result.get("first_name") and not result.get("surname"):
        fallback_first, fallback_surname = _extract_two_part_name(text)
        if fallback_surname and result["first_name"].lower() == fallback_first.lower():
            result["surname"] = fallback_surname

    return result


def _extract_two_part_name(text):
    """
    Fallback for simple names like:
    - Name: Rahul Sharma
    - Rahul Sharma
    """
    patterns = [
        r"(?:^|\n|\|)\s*(?:full\s*name|employee\s*name|candidate\s*name|student\s*name)\s*[:\-|]\s*([A-Za-z]+)\s+([A-Za-z]+)(?:\s|$)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if not match:
            continue

        first_name = re.sub(r"[^A-Za-z]", "", match.group(1) or "")
        surname = re.sub(r"[^A-Za-z]", "", match.group(2) or "")
        if len(first_name) >= 2 and len(surname) >= 2 and _has_person_context(text):
            # FIX: Apply OCR correction before returning
            return (
                _correct_ocr_chars_in_name(first_name.title()),
                _correct_ocr_chars_in_name(surname.title()),
            )

    return None, None


# ============================================
# PART C — STRATEGY 2: CERTIFICATE PARSER
# Works for: Internship/Completion Certificates
# KEY FIX: Look for recipient, NOT signatory
# ============================================
def extract_from_certificate(text):
    """
    Certificate mein 2 log hote hain:
    1. RECIPIENT — "certify that Ms. POOJA PATEL" ← YEH CHAHIYE
    2. SIGNATORY — "Ashish Meghani, Managing Director" ← YEH NAHI CHAHIYE
    """
    result = {}

    # Pattern 1: "certify that Ms./Mr. Firstname Lastname"
    cert_patterns = [
        r"certif[yi]\w*\s+that\s+(?:Ms\.|Mr\.|Mrs\.|Dr\.)?\s*([A-Z][a-z]+)\s+([A-Z][a-z]+)",
        r"certif[yi]\w*\s+that\s+(?:Ms\.|Mr\.|Mrs\.|Dr\.)?\s*([A-Z][A-Z]+)\s+([A-Z][A-Z]+)",
        r"(?:Ms\.|Mr\.|Mrs\.)\s+([A-Z][a-z]+)\s+([A-Z][a-z]+)\s+has\s+successfully",
        r"student\s+(?:Ms\.|Mr\.|Mrs\.|Dr\.)?\s*([A-Z][a-z]+)\s+([A-Z][a-z]+)",
    ]

    for pat in cert_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            # FIX: Apply OCR correction on extracted name parts
            result["first_name"] = _correct_ocr_chars_in_name(m.group(1).strip().title())
            result["surname"]    = _correct_ocr_chars_in_name(m.group(2).strip().title())
            cprint(f"  ✅ Certificate recipient found: {result['first_name']} {result['surname']}", Colors.GREEN)
            break

    # Email — usually company email, not person's
    em = re.search(r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)", text)
    if em:
        result["email"] = em.group(1)

    # Company name
    co = re.search(
        r"(?:at|in|of|from)\s+([A-Z][A-Za-z ]+(?:LLP|Pvt|Ltd|Inc|Tech|Technologies|Solutions|Ideas)\.?)",
        text
    )
    if co:
        result["company"] = co.group(1).strip()

    # Duration / internship period
    dur = re.search(r"(\d+(?:st|nd|rd|th)?\s+\w+\s+\d{4})\s+to\s+(\d+(?:st|nd|rd|th)?\s+\w+\s+\d{4})", text, re.I)
    if dur:
        result["internship_period"] = f"{dur.group(1)} to {dur.group(2)}"

    # Domain/Subject
    sub = re.search(r"(?:subject|internship\s+in|completed\s+in)\s*[:\-]?\s*([A-Za-z/. ]+?)(?:\n|\.)", text, re.I)
    if sub:
        result["domain"] = sub.group(1).strip()[:50]

    return result


# ============================================
# PART D — STRATEGY 3: TICKET PARSER
# Works for: IRCTC / Train Tickets
# ============================================
def extract_from_ticket(text):
    """
    Train ticket mein naam 'Passenger Details' section mein hota hai
    Format: "1. SANJAY PATOLIYA 35 M WL/13 WL/12"
    """
    result = {}

    # Pattern: "1. FIRSTNAME LASTNAME AGE GENDER"
    passenger = re.search(
        r'1\.\s+([A-Z]+)\s+([A-Z]+)(?:\s+[A-Z]+)?\s+(\d{1,3})\s+([MF])',
        text
    )
    if passenger:
        # FIX: Apply OCR correction on passenger name parts
        result["first_name"] = _correct_ocr_chars_in_name(passenger.group(1).title())
        result["surname"]    = _correct_ocr_chars_in_name(passenger.group(2).title())
        result["age"]        = passenger.group(3)
        result["gender"]     = "Male" if passenger.group(4) == "M" else "Female"
        cprint(f"  ✅ Passenger found: {result['first_name']} {result['surname']}", Colors.GREEN)

    # PNR number (10 digit)
    pnr = re.search(r'\bPNR\b.*?(\d{10})', text, re.I | re.DOTALL)
    if not pnr:
        pnr = re.search(r'\b(\d{10})\b', text)
    if pnr:
        result["unique_id"] = {"type": "PNR", "value": pnr.group(1)}

    # Route: From → To
    route = re.search(r'([A-Z ]+\([A-Z]+\))\s+.*?([A-Z ]+\([A-Z]+\))', text)
    if route:
        result["route"] = f"{route.group(1).strip()} → {route.group(2).strip()}"

    # Train name
    train = re.search(r'(\d{5}/[A-Z ]+)', text)
    if train:
        result["train"] = train.group(1).strip()

    # Travel date
    tdate = re.search(r'(\d{2}-\w{3}-\d{4})', text)
    if tdate:
        result["travel_date"] = tdate.group(1)

    return result


# ============================================
# PART E — STRATEGY 4: REPORT PARSER
# Works for: Internship Reports, College Docs
# ============================================
def extract_from_report(text):
    """
    Report mein naam brackets mein ya 'Submitted by' ke baad hota hai
    AVOID: Title lines like "INTERNSHIP COMPLETION CERTIFICATE"
    """
    result = {}

    # Pattern 1: [JASOLIYA TAMANNA JITESHBHAI]
    bracket = re.search(r'\[([A-Z]{2,}(?:\s+[A-Z]{2,}){1,3})\]', text)
    if bracket:
        parts = bracket.group(1).strip().split()
        if len(parts) >= 2:
            # Skip if it's a document title word
            if not any(w.lower() in SKIP_TITLE_WORDS for w in parts):
                # FIX: Apply OCR correction on bracket name parts
                result["surname"]    = _correct_ocr_chars_in_name(parts[0].title())
                result["first_name"] = _correct_ocr_chars_in_name(parts[1].title())
                if len(parts) >= 3:
                    result["father_name"] = _correct_ocr_chars_in_name(parts[2].title())

    # Pattern 2: Enrollment ID in brackets
    enroll = re.search(r'\[(\d{10,15})\]', text)
    if not enroll:
        enroll = re.search(r'\((\d{10,15})\)', text)
    if enroll:
        result["unique_id"] = {"type": "Enrollment", "value": enroll.group(1)}

    # Pattern 3: Department from brackets
    dept_b = re.search(
        r'\[([A-Za-z ]+(?:Technology|Engineering|Science|Commerce|IT|CS|EC))\]',
        text, re.I
    )
    if dept_b:
        result["department"] = dept_b.group(1).strip()

    return result


# ============================================
# PART F — STRATEGY 5: GENERIC / STANDALONE
# Last resort — carefully pick standalone names
# ============================================
def extract_generic_name(text):
    """
    Standalone 2-3 word lines se naam nikalo
    BUT: Skip title words, designations, company names
    """
    result = {}
    lines = [l.strip() for l in text.split('\n') if l.strip()]

    for i, line in enumerate(lines):
        words = line.split()

        if not _is_safe_generic_name_words(words, text, i):
            continue

        # Skip if NEXT line has a designation (means this is a signatory!)
        if i + 1 < len(lines):
            next_line = lines[i + 1].lower()
            if any(d in next_line for d in DESIGNATION_WORDS):
                cprint(f"  ⚠️  Skipping signatory: '{line}' (next: '{lines[i+1]}')", Colors.YELLOW)
                continue

        # This looks like a real person name!
        # FIX: Apply OCR correction on generic name parts
        result["first_name"] = _correct_ocr_chars_in_name(words[0].title())
        result["surname"]    = _correct_ocr_chars_in_name(words[-1].title())
        if len(words) == 3:
            result["father_name"] = _correct_ocr_chars_in_name(words[1].title())

        cprint(f"  ✅ Generic name found: {line}", Colors.GREEN)
        break

    return result


# ============================================
# PART G — UNIQUE ID EXTRACTOR (SAFE)
# ============================================
def find_unique_id(text):
    """
    Safely extract ID — avoid picking random words!
    Priority: Aadhar > PAN > Employee ID > PNR > Enrollment
    """
    # Aadhar: exactly 12 digits in groups of 4
    aadhar = re.search(r'\b(\d{4}\s\d{4}\s\d{4})\b', text)
    if aadhar: return "Aadhar", aadhar.group(1)

    # PAN: 5 letters + 4 digits + 1 letter
    pan = re.search(r'\b([A-Z]{5}[0-9]{4}[A-Z])\b', text)
    if pan: return "PAN", pan.group(1)

    # Employee ID: must have prefix word
    emp = re.search(r'(?:employee\s*id|emp\s*id|staff\s*id|id\s*no)\s*[:\-|]\s*([A-Z0-9\-]{3,15})',
                    text, re.I)
    if emp: return "Employee ID", emp.group(1)

    # PNR: exactly 10 digits
    pnr = re.search(r'\bPNR\b.*?(\d{10})', text, re.I | re.DOTALL)
    if pnr: return "PNR", pnr.group(1)

    # Enrollment: 10-15 digit number in brackets
    enroll = re.search(r'[\[\(](\d{10,15})[\]\)]', text)
    if enroll: return "Enrollment", enroll.group(1)

    # Transaction ID (labelled only)
    txn = re.search(r'(?:transaction\s*id|txn\s*id)\s*[:\-]?\s*(\d{10,20})', text, re.I)
    if txn: return "Transaction ID", txn.group(1)

    return "Unknown", None


# ============================================
# ⭐ MASTER EXTRACTION FUNCTION
# ============================================
def extract_entities(text):
    """
    ⭐ MAIN FUNCTION — Smart document-type-based extraction
    1. Translate to English
    2. Detect document type
    3. Use correct strategy
    4. Fill gaps with fallbacks
    """
    cprint("\n  🧠 Smart Entity Extraction starting...", Colors.CYAN)

    # Step 1: Translate
    try:
        translator   = GoogleTranslator(source='auto', target='en')
        english_text = translator.translate(text[:5000])
    except Exception as e:
        cprint(f"  ⚠️  Translation failed: {e}", Colors.YELLOW)
        english_text = text

    # Step 2: Detect document type
    doc_type = detect_doc_type(english_text)
    cprint(f"  📋 Document type detected: {doc_type.upper()}", Colors.CYAN)

    result = {
        "first_name"   : None,
        "surname"      : None,
        "father_name"  : None,
        "unique_id"    : {"type": None, "value": None},
        "dob"          : None,
        "email"        : None,
        "phone"        : None,
        "department"   : None,
        "extra_details": {},
        "doc_type"     : doc_type,
        "_translated"  : english_text,
    }

    # Step 3: Use correct strategy based on doc type
    extracted = {}

    if doc_type == "certificate":
        extracted = extract_from_certificate(english_text)

    elif doc_type == "ticket":
        extracted = extract_from_ticket(english_text)
        if "unique_id" in extracted:
            result["unique_id"] = extracted.pop("unique_id")

    elif doc_type == "report":
        extracted = extract_from_report(english_text)
        if "unique_id" in extracted:
            result["unique_id"] = extracted.pop("unique_id")
        # Also get labeled fields for reports
        labeled = extract_labeled_fields(english_text)
        for k, v in labeled.items():
            if k not in extracted:
                extracted[k] = v

    elif doc_type == "employee_form":
        extracted = extract_labeled_fields(english_text)

    elif doc_type == "marksheet":
        extracted = parse_marksheet(english_text)
        extracted = _enforce_marksheet_name_order(extracted, english_text)
        extracted = _prefer_raw_marksheet_names(text, extracted)

    else:
        # Generic: try labeled first, then certificate patterns
        extracted = extract_labeled_fields(english_text)
        if not extracted.get("first_name"):
            cert_try = extract_from_certificate(english_text)
            for k, v in cert_try.items():
                if k not in extracted:
                    extracted[k] = v
        if not extracted.get("first_name"):
            mark_try = parse_marksheet(english_text)
            mark_try = _enforce_marksheet_name_order(mark_try, english_text)
            mark_try = _prefer_raw_marksheet_names(text, mark_try)
            for k, v in mark_try.items():
                if k not in extracted:
                    extracted[k] = v

    extracted = _sanitize_extracted(extracted)

    # Step 4: Map extracted to result
    field_map = {
        "first_name"  : "first_name",
        "surname"     : "surname",
        "father_name" : "father_name",
        "dob"         : "dob",
        "email"       : "email",
        "phone"       : "phone",
        "department"  : "department",
        "employee_id" : None,  # goes to unique_id
    }

    for src_key, dst_key in field_map.items():
        if src_key in extracted and extracted[src_key]:
            if dst_key:
                result[dst_key] = extracted[src_key]

    if extracted.get("unique_id") and result["unique_id"]["value"] is None:
        result["unique_id"] = extracted["unique_id"]

    # Employee ID → unique_id
    if "employee_id" in extracted and result["unique_id"]["value"] is None:
        result["unique_id"] = {"type": "Employee ID", "value": extracted["employee_id"]}

    # Extra fields (company, route, train, domain, etc.)
    extra_keys = {
        "company", "route", "train", "travel_date", "age", "gender",
        "internship_period", "domain", "program_name", "stream",
        "college_name", "exam_name", "result_declared_on", "sgpa",
        "cgpa", "result_status",
    }
    for k in extra_keys:
        if k in extracted:
            result["extra_details"][k] = extracted[k]

    # Step 5: Unique ID (if not already found)
    if result["unique_id"]["value"] is None:
        uid_type, uid_val = find_unique_id(english_text)
        if uid_val:
            result["unique_id"] = {"type": uid_type, "value": uid_val}

    # Step 6: FALLBACK — generic standalone name (only if still not found)
    if doc_type != "marksheet" and not result["first_name"]:
        generic = extract_generic_name(english_text)
        for k in ["first_name","surname","father_name"]:
            if k in generic and not result[k]:
                result[k] = generic[k]

    # Step 7: spaCy fallback (last resort)
    if not result["first_name"]:
        spacy_names = _spacy_extract(english_text)
        if spacy_names:
            parts = spacy_names[0].split()
            # FIX: Apply OCR correction on spaCy extracted names
            if parts:
                result["first_name"] = _correct_ocr_chars_in_name(parts[0])
            if len(parts) > 1:
                result["surname"] = _correct_ocr_chars_in_name(parts[-1])

    # Clean up
    for key, val in result.items():
        if isinstance(val, str):
            result[key] = val.strip() or None

    cprint(f"  ✅ Extraction complete!", Colors.GREEN)
    return result


def _spacy_extract(text):
    try:
        import spacy
        try:
            nlp = spacy.load("en_core_web_sm")
        except OSError:
            os.system("python -m spacy download en_core_web_sm")
            nlp = spacy.load("en_core_web_sm")
        doc = nlp(text[:5000])
        return [ent.text for ent in doc.ents if ent.label_ == "PERSON"]
    except Exception:
        return []


SKIP_WORDS = {
    "internship", "completion", "certificate", "report", "form", "resume", "cv",
    "profile", "details", "document", "information", "declaration", "abstract",
    "acknowledgement", "introduction", "conclusion", "chapter", "appendix",
    "director", "manager", "managing", "head", "officer", "president", "chairman",
    "sincerely", "regards", "subject", "date", "dear", "sir", "madam", "respected",
    "university", "institute", "college", "department", "division",
    "technology", "engineering", "science", "commerce",
    "sparks", "ideas", "pavitrasoft", "qrious", "mbit", "cvm", "irctc", "railways",
    "general", "waiting", "confirmed", "class", "quota", "sitting", "second",
    "booked", "arrival", "departure", "train", "ticket", "reservation", "slip",
    "electronic", "normal", "user", "payment", "passenger", "invoice", "from", "to",
    "student", "program", "exam", "result", "course", "code", "credit", "backlog",
    "component", "semester", "seat", "registration", "enrolment", "enrollment",
    "cgpa", "sgpa", "pass", "fail", "all", "whatsapp", "image", "photo",
    "scan", "camera", "at", "pm", "am",
    "item", "amount", "total", "subtotal", "qty", "quantity", "price", "rate",
    "description", "product", "service", "gst", "tax", "taxable", "balance",
    "bill", "invoice", "order", "unit", "value", "table",
}

DESIGNATION_WORDS = {
    "director", "manager", "ceo", "cto", "president", "chairman", "founder",
    "head", "officer", "principal", "dean", "professor", "guide", "mentor",
    "supervisor", "coordinator", "authorized", "signature",
}


def detect_doc_type(text):
    t = text.lower()

    resume_hints = sum(
        1 for w in [
            "linkedin.com", "github.com", "summary", "education",
            "experience", "projects", "technologies",
        ]
        if w in t
    )
    if resume_hints >= 4:
        return "generic"

    if any(w in t for w in [
        "certify that", "completion certificate", "successfully completed",
        "internship certificate", "this is to certify"
    ]):
        return "certificate"

    if any(w in t for w in [
        "pnr", "passenger details", "irctc", "reservation slip",
        "booking status", "waitlist", "wl/"
    ]):
        return "ticket"

    if any(w in t for w in [
        "first name:", "surname:", "employee id:", "father's name:",
        "emp id:", "department:"
    ]):
        return "employee_form"

    if any(w in t for w in [
        "submitted by", "table of contents", "chapter", "abstract",
        "internship report", "industrial report", "project report"
    ]):
        return "report"

    if any(w in t for w in [
        "student name", "candidate's name", "candidate name", "program name",
        "seat no", "enrolment", "enrollment", "result declared",
        "statement of marks", "higher secondary certificate examination",
        "s.i.d. no", "sid no", "science stream", "commerce stream",
        "month & year of the exam"
    ]):
        return "marksheet"

    return "generic"


def parse_certificate(text):
    result = {}

    patterns = [
        r"certif[yi]\w*\s+that\s+(?:Ms\.|Mr\.|Mrs\.|Dr\.)?\s*([A-Z][a-z]+)\s+([A-Z][a-z]+)",
        r"(?:Ms\.|Mr\.|Mrs\.)\s+([A-Z][a-z]+)\s+([A-Z][a-z]+)\s+has\s+successfully",
        r"student\s+(?:Ms\.|Mr\.|Mrs\.)?\s*([A-Z][a-z]+)\s+([A-Z][a-z]+)",
    ]

    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            result["first_name"] = m.group(1).title()
            result["surname"] = m.group(2).title()
            break

    em = re.search(r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)", text)
    if em:
        result["email"] = em.group(1)

    co = re.search(
        r"(?:at|in|from)\s+([A-Z][A-Za-z ]+(?:LLP|Pvt|Ltd|Inc|Tech|Technologies|Solutions|Ideas)\.?)",
        text
    )
    if co:
        result["company"] = co.group(1).strip()

    dur = re.search(
        r"(\d+(?:st|nd|rd|th)?\s+\w+\s+\d{4})\s+to\s+(\d+(?:st|nd|rd|th)?\s+\w+\s+\d{4})",
        text, re.I
    )
    if dur:
        result["internship_period"] = f"{dur.group(1)} to {dur.group(2)}"

    return result


def parse_ticket(text):
    result = {}

    m = re.search(r'1\.\s+([A-Z]+)\s+([A-Z]+)(?:\s+[A-Z]+)?\s+(\d{1,3})\s+([MF])', text)
    if m:
        result["first_name"] = m.group(1).title()
        result["surname"] = m.group(2).title()
        result["age"] = m.group(3)
        result["gender"] = "Male" if m.group(4) == "M" else "Female"

    pnr = re.search(r'\bPNR\b.*?(\d{10})', text, re.I | re.DOTALL)
    if not pnr:
        pnr = re.search(r'\b(\d{10})\b', text)
    if pnr:
        result["unique_id"] = {"type": "PNR", "value": pnr.group(1)}

    train = re.search(r'(\d{5}/[A-Z ]+?)(?:\n|Class|SECOND|SLEEPER)', text)
    if train:
        result["train"] = train.group(1).strip()

    tdate = re.search(r'(\d{2}-\w{3}-\d{4})', text)
    if tdate:
        result["travel_date"] = tdate.group(1)

    route = re.search(r'Booked from.*?To\s+([A-Z ()]+?)\s+([A-Z ()]+?)\s+Start', text, re.DOTALL)
    if route:
        result["route"] = f"{route.group(1).strip()} ƒ+' {route.group(2).strip()}"

    return result


def parse_employee_form(text):
    result = {}

    patterns = {
        "first_name": r"(?:first\s*name|given\s*name)\s*[:\-|]\s*([A-Za-z]+)",
        "surname": r"(?:sur\s*name|last\s*name|family\s*name)\s*[:\-|]\s*([A-Za-z]+)",
        "father_name": r"(?:father'?s?\s*name|s/o|d/o)\s*[:\-|]\s*([A-Za-z ]+?)(?:\n|$|\|)",
        "dob": r"(?:dob|date\s*of\s*birth)\s*[:\-]?\s*(\d{1,2}[-/]\w+[-/]\d{2,4})",
        "email": r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)",
        "phone": r"\b([6-9]\d{9})\b",
        "department": r"(?:department|dept|division)\s*[:\-|]\s*([A-Za-z /&]+?)(?:\n|$)",
        "employee_id": r"(?:employee\s*id|emp\s*id|staff\s*id)\s*[:\-|]\s*([A-Z0-9\-]+)",
    }

    for field, pat in patterns.items():
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            result[field] = re.sub(r'\s+', ' ', m.group(1).strip())

    return result


def _is_noise_text(value):
    if value is None:
        return True

    cleaned = _clean_capture(str(value))
    if not cleaned:
        return True
    if cleaned in {"()", "[]", "{}", "-", "--", "_"}:
        return True
    if not re.search(r"[A-Za-z0-9]", cleaned):
        return True

    lowered = cleaned.lower()
    noise_words = {
        "whatsapp", "image", "photo", "scan", "camera", "screenshot",
        "score", "scores", "sores", "at", "pm", "am", "eg", "e.g",
    }
    return lowered in noise_words


def _is_valid_name_value(value):
    if _is_noise_text(value):
        return False

    words = re.findall(r"[A-Za-z]+", str(value))
    if not words:
        return False
    if any(len(word) < 2 for word in words):
        return False
    if any(word.lower() in SKIP_WORDS for word in words):
        return False
    return True


def _is_valid_department_value(value):
    if _is_noise_text(value):
        return False

    cleaned = _clean_capture(str(value))
    if len(cleaned) < 3:
        return False
    if re.fullmatch(r"[\W_]+", cleaned):
        return False
    return True


def _is_valid_id_value(value):
    if _is_noise_text(value):
        return False

    cleaned = _clean_capture(str(value))
    if len(cleaned) < 4:
        return False
    if not re.search(r"\d", cleaned):
        return False
    if not re.fullmatch(r"[A-Za-z0-9\- ]{4,25}", cleaned):
        return False
    return True


def _sanitize_extracted(extracted):
    cleaned = dict(extracted or {})

    for key in ["first_name", "surname", "father_name"]:
        value = cleaned.get(key)
        if value and not _is_valid_name_value(value):
            cleaned.pop(key, None)

    dept = cleaned.get("department")
    if dept and not _is_valid_department_value(dept):
        cleaned.pop("department", None)

    for key in ["employee_id"]:
        value = cleaned.get(key)
        if value and not _is_valid_id_value(value):
            cleaned.pop(key, None)

    unique_id = cleaned.get("unique_id")
    if isinstance(unique_id, dict):
        if not _is_valid_id_value(unique_id.get("value")):
            cleaned.pop("unique_id", None)

    return cleaned


def parse_report(text):
    result = {}

    bracket = re.search(r'\[([A-Z]{2,}(?:\s+[A-Z]{2,}){1,3})\]', text)
    if bracket:
        parts = bracket.group(1).strip().split()
        if not any(w.lower() in SKIP_WORDS for w in parts):
            if len(parts) >= 2:
                result["surname"] = parts[0].title()
                result["first_name"] = parts[1].title()
            if len(parts) >= 3:
                result["father_name"] = parts[2].title()

    for pat in [
        r'\[(\d{10,15})\]',
        r'\((\d{10,15})\)',
        r'(?:enrollment|roll\s*no|student\s*id)\s*[:\-]?\s*(\d{8,15})'
    ]:
        m = re.search(pat, text, re.I)
        if m:
            result["unique_id"] = {"type": "Enrollment", "value": m.group(1)}
            break

    db = re.search(
        r'\[([A-Za-z ]+(?:Technology|Engineering|Science|IT|CS|EC))\]',
        text, re.I
    )
    if db:
        result["department"] = db.group(1).strip()

    return result


def parse_generic_name(text):
    result = {}

    lines = [l.strip() for l in text.split("\n") if l.strip()]
    for i, line in enumerate(lines):
        words = line.split()

        if not _is_safe_generic_name_words(words, text, i):
            continue

        if i + 1 < len(lines):
            if any(d in lines[i + 1].lower() for d in DESIGNATION_WORDS):
                continue

        result["first_name"] = words[0].title()
        result["surname"] = words[-1].title()
        if len(words) == 3:
            result["father_name"] = words[1].title()
        break

    return result


def find_unique_id(text):
    m = re.search(r'\b(\d{4}\s\d{4}\s\d{4})\b', text)
    if m:
        return "Aadhar", m.group(1)

    m = re.search(r'\b([A-Z]{5}[0-9]{4}[A-Z])\b', text)
    if m:
        return "PAN", m.group(1)

    m = re.search(r'(?:employee\s*id|emp\s*id|staff\s*id)\s*[:\-|]\s*([A-Z0-9\-]+)', text, re.I)
    if m:
        return "Employee ID", m.group(1)

    m = re.search(r'\bPNR\b.*?(\d{10})', text, re.I | re.DOTALL)
    if m:
        return "PNR", m.group(1)

    m = re.search(r'[\[\(](\d{10,15})[\]\)]', text)
    if m:
        return "Enrollment", m.group(1)

    return None, None


def smart_parse(raw_text):
    try:
        translator = GoogleTranslator(source="auto", target="en")
        english_text = translator.translate(raw_text[:4000])
    except Exception:
        english_text = raw_text

    multilingual_hint_text = _build_multilingual_english_hint_text(raw_text)
    if multilingual_hint_text:
        working_text = f"{multilingual_hint_text}\n{english_text}"
    else:
        working_text = english_text

    doc_type = detect_doc_type(working_text)

    if doc_type == "certificate":
        extracted = parse_certificate(working_text)

    elif doc_type == "ticket":
        extracted = parse_ticket(working_text)

    elif doc_type == "employee_form":
        extracted = parse_employee_form(working_text)

    elif doc_type == "report":
        extracted = parse_report(working_text)
        labeled = parse_employee_form(working_text)
        for k, v in labeled.items():
            if k not in extracted:
                extracted[k] = v

    elif doc_type == "marksheet":
        extracted = parse_marksheet(working_text)
        extracted = _enforce_marksheet_name_order(extracted, working_text)
        extracted = _prefer_raw_marksheet_names(raw_text, extracted)

    else:
        extracted = parse_employee_form(working_text)
        if not extracted.get("first_name"):
            cert_try = parse_certificate(working_text)
            for k, v in cert_try.items():
                if k not in extracted:
                    extracted[k] = v
        if not extracted.get("first_name"):
            mark_try = parse_marksheet(working_text)
            mark_try = _enforce_marksheet_name_order(mark_try, working_text)
            mark_try = _prefer_raw_marksheet_names(raw_text, mark_try)
            for k, v in mark_try.items():
                if k not in extracted:
                    extracted[k] = v

    multilingual_fields = _extract_multilingual_labeled_fields(raw_text)
    if multilingual_fields.get("first_name") and not extracted.get("first_name"):
        extracted["first_name"] = multilingual_fields["first_name"]
    if multilingual_fields.get("surname") and not extracted.get("surname"):
        extracted["surname"] = multilingual_fields["surname"]
    if multilingual_fields.get("father_name") and not extracted.get("father_name"):
        extracted["father_name"] = multilingual_fields["father_name"]
    if multilingual_fields.get("full_name") and not extracted.get("full_name"):
        extracted["full_name"] = multilingual_fields["full_name"]
    if multilingual_fields.get("department") and not extracted.get("department"):
        extracted["department"] = multilingual_fields["department"]
    if multilingual_fields.get("email") and not extracted.get("email"):
        extracted["email"] = multilingual_fields["email"]
    if multilingual_fields.get("phone") and not extracted.get("phone"):
        extracted["phone"] = multilingual_fields["phone"]
    if multilingual_fields.get("employee_id") and not extracted.get("employee_id"):
        extracted["employee_id"] = multilingual_fields["employee_id"]

    extracted = _sanitize_extracted(extracted)

    if doc_type != "marksheet" and not extracted.get("first_name"):
        generic = parse_generic_name(working_text)
        for k, v in generic.items():
            if k not in extracted:
                extracted[k] = v

    uid_dict = extracted.get("unique_id")
    if not uid_dict:
        uid_type, uid_val = find_unique_id(working_text)
        if (not uid_val) and multilingual_fields.get("employee_id"):
            uid_type, uid_val = "Employee ID", multilingual_fields["employee_id"]
        uid_dict = {"type": uid_type, "value": uid_val}

    display_date = (
        extracted.get("dob")
        or extracted.get("travel_date")
        or extracted.get("result_declared_on")
        or extracted.get("month_year_of_exam")
        or extracted.get("date")
    )

    full_name = extracted.get("full_name")
    if not full_name:
        name_parts = [
            extracted.get("first_name"),
            extracted.get("father_name"),
            extracted.get("surname"),
        ]
        full_name = " ".join(part for part in name_parts if part)

    result = {
        "First Name": extracted.get("first_name", "Not Found") or "Not Found",
        "Middle Name": extracted.get("father_name", "Not Found") or "Not Found",
        "Last Name": extracted.get("surname", "Not Found") or "Not Found",
        "Full Name": full_name or "Not Found",
        "Surname": extracted.get("surname", "Not Found") or "Not Found",
        "Father's Name": extracted.get("father_name", "Not Found") or "Not Found",
        "Date": display_date or "Not Found",
        "Email": extracted.get("email", "Not Found") or "Not Found",
        "Phone": extracted.get("phone", "Not Found") or "Not Found",
        "Department": extracted.get("department", "Not Found") or "Not Found",
        "ID": (uid_dict.get("value") if uid_dict else None) or "Not Found",
        "ID_Type": (uid_dict.get("type") if uid_dict else None) or "ID",
        "doc_type": doc_type,
        "_translated": working_text,
    }

    extra_keys = [
        "company", "route", "train", "travel_date", "age", "gender",
        "internship_period", "domain", "program_name", "college_name",
        "exam_name", "result_declared_on", "sgpa", "cgpa", "result_status",
        "stream",
    ]
    result["extra"] = {k: extracted[k] for k in extra_keys if k in extracted}

    return result


def extract_from_filename(filename):
    result = {
        "First Name": "Not Found",
        "Surname": "Not Found",
        "Father's Name": "Not Found"
    }

    name = re.sub(r'\.(docx|pdf|xlsx|txt|xls|jpg|jpeg|png|bmp|webp)$', '', filename, flags=re.I)
    name = re.sub(r'[_\-\.]', ' ', name)
    name = re.sub(r'[\(\)\[\]\{\}]', ' ', name)
    name = re.sub(r'\b\d+\b', '', name)
    name = re.sub(r'\s+', ' ', name).strip()

    skip = {
        "Report", "Resume", "Form", "Doc", "Document", "File", "Employee",
        "Info", "Details", "Data", "Sheet", "New", "Final", "Updated",
        "Qrious", "Tech", "Sparks", "Ideas", "Certificate", "Internship",
        "Ticket", "Ahe", "Removed", "Sem", "Marksheet", "Result",
        "Screenshot", "Screen", "Photo", "Image", "Img", "Jpg", "Jpeg",
        "Png", "Webp", "Bmp", "Whatsapp", "At", "Pm", "Am", "Scan",
        "Camera", "Cam", "Scanned"
    }

    parts = [p.title() for p in re.findall(r"[A-Za-z]{2,}", name) if p.title() not in skip]

    if len(parts) >= 1:
        result["First Name"] = parts[0]
    if len(parts) >= 2:
        result["Surname"] = parts[1]
    if len(parts) >= 3:
        result["Father's Name"] = parts[2]

    return result


def smart_merge(doc_det, file_det):
    merged = {}

    for f in [
        "First Name",
        "Middle Name",
        "Last Name",
        "Full Name",
        "Surname",
        "Father's Name",
        "Date",
        "Email",
        "Phone",
        "Department",
        "ID",
    ]:
        dv = doc_det.get(f, "Not Found")
        fv = file_det.get(f, "Not Found")
        merged[f] = dv if dv != "Not Found" else (fv if fv != "Not Found" else "Not Found")

    merged["ID_Type"] = doc_det.get("ID_Type", "ID")
    merged["doc_type"] = doc_det.get("doc_type", "generic")
    merged["extra"] = doc_det.get("extra", {})
    merged["_translated"] = doc_det.get("_translated", "")

    return merged


# ============================================
# PRINT RESULT
# ============================================
def print_entities(entities):
    uid   = entities.get("unique_id", {}) or {}
    extra = entities.get("extra_details", {}) or {}

    print(f"""
╔══════════════════════════════════════════════╗
║     📋 EXTRACTED INFORMATION                 ║
║     Doc Type: {str(entities.get('doc_type','?')).upper():<29}║
╠══════════════════════════════════════════════╣
║  First Name   : {str(entities.get('first_name')  or '❌ Not found'):<29}║
║  Surname      : {str(entities.get('surname')     or '❌ Not found'):<29}║
║  Father Name  : {str(entities.get('father_name') or '❌ Not found'):<29}║
║  Unique ID    : {str((uid.get('type') or '?')+': '+(uid.get('value') or 'Not found')):<29}║
║  DOB          : {str(entities.get('dob')         or '❌ Not found'):<29}║
║  Email        : {str(entities.get('email')       or '❌ Not found'):<29}║
║  Phone        : {str(entities.get('phone')       or '❌ Not found'):<29}║
║  Department   : {str(entities.get('department')  or '❌ Not found'):<29}║
╚══════════════════════════════════════════════╝""")

    if extra:
        print("  ✨ Extra Details:")
        for k, v in extra.items():
            print(f"     ➤ {k:<18} : {v}")


# ============================================
# DIRECT TEST — Run: python nlp_parser.py
# ============================================
if __name__ == "__main__":
    import pdfplumber

    print("\n" + "="*55)
    print("TEST 1: INTERNSHIP CERTIFICATE")
    print("="*55)
    with pdfplumber.open("../../sample_documents/sparks_to_idea_internship_certificate.pdf") as pdf:
        text = "\n".join(p.extract_text() or "" for p in pdf.pages)
    entities = extract_entities(text)
    print_entities(entities)

    print("\n" + "="*55)
    print("TEST 2: TRAIN TICKET")
    print("="*55)
    with pdfplumber.open("../../sample_documents/ticket.pdf") as pdf:
        text = "\n".join(p.extract_text() or "" for p in pdf.pages)
    entities = extract_entities(text)
    print_entities(entities)
