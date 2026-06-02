import html
import io
import json
import mimetypes
import os
import re
import sqlite3
import smtplib
import zipfile
from datetime import datetime
from email.message import EmailMessage
from urllib.parse import quote_plus

import pandas as pd
import streamlit as st

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

from config import Colors, OUTPUT_DIR, cprint
from modules.extractor import extract_text_from_file as _core_extract_text_from_file
from modules.multilingual import (
    NOT_CLEAR,
    extract_person_name as multilingual_extract_person_name,
    is_weak_summary,
    log_indicator,
    process_multilingual_text,
    summary_confidence,
    validate_person_name,
)
from modules.nlp_parser import extract_from_filename, smart_merge, smart_parse
from modules.ocr import format_extracted_text_for_display, prepare_display_details
from modules.router import save_uploaded_bytes
from modules.summarizer import summarize_document


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_ROOT = OUTPUT_DIR
UPLOADS_ROOT = os.path.join(BASE_DIR, "uploads")
DATABASE_PATH = os.path.join(BASE_DIR, "adms_documents.db")
MAX_GMAIL_ATTACHMENT_BYTES = 25 * 1024 * 1024

SUPPORTED_FILE_TYPES = ["pdf", "docx", "txt", "xlsx", "xls", "csv", "jpg", "jpeg", "png"]
FORMAT_FILE_TYPES = {
    "Word Document": ["docx"],
    "PDF": ["pdf"],
    "Excel": ["xlsx", "xls", "csv"],
    "Image": ["jpg", "jpeg", "png"],
}
PROCESSED_DOCS_KEY = "processed_documents"
LAST_ACTION_KEY = "last_action"
RECEIVER_SUMMARY_KEY = "receiver_summary"
PENDING_EMAIL_SETTINGS_KEY = "pending_email_settings"
HISTORY_SEARCH_KEY = "history_search_text"
HISTORY_SEARCH_PARAM_KEY = "adms_history_search"

EMAIL_REGEX = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
def init_database():
    os.makedirs(BASE_DIR, exist_ok=True)
    with sqlite3.connect(DATABASE_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_name TEXT,
                document_type TEXT,
                confidence_score REAL,
                extracted_name TEXT,
                short_summary TEXT,
                detailed_summary TEXT,
                important_fields_json TEXT,
                raw_text TEXT,
                receiver_emails TEXT,
                email_status TEXT,
                processing_status TEXT,
                error_message TEXT,
                created_at TEXT
            )
            """
        )


def save_to_database(document):
    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.execute(
            """
            INSERT INTO documents (
                file_name, document_type, confidence_score, extracted_name,
                short_summary, detailed_summary, important_fields_json, raw_text,
                receiver_emails, email_status,
                processing_status, error_message, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                document.get("file_name", ""),
                document.get("display_doc_type", "General Document"),
                document.get("confidence_score", 0),
                document.get("extracted_name", NOT_CLEAR),
                document.get("short_summary", ""),
                document.get("detailed_summary", ""),
                json.dumps(document.get("important_fields", {}), ensure_ascii=False),
                document.get("raw_text", ""),
                ", ".join(document.get("receiver_emails", [])),
                document.get("email_status", "Not Requested"),
                document.get("processing_status", "Failed"),
                document.get("error_message", ""),
                document.get("created_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            ),
        )
        return cursor.lastrowid


def update_database_document(document):
    database_id = document.get("database_id")
    if not database_id:
        return

    with sqlite3.connect(DATABASE_PATH) as conn:
        conn.execute(
            """
            UPDATE documents
            SET document_type = ?,
                confidence_score = ?,
                extracted_name = ?,
                short_summary = ?,
                detailed_summary = ?,
                important_fields_json = ?,
                receiver_emails = ?,
                email_status = ?,
                processing_status = ?,
                error_message = ?
            WHERE id = ?
            """,
            (
                document.get("display_doc_type", "General Document"),
                document.get("confidence_score", 0),
                document.get("extracted_name", NOT_CLEAR),
                document.get("short_summary", ""),
                document.get("detailed_summary", ""),
                json.dumps(document.get("important_fields", {}), ensure_ascii=False),
                ", ".join(document.get("receiver_emails", [])),
                document.get("email_status", "Not Requested"),
                document.get("processing_status", "Failed"),
                document.get("error_message", ""),
                database_id,
            ),
        )


def search_database(search_text="", document_type="", email_status=""):
    query = "SELECT * FROM documents"
    clauses = []
    params = []

    if search_text:
        like_value = f"%{search_text.lower()}%"
        clauses.append(
            """
            (
                lower(file_name) LIKE ?
                OR lower(extracted_name) LIKE ?
                OR lower(document_type) LIKE ?
                OR lower(email_status) LIKE ?
            )
            """
        )
        params.extend([like_value, like_value, like_value, like_value])

    if document_type and document_type != "All":
        clauses.append("document_type = ?")
        params.append(document_type)

    if email_status and email_status != "All":
        clauses.append("email_status = ?")
        params.append(email_status)

    if clauses:
        query += " WHERE " + " AND ".join(clauses)

    query += " ORDER BY id DESC"
    with sqlite3.connect(DATABASE_PATH) as conn:
        return pd.read_sql_query(query, conn, params=params)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _clean_value(value):
    text = str(value or "").strip()
    return "" if not text or text.lower() == "not found" else text


def _display_value(value, default="Not Found"):
    return _clean_value(value) or default


def _safe_doc_key(file_name, index):
    base = re.sub(r"[^A-Za-z0-9]+", "_", str(file_name or "")).strip("_").lower()
    return f"{index}_{base or 'document'}"


def _safe_folder_name(value):
    cleaned = re.sub(r'[<>:"/\\|?*\n\r\t]', "", str(value or "General Document")).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:80] or "General Document"


def _shorten(value, limit=240):
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return text[: max(limit - 3, 1)].rstrip() + "..."


def _build_full_name(details):
    explicit = _clean_value(details.get("Full Name"))
    if explicit:
        return explicit

    parts = [
        _clean_value(details.get("First Name")),
        _clean_value(details.get("Middle Name") or details.get("Father's Name")),
        _clean_value(details.get("Last Name") or details.get("Surname")),
    ]
    return " ".join(part for part in parts if part)


