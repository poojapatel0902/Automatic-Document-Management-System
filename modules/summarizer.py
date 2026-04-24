# MODULE 6: SUMMARIZER.PY
# import os, sys, re
# sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# from config import Colors, cprint, SUMMARY_SENTENCES

# def summarize_simple(text, num_sentences=SUMMARY_SENTENCES):
#     """Frequency-based extractive summarization — always works, no libraries needed"""
#     if not text or len(text.strip()) < 50:
#         return text.strip()
#     text_clean = re.sub(r'\s+', ' ', text).strip()
#     sentences  = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text_clean) if len(s.strip()) > 20]
#     if len(sentences) <= num_sentences:
#         return " ".join(sentences)
#     stop = {"the","a","an","is","are","was","were","be","been","have","has","had",
#             "do","does","did","will","would","can","could","i","you","he","she","it",
#             "we","they","and","but","or","in","on","at","to","from","with","by","of",
#             "not","no","this","that","my","your","his","her","its","our","their"}
#     words = re.findall(r'\b[a-z]+\b', text_clean.lower())
#     freq  = {}
#     for w in words:
#         if w not in stop and len(w) > 2:
#             freq[w] = freq.get(w, 0) + 1
#     scores = {}
#     for s in sentences:
#         score = sum(freq.get(w, 0) for w in re.findall(r'\b[a-z]+\b', s.lower()))
#         if re.search(r'(?i)(name|id|department|role|employee)', s):
#             score *= 1.5
#         scores[s] = score
#     top    = sorted(scores, key=scores.get, reverse=True)[:num_sentences]
#     return " ".join(s for s in sentences if s in top) or sentences[0]

# def summarize_sumy(text, num_sentences=SUMMARY_SENTENCES):
#     """Sumy LSA summarization"""
#     try:
#         from sumy.parsers.plaintext import PlaintextParser
#         from sumy.nlp.tokenizers import Tokenizer
#         from sumy.summarizers.lsa import LsaSummarizer
#         from sumy.nlp.stemmers import Stemmer
#         from sumy.utils import get_stop_words
#         import nltk
#         for pkg in ["punkt","punkt_tab","stopwords"]:
#             try: nltk.data.find(f"tokenizers/{pkg}")
#             except LookupError: nltk.download(pkg, quiet=True)
#         parser = PlaintextParser.from_string(text, Tokenizer("english"))
#         sumr   = LsaSummarizer(Stemmer("english"))
#         sumr.stop_words = get_stop_words("english")
#         result = " ".join(str(s) for s in sumr(parser.document, num_sentences))
#         return result or None
#     except Exception:
#         return None

# def summarize_document(text, method="auto"):
#     """Master summarization — tries sumy first, falls back to simple"""
#     if not text or len(text.strip()) < 30:
#         return "Document is too short to summarize."
#     cprint(f"\n  📝 Summarizing ({len(text)} chars)...", Colors.CYAN)
#     clean = re.sub(r'\[(?:Sheet|Page)[^\]]*\]|[-=]{3,}|\|', ' ', text)
#     clean = re.sub(r'\s+', ' ', clean).strip()
#     if len(clean) < 30:
#         return "Insufficient text for summarization."
#     summary = None
#     if method in ("auto","sumy"):
#         summary = summarize_sumy(clean)
#     if not summary:
#         summary = summarize_simple(clean)
#     cprint(f"  ✅ Summary ready!", Colors.GREEN)
#     return (summary or clean[:200]).strip()


# MODULE 6: SUMMARIZER.PY
# import os, sys, re, json
# sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# from config import Colors, cprint, SUMMARY_SENTENCES

# # ── Claude API summarization (abstractive, 3-4 sentences) ────────────────────
# def summarize_claude(text: str) -> str | None:
#     """
#     Calls the Anthropic Messages API to produce a proper 3-4 sentence
#     abstractive summary.  Returns None on any failure so the caller can
#     fall back to the local method.
#     """
#     try:
#         import urllib.request

#         api_key = os.environ.get("ANTHROPIC_API_KEY", "")
#         if not api_key:
#             return None                          # no key → skip silently

#         # Truncate very long docs to stay within token limits
#         snippet = text[:12000] if len(text) > 12000 else text

#         payload = json.dumps({
#             "model": "claude-sonnet-4-20250514",
#             "max_tokens": 300,
#             "messages": [
#                 {
#                     "role": "user",
#                     "content": (
#                         "Summarize the following document in exactly 3-4 concise sentences. "
#                         "Capture the key purpose, main findings or activities, and any important "
#                         "conclusions. Do NOT copy sentences verbatim — write in your own words.\n\n"
#                         f"Document:\n{snippet}"
#                     )
#                 }
#             ]
#         }).encode()

#         req = urllib.request.Request(
#             "https://api.anthropic.com/v1/messages",
#             data=payload,
#             headers={
#                 "x-api-key": api_key,
#                 "anthropic-version": "2023-06-01",
#                 "content-type": "application/json",
#             },
#             method="POST",
#         )
#         with urllib.request.urlopen(req, timeout=20) as resp:
#             data = json.loads(resp.read())

#         # Extract text from the response
#         for block in data.get("content", []):
#             if block.get("type") == "text":
#                 summary = block["text"].strip()
#                 if summary:
#                     return summary
#         return None

#     except Exception:
#         return None


# # ── Local fallback: frequency-based extractive (always works) ────────────────
# def summarize_simple(text, num_sentences=SUMMARY_SENTENCES):
#     """Frequency-based extractive summarization — no libraries needed"""
#     # Cap at 4 sentences maximum so it never dumps the whole doc
#     num_sentences = min(num_sentences, 4)

#     if not text or len(text.strip()) < 50:
#         return text.strip()

#     text_clean = re.sub(r'\s+', ' ', text).strip()
#     sentences  = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text_clean)
#                   if len(s.strip()) > 20]

#     if len(sentences) <= num_sentences:
#         return " ".join(sentences)

#     stop = {
#         "the","a","an","is","are","was","were","be","been","have","has","had",
#         "do","does","did","will","would","can","could","i","you","he","she","it",
#         "we","they","and","but","or","in","on","at","to","from","with","by","of",
#         "not","no","this","that","my","your","his","her","its","our","their"
#     }

#     words = re.findall(r'\b[a-z]+\b', text_clean.lower())
#     freq  = {}
#     for w in words:
#         if w not in stop and len(w) > 2:
#             freq[w] = freq.get(w, 0) + 1

#     scores = {}
#     for s in sentences:
#         score = sum(freq.get(w, 0) for w in re.findall(r'\b[a-z]+\b', s.lower()))
#         if re.search(r'(?i)(name|id|department|role|employee)', s):
#             score *= 1.5
#         scores[s] = score

#     top = sorted(scores, key=scores.get, reverse=True)[:num_sentences]
#     return " ".join(s for s in sentences if s in top) or sentences[0]


# def summarize_sumy(text, num_sentences=SUMMARY_SENTENCES):
#     """Sumy LSA summarization"""
#     num_sentences = min(num_sentences, 4)
#     try:
#         from sumy.parsers.plaintext import PlaintextParser
#         from sumy.nlp.tokenizers import Tokenizer
#         from sumy.summarizers.lsa import LsaSummarizer
#         from sumy.nlp.stemmers import Stemmer
#         from sumy.utils import get_stop_words
#         import nltk
#         for pkg in ["punkt", "punkt_tab", "stopwords"]:
#             try:    nltk.data.find(f"tokenizers/{pkg}")
#             except LookupError: nltk.download(pkg, quiet=True)
#         parser = PlaintextParser.from_string(text, Tokenizer("english"))
#         sumr   = LsaSummarizer(Stemmer("english"))
#         sumr.stop_words = get_stop_words("english")
#         result = " ".join(str(s) for s in sumr(parser.document, num_sentences))
#         return result or None
#     except Exception:
#         return None


# # ── Master entry point ────────────────────────────────────────────────────────
# def summarize_document(text, method="auto"):
#     """
#     Summarization pipeline (best → good → always-works):
#       1. Claude API  — proper abstractive 3-4 sentence summary
#       2. Sumy LSA    — statistical extractive (if installed)
#       3. simple      — pure-Python frequency extractive (hard cap: 4 sentences)
#     """
#     if not text or len(text.strip()) < 30:
#         return "Document is too short to summarize."