def _normalize_text(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _dedupe_preserve_order(values):
    result = []
    seen = set()
    for value in values or []:
        cleaned = str(value or "").strip()
        key = cleaned.lower()
        if cleaned and key not in seen:
            seen.add(key)
            result.append(cleaned)
    return result


def _render_dark_table(rows, columns):
    if not rows:
        return ""

    header_html = "".join(f"<th>{html.escape(str(column))}</th>" for column in columns)
    body_rows = []
    for row in rows:
        body_cells = "".join(f"<td>{html.escape(str(value))}</td>" for value in row)
        body_rows.append(f"<tr>{body_cells}</tr>")

    return f"""
    <div class="data-table-shell">
        <table class="data-table">
            <thead><tr>{header_html}</tr></thead>
            <tbody>{''.join(body_rows)}</tbody>
        </table>
    </div>
    """


def _render_dark_dataframe(dataframe, columns=None):
    if dataframe is None or dataframe.empty:
        return ""

    visible_columns = columns or list(dataframe.columns)
    visible_columns = [column for column in visible_columns if column in dataframe.columns]
    rows = []
    for _, row in dataframe[visible_columns].iterrows():
        rows.append([
            "" if pd.isna(row.get(column, "")) else row.get(column, "")
            for column in visible_columns
        ])
    return _render_dark_table(rows, visible_columns)


def _status_badge(label):
    key = _normalize_text(label).replace(" ", "-")
    return f'<span class="status-badge status-{html.escape(key)}">{html.escape(str(label))}</span>'


def _streamlit_secret(*path):
    try:
        value = st.secrets
        for item in path:
            value = value[item]
        return str(value)
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Receiver parsing and matching
# ---------------------------------------------------------------------------
EMAIL_COLUMN_KEYS = {
    "email",
    "emailaddress",
    "receiveremail",
    "receiver",
    "recipient",
    "recipientemail",
    "mail",
    "mailid",
}
NAME_COLUMN_KEYS = {"name", "receivername", "recipientname", "fullname"}
DOC_TYPE_COLUMN_KEYS = {"documenttype", "doctype", "type", "category"}


def _normalize_column_key(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def validate_email(value):
    return bool(EMAIL_REGEX.fullmatch(str(value or "").strip()))


def _clean_email_candidate(value):
    text = str(value or "").strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return ""

    mailto_match = re.search(r"mailto:([^)\]\s?>]+)", text, re.I)
    if mailto_match:
        text = mailto_match.group(1)

    embedded = re.findall(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", text)
    if len(embedded) == 1:
        return embedded[0]

    return text.strip(" <>[](){}'\".,;")


def _split_email_values(value):
    raw_items = []
    if isinstance(value, (list, tuple, set)):
        for item in value:
            raw_items.extend(re.split(r"[,\n;]+", str(item or "")))
    else:
        raw_items.extend(re.split(r"[,\n;]+", str(value or "")))
    return raw_items


def parse_manual_emails(value):
    valid_emails = []
    invalid_emails = []
    seen = set()

    for item in _split_email_values(value):
        email = _clean_email_candidate(item)
        if not email:
            continue

        if not validate_email(email):
            invalid_emails.append(email)
            continue

        key = email.lower()
        if key not in seen:
            seen.add(key)
            valid_emails.append(email)

    return valid_emails, _dedupe_preserve_order(invalid_emails)


def parse_receiver_emails(value):
    return parse_manual_emails(value)


def _find_receiver_column(columns, candidates):
    normalized = {_normalize_column_key(column): column for column in columns}
    for candidate in candidates:
        if candidate in normalized:
            return normalized[candidate]
    for key, column in normalized.items():
        if "email" in key and candidates is EMAIL_COLUMN_KEYS:
            return column
    return None


def merge_and_deduplicate_emails(*email_groups):
    merged = []
    for group in email_groups:
        merged.extend(group or [])
    return _dedupe_preserve_order(merged)


def load_receiver_list(uploaded_file):
    empty = {
        "dataframe": pd.DataFrame(),
        "valid_rows": [],
        "valid_emails": [],
        "invalid_rows": [],
        "error": "",
    }
    if uploaded_file is None:
        return empty

    try:
        if hasattr(uploaded_file, "seek"):
            uploaded_file.seek(0)

        extension = uploaded_file.name.rsplit(".", 1)[-1].lower()
        if extension not in {"xlsx", "xls", "csv"}:
            return {**empty, "error": "Receiver list must be an Excel or CSV file."}

        if extension == "csv":
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)

        df = df.dropna(how="all")
        if df.empty:
            return {**empty, "error": "Receiver list file is empty."}

        email_col = _find_receiver_column(df.columns, EMAIL_COLUMN_KEYS)
        if not email_col:
            return {**empty, "error": "Receiver list file has no email column."}

        name_col = _find_receiver_column(df.columns, NAME_COLUMN_KEYS)
        doc_type_col = _find_receiver_column(df.columns, DOC_TYPE_COLUMN_KEYS)

        preview_rows = []
        valid_rows = []
        invalid_rows = []
        valid_emails = []
        seen_valid = set()

        for _, row in df.iterrows():
            name = str(row.get(name_col, "") or "").strip() if name_col else ""
            doc_type = str(row.get(doc_type_col, "") or "").strip() if doc_type_col else ""
            row_valid, row_invalid = parse_manual_emails(row.get(email_col, ""))

            if not row_valid and not row_invalid:
                preview_rows.append(
                    {
                        "Name": name,
                        "Email": "",
                        "Document Type": doc_type,
                        "Status": "Missing Email",
                    }
                )
                invalid_rows.append({"name": name, "email": "", "reason": "Missing email"})
                continue

            for email in row_valid:
                key = email.lower()
                status = "Valid"
                if key in seen_valid:
                    status = "Duplicate Skipped"
                else:
                    seen_valid.add(key)
                    valid_rows.append({"name": name, "email": email, "document_type": doc_type})
                    valid_emails.append(email)

                preview_rows.append(
                    {
                        "Name": name,
                        "Email": email,
                        "Document Type": doc_type,
                        "Status": status,
                    }
                )

            for email in row_invalid:
                invalid_rows.append({"name": name, "email": email, "reason": "Invalid email format"})
                preview_rows.append(
                    {
                        "Name": name,
                        "Email": email,
                        "Document Type": doc_type,
                        "Status": "Invalid Email",
                    }
                )

        return {
            "dataframe": pd.DataFrame(preview_rows),
            "valid_rows": valid_rows,
            "valid_emails": valid_emails,
            "invalid_rows": invalid_rows,
            "error": "",
        }
    except Exception as exc:
        return {**empty, "error": f"Could not read receiver list: {exc}"}


def read_receiver_excel(uploaded_file):
    return load_receiver_list(uploaded_file)


def _extract_name_from_filename(file_name):
    try:
        file_det = extract_from_filename(file_name)
    except Exception:
        file_det = {}

    parts = [
        _clean_value(file_det.get("First Name")),
        _clean_value(file_det.get("Father's Name")),
        _clean_value(file_det.get("Surname")),
    ]
    candidate = " ".join(part for part in parts if part)
    if candidate:
        return candidate

    base = re.sub(r"\.[A-Za-z0-9]+$", "", str(file_name or ""))
    base = re.sub(r"[_\-.()\[\]{}]", " ", base)
    skip = {
        "resume",
        "salary",
        "slip",
        "offer",
        "letter",
        "invoice",
        "ticket",
        "railway",
        "hospital",
        "bill",
        "marksheet",
        "form",
        "document",
        "scan",
        "final",
        "copy",
        "pdf",
        "docx",
        "xlsx",
        "csv",
        "image",
    }
    words = [w.title() for w in re.findall(r"[A-Za-z]{2,}", base) if w.lower() not in skip]
    if len(words) >= 2:
        return " ".join(words[:3])
    return words[0] if words else ""


def extract_person_name_result(file_name, raw_text, details, important_fields, english_text="", document_type=""):
    result = multilingual_extract_person_name(raw_text, english_text or raw_text, document_type)
    candidates = []
    combined_text_compact = _summary_compact_text(f"{raw_text} {english_text}")

    for candidate in [
        _build_full_name(details),
        important_fields.get("Candidate Name", ""),
        important_fields.get("Employee Name", ""),
        important_fields.get("Passenger Name", ""),
        important_fields.get("Patient Name", ""),
        important_fields.get("Student Name", ""),
        important_fields.get("Policy Holder", ""),
        important_fields.get("Applicant Name", ""),
        important_fields.get("Name", ""),
    ]:
        name, confidence = validate_person_name(candidate, require_two_words=True)
        if name and _summary_compact_text(name) in combined_text_compact:
            candidates.append({"name": name, "confidence": confidence, "source": "existing_fields"})

    if candidates:
        candidates.sort(key=lambda item: item["confidence"], reverse=True)
        if candidates[0]["confidence"] > result.get("confidence", 0):
            result = candidates[0]

    if result.get("name") and result.get("name") != NOT_CLEAR and result.get("confidence", 0) >= 70:
        return result

    return {
        "name": NOT_CLEAR,
        "confidence": int(result.get("confidence", 0) or 0),
        "source": result.get("source", "low_confidence"),
    }


def extract_extracted_name(file_name, raw_text, details, important_fields, english_text="", document_type=""):
    return extract_person_name_result(
        file_name,
        raw_text,
        details,
        important_fields,
        english_text=english_text,
        document_type=document_type,
    )["name"]


def _apply_detected_name_to_fields(details, important_fields, detected_name, document_type):
    name, confidence = validate_person_name(detected_name, require_two_words=True)
    if not name or confidence < 70:
        return details, important_fields

    words = name.split()
    first_name = words[0]
    last_name = words[-1] if len(words) > 1 else "Not Found"
    middle_name = " ".join(words[1:-1]) if len(words) > 2 else "Not Found"

    details["Full Name"] = name
    details["First Name"] = first_name
    details["Middle Name"] = middle_name
    details["Last Name"] = last_name
    details["Surname"] = last_name
    if middle_name != "Not Found":
        details["Father's Name"] = middle_name

    name_field_by_type = {
        "Resume": "Candidate Name",
        "Certificate": "Candidate Name",
        "Marksheet": "Student Name",
        "Employee Form": "Employee Name",
        "Application Form": "Applicant Name",
        "Insurance Document": "Policy Holder",
        "Invoice": "Customer",
        "Hospital Bill": "Patient Name",
        "Railway Ticket": "Passenger Name",
    }
    important_fields[name_field_by_type.get(document_type, "Name")] = name
    return details, important_fields


def match_receiver_by_name(document, receiver_rows):
    if not receiver_rows:
        return [], []

    doc_type = document.get("display_doc_type", "")
    doc_type_norm = _normalize_text(doc_type)
    candidate_sources = [
        document.get("file_name", ""),
        document.get("extracted_name", ""),
        " ".join(str(v) for v in document.get("important_fields", {}).values()),
        document.get("raw_text", "")[:3000],
    ]
    candidate_text = _normalize_text(" ".join(candidate_sources))

    matched_emails = []
    matched_names = []

    for row in receiver_rows:
        receiver_name = str(row.get("name") or "").strip()
        receiver_email = str(row.get("email") or "").strip()
        receiver_type = str(row.get("document_type") or "").strip()

        if not receiver_name or not receiver_email:
            continue

        name_norm = _normalize_text(receiver_name)
        name_parts = [part for part in name_norm.split() if len(part) > 1]
        name_matches = name_norm in candidate_text or all(part in candidate_text for part in name_parts)

        type_matches = True
        if receiver_type:
            receiver_type_norm = _normalize_text(receiver_type)
            type_matches = (
                receiver_type_norm in doc_type_norm
                or doc_type_norm in receiver_type_norm
                or bool(set(receiver_type_norm.split()) & set(doc_type_norm.split()))
            )

        if name_matches and type_matches:
            matched_emails.append(receiver_email)
            matched_names.append(receiver_name)

    return _dedupe_preserve_order(matched_emails), _dedupe_preserve_order(matched_names)


def resolve_document_recipients(document, receiver_rows, manual_emails, unmatched_fallback, all_recipients=None):
    recipients = merge_and_deduplicate_emails(
        all_recipients,
        manual_emails,
        [row.get("email", "") for row in receiver_rows or []],
    )
    document["matched_receiver_emails"] = []
    document["matched_receiver_names"] = []

    if recipients:
        if manual_emails and receiver_rows:
            return recipients, "Manual and uploaded receiver list"
        if receiver_rows:
            return recipients, "Uploaded receiver list"
        return recipients, "Manual receivers"

    return [], "Please enter receiver email manually or upload a receiver list file."


# ---------------------------------------------------------------------------
# Document detection and summaries
# ---------------------------------------------------------------------------
def extract_text_from_file(uploaded_file):
    if hasattr(uploaded_file, "seek"):
        uploaded_file.seek(0)
    return _core_extract_text_from_file(uploaded_file)


DOCUMENT_KEYWORDS = {
    "Resume": [
        "resume",
        "curriculum vitae",
        "education",
        "experience",
        "skills",
        "projects",
        "linkedin",
        "github",
    ],
    "Salary Slip": [
        "salary slip",
        "payslip",
        "basic salary",
        "net pay",
        "gross salary",
        "employee id",
        "earnings",
        "deductions",
        "provident fund",
    ],
    "Offer Letter": [
        "offer letter",
        "joining date",
        "designation",
        "salary package",
        "compensation",
        "appointment",
        "employment offer",
        "pleased to offer",
    ],
    "Hospital Bill": [
        "hospital",
        "patient",
        "doctor",
        "bill amount",
        "diagnosis",
        "medicine",
        "consultation",
        "discharge",
        "room charges",
    ],
    "Railway Ticket": [
        "pnr",
        "train number",
        "train no",
        "departure",
        "arrival",
        "passenger",
        "irctc",
        "coach",
        "berth",
        "railway",
    ],
    "Invoice": [
        "invoice",
        "invoic",
        "invoice number",
        "tax invoice",
        "bill",
        "receipt",
        "bill to",
        "gst",
        "total amount",
        "due date",
        "unit price",
        "quantity",
    ],
    "Insurance Document": [
        "insurance",
        "policy number",
        "premium",
        "insurer",
        "nominee",
        "coverage",
        "claim",
        "sum insured",
    ],
    "Marksheet": [
        "marksheet",
        "mark sheet",
        "statement of marks",
        "grade",
        "cgpa",
        "sgpa",
        "seat no",
        "examination",
        "result declared",
    ],
    "Certificate": [
        "certificate",
        "certific",
        "certificat",
        "certification",
        "this is to certify",
        "certify that",
        "completion certificate",
        "internship certificate",
        "successfully completed",
        "awarded to",
        "presented to",
    ],
    "ID Proof": [
        "id proof",
        "identity proof",
        "aadhaar",
        "aadhar",
        "pan",
        "driving license",
        "driving licence",
        "license number",
        "licence number",
    ],
    "Application Form": [
        "application form",
        "information form",
        "applicant",
        "form",
        "personal details",
        "academic details",
    ],
    "Employee Form": [
        "employee form",
        "employee id",
        "department",
        "designation",
        "joining",
        "first name",
        "father's name",
    ],
    "Finance Document": [
        "bank statement",
        "account number",
        "balance",
        "transaction",
        "credit",
        "debit",
        "loan",
        "interest",
        "finance",
    ],
    "Legal Document": [
        "agreement",
        "contract",
        "affidavit",
        "legal",
        "clause",
        "court",
        "party",
        "terms and conditions",
        "signature",
    ],
}

LEGACY_DOC_TYPE_MAP = {
    "resume": "Resume",
    "ticket": "Railway Ticket",
    "employee_form": "Employee Form",
    "marksheet": "Marksheet",
    "report": "General Document",
    "certificate": "Certificate",
    "generic": "General Document",
}

DOCUMENT_TYPE_ALIASES = {
    "certificate": "Certificate",
    "certific": "Certificate",
    "certificat": "Certificate",
    "certification": "Certificate",
    "resume": "Resume",
    "resum": "Resume",
    "cv": "Resume",
    "curriculum vitae": "Resume",
    "biodata": "Resume",
    "marksheet": "Marksheet",
    "markshet": "Marksheet",
    "mark sheet": "Marksheet",
    "result": "Marksheet",
    "grade sheet": "Marksheet",
    "invoice": "Invoice",
    "invoic": "Invoice",
    "bill": "Invoice",
    "receipt": "Invoice",
    "insurance": "Insurance Document",
    "policy": "Insurance Document",
    "claim": "Insurance Document",
    "id proof": "ID Proof",
    "identity proof": "ID Proof",
    "aadhaar": "ID Proof",
    "aadhar": "ID Proof",
    "pan": "ID Proof",
    "license": "ID Proof",
    "licence": "ID Proof",
    "application": "Application Form",
    "application form": "Application Form",
    "information form": "Application Form",
    "form": "Application Form",
}


def normalize_document_type_name(value):
    normalized = _normalize_text(value)
    if not normalized:
        return ""

    if normalized in DOCUMENT_TYPE_ALIASES:
        return DOCUMENT_TYPE_ALIASES[normalized]
    if normalized in LEGACY_DOC_TYPE_MAP:
        return LEGACY_DOC_TYPE_MAP[normalized]
    for alias, canonical in DOCUMENT_TYPE_ALIASES.items():
        alias_norm = _normalize_text(alias)
        if alias_norm and re.search(rf"(?<![a-z0-9]){re.escape(alias_norm)}(?![a-z0-9])", normalized):
            return canonical
    return ""


def detect_document_type(file_name, raw_text, existing_type=""):
    combined_text = _normalize_text(f"{file_name} {raw_text}")
    file_text = _normalize_text(file_name)
    existing_text = _normalize_text(existing_type)
    scores = {}

    for category, keywords in DOCUMENT_KEYWORDS.items():
        score = 0.0
        for keyword in keywords:
            keyword_norm = _normalize_text(keyword)
            if keyword_norm and keyword_norm in combined_text:
                score += 1.0
                if keyword_norm in file_text:
                    score += 1.0

        if _normalize_text(category) in file_text:
            score += 2.0

        if existing_text:
            mapped = LEGACY_DOC_TYPE_MAP.get(existing_text.replace(" ", "_"), "")
            if mapped == category:
                score += 3.0
            normalized_existing = normalize_document_type_name(existing_text)
            if normalized_existing == category:
                score += 3.0

        for alias, canonical in DOCUMENT_TYPE_ALIASES.items():
            if canonical != category:
                continue
            alias_norm = _normalize_text(alias)
            if not alias_norm:
                continue
            if re.search(rf"(?<![a-z0-9]){re.escape(alias_norm)}(?![a-z0-9])", combined_text):
                score += 2.5 if len(alias_norm) > 4 else 1.0
                if alias_norm in file_text:
                    score += 1.0

        scores[category] = score

    best_category = max(scores, key=scores.get)
    best_score = scores[best_category]

    if best_score < 2:
        return "General Document", 35

    confidence = min(95, int(42 + best_score * 9))
    if confidence < 50:
        return "General Document", confidence

    return normalize_document_type_name(best_category) or best_category, confidence


def _regex_field(raw_text, patterns):
    for pattern in patterns:
        match = re.search(pattern, raw_text or "", re.I | re.S)
        if match:
            value = re.sub(r"\s+", " ", str(match.group(1))).strip(" :-|")
            if value:
                return _shorten(value, 120)
    return "Not Found"


def _field_from_details(details, *keys):
    for key in keys:
        value = _display_value(details.get(key))
        if value != "Not Found":
            return value
    return "Not Found"


def extract_important_fields(document_type, details, raw_text, file_name=""):
    name_guess = _display_value(_build_full_name(details) or _extract_name_from_filename(file_name))
    common_id = _field_from_details(details, "ID")
    common_date = _field_from_details(details, "Date")

    definitions = {
        "Resume": {
            "Candidate Name": lambda: name_guess,
            "Email": lambda: _field_from_details(details, "Email"),
            "Phone": lambda: _field_from_details(details, "Phone"),
            "Education": lambda: _regex_field(raw_text, [r"education\s*[:\-]?\s*(.{5,160})(?:experience|skills|projects|$)"]),
            "Skills": lambda: _regex_field(raw_text, [r"skills\s*[:\-]?\s*(.{5,180})(?:projects|experience|education|$)"]),
            "Experience": lambda: _regex_field(raw_text, [r"experience\s*[:\-]?\s*(.{5,180})(?:projects|education|skills|$)"]),
        },
        "Salary Slip": {
            "Employee Name": lambda: name_guess,
            "Employee ID": lambda: _regex_field(raw_text, [r"(?:employee id|emp id)\s*[:\-]\s*([A-Z0-9\-]+)"]) if common_id == "Not Found" else common_id,
            "Month": lambda: _regex_field(raw_text, [r"(?:month|salary month|pay period)\s*[:\-]\s*([A-Za-z0-9 ,/-]+)"]),
            "Gross Salary": lambda: _regex_field(raw_text, [r"(?:gross salary|gross pay)\s*[:\-]?\s*(?:rs\.?|inr)?\s*([0-9,]+(?:\.\d+)?)"]),
            "Deduction": lambda: _regex_field(raw_text, [r"(?:deduction|total deductions)\s*[:\-]?\s*(?:rs\.?|inr)?\s*([0-9,]+(?:\.\d+)?)"]),
            "Net Salary": lambda: _regex_field(raw_text, [r"(?:net salary|net pay|take home)\s*[:\-]?\s*(?:rs\.?|inr)?\s*([0-9,]+(?:\.\d+)?)"]),
        },
        "Offer Letter": {
            "Candidate Name": lambda: name_guess,
            "Designation": lambda: _regex_field(raw_text, [r"designation\s*[:\-]\s*([A-Za-z0-9 /&.-]+)"]),
            "Joining Date": lambda: _regex_field(raw_text, [r"joining date\s*[:\-]?\s*([A-Za-z0-9 ,/-]+)"]),
            "Salary Package": lambda: _regex_field(raw_text, [r"(?:salary package|ctc|compensation)\s*[:\-]?\s*(?:rs\.?|inr)?\s*([A-Za-z0-9, ./-]+)"]),
            "Company": lambda: _regex_field(raw_text, [r"(?:company|organization)\s*[:\-]\s*([A-Za-z0-9 &.,-]+)"]),
        },
        "Hospital Bill": {
            "Patient Name": lambda: name_guess,
            "Doctor": lambda: _regex_field(raw_text, [r"doctor\s*[:\-]\s*([A-Za-z .'-]+)"]),
            "Bill Amount": lambda: _regex_field(raw_text, [r"(?:bill amount|total amount|amount payable)\s*[:\-]?\s*(?:rs\.?|inr)?\s*([0-9,]+(?:\.\d+)?)"]),
            "Diagnosis": lambda: _regex_field(raw_text, [r"diagnosis\s*[:\-]\s*([A-Za-z0-9 ,./-]+)"]),
            "Date": lambda: common_date,
        },
        "Railway Ticket": {
            "Passenger Name": lambda: name_guess,
            "PNR": lambda: _regex_field(raw_text, [r"\bPNR\b[^\d]*(\d{10})", r"\b(\d{10})\b"]),
            "Train Number": lambda: _regex_field(raw_text, [r"(?:train number|train no\.?|train)\s*[:\-]?\s*([0-9]{4,6})"]),
            "From Station": lambda: _regex_field(raw_text, [r"(?:from|booked from)\s*[:\-]?\s*([A-Za-z ]{2,40})(?:\s+to|\n|$)"]),
            "To Station": lambda: _regex_field(raw_text, [r"(?:to|destination)\s*[:\-]?\s*([A-Za-z ]{2,40})(?:\s+start|\n|$)"]),
            "Date": lambda: _regex_field(raw_text, [r"(\d{1,2}[-/][A-Za-z]{3}[-/]\d{2,4})", r"(?:date|journey date)\s*[:\-]?\s*([A-Za-z0-9 ,/-]+)"]),
            "Status": lambda: _regex_field(raw_text, [r"(?:status|booking status|current status)\s*[:\-]?\s*([A-Za-z0-9 /-]+)"]),
        },
        "Invoice": {
            "Invoice Number": lambda: _regex_field(raw_text, [r"(?:invoice no|invoice number|invoice #)\s*[:\-]?\s*([A-Z0-9\-/]+)"]),
            "Vendor": lambda: _regex_field(raw_text, [r"(?:vendor|seller|from)\s*[:\-]\s*([A-Za-z0-9 &.,-]+)"]),
            "Customer": lambda: _regex_field(raw_text, [r"(?:customer|bill to|buyer)\s*[:\-]\s*([A-Za-z0-9 &.,-]+)"]),
            "Invoice Date": lambda: _regex_field(raw_text, [r"(?:invoice date|date)\s*[:\-]?\s*([A-Za-z0-9 ,/-]+)"]),
            "Total Amount": lambda: _regex_field(raw_text, [r"(?:grand total|total amount|amount due)\s*[:\-]?\s*(?:rs\.?|inr)?\s*([0-9,]+(?:\.\d+)?)"]),
            "GST Number": lambda: _regex_field(raw_text, [r"\b([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][A-Z0-9]Z[A-Z0-9])\b"]),
        },
        "Insurance Document": {
            "Policy Holder": lambda: name_guess,
            "Policy Number": lambda: _regex_field(raw_text, [r"(?:policy number|policy no)\s*[:\-]?\s*([A-Z0-9\-/]+)"]),
            "Premium": lambda: _regex_field(raw_text, [r"premium\s*[:\-]?\s*(?:rs\.?|inr)?\s*([0-9,]+(?:\.\d+)?)"]),
            "Nominee": lambda: _regex_field(raw_text, [r"nominee\s*[:\-]\s*([A-Za-z .'-]+)"]),
            "Sum Insured": lambda: _regex_field(raw_text, [r"sum insured\s*[:\-]?\s*(?:rs\.?|inr)?\s*([0-9,]+(?:\.\d+)?)"]),
        },
        "Certificate": {
            "Candidate Name": lambda: name_guess,
            "Organization": lambda: _summary_find_organization(raw_text),
            "Field": lambda: _summary_find_branch_or_field(raw_text) or _regex_field(raw_text, [r"(?:field|domain|course|training|internship)\s*[:\-]?\s*([A-Za-z0-9 &./-]{3,70})"]),
            "Duration": lambda: _summary_find_duration(raw_text),
            "Date": lambda: _summary_find_date(raw_text) or common_date,
        },
        "Marksheet": {
            "Student Name": lambda: name_guess,
            "Seat Number": lambda: _regex_field(raw_text, [r"(?:seat no|seat number|roll no)\s*[:\-]?\s*([A-Z0-9\-/]+)"]),
            "Exam": lambda: _regex_field(raw_text, [r"(?:exam|examination)\s*[:\-]\s*([A-Za-z0-9 ,/-]+)"]),
            "Result": lambda: _regex_field(raw_text, [r"(?:result|status)\s*[:\-]\s*([A-Za-z ]+)"]),
            "CGPA": lambda: _regex_field(raw_text, [r"\bCGPA\s*[:\-]?\s*([0-9.]+)"]),
            "Percentage": lambda: _regex_field(raw_text, [r"(?:percentage|percentile)\s*[:\-]?\s*([0-9.]+%?)"]),
        },
        "Employee Form": {
            "Employee Name": lambda: name_guess,
            "Employee ID": lambda: common_id,
            "Department": lambda: _field_from_details(details, "Department"),
            "Email": lambda: _field_from_details(details, "Email"),
            "Phone": lambda: _field_from_details(details, "Phone"),
            "Date": lambda: common_date,
        },
        "Application Form": {
            "Applicant Name": lambda: name_guess,
            "Document ID": lambda: common_id,
            "Department": lambda: _field_from_details(details, "Department"),
            "Email": lambda: _field_from_details(details, "Email"),
            "Phone": lambda: _field_from_details(details, "Phone"),
            "Date": lambda: common_date,
        },
        "ID Proof": {
            "Name": lambda: name_guess,
            "ID Type": lambda: _regex_field(raw_text, [r"\b(aadhaar|aadhar|pan|driving licen[cs]e|id proof)\b"]),
            "Document ID": lambda: common_id,
            "Date": lambda: common_date,
        },
        "Finance Document": {
            "Account Holder": lambda: name_guess,
            "Account Number": lambda: _regex_field(raw_text, [r"(?:account number|a/c no)\s*[:\-]?\s*([0-9Xx\- ]{6,25})"]),
            "Bank Name": lambda: _regex_field(raw_text, [r"(?:bank name|bank)\s*[:\-]\s*([A-Za-z &.-]+)"]),
            "Balance": lambda: _regex_field(raw_text, [r"(?:balance|closing balance)\s*[:\-]?\s*(?:rs\.?|inr)?\s*([0-9,]+(?:\.\d+)?)"]),
            "Transaction Date": lambda: common_date,
        },
        "Legal Document": {
            "Party Name": lambda: name_guess,
            "Agreement Date": lambda: common_date,
            "Document ID": lambda: common_id,
            "Court/Authority": lambda: _regex_field(raw_text, [r"(?:court|authority)\s*[:\-]\s*([A-Za-z0-9 &.,-]+)"]),
            "Subject": lambda: _regex_field(raw_text, [r"(?:subject|matter)\s*[:\-]\s*([A-Za-z0-9 ,./-]+)"]),
        },
        "General Document": {
            "Name": lambda: name_guess,
            "Email": lambda: _field_from_details(details, "Email"),
            "Phone": lambda: _field_from_details(details, "Phone"),
            "Date": lambda: common_date,
            "Document ID": lambda: common_id,
        },
    }

    selected = definitions.get(document_type, definitions["General Document"])
    important_fields = {}
    for field_name, resolver in selected.items():
        try:
            important_fields[field_name] = _display_value(resolver())
        except Exception:
            important_fields[field_name] = "Not Found"

    extra = details.get("extra", {}) if isinstance(details, dict) else {}
    for key, value in extra.items():
        label = str(key).replace("_", " ").title()
        important_fields.setdefault(label, _display_value(value))

    return important_fields


SUMMARY_NAME_STOPWORDS = {
    "resume",
    "curriculum vitae",
    "information form",
    "application form",
    "employee form",
    "document",
    "marksheet",
    "mark sheet",
    "certificate",
    "invoice",
    "bill",
    "receipt",
    "insurance",
    "unknown",
    "not found",
    "not clearly available",
    "not",
    "clearly",
    "available",
    "overload",
}

SUMMARY_SKILLS = [
    "Python",
    "Machine Learning",
    "Deep Learning",
    "Data Science",
    "Data Analytics",
    "Data Visualization",
    "SQL",
    "Power BI",
    "Tableau",
    "Excel",
    "Pandas",
    "NumPy",
    "TensorFlow",
    "Keras",
    "Scikit-learn",
    "Java",
    "C++",
    "JavaScript",
    "HTML",
    "CSS",
    "React",
    "Django",
    "Flask",
    "MySQL",
    "MongoDB",
    "Cloud",
]


def _clean_summary_text(extracted_text):
    raw = str(extracted_text or "").replace("\r", "\n")
    raw = re.sub(r"[ \t]+", " ", raw)
    lines = []
    seen = set()
    for raw_line in raw.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip(" :-|")
        if not line:
            continue
        if len(line) < 3 and not re.search(r"\d", line):
            continue
        alpha_num_count = len(re.findall(r"[A-Za-z0-9]", line))
        if alpha_num_count < max(2, len(line) * 0.35):
            continue
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        lines.append(line)

    compact_text = "\n".join(lines)
    compact_text = re.sub(r"\n{3,}", "\n\n", compact_text)
    return compact_text, lines


def _summary_flat_text(extracted_text):
    cleaned_text, _lines = _clean_summary_text(extracted_text)
    return re.sub(r"\s+", " ", cleaned_text).strip()


def _summary_regex(text, patterns, default=""):
    for pattern in patterns:
        match = re.search(pattern, text or "", re.I | re.S)
        if match:
            value = re.sub(r"\s+", " ", str(match.group(1))).strip(" :-|.,")
            if value:
                return _shorten(value, 120)
    return default


def _summary_from_fields(fields, *keys):
    for key in keys:
        value = _display_value((fields or {}).get(key), "")
        if value:
            return value
    return ""


def _summary_title_value(value):
    cleaned = re.sub(r"\s+", " ", str(value or "")).strip(" :-|.,")
    if not cleaned:
        return ""
    if cleaned.isupper() and len(cleaned) > 4:
        return cleaned.title()
    return cleaned


def _summary_compact_text(value):
    return re.sub(r"\s+", "", _normalize_text(value))


def _is_valid_summary_name(value, extracted_text=""):
    cleaned = _summary_title_value(value)
    if not cleaned or cleaned.lower() in SUMMARY_NAME_STOPWORDS:
        return ""
    if re.search(r"[@\d_]", cleaned):
        return ""
    words = re.findall(r"[A-Za-z][A-Za-z.'-]*", cleaned)
    if not 1 <= len(words) <= 5:
        return ""
    lowered = cleaned.lower()
    if any(stop in lowered for stop in SUMMARY_NAME_STOPWORDS):
        return ""
    if len(words) == 1 and extracted_text:
        text_compact = _summary_compact_text(extracted_text)
        if _summary_compact_text(cleaned) not in text_compact:
            return ""
    return " ".join(word.title() if word.isupper() else word for word in words)


def _summary_person_name(fields, extracted_text):
    for key in [
        "Full Name",
        "Candidate Name",
        "Student Name",
        "Employee Name",
        "Patient Name",
        "Passenger Name",
        "Policy Holder",
        "Account Holder",
        "Party Name",
        "Name",
        "Applicant Name",
    ]:
        name = _is_valid_summary_name((fields or {}).get(key), extracted_text)
        if name:
            return name

    built_name = _is_valid_summary_name(
        " ".join(
            part
            for part in [
                _clean_value((fields or {}).get("First Name")),
                _clean_value((fields or {}).get("Middle Name") or (fields or {}).get("Father's Name")),
                _clean_value((fields or {}).get("Last Name") or (fields or {}).get("Surname")),
            ]
            if part
        ),
        extracted_text,
    )
    if built_name:
        return built_name

    cleaned_text, lines = _clean_summary_text(extracted_text)
    label_pattern = re.compile(
        r"(?:candidate|student|employee|applicant|patient|passenger|policy holder|name)\s*(?:name)?\s*[:\-]\s*([A-Za-z][A-Za-z .'-]{2,70})",
        re.I,
    )
    for line in lines[:80]:
        match = label_pattern.search(line)
        if match:
            name = _is_valid_summary_name(match.group(1), cleaned_text)
            if name:
                return name
    return ""


def _summary_keyword_list(text, candidates, limit=8):
    found = []
    lower_text = str(text or "").lower()
    for candidate in candidates:
        candidate_lower = candidate.lower()
        if re.search(rf"(?<![A-Za-z0-9]){re.escape(candidate_lower)}(?![A-Za-z0-9])", lower_text, re.I):
            found.append(candidate)
    return _dedupe_preserve_order(found)[:limit]


def _summary_join(items):
    items = [str(item).strip() for item in items if str(item or "").strip()]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


def _summary_first_available(*values):
    for value in values:
        cleaned = _display_value(value, "")
        if cleaned:
            return cleaned
    return ""


def _summary_find_status(text):
    match = re.search(r"\b(PASS|PASSED|FAIL|FAILED|COMPLETED|APPROVED|REJECTED|PENDING|PAID|UNPAID)\b", text or "", re.I)
    return match.group(1).upper() if match else ""


def _summary_find_amount(text):
    return _summary_regex(
        text,
        [
            r"(?:total amount|amount payable|bill amount|claim amount|sum insured|premium|grand total|net amount|paid amount)\s*[:\-]?\s*(?:rs\.?|inr|₹)?\s*([0-9,]+(?:\.\d{1,2})?)",
            r"(?:rs\.?|inr|₹)\s*([0-9,]+(?:\.\d{1,2})?)",
        ],
    )


def _summary_find_date(text):
    return _summary_regex(
        text,
        [
            r"(?:date|issued on|completion date|invoice date|bill date)\s*[:\-]?\s*([0-9]{1,2}[-/][0-9]{1,2}[-/][0-9]{2,4})",
            r"(?:date|issued on|completion date|invoice date|bill date)\s*[:\-]?\s*([A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})",
        ],
    )


def _summary_find_semester(text):
    semester = _summary_regex(
        text,
        [
            r"(?:semester|sem)\s*[:\-]?\s*(\d{1,2}|[IVX]{1,5})(?:st|nd|rd|th)?",
            r"\b(\d{1,2})(?:st|nd|rd|th)\s+semester\b",
        ],
    )
    return semester


def _summary_find_branch_or_field(text):
    fields = [
        "Computer Engineering",
        "Information Technology",
        "Data Science",
        "Artificial Intelligence",
        "Computer Science",
        "Electronics and Communication",
        "Mechanical Engineering",
        "Civil Engineering",
        "Finance",
        "Human Resources",
        "Marketing",
    ]
    matches = _summary_keyword_list(text, fields, limit=3)
    return _summary_join(matches)


def _summary_find_organization(text):
    org = _summary_regex(
        text,
        [
            r"\b(?:at|from|by|issued by|organization|company|institute)\s+([A-Z][A-Za-z0-9 &'-]{2,50})(?:\.|\n|,| for | during | from | to |$)",
            r"\b([A-Z][A-Z0-9 &.-]{4,})\b",
        ],
    )
    return _summary_title_value(org)


def _summary_find_duration(text):
    return _summary_regex(
        text,
        [
            r"(?:duration|period)\s*[:\-]?\s*([A-Za-z0-9 ,./-]{4,70})",
            r"from\s+([A-Za-z0-9 ,./-]{4,35}\s+to\s+[A-Za-z0-9 ,./-]{4,35})",
        ],
    )


def _summary_find_identifier(text, fields, *field_keys):
    from_fields = _summary_from_fields(fields, *field_keys)
    if from_fields:
        return from_fields
    return _summary_regex(
        text,
        [
            r"(?:enrollment|roll|seat|student id|employee id)(?:\s*(?:number|no|id))?\s*[:\-]\s*([A-Z0-9\-/ ]{4,30})",
            r"(?:policy|claim|invoice|bill)(?:\s*(?:number|no|id))?\s*[:\-]\s*([A-Z0-9\-/]{4,30})",
            r"\bPAN(?:\s*(?:number|no|id))?\s*[:\-]?\s*([A-Z]{5}[0-9]{4}[A-Z])",
            r"(?:aadhaar|aadhar)(?:\s*(?:number|no|id))\s*[:\-]\s*([0-9 -]{8,20})",
            r"(?:license|licence)(?:\s*(?:number|no|id))?\s*[:\-]\s*([A-Z0-9\-/ ]{4,30})",
        ],
    )


def _mask_identifier(value):
    cleaned = re.sub(r"\s+", "", str(value or ""))
    if not cleaned:
        return ""
    if len(cleaned) <= 4:
        return "****"
    return "*" * max(len(cleaned) - 4, 4) + cleaned[-4:]


def _summary_meaningful_lines(text, limit=3):
    _cleaned_text, lines = _clean_summary_text(text)
    selected = []
    skip_words = {"page", "signature", "authorized", "copyright", "www", "http"}
    for line in lines:
        normalized = _normalize_text(line)
        if any(word in normalized for word in skip_words):
            continue
        if len(line) < 18:
            continue
        selected.append(_shorten(line, 150))
        if len(selected) >= limit:
            break
    return selected


def _summary_doc_family(document_type, text, file_name):
    combined = _normalize_text(f"{document_type} {file_name} {text[:2500]}")
    normalized_type = normalize_document_type_name(document_type)
    if normalized_type == "Resume" or "resume" in combined or "resum" in combined or "curriculum vitae" in combined or re.search(r"\bcv\b", combined):
        return "resume"
    if normalized_type == "Marksheet" or any(word in combined for word in ["marksheet", "markshet", "mark sheet", "result", "grade sheet", "cgpa", "sgpa"]):
        return "marksheet"
    if normalized_type == "Certificate" or any(word in combined for word in ["certificate", "certific", "certificat", "certification"]):
        return "certificate"
    if normalized_type == "Insurance Document" or any(word in combined for word in ["insurance", "policy", "claim"]):
        return "insurance"
    if normalized_type == "Invoice" or any(word in combined for word in ["invoice", "invoic", "receipt", "bill", "amount payable", "grand total"]):
        return "invoice"
    if normalized_type == "ID Proof" or any(word in combined for word in ["aadhaar", "aadhar", "pan", "driving license", "licence", "id proof"]):
        return "id"
    if normalized_type == "Application Form" or "form" in combined or "application" in combined or "information form" in combined:
        return "form"
    return _normalize_text(document_type)


def _fallback_document_summary(text, document_type):
    meaningful = _summary_meaningful_lines(text, limit=3)
    if meaningful:
        return _shorten(
            f"This {document_type.lower()} contains extracted details such as {meaningful[0]}"
            + (f". Additional visible information includes {meaningful[1]}." if len(meaningful) > 1 else "."),
            520,
        )
    return (
        f"This appears to be a {document_type} document. Some important text was detected, "
        "but the person name or full details are not clearly available due to OCR quality. "
        "Please review the extracted text before sending."
    )


def _resume_summary(text, fields):
    name = _summary_person_name(fields, text)
    skills = _summary_keyword_list(text, SUMMARY_SKILLS, limit=8)
    field = _summary_find_branch_or_field(text)
    if field:
        skills = [skill for skill in skills if skill.lower() not in field.lower()]
    has_education = bool(re.search(r"\b(education|b\.?tech|bachelor|degree|diploma|university|college)\b", text, re.I))
    has_experience = bool(re.search(r"\b(experience|internship|intern|training|work experience)\b", text, re.I))
    has_projects = bool(re.search(r"\b(project|analytics|prediction|system|model|dashboard)\b", text, re.I))

    lead = "Resume"
    if name:
        lead += f" of {name}"
    if field and skills:
        lead += f", a {field} candidate skilled in {_summary_join(skills)}"
    elif field:
        lead += f" for a {field} candidate"
    elif skills:
        lead += f" highlighting skills in {_summary_join(skills)}"
    else:
        lead += " containing candidate profile information from the extracted text"

    included = []
    if has_education:
        included.append("education details")
    if has_experience:
        included.append("internship or work experience")
    if has_projects:
        included.append("project details")

    if included:
        return f"{lead}. The resume includes {_summary_join(included)}."
    return f"{lead}. {_fallback_document_summary(text, 'resume')}"


def _marksheet_summary(text, fields):
    name = _summary_person_name(fields, text)
    enrollment = _summary_find_identifier(text, fields, "Seat Number", "Student ID", "Employee ID", "Document ID", "ID")
    semester = _summary_find_semester(text)
    branch = _summary_find_branch_or_field(text) or _summary_regex(text, [r"(?:branch|course|program)\s*[:\-]\s*([A-Za-z &./-]{3,70})"])
    cgpa = _summary_first_available(
        _summary_from_fields(fields, "CGPA"),
        _summary_regex(text, [r"\bCGPA\s*[:\-]?\s*([0-9.]+)", r"\bSGPA\s*[:\-]?\s*([0-9.]+)"]),
    )
    percentage = _summary_first_available(
        _summary_from_fields(fields, "Percentage"),
        _summary_regex(text, [r"(?:percentage|percent)\s*[:\-]?\s*([0-9.]+%?)"]),
    )
    status = _summary_from_fields(fields, "Result") or _summary_find_status(text)

    lead = "Marksheet"
    if name:
        lead += f" of {name}"
    if semester:
        lead += f" for Semester {semester}"
    if branch:
        lead += f" {branch}"

    details = []
    if enrollment:
        details.append("enrollment/roll number")
    if re.search(r"\b(subject|marks?|grade|credit)\b", text, re.I):
        details.append("subject-wise marks or grades")
    if cgpa or percentage:
        details.append("overall CGPA/SGPA/percentage details")
    if status:
        details.append("result status")

    sentence = f"{lead}. "
    if details:
        sentence += f"The document contains {_summary_join(details)}."
    else:
        sentence += _fallback_document_summary(text, "marksheet")
    if status:
        sentence += f" Result status appears as {status}."
    return sentence


def _certificate_summary(text, fields):
    name = _summary_person_name(fields, text)
    organization = _summary_find_organization(text)
    duration = _summary_find_duration(text)
    skills = _summary_keyword_list(text, SUMMARY_SKILLS, limit=6)
    field = _summary_find_branch_or_field(text)
    if field:
        skills = [skill for skill in skills if skill.lower() not in field.lower()]

    purpose = "certificate"
    if re.search(r"\binternship\b", text, re.I):
        purpose = "internship completion"
    elif re.search(r"\bcompletion\b", text, re.I):
        purpose = "course or training completion"
    elif re.search(r"\bachievement|participation|award\b", text, re.I):
        purpose = "achievement or participation"

    lead = "Certificate"
    if name:
        lead += f" of {name}"
    lead += f" related to {purpose}"
    if organization:
        lead += f" at {organization}"

    mentions = []
    if field:
        mentions.append(field)
    if skills:
        mentions.append("activities or skills such as " + _summary_join(skills))
    if duration:
        mentions.append("duration details")

    if mentions:
        return f"{lead}. The certificate mentions {_summary_join(mentions)}."
    return f"{lead}. {_fallback_document_summary(text, 'certificate')}"


def _insurance_summary(text, fields):
    person = _summary_person_name(fields, text)
    company = _summary_find_organization(text)
    policy = _summary_find_identifier(text, fields, "Policy Number", "Document ID", "ID")
    amount = _summary_find_amount(text)
    status = _summary_find_status(text)
    date = _summary_find_date(text)

    lead = "Insurance document"
    if person:
        lead += f" for {person}"
    if company:
        lead += f" from {company}"

    details = []
    if policy:
        details.append("policy/claim number")
    if amount:
        details.append(f"amount {amount}")
    if status:
        details.append(f"status {status}")
    if date:
        details.append(f"date {date}")

    if details:
        return f"{lead}. It includes {_summary_join(details)}."
    return f"{lead}. {_fallback_document_summary(text, 'insurance document')}"


def _invoice_summary(text, fields):
    invoice_no = _summary_find_identifier(text, fields, "Invoice Number", "Document ID", "ID")
    amount = _summary_first_available(_summary_from_fields(fields, "Total Amount", "Bill Amount"), _summary_find_amount(text))
    date = _summary_first_available(_summary_from_fields(fields, "Invoice Date", "Date"), _summary_find_date(text))
    vendor = _summary_from_fields(fields, "Vendor")
    customer = _summary_from_fields(fields, "Customer", "Patient Name")
    status = _summary_find_status(text)

    doc_label = "Invoice/bill document"
    details = []
    if vendor:
        details.append(f"vendor {vendor}")
    if customer:
        details.append(f"customer/patient {customer}")
    if invoice_no:
        details.append("bill or invoice number")
    if date:
        details.append(f"date {date}")
    if amount:
        details.append(f"total amount {amount}")
    if re.search(r"\b(item|service|description|particulars)\b", text, re.I):
        details.append("item/service details")
    if status:
        details.append(f"payment/status {status}")

    if details:
        return f"{doc_label} containing {_summary_join(details)}."
    return f"{doc_label}. {_fallback_document_summary(text, 'invoice or bill')}"


def _id_summary(text, fields):
    name = _summary_person_name(fields, text)
    id_type = "ID proof"
    if re.search(r"\baadhaar|aadhar\b", text, re.I):
        id_type = "Aadhaar"
    elif re.search(r"\bpan\b", text, re.I):
        id_type = "PAN"
    elif re.search(r"\bdriving licen[cs]e\b", text, re.I):
        id_type = "Driving License"

    identifier = _summary_find_identifier(text, fields, "Document ID", "ID")
    masked = _mask_identifier(identifier)
    lead = f"{id_type} document"
    if name:
        lead += f" of {name}"
    details = ["personal identification details"]
    if masked:
        details.append(f"official ID number partially masked as {masked}")
    if re.search(r"\b(date of birth|dob|address)\b", text, re.I):
        details.append("DOB/address information where visible")
    return f"{lead}. It contains {_summary_join(details)}."


def _form_summary(text, fields):
    name = _summary_person_name(fields, text)
    field = _summary_find_branch_or_field(text) or _summary_from_fields(fields, "Department", "Designation")
    form_purpose = "information/application form"
    if re.search(r"\bemployee\b", text, re.I):
        form_purpose = "employee information form"
    elif re.search(r"\badmission|student|academic\b", text, re.I):
        form_purpose = "academic/student information form"

    lead = form_purpose.capitalize()
    if name:
        lead += f" of {name}"
    details = []
    if field:
        details.append(f"related to {field}")
    if re.search(r"\b(email|phone|mobile|contact)\b", text, re.I):
        details.append("contact details")
    if re.search(r"\b(department|course|branch|education|academic)\b", text, re.I):
        details.append("academic or department details")

    if details:
        return f"{lead} containing {_summary_join(details)}."
    return f"{lead}. {_fallback_document_summary(text, 'form')}"


def generate_short_summary(extracted_text, document_type, extracted_fields, file_name=""):
    cleaned_text, _lines = _clean_summary_text(extracted_text)
    flat_text = _summary_flat_text(cleaned_text)
    if not flat_text:
        return "The document text could not be clearly extracted. Please upload a clearer image/PDF or manually enter the summary before sending."

    family = _summary_doc_family(document_type or "Document", flat_text, file_name)
    if family == "resume":
        summary = _resume_summary(flat_text, extracted_fields)
    elif family == "marksheet":
        summary = _marksheet_summary(flat_text, extracted_fields)
    elif family == "certificate":
        summary = _certificate_summary(flat_text, extracted_fields)
    elif family == "insurance":
        summary = _insurance_summary(flat_text, extracted_fields)
    elif family == "invoice" or family == "hospital bill":
        summary = _invoice_summary(flat_text, extracted_fields)
    elif family == "id":
        summary = _id_summary(flat_text, extracted_fields)
    elif family == "form" or family == "employee form":
        summary = _form_summary(flat_text, extracted_fields)
    elif family == "railway ticket":
        fields = extracted_fields or {}
        summary = (
            f"Railway ticket for {_summary_from_fields(fields, 'Passenger Name') or 'the passenger mentioned in the document'} "
            f"from {_summary_from_fields(fields, 'From Station') or 'origin not clearly available'} "
            f"to {_summary_from_fields(fields, 'To Station') or 'destination not clearly available'}."
        )
    elif family == "salary slip":
        fields = extracted_fields or {}
        summary = (
            f"Salary slip for {_summary_from_fields(fields, 'Employee Name') or 'the employee mentioned in the document'}"
            + (f" for {_summary_from_fields(fields, 'Month')}." if _summary_from_fields(fields, "Month") else ".")
        )
    elif family == "offer letter":
        fields = extracted_fields or {}
        name = _summary_person_name(fields, flat_text)
        designation = _summary_from_fields(fields, "Designation")
        company = _summary_from_fields(fields, "Company") or _summary_find_organization(flat_text)
        parts = []
        if designation:
            parts.append(f"designation {designation}")
        if company:
            parts.append(f"company {company}")
        if _summary_from_fields(fields, "Joining Date"):
            parts.append(f"joining date {_summary_from_fields(fields, 'Joining Date')}")
        summary = f"Offer letter for {name or 'the candidate mentioned in the document'}"
        if parts:
            summary += f" including {_summary_join(parts)}."
        else:
            summary += ". " + _fallback_document_summary(flat_text, "offer letter")
    else:
        summary = _fallback_document_summary(flat_text, document_type or "document")

    return _shorten(re.sub(r"\s+", " ", summary).strip(), 520)


def _compose_short_summary(document_type, important_fields, fallback_summary):
    # Backward-compatible wrapper for any older call sites.
    return generate_short_summary(fallback_summary, document_type, important_fields, "")


def _action_required(document_type, important_fields):
    actions = {
        "Railway Ticket": "Check ticket status before journey.",
        "Salary Slip": "No action required.",
        "Resume": "Review candidate details and shortlist if relevant.",
        "Offer Letter": "Verify joining date, designation and salary package before sharing.",
        "Hospital Bill": "Verify bill amount and patient details before reimbursement.",
        "Invoice": "Validate invoice amount, GST details and payment due date.",
        "Insurance Document": "Review policy number, premium and coverage details.",
        "Marksheet": "Verify student name, seat number and result details.",
        "Certificate": "Verify recipient name, organization, duration and purpose before sharing.",
        "ID Proof": "Verify the name and masked ID details before sharing.",
        "Application Form": "Verify applicant, contact and department details before filing.",
        "Employee Form": "Verify employee details before HR filing.",
        "Finance Document": "Review account and transaction details carefully.",
        "Legal Document": "Review legal terms and signatures before approval.",
    }
    return actions.get(document_type, "Review the extracted fields and route the document as needed.")


def generate_summary(raw_text, document_type, details, important_fields, file_name=""):
    try:
        fallback_summary = summarize_document(raw_text)
    except Exception:
        fallback_summary = ""

    summary_fields = {}
    summary_fields.update(important_fields or {})
    summary_fields.update(details or {})
    short_summary = generate_short_summary(raw_text, document_type, summary_fields, file_name)
    extracted_name = _build_full_name(details)
    found_fields = [
        f"{key}: {value}"
        for key, value in (important_fields or {}).items()
        if _display_value(value) != "Not Found"
    ][:7]

    detailed_parts = [f"This document was detected as {document_type}."]
    if extracted_name:
        detailed_parts.append(f"It appears to be associated with {extracted_name}.")
    if found_fields:
        detailed_parts.append("Key extracted details include " + "; ".join(found_fields) + ".")
    if fallback_summary and fallback_summary not in short_summary:
        detailed_parts.append(_shorten(fallback_summary, 280))

    return {
        "short_summary": _shorten(short_summary, 520),
        "detailed_summary": _shorten(" ".join(detailed_parts), 650),
        "important_fields": important_fields,
        "action_required": _action_required(document_type, important_fields),
    }


# ---------------------------------------------------------------------------
# Routing and email
# ---------------------------------------------------------------------------
def route_document_by_type(file_name, file_bytes, document_type):
    folder = os.path.join(UPLOADS_ROOT, _safe_folder_name(document_type))
    os.makedirs(folder, exist_ok=True)

    safe_file_name = os.path.basename(file_name)
    destination = os.path.join(folder, safe_file_name)
    if os.path.exists(destination):
        name, ext = os.path.splitext(safe_file_name)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        destination = os.path.join(folder, f"{name}_{stamp}{ext}")

    with open(destination, "wb") as file:
        file.write(file_bytes)

    return folder, destination


def _build_email_body(document):
    return "\n".join(
        [
            "Short Summary:",
            _display_value(document.get("short_summary")),
        ]
    )


def _friendly_email_error(exc):
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return "Gmail authentication failed. Please check the sender email and Gmail app password."
    if isinstance(exc, (smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected, TimeoutError, OSError)):
        return "Could not connect to Gmail SMTP. Please check your internet connection and try again."
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return "Gmail refused this recipient address."
    if isinstance(exc, smtplib.SMTPSenderRefused):
        return "Gmail refused the sender address."
    if isinstance(exc, smtplib.SMTPDataError):
        return "Gmail rejected the message content or attachment."
    if isinstance(exc, smtplib.SMTPException):
        return f"Gmail SMTP failure: {str(exc).strip() or exc.__class__.__name__}"
    return str(exc).strip() or exc.__class__.__name__


def _build_email_message(document, sender_email, receiver_email):
    message = EmailMessage()
    message["From"] = sender_email
    message["To"] = receiver_email
    message["Subject"] = f"ADMS | {document.get('file_name')} | {document.get('display_doc_type')}"
    message.set_content(_build_email_body(document))

    file_bytes = document.get("file_bytes", b"")
    mime_type, _encoding = mimetypes.guess_type(document.get("file_name", ""))
    maintype, subtype = (mime_type or "application/octet-stream").split("/", 1)
    message.add_attachment(
        file_bytes,
        maintype=maintype,
        subtype=subtype,
        filename=document.get("file_name", "document"),
    )
    return message


def _email_result(status, count=0, failed_count=0, report=None, error=""):
    return {
        "success": status == "Email Sent",
        "status": status,
        "count": count,
        "failed_count": failed_count,
        "report": report or [],
        "error": error,
    }


def send_email_with_attachment(document, sender_email, app_password, receiver_emails):
    recipients, invalid_recipients = parse_manual_emails(receiver_emails)
    report = [
        {"email": email, "status": "Invalid email skipped", "error": "Invalid email format"}
        for email in invalid_recipients
    ]

    if not recipients:
        error = "Please enter receiver email manually or upload a receiver list file."
        return _email_result("Email Skipped", report=report, error=error)

    sender_email = str(sender_email or "").strip()
    if not sender_email:
        error = "Sender email is required."
        report.extend({"email": email, "status": "Failed", "error": error} for email in recipients)
        return _email_result("Email Failed", failed_count=len(recipients), report=report, error=error)

    if not validate_email(sender_email):
        error = "Valid sender email is required."
        report.extend({"email": email, "status": "Failed", "error": error} for email in recipients)
        return _email_result("Email Failed", failed_count=len(recipients), report=report, error=error)

    if not app_password:
        error = "Gmail app password is required."
        report.extend({"email": email, "status": "Failed", "error": error} for email in recipients)
        return _email_result("Email Failed", failed_count=len(recipients), report=report, error=error)

    file_bytes = document.get("file_bytes", b"")
    if not file_bytes:
        error = "Attachment/document is missing."
        report.extend({"email": email, "status": "Failed", "error": error} for email in recipients)
        return _email_result("Email Failed", failed_count=len(recipients), report=report, error=error)

    if len(file_bytes) > MAX_GMAIL_ATTACHMENT_BYTES:
        error = "This file is too large to send through Gmail. Please compress it or upload to Drive and share the link."
        report.extend({"email": email, "status": "Failed", "error": error} for email in recipients)
        return {
            **_email_result("Email Failed", failed_count=len(recipients), report=report, error=error),
        }

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
            smtp.login(sender_email, app_password)
            for recipient in recipients:
                try:
                    message = _build_email_message(document, sender_email, recipient)
                    smtp.send_message(message, from_addr=sender_email, to_addrs=[recipient])
                    report.append({"email": recipient, "status": "Sent", "error": ""})
                except Exception as exc:
                    report.append({"email": recipient, "status": "Failed", "error": _friendly_email_error(exc)})
    except Exception as exc:
        error = _friendly_email_error(exc)
        report.extend({"email": email, "status": "Failed", "error": error} for email in recipients)
        return _email_result("Email Failed", failed_count=len(recipients), report=report, error=error)

    sent_count = sum(1 for row in report if row.get("status") == "Sent")
    failed_count = sum(1 for row in report if row.get("status") == "Failed")

    if sent_count and failed_count:
        status = "Email Partial"
    elif sent_count:
        status = "Email Sent"
    else:
        status = "Email Failed"

    error = "" if status == "Email Sent" else "; ".join(
        _dedupe_preserve_order(row.get("error", "") for row in report if row.get("error"))
    )
    return _email_result(status, count=sent_count, failed_count=failed_count, report=report, error=error)


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------
def _report_rows(documents, include_raw_text=False):
    rows = []
    for document in documents:
        row = {
            "File Name": document.get("file_name", ""),
            "Document Type": document.get("display_doc_type", ""),
            "Confidence Score": document.get("confidence_score", 0),
            "Extracted Name": document.get("extracted_name", "Not Found"),
            "Short Summary": document.get("short_summary", ""),
            "Important Fields": json.dumps(document.get("important_fields", {}), ensure_ascii=False),
            "Receiver Email": ", ".join(document.get("receiver_emails", [])),
            "Email Status": document.get("email_status", "Not Requested"),
            "Processing Status": document.get("processing_status", ""),
            "Error Message": document.get("error_message", ""),
        }
        if include_raw_text:
            row["Raw Text"] = document.get("raw_text", "")
        rows.append(row)
    return rows


def generate_excel_report(documents):
    output = io.BytesIO()
    pd.DataFrame(_report_rows(documents)).to_excel(output, index=False, sheet_name="ADMS Report")
    return output.getvalue()


def generate_csv_report(documents):
    return pd.DataFrame(_report_rows(documents)).to_csv(index=False).encode("utf-8")


def build_invalid_receiver_rows(manual_invalid_emails, receiver_invalid_rows):
    invalid_rows = [
        {"Source": "Manual", "Email": email, "Reason": "Invalid email format"}
        for email in manual_invalid_emails
    ]
    invalid_rows.extend(
        {
            "Source": "Receiver List",
            "Email": row.get("email", ""),
            "Reason": row.get("reason", "Invalid email format"),
        }
        for row in receiver_invalid_rows
    )
    return invalid_rows


def generate_delivery_report(documents, invalid_rows=None):
    report_rows = []

    for row in invalid_rows or []:
        report_rows.append(
            {
                "File Name": "",
                "Email": row.get("Email", ""),
                "Status": "Invalid email skipped",
                "Error Message": row.get("Reason", "Invalid email format"),
            }
        )

    for document in documents or []:
        file_name = document.get("file_name", "")
        for row in document.get("email_delivery_report", []):
            report_rows.append(
                {
                    "File Name": file_name,
                    "Email": row.get("email", ""),
                    "Status": row.get("status", ""),
                    "Error Message": row.get("error", ""),
                }
            )

    return pd.DataFrame(report_rows, columns=["File Name", "Email", "Status", "Error Message"])


def _compact_search_text(value):
    return re.sub(r"\s+", "", _normalize_text(value))


def _history_field_matches(value, query):
    query_norm = _normalize_text(query)
    query_compact = _compact_search_text(query)
    value_norm = _normalize_text(value)
    value_compact = _compact_search_text(value)
    return bool(
        query_norm
        and (
            query_norm in value_norm
            or (query_compact and query_compact in value_compact)
        )
    )


def _history_suggestion_rank(row, query):
    query_norm = _normalize_text(query)
    query_compact = _compact_search_text(query)
    file_name = row.get("file_name", "")
    file_norm = _normalize_text(file_name)
    file_compact = _compact_search_text(file_name)

    if query_norm and (
        file_norm.startswith(query_norm)
        or (query_compact and file_compact.startswith(query_compact))
    ):
        return 0
    if _history_field_matches(file_name, query):
        return 1
    if _history_field_matches(row.get("extracted_name", ""), query):
        return 2
    if (
        _history_field_matches(row.get("document_type", ""), query)
        or _history_field_matches(row.get("email_status", ""), query)
    ):
        return 3
    return None


def _filter_history_records(history_df, query):
    if history_df is None or history_df.empty or not str(query or "").strip():
        return history_df

    mask = history_df.apply(
        lambda row: any(
            _history_field_matches(row.get(column, ""), query)
            for column in ["file_name", "extracted_name", "document_type", "email_status"]
        ),
        axis=1,
    )
    return history_df[mask]


def _history_suggestions(history_df, query, limit=10):
    if history_df is None or history_df.empty or not str(query or "").strip():
        return []

    ranked = []
    for index, row in history_df.iterrows():
        rank = _history_suggestion_rank(row, query)
        if rank is not None:
            ranked.append((rank, index, row))

    ranked.sort(key=lambda item: (item[0], item[1]))
    return [row for _rank, _index, row in ranked[:limit]]


def _render_history_suggestions(suggestions, query_param_key):
    if not suggestions:
        return ""

    items = []
    for row in suggestions:
        file_name = str(row.get("file_name", "") or "")
        document_type = str(row.get("document_type", "") or "General Document")
        extracted_name = str(row.get("extracted_name", "") or "Not Found")
        email_status = str(row.get("email_status", "") or "Not Requested")
        href = f"?{query_param_key}={quote_plus(file_name)}"
        items.append(
            f"""
            <a class="suggestion-item" href="{html.escape(href, quote=True)}">
                <span class="suggestion-file">{html.escape(file_name)}</span>
                <span>{html.escape(document_type)}</span>
                <span>{html.escape(extracted_name)}</span>
                <span>{html.escape(email_status)}</span>
            </a>
            """
        )

    return f"""
    <div class="suggestion-shell">
        <div class="suggestion-title">Matching documents</div>
        <div class="suggestion-list">{''.join(items)}</div>
    </div>
    """


def generate_pdf_report(documents, include_raw_text=False):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    output = io.BytesIO()
    doc = SimpleDocTemplate(
        output,
        pagesize=landscape(A4),
        leftMargin=0.4 * inch,
        rightMargin=0.4 * inch,
        topMargin=0.45 * inch,
        bottomMargin=0.45 * inch,
    )
    styles = getSampleStyleSheet()
    story = [
        Paragraph("ADMS Document Processing Report", styles["Title"]),
        Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles["Normal"]),
        Spacer(1, 0.2 * inch),
    ]

    columns = [
        "File Name",
        "Document Type",
        "Confidence Score",
        "Extracted Name",
        "Short Summary",
        "Receiver Email",
        "Email Status",
        "Processing Status",
        "Error Message",
    ]
    if include_raw_text:
        columns.append("Raw Text")

    table_data = [[Paragraph(f"<b>{column}</b>", styles["BodyText"]) for column in columns]]
    for row in _report_rows(documents, include_raw_text=include_raw_text):
        table_data.append([Paragraph(html.escape(_shorten(row.get(column, ""), 260)), styles["BodyText"]) for column in columns])

    table = Table(table_data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#182340")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#9aa8cc")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f7f8fc")),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(table)
    doc.build(story)
    return output.getvalue()


def prepare_uploaded_documents_download(documents):
    downloadable = [
        document
        for document in documents
        if document.get("file_bytes") and document.get("file_name")
    ]

    if not downloadable:
        return b"", "adms_documents.zip", "application/zip"

    if len(downloadable) == 1:
        document = downloadable[0]
        mime_type, _encoding = mimetypes.guess_type(document.get("file_name", ""))
        return (
            document.get("file_bytes", b""),
            document.get("file_name", "document"),
            mime_type or "application/octet-stream",
        )

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        used_names = set()
        for index, document in enumerate(downloadable, start=1):
            original_name = os.path.basename(document.get("file_name", f"document_{index}"))
            name, ext = os.path.splitext(original_name)
            safe_name = original_name
            if safe_name.lower() in used_names:
                safe_name = f"{name}_{index}{ext}"
            used_names.add(safe_name.lower())
            archive.writestr(safe_name, document.get("file_bytes", b""))

    return output.getvalue(), "adms_uploaded_documents.zip", "application/zip"


# ---------------------------------------------------------------------------
# Processing
# ---------------------------------------------------------------------------
def _failed_document(uploaded_file, index, error_message):
    file_name = getattr(uploaded_file, "name", f"document_{index}")
    file_bytes = uploaded_file.getvalue() if hasattr(uploaded_file, "getvalue") else b""
    return {
        "doc_key": _safe_doc_key(file_name, index),
        "file_name": file_name,
        "file_bytes": file_bytes,
        "raw_text": "",
        "english_text": "",
        "language_info": {},
        "display_raw_text": "",
        "doc_det": {},
        "details": {},
        "doc_summary": "",
        "display_doc_type": "General Document",
        "confidence_score": 0,
        "important_fields": {},
        "extracted_name": NOT_CLEAR,
        "name_confidence": 0,
        "name_detection_source": "",
        "short_summary": "",
        "summary_confidence": 0,
        "low_confidence": True,
        "detailed_summary": "",
        "action_required": "Review the error and upload a readable document.",
        "processing_status": "Failed",
        "error_message": error_message,
        "receiver_emails": [],
        "email_status": "Not Requested",
        "email_error": "",
        "email_sent_count": 0,
        "email_failed_count": 0,
        "email_delivery_report": [],
        "matched_receiver_emails": [],
        "matched_receiver_names": [],
        "category_folder": "",
        "category_file_path": "",
        "legacy_folder": "",
        "legacy_file_path": "",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def _process_uploaded_document(uploaded_file, index, route_to_local_folder=False):
    try:
        if hasattr(uploaded_file, "seek"):
            uploaded_file.seek(0)
        file_bytes = uploaded_file.getvalue()

        raw_text = extract_text_from_file(uploaded_file)
        if not raw_text or not str(raw_text).strip():
            raise ValueError("No text could be extracted from this document.")
        if str(raw_text).lower().startswith("error extracting text"):
            raise ValueError(raw_text)
        if "unsupported file format" in str(raw_text).lower():
            raise ValueError(raw_text)

        language_bundle = process_multilingual_text(raw_text)
        analysis_text = language_bundle.get("english_text") or raw_text

        file_det = extract_from_filename(uploaded_file.name)
        doc_det = smart_parse(raw_text)
        details = smart_merge(doc_det, file_det)
        details["_translated"] = analysis_text

        doc_summary = summarize_document(analysis_text)
        details, legacy_doc_type, doc_summary = prepare_display_details(details, raw_text, doc_summary)
        display_raw_text = format_extracted_text_for_display(raw_text, details)

        detected_type, confidence_score = detect_document_type(
            uploaded_file.name,
            analysis_text,
            details.get("doc_type") or legacy_doc_type,
        )
        important_fields = extract_important_fields(detected_type, details, analysis_text, uploaded_file.name)
        name_result = extract_person_name_result(
            uploaded_file.name,
            raw_text,
            details,
            important_fields,
            english_text=analysis_text,
            document_type=detected_type,
        )
        extracted_name = name_result["name"]
        details, important_fields = _apply_detected_name_to_fields(
            details,
            important_fields,
            extracted_name,
            detected_type,
        )
        summary_bundle = generate_summary(analysis_text, detected_type, details, important_fields, uploaded_file.name)
        summary_score = summary_confidence(summary_bundle["short_summary"], analysis_text)
        low_confidence = (
            name_result.get("confidence", 0) < 70
            or summary_score < 55
            or is_weak_summary(summary_bundle["short_summary"])
        )

        log_indicator(
            "pipeline",
            extracted_text_length=len(raw_text),
            analysis_text_length=len(analysis_text),
            language=language_bundle.get("detected_language"),
            translation_success=language_bundle.get("translation_success"),
            document_type=detected_type,
            name_confidence=name_result.get("confidence", 0),
            summary_confidence=summary_score,
            fallback_used=low_confidence,
        )

        category_folder, category_file_path = route_document_by_type(uploaded_file.name, file_bytes, detected_type)

        legacy_folder = ""
        legacy_file_path = ""
        if route_to_local_folder:
            legacy_folder, legacy_file_path = save_uploaded_bytes(
                uploaded_file.name,
                file_bytes,
                _display_value(details.get("First Name"), "Unknown"),
                _display_value(details.get("Last Name") or details.get("Surname"), "Unknown"),
                _display_value(details.get("Middle Name") or details.get("Father's Name"), "Unknown"),
                _display_value(details.get("ID"), "NoID"),
                OUTPUT_ROOT,
            )

        return {
            "doc_key": _safe_doc_key(uploaded_file.name, index),
            "file_name": uploaded_file.name,
            "file_bytes": file_bytes,
            "raw_text": raw_text,
            "english_text": analysis_text,
            "language_info": language_bundle,
            "display_raw_text": display_raw_text,
            "doc_det": doc_det,
            "details": details,
            "doc_summary": doc_summary,
            "legacy_doc_type": legacy_doc_type,
            "display_doc_type": detected_type,
            "confidence_score": confidence_score,
            "important_fields": summary_bundle["important_fields"],
            "extracted_name": extracted_name,
            "name_confidence": name_result.get("confidence", 0),
            "name_detection_source": name_result.get("source", ""),
            "short_summary": summary_bundle["short_summary"],
            "summary_confidence": summary_score,
            "low_confidence": low_confidence,
            "detailed_summary": summary_bundle["detailed_summary"],
            "action_required": summary_bundle["action_required"],
            "processing_status": "Processed",
            "error_message": "",
            "receiver_emails": [],
            "email_status": "Not Requested",
            "email_error": "",
            "email_sent_count": 0,
            "email_failed_count": 0,
            "email_delivery_report": [],
            "matched_receiver_emails": [],
            "matched_receiver_names": [],
            "category_folder": category_folder,
            "category_file_path": category_file_path,
            "legacy_folder": legacy_folder,
            "legacy_file_path": legacy_file_path,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    except Exception as exc:
        return _failed_document(uploaded_file, index, str(exc))


def _build_skipped_email_report(recipients, error):
    if not recipients:
        return [{"email": "", "status": "Skipped", "error": error}]
    return [{"email": email, "status": "Skipped", "error": error} for email in recipients]


def _apply_delivery_actions(document, actions, email_settings):
    if document.get("processing_status") != "Processed":
        if "Send via Email" in actions:
            recipients = email_settings.get("all_recipients", [])
            error = "Attachment/document is missing or document processing failed."
            document["receiver_emails"] = recipients
            document["receiver_source"] = "Document processing failed"
            document["email_status"] = "Email Skipped"
            document["email_error"] = error
            document["email_sent_count"] = 0
            document["email_failed_count"] = 0
            document["email_delivery_report"] = _build_skipped_email_report(recipients, error)
        else:
            document["email_status"] = "Not Sent"
        return document

    if "Send via Email" in actions:
        recipients, recipient_source = resolve_document_recipients(
            document,
            email_settings.get("receiver_rows", []),
            email_settings.get("manual_emails", []),
            email_settings.get("unmatched_fallback", "Skip unmatched document"),
            email_settings.get("all_recipients", []),
        )
        document["receiver_emails"] = recipients
        document["receiver_source"] = recipient_source

        if recipients:
            result = send_email_with_attachment(
                document,
                email_settings.get("sender_email", ""),
                email_settings.get("password", ""),
                recipients,
            )
            document["email_status"] = result["status"]
            document["email_error"] = result.get("error", "")
            document["email_sent_count"] = result.get("count", 0)
            document["email_failed_count"] = result.get("failed_count", 0)
            document["email_delivery_report"] = result.get("report", [])
        else:
            document["email_status"] = "Email Skipped"
            document["email_error"] = recipient_source
            document["email_sent_count"] = 0
            document["email_failed_count"] = 0
            document["email_delivery_report"] = _build_skipped_email_report(recipients, recipient_source)

    return document


def _identifier_from_document(document):
    details = document.get("details", {}) or {}
    important_fields = document.get("important_fields", {}) or {}
    return _summary_first_available(
        _field_from_details(details, "ID"),
        _summary_from_fields(
            important_fields,
            "ID",
            "Document ID",
            "Employee ID",
            "Student ID",
            "Seat Number",
            "Policy Number",
            "Invoice Number",
            "PNR",
        ),
    )


def _review_defaults(document):
    details = document.get("details", {}) or {}
    important_fields = document.get("important_fields", {}) or {}
    return {
        "document_type": document.get("display_doc_type", "General Document"),
        "name": document.get("extracted_name", NOT_CLEAR),
        "first_name": _display_value(details.get("First Name"), ""),
        "middle_name": _display_value(details.get("Middle Name") or details.get("Father's Name"), ""),
        "last_name": _display_value(details.get("Last Name") or details.get("Surname"), ""),
        "identifier": _identifier_from_document(document),
        "department": _summary_first_available(
            _field_from_details(details, "Department"),
            _summary_from_fields(important_fields, "Department", "Designation", "Branch", "Course", "Field"),
        ),
        "email": _summary_first_available(
            _field_from_details(details, "Email"),
            _summary_from_fields(important_fields, "Email"),
        ),
        "phone": _summary_first_available(
            _field_from_details(details, "Phone"),
            _summary_from_fields(important_fields, "Phone"),
        ),
        "summary": document.get("short_summary", ""),
    }


def _name_field_for_document_type(document_type):
    return {
        "Resume": "Candidate Name",
        "Certificate": "Candidate Name",
        "Marksheet": "Student Name",
        "Employee Form": "Employee Name",
        "Application Form": "Applicant Name",
        "Insurance Document": "Policy Holder",
        "Invoice": "Customer",
        "Hospital Bill": "Patient Name",
        "Railway Ticket": "Passenger Name",
    }.get(document_type, "Name")


def _identifier_field_for_document_type(document_type):
    return {
        "Marksheet": "Seat Number",
        "Employee Form": "Employee ID",
        "Insurance Document": "Policy Number",
        "Invoice": "Invoice Number",
        "ID Proof": "Document ID",
        "Railway Ticket": "PNR",
    }.get(document_type, "Document ID")


def apply_review_updates(document, values):
    details = document.setdefault("details", {})
    important_fields = document.setdefault("important_fields", {})

    requested_type = str(values.get("document_type") or "").strip()
    document_type = normalize_document_type_name(requested_type) or requested_type or "General Document"
    document["display_doc_type"] = document_type

    first_name = _display_value(values.get("first_name"), "")
    middle_name = _display_value(values.get("middle_name"), "")
    last_name = _display_value(values.get("last_name"), "")
    explicit_name = _display_value(values.get("name"), "")
    built_name = " ".join(part for part in [first_name, middle_name, last_name] if part)
    reviewed_name = explicit_name if explicit_name and explicit_name != NOT_CLEAR else built_name
    reviewed_name, name_score = validate_person_name(reviewed_name, require_two_words=False)
    if not reviewed_name:
        reviewed_name = NOT_CLEAR
        name_score = 0

    document["extracted_name"] = reviewed_name
    document["name_confidence"] = max(int(document.get("name_confidence", 0) or 0), name_score)
    details["Full Name"] = reviewed_name
    details["First Name"] = first_name or "Not Found"
    details["Middle Name"] = middle_name or "Not Found"
    details["Last Name"] = last_name or "Not Found"
    details["Surname"] = last_name or "Not Found"
    details["Father's Name"] = middle_name or details.get("Father's Name", "Not Found")

    identifier = _display_value(values.get("identifier"), "")
    department = _display_value(values.get("department"), "")
    email = _display_value(values.get("email"), "")
    phone = _display_value(values.get("phone"), "")

    details["ID"] = identifier or "Not Found"
    details["Department"] = department or "Not Found"
    details["Email"] = email or "Not Found"
    details["Phone"] = phone or "Not Found"

    important_fields[_name_field_for_document_type(document_type)] = reviewed_name
    important_fields[_identifier_field_for_document_type(document_type)] = identifier or "Not Found"
    important_fields["Department"] = department or "Not Found"
    important_fields["Email"] = email or "Not Found"
    important_fields["Phone"] = phone or "Not Found"

    summary = re.sub(r"\s+", " ", str(values.get("summary") or "")).strip()
    document["short_summary"] = summary
    document["summary_confidence"] = summary_confidence(summary, document.get("english_text") or document.get("raw_text") or "")
    document["low_confidence"] = (
        reviewed_name == NOT_CLEAR
        or is_weak_summary(summary)
        or document["summary_confidence"] < 55
    )
    document["review_confirmed"] = True
    document["action_required"] = _action_required(document_type, important_fields)

    found_fields = [
        f"{key}: {value}"
        for key, value in important_fields.items()
        if _display_value(value) != "Not Found"
    ][:7]
    detailed_parts = [f"This document was reviewed as {document_type}."]
    if reviewed_name != NOT_CLEAR:
        detailed_parts.append(f"It is associated with {reviewed_name}.")
    if found_fields:
        detailed_parts.append("Reviewed details include " + "; ".join(found_fields) + ".")
    document["detailed_summary"] = _shorten(" ".join(detailed_parts), 650)
    return document


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
st.set_page_config(page_title="ADMS Pro", page_icon="A", layout="wide")
init_database()

st.markdown(
    """
<style>
:root {
    --bg-main: #060b18;
    --bg-panel: #0f1730;
    --bg-panel-2: #182340;
    --text-main: #f7f8fc;
    --text-soft: #a7b2cf;
    --text-muted: #7d88a9;
    --line: rgba(111, 130, 177, 0.18);
    --blue: #4f73ff;
    --green: #22c55e;
    --red: #ef4444;
    --amber: #f59e0b;
}

html, body, [class*="css"] {
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 16px;
}

.stApp {
    background:
        radial-gradient(circle at top right, rgba(80, 115, 255, 0.14), transparent 24%),
        radial-gradient(circle at top left, rgba(125, 77, 255, 0.10), transparent 28%),
        linear-gradient(180deg, #050914 0%, #070d1c 100%);
    color: var(--text-main);
}

[data-testid="stAppViewContainer"],
[data-testid="stMain"],
section.main {
    background: transparent !important;
}

[data-testid="stHeader"],
.stAppHeader {
    background: linear-gradient(180deg, #050914 0%, #070d1c 100%) !important;
    border-bottom: 1px solid rgba(111, 130, 177, 0.08) !important;
}

.main .block-container {
    max-width: 1500px;
    padding: 2rem;
}

section[data-testid="stSidebar"] {
    width: 340px !important;
    min-width: 340px !important;
    border-right: 1px solid rgba(122, 138, 184, 0.14);
    background: linear-gradient(180deg, #10182e 0%, #0c1324 100%);
}

section[data-testid="stSidebar"] > div {
    background: linear-gradient(180deg, #10182e 0%, #0c1324 100%);
}

.brand-card {
    display: flex;
    align-items: center;
    gap: 14px;
    padding: 0.4rem 0 1.1rem 0;
    margin-bottom: 1rem;
    border-bottom: 1px solid rgba(123, 137, 176, 0.15);
}

.brand-icon {
    width: 48px;
    height: 48px;
    border-radius: 14px;
    background: linear-gradient(145deg, #4973ff, #8c42ff);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.3rem;
    font-weight: 800;
    color: white;
}

.brand-copy h1 {
    margin: 0;
    font-size: 1.9rem;
    line-height: 1;
    font-weight: 800;
    color: #f8f9ff;
}

.brand-copy p {
    margin: 0.3rem 0 0 0;
    color: var(--text-soft);
    font-size: 1rem;
    font-weight: 500;
}

.sidebar-label {
    margin-top: 1.2rem;
    margin-bottom: 0.65rem;
    font-size: 0.82rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--text-muted);
    font-weight: 700;
}

.hero-shell,
.section-panel,
.document-card,
.routing-card,
.empty-state {
    background: linear-gradient(180deg, rgba(18, 27, 50, 0.96), rgba(15, 22, 41, 0.96));
    border: 1px solid var(--line);
    border-radius: 18px;
    box-shadow: 0 24px 50px rgba(3, 8, 20, 0.25);
}

.hero-shell {
    padding: 1.8rem 2rem;
    margin-bottom: 1.25rem;
}

.hero-title {
    margin: 0;
    font-size: 2.65rem;
    line-height: 1.05;
    font-weight: 800;
    color: var(--text-main);
}

.hero-subtitle {
    margin-top: 0.75rem;
    font-size: 1.14rem;
    color: var(--text-soft);
}

.section-panel {
    padding: 1.2rem 1.35rem;
    margin-bottom: 1rem;
}

.panel-title {
    margin: 0.3rem 0 0.9rem 0;
    font-size: 1.16rem;
    color: var(--text-main);
    font-weight: 800;
}

.metric-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
    gap: 14px;
    margin-bottom: 1rem;
}

.metric-card {
    background: linear-gradient(180deg, rgba(24, 35, 64, 0.98), rgba(19, 29, 53, 0.98));
    border: 1px solid rgba(111, 130, 177, 0.18);
    border-radius: 14px;
    padding: 1rem;
}

.metric-card span {
    display: block;
    color: var(--text-muted);
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-weight: 700;
}

.metric-card strong {
    display: block;
    color: #ffffff;
    font-size: 2rem;
    line-height: 1.2;
    margin-top: 0.25rem;
}

.document-card {
    padding: 1rem 1.15rem;
    margin: 1rem 0 0.65rem 0;
}

.document-card h3 {
    margin: 0 0 0.55rem 0;
    font-size: 1.16rem;
    color: #ffffff;
}

.doc-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 0.55rem;
    align-items: center;
    color: var(--text-soft);
}

.doc-type-badge,
.status-badge {
    display: inline-flex;
    align-items: center;
    border-radius: 999px;
    padding: 0.35rem 0.65rem;
    font-size: 0.82rem;
    line-height: 1.1;
    font-weight: 700;
    border: 1px solid rgba(111, 130, 177, 0.24);
}

.doc-type-badge {
    color: #dbe4ff;
    background: rgba(79, 115, 255, 0.18);
    border-color: rgba(79, 115, 255, 0.35);
}

.status-badge {
    color: #dbe4ff;
    background: rgba(111, 130, 177, 0.16);
}

.status-processed,
.status-email-sent {
    color: #dcfff0;
    background: rgba(34, 197, 94, 0.16);
    border-color: rgba(34, 197, 94, 0.42);
}

.status-failed,
.status-email-failed {
    color: #ffe3e3;
    background: rgba(239, 68, 68, 0.16);
    border-color: rgba(239, 68, 68, 0.42);
}

.status-email-skipped,
.status-not-sent,
.status-pending-review,
.status-email-partial {
    color: #fff2cc;
    background: rgba(245, 158, 11, 0.16);
    border-color: rgba(245, 158, 11, 0.42);
}

.summary-box {
    background: linear-gradient(180deg, rgba(17, 25, 46, 0.98), rgba(14, 21, 38, 0.98));
    border: 1px solid rgba(111, 130, 177, 0.2);
    border-left: 4px solid #4f73ff;
    border-radius: 14px;
    padding: 1rem 1.15rem;
    font-size: 1rem;
    line-height: 1.75;
    color: #eef3ff;
}

.text-box {
    max-height: 380px;
    overflow-y: auto;
    white-space: pre-wrap;
    word-break: break-word;
}

.data-table-shell {
    margin-top: 0.85rem;
    border: 1px solid rgba(111, 130, 177, 0.18);
    border-radius: 14px;
    overflow-x: auto;
    background: rgba(18, 27, 50, 0.96);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.03);
}

.data-table {
    width: 100%;
    border-collapse: collapse;
    min-width: 760px;
}

.data-table thead th {
    background: rgba(31, 45, 78, 0.95);
    color: #cfd9f8;
    text-align: left;
    font-size: 0.78rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    padding: 0.82rem 0.9rem;
}

.data-table tbody td {
    color: #eef3ff;
    padding: 0.82rem 0.9rem;
    border-top: 1px solid rgba(111, 130, 177, 0.12);
    vertical-align: top;
    word-break: break-word;
}

.data-table tbody tr:nth-child(odd) td {
    background: rgba(18, 27, 50, 0.94);
}

.data-table tbody tr:nth-child(even) td {
    background: rgba(23, 34, 61, 0.94);
}

.suggestion-shell {
    margin-top: 0.45rem;
    border: 1px solid rgba(111, 130, 177, 0.24);
    border-radius: 14px;
    background: linear-gradient(180deg, rgba(15, 23, 42, 0.98), rgba(11, 18, 34, 0.98));
    overflow: hidden;
    box-shadow: 0 18px 36px rgba(3, 8, 20, 0.32);
}

.suggestion-title {
    padding: 0.65rem 0.85rem;
    color: var(--text-muted);
    font-size: 0.76rem;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    font-weight: 800;
    border-bottom: 1px solid rgba(111, 130, 177, 0.14);
    background: rgba(24, 35, 64, 0.92);
}

.suggestion-list {
    display: flex;
    flex-direction: column;
}

.suggestion-item,
.suggestion-item:visited {
    display: grid;
    grid-template-columns: minmax(150px, 2fr) minmax(90px, 1fr) minmax(100px, 1fr) minmax(95px, 1fr);
    gap: 0.65rem;
    align-items: center;
    padding: 0.72rem 0.85rem;
    color: #dce6ff !important;
    text-decoration: none !important;
    background: rgba(18, 27, 50, 0.95);
    border-top: 1px solid rgba(111, 130, 177, 0.10);
    transition: background 120ms ease, color 120ms ease, transform 120ms ease;
}

.suggestion-item:first-child {
    border-top: 0;
}

.suggestion-item:hover,
.suggestion-item:focus {
    color: #ffffff !important;
    background: linear-gradient(90deg, rgba(47, 92, 246, 0.28), rgba(125, 77, 255, 0.20));
    transform: translateY(-1px);
}

.suggestion-file {
    color: #ffffff;
    font-weight: 800;
}

.no-suggestions {
    margin-top: 0.45rem;
    padding: 0.72rem 0.85rem;
    border-radius: 12px;
    border: 1px solid rgba(111, 130, 177, 0.20);
    background: rgba(18, 27, 50, 0.92);
    color: var(--text-soft);
    font-size: 0.92rem;
}

div[data-testid="stDataFrame"],
div[data-testid="stDataFrame"] *,
div[data-testid="stTable"],
div[data-testid="stTable"] *,
[data-testid="stDataFrameResizable"],
[data-testid="stDataFrameResizable"] * {
    background-color: #101a32 !important;
    color: #eef3ff !important;
    border-color: rgba(111, 130, 177, 0.22) !important;
}

.stTextInput label,
.stTextArea label,
.stSelectbox label,
.stMultiSelect label,
.stRadio label,
.stFileUploader label,
.stCheckbox label {
    color: #dce4f7 !important;
    font-weight: 600 !important;
}

div[data-baseweb="input"],
div[data-baseweb="textarea"],
div[data-baseweb="select"] > div {
    border-radius: 12px !important;
    border: 1px solid rgba(111, 130, 177, 0.26) !important;
    background: linear-gradient(180deg, #1b2745 0%, #18233f 100%) !important;
    color: #ffffff !important;
}

div[data-baseweb="input"] input,
div[data-baseweb="textarea"] textarea,
div[data-baseweb="select"] span,
div[data-baseweb="select"] input {
    color: #ffffff !important;
}

input,
textarea,
input:hover,
textarea:hover,
input:focus,
textarea:focus {
    background: #18233f !important;
    color: #ffffff !important;
    caret-color: #ffffff !important;
    -webkit-text-fill-color: #ffffff !important;
}

input::placeholder,
textarea::placeholder {
    color: #a7b2cf !important;
    opacity: 1 !important;
}

div[data-baseweb="input"]:hover,
div[data-baseweb="textarea"]:hover,
div[data-baseweb="select"] > div:hover,
div[data-baseweb="input"]:focus-within,
div[data-baseweb="textarea"]:focus-within,
div[data-baseweb="select"] > div:focus-within {
    background: linear-gradient(180deg, #223158 0%, #1a2748 100%) !important;
    border-color: rgba(129, 154, 255, 0.55) !important;
}

div[data-baseweb="popover"] {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
}

div[data-baseweb="popover"] > div,
div[data-baseweb="menu"],
ul[role="listbox"],
[role="listbox"] {
    background: #101a32 !important;
    color: #f8fbff !important;
    border: 1px solid rgba(129, 154, 255, 0.35) !important;
    border-radius: 12px !important;
    box-shadow: 0 22px 48px rgba(0, 0, 0, 0.45) !important;
}

div[data-baseweb="menu"] *,
ul[role="listbox"] *,
[role="listbox"] *,
div[role="option"] *,
li[role="option"] * {
    color: #f8fbff !important;
    opacity: 1 !important;
}

div[role="option"],
li[role="option"],
[role="listbox"] li,
[role="listbox"] div {
    background: #101a32 !important;
    color: #f8fbff !important;
}

div[role="option"]:hover,
li[role="option"]:hover,
div[role="option"][aria-selected="true"],
li[role="option"][aria-selected="true"],
[data-baseweb="menu"] [aria-selected="true"] {
    background: #263a72 !important;
    color: #ffffff !important;
}

div[data-testid="stExpander"] {
    border: 1px solid rgba(111, 130, 177, 0.18) !important;
    border-radius: 14px !important;
    background: linear-gradient(180deg, rgba(18, 27, 50, 0.96), rgba(15, 22, 41, 0.96)) !important;
    overflow: hidden !important;
}

div[data-testid="stExpander"] summary,
div[data-testid="stExpander"] summary:hover,
div[data-testid="stExpander"] summary:focus,
div[data-testid="stExpander"] details[open] > summary {
    background: linear-gradient(180deg, rgba(24, 36, 64, 0.98), rgba(19, 29, 53, 0.98)) !important;
    color: #eef3ff !important;
}

div[data-testid="stExpander"] summary *,
div[data-testid="stExpander"] summary svg {
    color: #eef3ff !important;
    fill: #eef3ff !important;
    opacity: 1 !important;
}

section[data-testid="stFileUploaderDropzone"] {
    border-radius: 14px;
    border: 1px dashed rgba(111, 130, 177, 0.32);
    background: linear-gradient(180deg, rgba(22, 31, 54, 0.92), rgba(17, 24, 44, 0.92));
}

section[data-testid="stFileUploaderDropzone"] *,
[data-testid="stFileUploaderFile"] * {
    color: #dce4f7 !important;
}

[data-testid="stFileUploaderFile"] button,
[data-testid="stFileUploaderFile"] button:hover,
[data-testid="stFileUploaderFile"] svg {
    color: #eef3ff !important;
    fill: #eef3ff !important;
}

section[data-testid="stFileUploaderDropzone"] button,
section[data-testid="stFileUploaderDropzone"] button:hover,
section[data-testid="stFileUploaderDropzone"] [data-testid="stBaseButton-secondary"],
section[data-testid="stFileUploaderDropzone"] [data-testid="stBaseButton-secondary"]:hover {
    background: linear-gradient(180deg, #20345f 0%, #1a2c52 100%) !important;
    border: 1px solid rgba(79, 115, 255, 0.42) !important;
    color: #eef3ff !important;
}

.stButton > button,
div[data-testid="stButton"] button,
div[data-testid="stFormSubmitButton"] button,
div[data-testid="stDownloadButton"] button {
    min-height: 48px;
    border: none !important;
    border-radius: 12px !important;
    background: linear-gradient(90deg, #2f5cf6 0%, #7d4dff 100%) !important;
    color: white !important;
    -webkit-text-fill-color: white !important;
    font-weight: 700 !important;
}

.stButton > button:hover,
.stButton > button:focus,
.stButton > button:active,
div[data-testid="stButton"] button:hover,
div[data-testid="stButton"] button:focus,
div[data-testid="stButton"] button:active,
div[data-testid="stFormSubmitButton"] button:hover,
div[data-testid="stFormSubmitButton"] button:focus,
div[data-testid="stFormSubmitButton"] button:active,
div[data-testid="stDownloadButton"] button:hover,
div[data-testid="stDownloadButton"] button:focus,
div[data-testid="stDownloadButton"] button:active {
    background: linear-gradient(90deg, #2f5cf6 0%, #7d4dff 100%) !important;
    color: #ffffff !important;
    -webkit-text-fill-color: #ffffff !important;
    border: none !important;
    box-shadow: none !important;
    opacity: 1 !important;
}

.stButton > button *,
div[data-testid="stButton"] button *,
div[data-testid="stFormSubmitButton"] button *,
div[data-testid="stDownloadButton"] button *,
.stButton > button:hover *,
div[data-testid="stButton"] button:hover *,
div[data-testid="stFormSubmitButton"] button:hover *,
div[data-testid="stDownloadButton"] button:hover * {
    color: #ffffff !important;
    fill: #ffffff !important;
    -webkit-text-fill-color: #ffffff !important;
    opacity: 1 !important;
}

.stButton > button:disabled,
div[data-testid="stButton"] button:disabled,
div[data-testid="stFormSubmitButton"] button:disabled,
div[data-testid="stFormSubmitButton"] button[disabled],
div[data-testid="stFormSubmitButton"] button[aria-disabled="true"],
div[data-testid="stDownloadButton"] button:disabled {
    background: linear-gradient(90deg, #263452 0%, #2f3657 100%) !important;
    color: #dce4f7 !important;
    -webkit-text-fill-color: #dce4f7 !important;
    border: 1px solid rgba(111, 130, 177, 0.35) !important;
    box-shadow: none !important;
    opacity: 1 !important;
}

.stButton > button:disabled *,
div[data-testid="stButton"] button:disabled *,
div[data-testid="stFormSubmitButton"] button:disabled *,
div[data-testid="stFormSubmitButton"] button[disabled] *,
div[data-testid="stFormSubmitButton"] button[aria-disabled="true"] *,
div[data-testid="stDownloadButton"] button:disabled * {
    color: #dce4f7 !important;
    fill: #dce4f7 !important;
    -webkit-text-fill-color: #dce4f7 !important;
    opacity: 1 !important;
}

div[data-testid="stFormSubmitButton"] button p,
div[data-testid="stFormSubmitButton"] button span,
div[data-testid="stFormSubmitButton"] button div {
    color: inherit !important;
    -webkit-text-fill-color: inherit !important;
    opacity: 1 !important;
}

div[data-testid="stDownloadButton"],
div[data-testid="stDownloadButton"] > div {
    background: transparent !important;
}

div[data-testid="stAlert"] {
    background: rgba(18, 27, 50, 0.96) !important;
    border: 1px solid rgba(111, 130, 177, 0.22) !important;
    color: #eef3ff !important;
    border-radius: 12px !important;
}

div[data-testid="stAlert"] * {
    color: #eef3ff !important;
}

div[data-testid="stLinkButton"] a,
div[data-testid="stLinkButton"] a:hover,
div[data-testid="stLinkButton"] a:focus,
div[data-testid="stLinkButton"] a:visited {
    min-height: 48px !important;
    border: none !important;
    border-radius: 12px !important;
    background: linear-gradient(90deg, #16a34a 0%, #2563eb 100%) !important;
    color: #ffffff !important;
    font-weight: 800 !important;
    text-decoration: none !important;
    box-shadow: 0 14px 28px rgba(3, 8, 20, 0.25) !important;
}

div[data-testid="stLinkButton"] a *,
div[data-testid="stLinkButton"] a:hover * {
    color: #ffffff !important;
    opacity: 1 !important;
}

button[data-baseweb="tab"] {
    background: transparent !important;
    color: var(--text-soft) !important;
    font-weight: 650 !important;
}

button[data-baseweb="tab"][aria-selected="true"] {
    color: #8ea2ff !important;
}

div[data-baseweb="tab-highlight"] {
    background: linear-gradient(90deg, #3b82f6, #7d4dff) !important;
}

@media (max-width: 900px) {
    .hero-title {
        font-size: 2rem;
    }
    .suggestion-item,
    .suggestion-item:visited {
        grid-template-columns: 1fr;
        gap: 0.28rem;
    }
    .main .block-container {
        padding-left: 1rem;
        padding-right: 1rem;
    }
    section[data-testid="stSidebar"] {
        width: 100% !important;
        min-width: 100% !important;
    }
}
</style>
""",
    unsafe_allow_html=True,
)

st.markdown(
    """
<div class="hero-shell">
    <h1 class="hero-title">Automatic Document Management System</h1>
    <div class="hero-subtitle">Multi-document extraction, routing, email delivery and reporting.</div>
</div>
""",
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown(
        """
    <div class="brand-card">
        <div class="brand-icon">A</div>
        <div class="brand-copy">
            <h1>ADMS</h1>
            <p>AI Powered</p>
        </div>
    </div>
    """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="sidebar-label">Processing Settings</div>', unsafe_allow_html=True)
    target_format = st.selectbox(
        "Target Format",
        ["Word Document", "PDF", "Excel", "Image"],
        help="Only files matching the selected format will be accepted.",
    )
    allowed_file_types = FORMAT_FILE_TYPES[target_format]

    selected_actions = st.multiselect(
        "Actions",
        ["Route to Local Folder", "Send via Email"],
        default=["Route to Local Folder"],
    )

    st.markdown('<div class="sidebar-label">Upload Documents</div>', unsafe_allow_html=True)
    uploaded_files = st.file_uploader(
        f"Upload {target_format}",
        type=allowed_file_types,
        accept_multiple_files=True,
        help=f"Allowed file type(s): {', '.join(ext.upper() for ext in allowed_file_types)}.",
    )

    email_settings = {
        "sender_email": "",
        "password": "",
        "manual_emails": [],
        "manual_invalid": [],
        "receiver_rows": [],
        "receiver_invalid_rows": [],
        "unmatched_fallback": "Skip unmatched document",
    }
    receiver_file = None
    manual_receiver_text = ""

    if "Send via Email" in selected_actions:
        st.markdown('<div class="sidebar-label">Email Delivery</div>', unsafe_allow_html=True)
        sender_default = (
            os.getenv("ADMS_EMAIL_FROM")
            or os.getenv("ADMS_EMAIL_SENDER")
            or os.getenv("ADMS_SMTP_USER")
            or _streamlit_secret("ADMS_EMAIL_FROM")
            or _streamlit_secret("email", "sender")
        )
        password_default = (
            os.getenv("ADMS_EMAIL_PASSWORD")
            or os.getenv("ADMS_SMTP_PASSWORD")
            or _streamlit_secret("ADMS_EMAIL_PASSWORD")
            or _streamlit_secret("email", "password")
        )

        email_settings["sender_email"] = st.text_input(
            "Sender Email",
            value=sender_default,
            placeholder="sender@gmail.com",
        ).strip()
        email_settings["password"] = st.text_input(
            "Sender Gmail App Password",
            value=password_default,
            type="password",
            placeholder="Enter Gmail app password",
        )
        manual_receiver_text = st.text_area(
            "Manual Receiver Emails",
            value=os.getenv("ADMS_EMAIL_TO", ""),
            placeholder="pooja1@gmail.com, pooja2@gmail.com\npooja3@gmail.com",
            help="Separate emails using comma or new line. Emails are sent one by one for recipient privacy.",
        )
        receiver_file = st.file_uploader(
            "Upload Receiver List",
            type=["xlsx", "xls", "csv"],
            help="Optional Excel/CSV list. Email column is required; Name is optional.",
            key="receiver_list_upload",
        )
        email_settings["unmatched_fallback"] = st.selectbox(
            "Unmatched Document Fallback",
            ["Skip unmatched document", "Send to manually entered receivers"],
            help="Unmatched documents are not emailed unless you explicitly choose the manual fallback.",
        )

    process_btn = st.button("Start Extraction", type="primary", use_container_width=True)


manual_valid_emails, manual_invalid_emails = parse_manual_emails(manual_receiver_text)
receiver_result = load_receiver_list(receiver_file) if receiver_file else load_receiver_list(None)
combined_receiver_emails = merge_and_deduplicate_emails(manual_valid_emails, receiver_result["valid_emails"])
invalid_receiver_rows = build_invalid_receiver_rows(manual_invalid_emails, receiver_result["invalid_rows"])

if "Send via Email" in selected_actions:
    email_settings["manual_emails"] = manual_valid_emails
    email_settings["manual_invalid"] = manual_invalid_emails
    email_settings["receiver_rows"] = receiver_result["valid_rows"]
    email_settings["receiver_invalid_rows"] = receiver_result["invalid_rows"]
    email_settings["all_recipients"] = combined_receiver_emails
    email_settings["invalid_rows"] = invalid_receiver_rows

if "Send via Email" in selected_actions:
    with st.expander("Receiver List Preview", expanded=bool(receiver_file or manual_receiver_text)):
        if receiver_result["error"]:
            st.error(receiver_result["error"])

        metric_html = f"""
        <div class="metric-grid">
            <div class="metric-card"><span>Total Valid Receivers</span><strong>{len(combined_receiver_emails)}</strong></div>
            <div class="metric-card"><span>Manual Valid</span><strong>{len(manual_valid_emails)}</strong></div>
            <div class="metric-card"><span>List Valid</span><strong>{len(receiver_result['valid_emails'])}</strong></div>
        </div>
        """
        st.markdown(metric_html, unsafe_allow_html=True)

        if not receiver_result["dataframe"].empty:
            st.markdown(_render_dark_dataframe(receiver_result["dataframe"]), unsafe_allow_html=True)

        if invalid_receiver_rows:
            st.warning("Invalid receiver emails were found and will be ignored.")
            st.markdown(
                _render_dark_table(
                    [[row["Source"], row["Email"], row["Reason"]] for row in invalid_receiver_rows],
                    ["Source", "Email", "Reason"],
                ),
                unsafe_allow_html=True,
            )


if process_btn:
    if not uploaded_files:
        st.warning("Please upload at least one document first.")
    else:
        if "Send via Email" in selected_actions and not combined_receiver_emails:
            st.warning("Please enter receiver email manually or upload a receiver list file.")

        processed_documents = []
        progress_bar = st.progress(0)
        status_placeholder = st.empty()

        for index, uploaded_file in enumerate(uploaded_files, start=1):
            status_placeholder.info(f"Processing {index} of {len(uploaded_files)}: {uploaded_file.name}")
            document = _process_uploaded_document(
                uploaded_file,
                index,
                route_to_local_folder="Route to Local Folder" in selected_actions,
            )
            if "Send via Email" in selected_actions and document.get("processing_status") == "Processed":
                recipients, recipient_source = resolve_document_recipients(
                    document,
                    email_settings.get("receiver_rows", []),
                    email_settings.get("manual_emails", []),
                    email_settings.get("unmatched_fallback", "Skip unmatched document"),
                    email_settings.get("all_recipients", []),
                )
                document["receiver_emails"] = recipients
                document["receiver_source"] = recipient_source
                document["email_status"] = "Pending Review" if recipients else "Email Skipped"
                document["email_error"] = "" if recipients else recipient_source
            else:
                document = _apply_delivery_actions(document, selected_actions, email_settings)
            document["database_id"] = save_to_database(document)
            processed_documents.append(document)
            progress_bar.progress(index / len(uploaded_files))

        success_count = sum(1 for doc in processed_documents if doc.get("processing_status") == "Processed")
        failed_count = len(processed_documents) - success_count
        status_placeholder.success(f"{success_count} document(s) processed successfully, {failed_count} failed.")

        st.session_state[PROCESSED_DOCS_KEY] = processed_documents
        st.session_state[LAST_ACTION_KEY] = selected_actions
        st.session_state[PENDING_EMAIL_SETTINGS_KEY] = email_settings
        st.session_state[RECEIVER_SUMMARY_KEY] = {
            "total_valid_receivers": len(combined_receiver_emails),
            "total_recipients_found": len(combined_receiver_emails) + len(invalid_receiver_rows),
            "manual_invalid": manual_invalid_emails,
            "receiver_invalid": receiver_result["invalid_rows"],
            "invalid_rows": invalid_receiver_rows,
        }


processed_documents = st.session_state.get(PROCESSED_DOCS_KEY, [])
active_actions = st.session_state.get(LAST_ACTION_KEY, selected_actions)

dashboard_tab, history_tab = st.tabs(["Dashboard", "Search History"])

with dashboard_tab:
    if processed_documents:
        total_docs = len(processed_documents)
        successful_docs = sum(1 for doc in processed_documents if doc.get("processing_status") == "Processed")
        failed_docs = total_docs - successful_docs
        emails_sent = sum(int(doc.get("email_sent_count", 0) or 0) for doc in processed_documents)
        receiver_summary = st.session_state.get(RECEIVER_SUMMARY_KEY, {})
        delivery_report_df = generate_delivery_report(
            processed_documents,
            receiver_summary.get("invalid_rows", []),
        )
        valid_recipient_count = int(receiver_summary.get("total_valid_receivers", 0) or 0)
        total_recipients_found = int(
            receiver_summary.get("total_recipients_found", valid_recipient_count) or 0
        )
        invalid_skipped_count = int((delivery_report_df["Status"] == "Invalid email skipped").sum()) if not delivery_report_df.empty else 0
        failed_email_count = int((delivery_report_df["Status"] == "Failed").sum()) if not delivery_report_df.empty else 0
        pending_skipped_count = int((delivery_report_df["Status"] == "Skipped").sum()) if not delivery_report_df.empty else 0

        st.markdown(
            f"""
            <div class="metric-grid">
                <div class="metric-card"><span>Total Uploaded Documents</span><strong>{total_docs}</strong></div>
                <div class="metric-card"><span>Successfully Processed</span><strong>{successful_docs}</strong></div>
                <div class="metric-card"><span>Failed Documents</span><strong>{failed_docs}</strong></div>
                <div class="metric-card"><span>Emails Sent</span><strong>{emails_sent}</strong></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.success(f"{successful_docs} document(s) processed successfully, {failed_docs} failed.")
        if "Send via Email" in active_actions and emails_sent:
            st.success(f"Email sent successfully for {emails_sent} recipient delivery attempt(s).")
        if "Send via Email" in active_actions:
            pending_review_count = sum(1 for doc in processed_documents if doc.get("email_status") == "Pending Review")
            if pending_review_count:
                st.info(f"{pending_review_count} document(s) are waiting for review before email sending.")

        if "Send via Email" in active_actions:
            st.markdown('<div class="panel-title">Email Delivery Report</div>', unsafe_allow_html=True)
            st.markdown(
                f"""
                <div class="metric-grid">
                    <div class="metric-card"><span>Total Recipients Found</span><strong>{total_recipients_found}</strong></div>
                    <div class="metric-card"><span>Valid Recipients</span><strong>{valid_recipient_count}</strong></div>
                    <div class="metric-card"><span>Invalid Emails Skipped</span><strong>{invalid_skipped_count}</strong></div>
                    <div class="metric-card"><span>Successfully Sent</span><strong>{emails_sent}</strong></div>
                    <div class="metric-card"><span>Failed</span><strong>{failed_email_count}</strong></div>
                    <div class="metric-card"><span>Pending/Skipped</span><strong>{pending_skipped_count}</strong></div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if not delivery_report_df.empty:
                st.markdown(_render_dark_dataframe(delivery_report_df), unsafe_allow_html=True)
                st.download_button(
                    "Download Delivery Report CSV",
                    data=delivery_report_df.to_csv(index=False).encode("utf-8"),
                    file_name="adms_email_delivery_report.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
            else:
                st.info("No email delivery records to show.")

        st.markdown('<div class="panel-title">Processed Documents</div>', unsafe_allow_html=True)
        for index, document in enumerate(processed_documents, start=1):
            file_name = html.escape(document.get("file_name", "Document"))
            doc_type = html.escape(document.get("display_doc_type", "General Document"))
            confidence = document.get("confidence_score", 0)
            extracted_name = html.escape(document.get("extracted_name", "Not Found"))
            short_summary = html.escape(document.get("short_summary", ""))
            email_status = document.get("email_status", "Not Requested")
            processing_status = document.get("processing_status", "Failed")

            st.markdown(
                f"""
                <div class="document-card">
                    <h3>{index}. {file_name}</h3>
                    <div class="doc-meta">
                        <span class="doc-type-badge">{doc_type}</span>
                        <span>Confidence: <b>{confidence}%</b></span>
                        <span>Extracted Name: <b>{extracted_name}</b></span>
                        {_status_badge(processing_status)}
                        {_status_badge(email_status)}
                    </div>
                    <div style="margin-top:0.75rem;color:#cfd9f8;">{short_summary}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            with st.expander(f"Open details for {document.get('file_name', 'Document')}", expanded=total_docs == 1):
                review_tab, detail_tab, short_tab, detailed_tab, fields_tab, action_tab, raw_tab, routing_tab = st.tabs(
                    [
                        "Review/Edit",
                        "Extracted Details",
                        "Short Summary",
                        "Detailed Summary",
                        "Important Fields",
                        "Action Required",
                        "Raw Text",
                        "Routing",
                    ]
                )

                with review_tab:
                    defaults = _review_defaults(document)
                    language_info = document.get("language_info", {}) or {}
                    if document.get("low_confidence"):
                        st.warning("Low confidence OCR/name detection. Please verify before sending.")
                    if language_info.get("translation_warning"):
                        st.warning(language_info.get("translation_warning"))
                    st.caption(
                        "Detected language: "
                        + str(language_info.get("detected_language", "unknown"))
                        + f" | Name confidence: {document.get('name_confidence', 0)}%"
                        + f" | Summary confidence: {document.get('summary_confidence', 0)}%"
                    )

                    with st.form(f"review_form_{document.get('doc_key', index)}"):
                        r1, r2 = st.columns(2)
                        with r1:
                            review_doc_type = st.text_input(
                                "Detected Document Type",
                                value=defaults["document_type"],
                                key=f"review_type_{document.get('doc_key', index)}",
                            )
                            review_name = st.text_input(
                                "Detected Name",
                                value=defaults["name"],
                                key=f"review_name_{document.get('doc_key', index)}",
                            )
                            review_first_name = st.text_input(
                                "First Name",
                                value=defaults["first_name"],
                                key=f"review_first_{document.get('doc_key', index)}",
                            )
                            review_middle_name = st.text_input(
                                "Middle Name",
                                value=defaults["middle_name"],
                                key=f"review_middle_{document.get('doc_key', index)}",
                            )
                            review_last_name = st.text_input(
                                "Last Name",
                                value=defaults["last_name"],
                                key=f"review_last_{document.get('doc_key', index)}",
                            )
                        with r2:
                            review_identifier = st.text_input(
                                "ID/Enrollment/Policy/Invoice number",
                                value=defaults["identifier"],
                                key=f"review_id_{document.get('doc_key', index)}",
                            )
                            review_department = st.text_input(
                                "Department/Field",
                                value=defaults["department"],
                                key=f"review_department_{document.get('doc_key', index)}",
                            )
                            review_email = st.text_input(
                                "Email",
                                value=defaults["email"],
                                key=f"review_email_{document.get('doc_key', index)}",
                            )
                            review_phone = st.text_input(
                                "Phone",
                                value=defaults["phone"],
                                key=f"review_phone_{document.get('doc_key', index)}",
                            )

                        review_summary = st.text_area(
                            "Generated English Short Summary",
                            value=defaults["summary"],
                            height=140,
                            key=f"review_summary_{document.get('doc_key', index)}",
                        )

                        apply_clicked = st.form_submit_button("Apply Review Updates", use_container_width=True)
                        send_clicked = False
                        if "Send via Email" in active_actions:
                            send_clicked = st.form_submit_button(
                                "Apply & Send Reviewed Email",
                                use_container_width=True,
                                disabled=document.get("email_status") == "Email Sent",
                            )

                    if apply_clicked or send_clicked:
                        review_values = {
                            "document_type": review_doc_type,
                            "name": review_name,
                            "first_name": review_first_name,
                            "middle_name": review_middle_name,
                            "last_name": review_last_name,
                            "identifier": review_identifier,
                            "department": review_department,
                            "email": review_email,
                            "phone": review_phone,
                            "summary": review_summary,
                        }
                        document = apply_review_updates(document, review_values)

                        if send_clicked:
                            pending_email_settings = st.session_state.get(PENDING_EMAIL_SETTINGS_KEY, email_settings)
                            document = _apply_delivery_actions(document, ["Send via Email"], pending_email_settings)
                            if document.get("email_status") == "Email Sent":
                                st.success("Reviewed email sent successfully.")
                            elif document.get("email_status") == "Email Partial":
                                st.warning("Reviewed email sent to some recipients. Check the delivery report.")
                            else:
                                st.warning(document.get("email_error") or "Email was not sent.")
                        else:
                            st.success("Review updates applied.")

                        processed_documents[index - 1] = document
                        st.session_state[PROCESSED_DOCS_KEY] = processed_documents
                        update_database_document(document)

                with detail_tab:
                    if document.get("processing_status") == "Failed":
                        st.error(document.get("error_message", "Document processing failed."))
                    details = document.get("details", {})
                    rows = [
                        ["File Name", document.get("file_name", "")],
                        ["Document Type", document.get("display_doc_type", "General Document")],
                        ["Confidence Score", f"{document.get('confidence_score', 0)}%"],
                        ["Extracted Name", document.get("extracted_name", "Not Found")],
                        ["First Name", _display_value(details.get("First Name"))],
                        ["Middle Name", _display_value(details.get("Middle Name") or details.get("Father's Name"))],
                        ["Last Name", _display_value(details.get("Last Name") or details.get("Surname"))],
                        ["Email", _display_value(details.get("Email"))],
                        ["Phone", _display_value(details.get("Phone"))],
                        ["ID", _display_value(details.get("ID"))],
                    ]
                    st.markdown(_render_dark_table(rows, ["Field", "Value"]), unsafe_allow_html=True)

                with short_tab:
                    st.markdown(
                        f'<div class="summary-box">{html.escape(document.get("short_summary", "Not Found"))}</div>',
                        unsafe_allow_html=True,
                    )

                with detailed_tab:
                    st.markdown(
                        f'<div class="summary-box">{html.escape(document.get("detailed_summary", "Not Found"))}</div>',
                        unsafe_allow_html=True,
                    )

                with fields_tab:
                    field_rows = [[key, value] for key, value in document.get("important_fields", {}).items()]
                    st.markdown(_render_dark_table(field_rows, ["Important Field", "Value"]), unsafe_allow_html=True)

                with action_tab:
                    st.markdown(
                        f'<div class="summary-box">{html.escape(document.get("action_required", "Review required."))}</div>',
                        unsafe_allow_html=True,
                    )

                with raw_tab:
                    raw_text = document.get("display_raw_text") or document.get("raw_text") or "No raw text available."
                    st.markdown(
                        f'<div class="summary-box text-box">{html.escape(raw_text)}</div>',
                        unsafe_allow_html=True,
                    )

                with routing_tab:
                    routing_rows = [
                        ["Selected Actions", ", ".join(active_actions) if active_actions else "None"],
                        ["Category Folder", document.get("category_folder", "Not Found")],
                        ["Category File", document.get("category_file_path", "Not Found")],
                        ["Legacy Local Folder", document.get("legacy_folder", "Not Requested") or "Not Requested"],
                        ["Receiver Emails", ", ".join(document.get("receiver_emails", [])) or "No receiver selected."],
                        ["Receiver Source", document.get("receiver_source", "Not Requested")],
                        ["Email Status", document.get("email_status", "Not Requested")],
                        ["Email Error", document.get("email_error", "") or "None"],
                    ]
                    st.markdown(_render_dark_table(routing_rows, ["Field", "Value"]), unsafe_allow_html=True)

        download_data, download_name, download_mime = prepare_uploaded_documents_download(processed_documents)
        st.markdown(
            '<div class="section-panel"><div class="panel-title">Download Uploaded Document</div>',
            unsafe_allow_html=True,
        )
        st.download_button(
            "Download",
            data=download_data,
            file_name=download_name,
            mime=download_mime,
            use_container_width=True,
            disabled=not bool(download_data),
        )
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.markdown(
            """
            <div class="empty-state" style="padding:1.25rem 1.4rem;">
                <div class="panel-title" style="margin-top:0;">Ready to Process</div>
                <div style="color: var(--text-soft); line-height:1.8;">
                    Upload one or more supported documents, choose routing and delivery actions, then start extraction.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

with history_tab:
    st.markdown('<div class="section-panel"><div class="panel-title">Search Processed Document Records</div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns([2, 1, 1])
    with c2:
        doc_type_filter = st.selectbox("Document Type", ["All", *DOCUMENT_KEYWORDS.keys(), "General Document"])
    with c3:
        email_filter = st.selectbox("Email Status", ["All", "Pending Review", "Email Sent", "Email Partial", "Email Failed", "Email Skipped", "Not Requested", "Not Sent"])

    query_search_value = str(st.query_params.get(HISTORY_SEARCH_PARAM_KEY, "") or "").strip()
    if query_search_value and st.session_state.get("_last_history_query_param") != query_search_value:
        st.session_state[HISTORY_SEARCH_KEY] = query_search_value
        st.session_state["_last_history_query_param"] = query_search_value

    base_history_df = search_database("", doc_type_filter, email_filter)

    with c1:
        search_text = st.text_input(
            "Search by file name, extracted name, document type or email status",
            key=HISTORY_SEARCH_KEY,
        )
        suggestions = _history_suggestions(base_history_df, search_text, limit=10)
        if str(search_text or "").strip():
            if suggestions:
                st.markdown(
                    _render_history_suggestions(suggestions, HISTORY_SEARCH_PARAM_KEY),
                    unsafe_allow_html=True,
                )
            else:
                st.markdown('<div class="no-suggestions">No matching documents found</div>', unsafe_allow_html=True)

    history_df = _filter_history_records(base_history_df, search_text)
    if history_df.empty:
        st.info("No matching records found.")
    else:
        visible_columns = [
            "id",
            "file_name",
            "document_type",
            "confidence_score",
            "extracted_name",
            "short_summary",
            "receiver_emails",
            "email_status",
            "processing_status",
            "error_message",
            "created_at",
        ]
        visible_columns = [column for column in visible_columns if column in history_df.columns]
        st.markdown(_render_dark_dataframe(history_df, visible_columns), unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)