#     cprint(f"\n  📝 Summarizing ({len(text)} chars)...", Colors.CYAN)

#     # Pre-clean: strip page/sheet markers and table pipes
#     clean = re.sub(r'\[(?:Sheet|Page)[^\]]*\]|[-=]{3,}|\|', ' ', text)
#     clean = re.sub(r'\s+', ' ', clean).strip()

#     if len(clean) < 30:
#         return "Insufficient text for summarization."

#     summary = None

#     # 1️⃣ Claude API (best quality)
#     if method in ("auto", "claude"):
#         cprint("  🤖 Trying Claude API summarization...", Colors.CYAN)
#         summary = summarize_claude(clean)
#         if summary:
#             cprint("  ✅ Claude summary ready!", Colors.GREEN)

#     # 2️⃣ Sumy LSA
#     if not summary and method in ("auto", "sumy"):
#         summary = summarize_sumy(clean)

#     # 3️⃣ Simple frequency (always available, capped at 4 sentences)
#     if not summary:
#         summary = summarize_simple(clean)

#     cprint("  ✅ Summary ready!", Colors.GREEN)
#     return (summary or clean[:300]).strip()

# ============================================================
# MODULE: summarizer.py
# Zero API, Zero internet — Pure Python
# Smart summarizer for all document types
# ============================================================

import re
from collections import Counter

RESUME_SECTION_HEADINGS = (
    "summary",
    "education",
    "experience",
    "projects",
    "technologies",
    "skills",
    "certificates",
    "certificate",
    "achievements",
)


# ------------------------------------------------------------
# Detect document type
# ------------------------------------------------------------
def _detect_type(text: str) -> str:
    t = text.lower()

    resume_hints = sum(
        1 for w in [
            "linkedin.com",
            "github.com",
            "summary",
            "education",
            "experience",
            "projects",
            "technologies",
        ]
        if w in t
    )
    if resume_hints >= 4:
        return "resume"

    if any(w in t for w in [
        "pnr", "passenger details", "irctc", "reservation slip",
        "booking status", "waitlist", "wl/", "train no", "booked from"
    ]):
        return "ticket"

    if any(w in t for w in [
        "certificate of", "this is to certify", "certify that",
        "completion certificate", "internship certificate",
        "successfully completed"
    ]):
        return "certificate"

    if any(w in t for w in [
        "first name", "surname", "employee id", "emp id",
        "father's name", "department", "email"
    ]):
        return "employee_form"

    if any(w in t for w in [
        "abstract", "introduction", "conclusion", "chapter",
        "table of contents", "submitted by", "project report",
        "internship report"
    ]):
        return "report"

    return "generic"


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
def _clean_text(text: str) -> str:
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _shorten(text: str, limit: int = 180) -> str:
    text = _clean_text(text)
    return text if len(text) <= limit else text[:limit - 3] + "..."


def _split_sentences(text: str):
    text = _clean_text(text)
    sentences = re.split(r'(?<=[.!?])\s+', text)
    return [s.strip() for s in sentences if len(s.strip()) > 20]


def _normalize_resume_fragment(text: str) -> str:
    text = text.replace("|", " ")
    text = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', text)
    text = re.sub(r',(?=\S)', ', ', text)
    text = re.sub(r'\s+', ' ', text).strip(" -|:")

    replacements = {
        "Scienceenthusiast": "Science enthusiast",
        "enthusiastskilledin": "enthusiast skilled in",
        "experiencein": "experience in",
        "hands-onexperience": "hands-on experience",
        "withhands-on": "with hands-on",
        "buildingreal-world": "building real-world",
        "real-worldanalytics": "real-world analytics",
        "analyticsand": "analytics and ",
        "Visualizationwith": "Visualization with",
        "predictionsystems": "prediction systems",
        "ToolandPlatform": "Tool and Platform",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)

    return _clean_text(text)


def _resume_lines(text: str):
    lines = []
    for raw_line in text.splitlines():
        line = _normalize_resume_fragment(raw_line)
        if line:
            lines.append(line)
    return lines


def _is_resume_heading(line: str) -> bool:
    return line.strip().lower().rstrip(":") in RESUME_SECTION_HEADINGS


def _extract_resume_name(text: str) -> str | None:
    for line in _resume_lines(text)[:6]:
        if "@" in line or "linkedin.com" in line.lower() or "github.com" in line.lower():
            continue
        if _is_resume_heading(line):
            continue

        words = re.findall(r"[A-Za-z]+", line)
        if 2 <= len(words) <= 4 and all(len(w) >= 2 for w in words):
            return " ".join(w.title() for w in words)
    return None


def _extract_resume_section(text: str, heading: str) -> str | None:
    lines = _resume_lines(text)
    heading = heading.lower()

    for idx, line in enumerate(lines):
        if line.lower().rstrip(":") != heading:
            continue

        collected = []
        for next_line in lines[idx + 1:]:
            if _is_resume_heading(next_line):
                break
            if "@" in next_line or "linkedin.com" in next_line.lower() or "github.com" in next_line.lower():
                continue
            collected.append(next_line)
            if len(" ".join(collected)) >= 220:
                break

        if collected:
            return _normalize_resume_fragment(" ".join(collected))

    flat_text = text
    stops = "|".join(re.escape(h.title()) for h in RESUME_SECTION_HEADINGS if h != heading)
    pattern = rf'\b{re.escape(heading.title())}\b\s*(.+?)(?=\b(?:{stops})\b|$)'
    match = re.search(pattern, flat_text, re.I | re.S)
    if match:
        fragment = _normalize_resume_fragment(match.group(1))
        if fragment:
            return fragment

    return None


# ------------------------------------------------------------
# Extractive summary for generic/report docs
# ------------------------------------------------------------
def _extractive_summary(text: str, max_sentences: int = 2) -> str:
    sentences = _split_sentences(text)

    if not sentences:
        return _shorten(text, 180)

    if len(sentences) <= max_sentences:
        return " ".join(sentences)

    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "shall",
        "should", "can", "could", "may", "might", "must", "this", "that",
        "these", "those", "and", "or", "but", "if", "then", "than", "so",
        "to", "of", "in", "on", "at", "for", "from", "with", "by", "as",
        "it", "its", "their", "there", "here", "we", "you", "he", "she",
        "they", "them", "his", "her", "our", "your", "my"
    }

    words = re.findall(r'\b[a-zA-Z]+\b', text.lower())
    keywords = [w for w in words if w not in stop_words and len(w) > 2]
    freq = Counter(keywords)

    scored = []
    for i, sent in enumerate(sentences):
        sent_words = re.findall(r'\b[a-zA-Z]+\b', sent.lower())
        score = sum(freq.get(w, 0) for w in sent_words)

        # थोड़ा importance boost
        if re.search(r'\b(project|report|summary|analysis|objective|result|conclusion|department|employee|certificate)\b', sent, re.I):
            score += 5

        scored.append((score, i, sent))

    top = sorted(scored, reverse=True)[:max_sentences]
    top = sorted(top, key=lambda x: x[1])

    final = " ".join(s for _, _, s in top)
    return _shorten(final, 220)


# ------------------------------------------------------------
# Ticket summary
# ------------------------------------------------------------
def _summarize_ticket(text: str) -> str:
    clean = _clean_text(text)

    pnr = re.search(r'\bPNR\b.*?(\d{10})', clean, re.I)
    if not pnr:
        pnr = re.search(r'\b(\d{10})\b', clean)

    train = re.search(r'(\d{5})/([A-Z][A-Z ]+)', clean)

    date = re.search(r'(\d{2}-[A-Za-z]{3}-\d{4})', clean)

    from_station = None
    to_station = None

    m1 = re.search(r'Booked from\s+(.+?)\s+To\s+(.+?)\s+Start Date', clean, re.I)
    if m1:
        from_station = m1.group(1).strip()
        to_station = m1.group(2).strip()

    parts = ["Railway Ticket"]
    if pnr:
        parts.append(f"PNR: {pnr.group(1)}")
    if train:
        parts.append(f"Train: {train.group(1)} {train.group(2).strip()}")
    if from_station and to_station:
        parts.append(f"Route: {from_station} → {to_station}")
    if date:
        parts.append(f"Date: {date.group(1)}")

    return _shorten(" | ".join(parts), 180)


# ------------------------------------------------------------
# Certificate summary
# ------------------------------------------------------------
def _summarize_certificate(text: str) -> str:
    clean = _clean_text(text)

    name = None
    org = None
    course = None

    m_name = re.search(
        r'(?:certify that|this is to certify that)\s+(?:Ms\.|Mr\.|Mrs\.|Dr\.)?\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)',
        clean,
        re.I
    )
    if m_name:
        name = m_name.group(1).strip()

    m_org = re.search(
        r'(?:at|from)\s+([A-Z][A-Za-z ]+(?:Ltd|LLP|Inc|Technologies|Solutions|Ideas|University|Institute|College))',
        clean
    )
    if m_org:
        org = m_org.group(1).strip()

    m_course = re.search(r'(?:for|in)\s+([A-Za-z &]{3,40})', clean, re.I)
    if m_course:
        course = m_course.group(1).strip()

    parts = ["Certificate"]
    if name:
        parts.append(f"Name: {name}")
    if course:
        parts.append(f"Field: {course}")
    if org:
        parts.append(f"Org: {org}")

    if len(parts) > 1:
        return _shorten(" | ".join(parts), 180)

    return _extractive_summary(text, max_sentences=2)


# ------------------------------------------------------------
# Employee form summary
# ------------------------------------------------------------
def _summarize_employee_form(text: str) -> str:
    clean = _clean_text(text)

    fields = []

    m_name = re.search(r'(?:first name|name)\s*[:\-]\s*([A-Za-z ]+)', clean, re.I)
    if m_name:
        fields.append(f"Name: {m_name.group(1).strip()}")

    m_id = re.search(r'(?:employee id|emp id|id)\s*[:\-]\s*([A-Z0-9\-]+)', clean, re.I)
    if m_id:
        fields.append(f"ID: {m_id.group(1).strip()}")

    m_dept = re.search(r'(?:department|dept)\s*[:\-]\s*([A-Za-z /&]+)', clean, re.I)
    if m_dept:
        fields.append(f"Dept: {m_dept.group(1).strip()}")

    m_email = re.search(r'([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)', clean)
    if m_email:
        fields.append(f"Email: {m_email.group(1).strip()}")

    if fields:
        return _shorten("Employee Form | " + " | ".join(fields), 200)

    return _extractive_summary(text, max_sentences=2)


# ------------------------------------------------------------
# Report summary
# ------------------------------------------------------------
def _summarize_report(text: str) -> str:
    return _extractive_summary(text, max_sentences=2)


# ------------------------------------------------------------
# Resume summary
# ------------------------------------------------------------
def _summarize_resume(text: str) -> str:
    name = _extract_resume_name(text)
    summary = _extract_resume_section(text, "summary")

    if summary:
        if name:
            return _shorten(f"Resume of {name}. {summary}", 220)
        return _shorten(summary, 220)

    education = _extract_resume_section(text, "education")
    experience = _extract_resume_section(text, "experience")

    parts = []
    if name:
        parts.append(f"Resume of {name}")
    if education:
        parts.append(education)
    if experience:
        parts.append(experience)

    if parts:
        return _shorten(". ".join(parts), 220)

    return _extractive_summary(text, max_sentences=2)


# ------------------------------------------------------------
# Generic summary
# ------------------------------------------------------------
def _summarize_generic(text: str) -> str:
    return _extractive_summary(text, max_sentences=2)


# ------------------------------------------------------------
# Main function
# ------------------------------------------------------------
def summarize_document(text: str) -> str:
    if not text or len(text.strip()) < 5:
        return "Empty/Invalid document."

    raw_text = text.strip()
    doc_type = _detect_type(raw_text)

    if doc_type == "ticket":
        return _summarize_ticket(raw_text)

    elif doc_type == "certificate":
        return _summarize_certificate(raw_text)

    elif doc_type == "employee_form":
        return _summarize_employee_form(raw_text)

    elif doc_type == "resume":
        return _summarize_resume(raw_text)

    elif doc_type == "report":
        return _summarize_report(raw_text)

    else:
        return _summarize_generic(raw_text)
