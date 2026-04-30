import html
import os
import re

import streamlit as st

from modules.extractor import extract_text_from_file
from modules.nlp_parser import smart_merge, smart_parse
from modules.ocr import format_extracted_text_for_display, prepare_display_details
from modules.router import save_uploaded_bytes, send_processed_documents_email
from modules.summarizer import summarize_document


OUTPUT_ROOT = r"D:\Pooja\project\AI_DMS\output"
PROCESSED_DOCS_KEY = "processed_documents"
EMAIL_STATUS_KEY = "email_status"
SAVED_DOCS_KEY = "saved_documents"
LAST_ACTION_KEY = "last_action"


def _clean_value(value):
    text = str(value or "").strip()
    return "" if not text or text == "Not Found" else text


def _display_value(value, default="Not Found"):
    cleaned = _clean_value(value)
    return cleaned or default


def _safe_doc_key(file_name, index):
    base = re.sub(r"[^A-Za-z0-9]+", "_", str(file_name or "")).strip("_").lower()
    return f"{index}_{base or 'document'}"


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


def _process_uploaded_document(uploaded_file, index):
    if hasattr(uploaded_file, "seek"):
        uploaded_file.seek(0)
    file_bytes = uploaded_file.getvalue()

    raw_text = extract_text_from_file(uploaded_file)
    doc_det = smart_parse(raw_text)
    details = smart_merge(doc_det, {})

    summary_source = details.get("_translated") or raw_text
    doc_summary = summarize_document(summary_source)
    details, display_doc_type, doc_summary = prepare_display_details(
        details,
        raw_text,
        doc_summary,
    )
    display_raw_text = format_extracted_text_for_display(raw_text, details)

    return {
        "doc_key": _safe_doc_key(uploaded_file.name, index),
        "file_name": uploaded_file.name,
        "file_bytes": file_bytes,
        "raw_text": raw_text,
        "display_raw_text": display_raw_text,
        "doc_det": doc_det,
        "details": details,
        "doc_summary": doc_summary,
        "display_doc_type": display_doc_type,
    }


def _build_email_payload(document):
    details = document["details"]
    return {
        "file_name": document["file_name"],
        "file_bytes": document["file_bytes"],
        "full_name": _build_full_name(details),
        "first_name": _display_value(details.get("First Name")),
        "middle_name": _display_value(details.get("Middle Name") or details.get("Father's Name")),
        "last_name": _display_value(details.get("Last Name") or details.get("Surname")),
        "document_type": document["display_doc_type"],
        "date": _display_value(details.get("Date")),
        "email": _display_value(details.get("Email")),
        "phone": _display_value(details.get("Phone")),
        "summary": document["doc_summary"],
        "raw_text": document["raw_text"],
    }


def _render_saved_card(saved_doc):
    return f"""
    <div class="saved-card">
        <b>Saved to:</b> <code>{html.escape(saved_doc['folder'])}</code><br><br>
        <b>Name:</b> {html.escape(saved_doc['first_name'])} {html.escape(saved_doc['middle_name'])} {html.escape(saved_doc['last_name'])} &nbsp;|&nbsp;
        <b>Email:</b> {html.escape(saved_doc['email'])} &nbsp;|&nbsp;
        <b>{html.escape(saved_doc['id_type'])}:</b> {html.escape(saved_doc['id_value'])}
    </div>
    """


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
            <thead>
                <tr>{header_html}</tr>
            </thead>
            <tbody>
                {''.join(body_rows)}
            </tbody>
        </table>
    </div>
    """


st.set_page_config(page_title="AI-DMS Pro", page_icon="A", layout="wide")

st.markdown(
    """
<style>
:root {
    --bg-main: #060b18;
    --bg-panel: #0f1730;
    --bg-panel-2: #182340;
    --bg-panel-3: #131d35;
    --text-main: #f7f8fc;
    --text-soft: #a7b2cf;
    --text-muted: #7d88a9;
}

html, body, [class*="css"] {
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 17px;
}

html,
body {
    background: #070d1c !important;
}

.stApp {
    background:
        radial-gradient(circle at top right, rgba(80, 115, 255, 0.14), transparent 24%),
        radial-gradient(circle at top left, rgba(125, 77, 255, 0.10), transparent 28%),
        linear-gradient(180deg, #050914 0%, #070d1c 100%);
    color: var(--text-main);
}

[data-testid="stAppViewContainer"] {
    background: transparent;
}

[data-testid="stMain"],
section.main {
    background: transparent !important;
}

header,
[data-testid="stHeader"],
.stAppHeader {
    background: linear-gradient(180deg, #050914 0%, #070d1c 100%) !important;
}

[data-testid="stHeader"] {
    border-bottom: 1px solid rgba(111, 130, 177, 0.08) !important;
}

[data-testid="stHeader"] > div,
[data-testid="stToolbar"],
[data-testid="stDecoration"] {
    background: transparent !important;
}

.main .block-container {
    max-width: 1500px;
    padding-top: 2rem;
    padding-bottom: 2rem;
    padding-left: 2rem;
    padding-right: 2rem;
}

section[data-testid="stSidebar"] {
    width: 320px !important;
    min-width: 320px !important;
    border-right: 1px solid rgba(122, 138, 184, 0.14);
    background: linear-gradient(180deg, #10182e 0%, #0c1324 100%);
}

section[data-testid="stSidebar"] > div {
    background: linear-gradient(180deg, #10182e 0%, #0c1324 100%);
}

section[data-testid="stSidebar"] .block-container {
    padding-top: 1.4rem;
    padding-left: 1.2rem;
    padding-right: 1.2rem;
    padding-bottom: 1rem;
}

.brand-card {
    display: flex;
    align-items: center;
    gap: 14px;
    padding: 0.5rem 0 1.1rem 0;
    margin-bottom: 1rem;
    border-bottom: 1px solid rgba(123, 137, 176, 0.15);
}

.brand-icon {
    width: 48px;
    height: 48px;
    border-radius: 16px;
    background: linear-gradient(145deg, #4973ff, #8c42ff);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.3rem;
    font-weight: 800;
    color: white;
    box-shadow: 0 12px 28px rgba(69, 93, 214, 0.35);
}

.brand-copy h1 {
    margin: 0;
    font-size: 2rem;
    line-height: 1;
    font-weight: 800;
    color: #f8f9ff;
}

.brand-copy p {
    margin: 0.3rem 0 0 0;
    color: var(--text-soft);
    font-size: 1.04rem;
    font-weight: 500;
}

.sidebar-label {
    margin-top: 1.2rem;
    margin-bottom: 0.65rem;
    font-size: 0.92rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--text-muted);
    font-weight: 700;
}

.sidebar-footer {
    margin-top: 1.5rem;
    padding-top: 1rem;
    border-top: 1px solid rgba(123, 137, 176, 0.15);
    color: var(--text-muted);
    font-size: 1rem;
    line-height: 1.7;
}

.hero-shell {
    background: linear-gradient(180deg, rgba(11, 17, 35, 0.96), rgba(8, 13, 28, 0.96));
    border: 1px solid rgba(111, 130, 177, 0.16);
    border-radius: 24px;
    padding: 2rem 2.1rem;
    box-shadow: 0 24px 60px rgba(3, 8, 20, 0.42);
    margin-bottom: 1.35rem;
}

.hero-title {
    margin: 0;
    font-size: 3rem;
    line-height: 1.05;
    font-weight: 800;
    color: var(--text-main);
    letter-spacing: -0.03em;
}

.hero-subtitle {
    margin-top: 0.75rem;
    font-size: 1.24rem;
    color: var(--text-soft);
}

.status-banner {
    display: flex;
    align-items: center;
    gap: 1rem;
    background: linear-gradient(180deg, rgba(12, 44, 39, 0.92), rgba(11, 39, 34, 0.92));
    border: 1px solid rgba(41, 212, 138, 0.4);
    border-radius: 18px;
    padding: 1.05rem 1.15rem;
    margin: 0 0 1.35rem 0;
    box-shadow: 0 18px 40px rgba(8, 17, 27, 0.28);
}

.status-icon {
    width: 44px;
    height: 44px;
    border-radius: 50%;
    background: linear-gradient(180deg, #34d399, #22c55e);
    color: white;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1rem;
    font-weight: 800;
    flex: 0 0 44px;
}

.status-copy strong {
    display: block;
    color: #dcfff0;
    font-size: 1.25rem;
    margin-bottom: 0.15rem;
}

.status-copy span {
    color: #98f0c7;
    font-size: 1.08rem;
}

.doc-chip {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    border-radius: 16px;
    padding: 0.9rem 1.15rem;
    margin-bottom: 1rem;
    border: 1px solid rgba(82, 114, 255, 0.2);
    background: linear-gradient(135deg, rgba(60, 90, 255, 0.30), rgba(125, 77, 255, 0.24));
    color: #dbe4ff;
    font-size: 1.14rem;
    font-weight: 700;
}

.doc-chip span {
    color: white;
}

.panel-title {
    margin: 0.5rem 0 0.8rem 0;
    font-size: 1.28rem;
    color: var(--text-main);
    font-weight: 800;
}

div[data-testid="stForm"] {
    background: linear-gradient(180deg, rgba(18, 27, 50, 0.96), rgba(15, 22, 41, 0.96));
    border: 1px solid rgba(111, 130, 177, 0.2);
    border-radius: 20px;
    padding: 1.8rem 1.65rem 1.4rem;
    box-shadow: 0 24px 50px rgba(3, 8, 20, 0.26);
}

div[data-testid="stExpander"] {
    border: 1px solid rgba(111, 130, 177, 0.18) !important;
    border-radius: 16px !important;
    background: linear-gradient(180deg, rgba(18, 27, 50, 0.96), rgba(15, 22, 41, 0.96)) !important;
    overflow: hidden !important;
    margin-bottom: 1rem !important;
}

div[data-testid="stExpander"] summary,
div[data-testid="stExpander"] summary:hover,
div[data-testid="stExpander"] summary:focus,
div[data-testid="stExpander"] details[open] > summary {
    background: linear-gradient(180deg, rgba(24, 36, 64, 0.98), rgba(19, 29, 53, 0.98)) !important;
    color: #eef3ff !important;
}

div[data-testid="stExpander"] summary p,
div[data-testid="stExpander"] summary span,
div[data-testid="stExpander"] summary svg {
    color: #eef3ff !important;
    fill: #eef3ff !important;
}

.stTextInput label,
.stSelectbox label,
.stRadio label,
.stFileUploader label {
    color: #dce4f7 !important;
    font-weight: 600 !important;
    font-size: 1.02rem !important;
}

div[data-baseweb="input"] {
    min-height: 56px;
    border-radius: 14px !important;
    border: 1px solid rgba(111, 130, 177, 0.18) !important;
    background: linear-gradient(180deg, #1b2745 0%, #18233f 100%) !important;
}

div[data-baseweb="input"] > div {
    background: transparent !important;
}

div[data-baseweb="input"] input {
    color: var(--text-main) !important;
    font-size: 1.08rem !important;
}

div[data-baseweb="input"] input::placeholder {
    color: var(--text-muted) !important;
}

/* SELECTBOX VISIBILITY FIX START */
div[data-baseweb="select"] > div {
    min-height: 54px;
    border-radius: 14px !important;
    border: 1px solid rgba(111, 130, 177, 0.32) !important;
    background: linear-gradient(180deg, #1b2745 0%, #17223d 100%) !important;
    color: #ffffff !important;
    font-size: 1.06rem !important;
    font-weight: 700 !important;
    box-shadow: 0 12px 28px rgba(3, 8, 20, 0.18) !important;
}

div[data-baseweb="select"] > div:hover {
    border-color: rgba(129, 154, 255, 0.55) !important;
    background: linear-gradient(180deg, #223158 0%, #1a2748 100%) !important;
}

div[data-baseweb="select"] div,
div[data-baseweb="select"] span,
div[data-baseweb="select"] input {
    color: #ffffff !important;
    opacity: 1 !important;
}

div[data-baseweb="select"] svg {
    fill: #dce4ff !important;
    color: #dce4ff !important;
}

div[data-baseweb="popover"] {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
}

div[data-baseweb="popover"] > div {
    background: #101a32 !important;
    border: 1px solid rgba(129, 154, 255, 0.35) !important;
    border-radius: 16px !important;
    box-shadow: 0 22px 48px rgba(0, 0, 0, 0.45) !important;
    overflow: hidden !important;
}

div[data-baseweb="menu"],
ul[role="listbox"],
[role="listbox"] {
    background: #101a32 !important;
    color: #ffffff !important;
    border-radius: 16px !important;
    padding: 0.35rem !important;
}

div[role="option"],
li[role="option"],
[role="listbox"] li,
[role="listbox"] div {
    background: #101a32 !important;
    color: #f8fbff !important;
    opacity: 1 !important;
}

div[role="option"] *,
li[role="option"] *,
[role="listbox"] li *,
[role="listbox"] div * {
    color: #f8fbff !important;
    opacity: 1 !important;
}

div[role="option"]:hover,
li[role="option"]:hover,
div[role="option"][aria-selected="true"],
li[role="option"][aria-selected="true"] {
    background: #263a72 !important;
    color: #ffffff !important;
}

div[role="option"]:hover *,
li[role="option"]:hover *,
div[role="option"][aria-selected="true"] *,
li[role="option"][aria-selected="true"] * {
    color: #ffffff !important;
}

[data-baseweb="menu"] [aria-selected="true"],
[data-baseweb="menu"] [aria-selected="true"] * {
    background: #2f5cf6 !important;
    color: #ffffff !important;
}
/* SELECTBOX VISIBILITY FIX END */

div[role="radiogroup"] label,
div[role="radiogroup"] label *,
div[role="radiogroup"] [data-testid="stMarkdownContainer"] p {
    color: #eef3ff !important;
    opacity: 1 !important;
}

section[data-testid="stFileUploaderDropzone"] {
    border-radius: 18px;
    border: 1px dashed rgba(111, 130, 177, 0.32);
    background: linear-gradient(180deg, rgba(22, 31, 54, 0.92), rgba(17, 24, 44, 0.92));
    padding: 1.3rem 1rem;
}

section[data-testid="stFileUploaderDropzone"] div,
section[data-testid="stFileUploaderDropzone"] p,
section[data-testid="stFileUploaderDropzone"] span,
section[data-testid="stFileUploaderDropzone"] small {
    color: #d6def6 !important;
    opacity: 1 !important;
}

[data-testid="stFileUploaderDropzoneInstructions"] *,
[data-testid="stFileUploaderDropzone"] [data-testid="stMarkdownContainer"] p {
    color: #dce4f7 !important;
    opacity: 1 !important;
}

[data-testid="stFileUploaderFile"] {
    background: rgba(27, 39, 69, 0.92) !important;
    border: 1px solid rgba(111, 130, 177, 0.18) !important;
    border-radius: 14px !important;
}

[data-testid="stFileUploaderFile"] * {
    color: #dce4f7 !important;
}

section[data-testid="stFileUploaderDropzone"] button,
section[data-testid="stFileUploaderDropzone"] button:hover,
section[data-testid="stFileUploaderDropzone"] button:focus,
section[data-testid="stFileUploaderDropzone"] button:active,
section[data-testid="stFileUploaderDropzone"] [data-testid="stBaseButton-secondary"],
section[data-testid="stFileUploaderDropzone"] [data-testid="stBaseButton-secondary"]:hover,
section[data-testid="stFileUploaderDropzone"] [data-testid="stBaseButton-secondary"]:focus,
section[data-testid="stFileUploaderDropzone"] [data-testid="stBaseButton-secondary"]:active {
    min-height: 46px !important;
    border-radius: 12px !important;
    border: 1px solid rgba(79, 115, 255, 0.42) !important;
    background: linear-gradient(180deg, #20345f 0%, #1a2c52 100%) !important;
    color: #eef3ff !important;
    box-shadow: none !important;
    transform: none !important;
    filter: none !important;
}

.stButton > button,
div[data-testid="stFormSubmitButton"] button {
    min-height: 54px;
    border: none !important;
    border-radius: 14px !important;
    background: linear-gradient(90deg, #2f5cf6 0%, #7d4dff 100%) !important;
    color: white !important;
    font-size: 1.08rem !important;
    font-weight: 700 !important;
    box-shadow: 0 18px 34px rgba(60, 79, 199, 0.34);
}

button[data-baseweb="tab"] {
    background: transparent !important;
    border: none !important;
    color: var(--text-soft) !important;
    font-size: 1.1rem !important;
    font-weight: 600 !important;
}

button[data-baseweb="tab"][aria-selected="true"] {
    color: #7f97ff !important;
}

div[data-baseweb="tab-highlight"] {
    background: linear-gradient(90deg, #3b82f6, #7d4dff) !important;
    height: 3px !important;
}

.summary-box {
    background: linear-gradient(180deg, rgba(17, 25, 46, 0.98), rgba(14, 21, 38, 0.98));
    border: 1px solid rgba(111, 130, 177, 0.2);
    border-left: 4px solid #4f73ff;
    border-radius: 18px;
    padding: 1.3rem 1.5rem;
    font-size: 1.08rem;
    line-height: 1.85;
    color: #eef3ff;
}

.classic-summary-box {
    background: linear-gradient(180deg, #11192e 0%, #0f172a 100%);
    border: 1px solid rgba(111, 130, 177, 0.24);
    border-left: 5px solid #3b82f6;
    border-radius: 14px;
    padding: 1rem 1.2rem;
    color: #eef3ff;
    line-height: 1.8;
    font-size: 1.04rem;
}

.classic-detail-list {
    margin-top: 0.75rem;
}

.classic-detail-row {
    margin-bottom: 0.95rem;
    color: #eef3ff;
    font-size: 1.04rem;
    line-height: 1.7;
}

.classic-detail-row strong {
    color: #ffffff;
}

.routing-card,
.empty-state,
.saved-card {
    background: linear-gradient(180deg, rgba(18, 27, 50, 0.96), rgba(15, 22, 41, 0.96));
    border: 1px solid rgba(111, 130, 177, 0.18);
    border-radius: 20px;
    padding: 1.35rem 1.45rem;
    box-shadow: 0 22px 44px rgba(4, 10, 20, 0.2);
}

.saved-card {
    margin-top: 0.85rem;
}

.saved-card,
.saved-card * {
    color: #eef3ff !important;
}

.saved-card code {
    background: #0b1224 !important;
    color: #b7c7ff !important;
    padding: 0.2rem 0.45rem;
    border-radius: 8px;
}

.routing-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
    gap: 14px;
    margin-top: 0.8rem;
}

.route-pill {
    background: rgba(27, 39, 69, 0.95);
    border: 1px solid rgba(111, 130, 177, 0.16);
    border-radius: 16px;
    padding: 1rem;
}

.route-pill span {
    display: block;
    color: var(--text-muted);
    font-size: 0.78rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    margin-bottom: 0.35rem;
    font-weight: 700;
}

.route-pill strong {
    color: var(--text-main);
    font-size: 1.08rem;
    line-height: 1.5;
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
    border-radius: 18px;
    overflow: hidden;
    background: linear-gradient(180deg, rgba(18, 27, 50, 0.96), rgba(15, 22, 41, 0.96));
}

.data-table {
    width: 100%;
    border-collapse: collapse;
}

.data-table thead th {
    background: rgba(31, 45, 78, 0.95);
    color: #cfd9f8;
    text-align: left;
    font-size: 0.84rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    padding: 0.95rem 1rem;
    border-bottom: 1px solid rgba(111, 130, 177, 0.18);
}

.data-table tbody td {
    color: #eef3ff;
    padding: 0.95rem 1rem;
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

@media (max-width: 900px) {
    .hero-title {
        font-size: 2.2rem;
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
    <div class="hero-subtitle">Upload documents, extract information and manage automatically</div>
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
    )

    send_method = st.radio(
        "Action",
        ["Route to Local Folder", "Send via Email"],
    )

    st.markdown('<div class="sidebar-label">Upload Document</div>', unsafe_allow_html=True)

    format_map = {
        "Word Document": ["docx"],
        "PDF": ["pdf"],
        "Excel": ["xlsx", "xls"],
        "Image": ["jpg", "jpeg", "png"],
    }

    allowed_types = format_map[target_format]

    uploaded_files = st.file_uploader(
        f"Upload {target_format}",
        type=allowed_types,
        help=f"Only {', '.join(t.upper() for t in allowed_types)} accepted",
        accept_multiple_files=True,
    )

    email_settings = {}
    if send_method == "Send via Email":
        st.markdown('<div class="sidebar-label">Email Delivery</div>', unsafe_allow_html=True)
        email_settings = {
            "mode": "auto",
            "sender_email": st.text_input(
                "Sender Email",
                value=os.getenv(
                    "ADMS_EMAIL_FROM",
                    os.getenv("ADMS_EMAIL_SENDER", os.getenv("ADMS_SMTP_USER", "")),
                ),
                placeholder="sender@example.com",
            ),
            "receiver_email": st.text_input(
                "Receiver Email",
                value=os.getenv("ADMS_EMAIL_TO", ""),
                placeholder="receiver@example.com",
                help="Leave blank to use the email extracted from the uploaded document, when exactly one email is found.",
            ),
        }

    process_btn = st.button(
        "Start Extraction",
        type="primary",
        use_container_width=True,
    )

    st.markdown(
        """
    <div class="sidebar-footer">
        © 2025 ADMS<br>
        All rights reserved
    </div>
    """,
        unsafe_allow_html=True,
    )


if process_btn:
    if not uploaded_files:
        st.warning(f"Please upload at least one {target_format} file first!")
    else:
        with st.spinner("Reading documents..."):
            processed_documents = [
                _process_uploaded_document(uploaded_file, index)
                for index, uploaded_file in enumerate(uploaded_files, start=1)
            ]
            email_status = None
            if send_method == "Send via Email":
                email_status = send_processed_documents_email(
                    [_build_email_payload(document) for document in processed_documents],
                    email_settings,
                )

        st.session_state[PROCESSED_DOCS_KEY] = processed_documents
        st.session_state[EMAIL_STATUS_KEY] = email_status
        st.session_state[SAVED_DOCS_KEY] = {}
        st.session_state[LAST_ACTION_KEY] = send_method


processed_documents = st.session_state.get(PROCESSED_DOCS_KEY, [])
saved_documents = st.session_state.setdefault(SAVED_DOCS_KEY, {})
email_status = st.session_state.get(EMAIL_STATUS_KEY)
active_action = st.session_state.get(LAST_ACTION_KEY, send_method)


if processed_documents:
    badge_colors = {
        "certificate": "#0ea5e9",
        "ticket": "#8b5cf6",
        "employee_form": "#10b981",
        "marksheet": "#ec4899",
        "report": "#f59e0b",
        "generic": "#6b7280",
    }

    doc_types = sorted({document["display_doc_type"] for document in processed_documents})
    primary_type = doc_types[0] if doc_types else "generic"
    chip_label = (
        primary_type.upper()
        if len(processed_documents) == 1
        else f"MULTIPLE DOCUMENTS | {len(processed_documents)} FILES"
    )
    dcolor = badge_colors.get(primary_type, "#6b7280")

    st.markdown(
        f"""
    <div class="status-banner">
        <div class="status-icon">OK</div>
        <div class="status-copy">
            <strong>Extraction Complete</strong>
            <span>{len(processed_documents)} document(s) processed successfully.</span>
        </div>
    </div>
    """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
    <div class="doc-chip" style="border-color:{dcolor}33;">
        <span>Document Type:</span> {chip_label}
    </div>
    """,
        unsafe_allow_html=True,
    )

    if active_action == "Send via Email" and email_status:
        if email_status.get("success"):
            st.success(
                f"Email delivered via {email_status.get('delivery_method', 'email')} from "
                f"{email_status.get('sender')} to {email_status.get('recipient')}."
            )
        else:
            st.error("Email delivery failed: " + " | ".join(email_status.get("errors", [])))

    tab1, tab2, tab3, tab4 = st.tabs(
        [
            "Extracted Details",
            "Summary",
            "Raw Text",
            "Routing",
        ]
    )

    with tab1:
        st.markdown('<div class="panel-title">Review & Confirm Details</div>', unsafe_allow_html=True)

        for index, document in enumerate(processed_documents, start=1):
            details = document["details"]
            doc_det = document["doc_det"]
            doc_key = document["doc_key"]
            expander_label = (
                f"{index}. {document['file_name']} | "
                f"{document['display_doc_type'].upper()} | "
                f"{_display_value(_build_full_name(details))}"
            )

            with st.expander(expander_label, expanded=len(processed_documents) == 1):

                def val(field_name, current_details=details):
                    value = current_details.get(field_name, "")
                    return "" if value == "Not Found" else value

                with st.form(f"confirm_form_{doc_key}"):
                    c1, c2 = st.columns(2)

                    with c1:
                        fn_in = st.text_input(
                            "First Name",
                            key=f"first_name_{doc_key}",
                            value=val("First Name"),
                            placeholder="e.g. Pooja",
                        )
                        mn_in = st.text_input(
                            "Middle Name",
                            key=f"middle_name_{doc_key}",
                            value=val("Middle Name") or val("Father's Name"),
                            placeholder="e.g. Bhadreshkumar",
                        )
                        ln_in = st.text_input(
                            "Last Name",
                            key=f"last_name_{doc_key}",
                            value=val("Last Name") or val("Surname"),
                            placeholder="e.g. Patel",
                        )

                    with c2:
                        em_in = st.text_input(
                            "Email",
                            key=f"email_{doc_key}",
                            value=val("Email"),
                            placeholder="e.g. pooja@gmail.com",
                        )
                        ph_in = st.text_input(
                            "Phone",
                            key=f"phone_{doc_key}",
                            value=val("Phone"),
                            placeholder="e.g. 9876543210",
                        )
                        id_type = details.get("ID_Type", "ID")
                        id_in = st.text_input(
                            f"ID / {id_type}",
                            key=f"id_{doc_key}",
                            value=val("ID"),
                            placeholder="e.g. DEV-402",
                        )

                    submitted = st.form_submit_button(
                        "Confirm & Save to Folder",
                        type="primary",
                        use_container_width=True,
                    )

                if submitted:
                    if not fn_in.strip():
                        st.error("First Name zaroori hai!")
                    else:
                        folder, _saved_path = save_uploaded_bytes(
                            document["file_name"],
                            document["file_bytes"],
                            fn_in.strip() or "Unknown",
                            ln_in.strip() or "Unknown",
                            mn_in.strip() or "Unknown",
                            id_in.strip() or "NoID",
                            OUTPUT_ROOT,
                        )

                        saved_documents[doc_key] = {
                            "folder": folder,
                            "first_name": fn_in.strip() or "Unknown",
                            "middle_name": mn_in.strip() or "Unknown",
                            "last_name": ln_in.strip() or "Unknown",
                            "email": em_in.strip() or "Not Found",
                            "phone": ph_in.strip() or "Not Found",
                            "id_type": id_type,
                            "id_value": id_in.strip() or "NoID",
                        }
                        st.session_state[SAVED_DOCS_KEY] = saved_documents

                saved_doc = saved_documents.get(doc_key)
                if saved_doc:
                    st.markdown(_render_saved_card(saved_doc), unsafe_allow_html=True)
                    st.markdown('<div class="panel-title">Data Source Summary</div>', unsafe_allow_html=True)

                    def fsrc(field, fval):
                        dv = doc_det.get(field, "Not Found")
                        if dv != "Not Found" and fval == dv:
                            return "AI (Document)"
                        if fval not in ("Not Found", "", "Unknown", "NoID"):
                            return "Manual"
                        return "Not Found"

                    rows = [
                        ["First Name", saved_doc["first_name"], fsrc("First Name", saved_doc["first_name"])],
                        ["Middle Name", saved_doc["middle_name"], fsrc("Middle Name", saved_doc["middle_name"])],
                        ["Last Name", saved_doc["last_name"], fsrc("Last Name", saved_doc["last_name"])],
                        ["Email", saved_doc["email"], fsrc("Email", saved_doc["email"])],
                        ["Phone", saved_doc["phone"], fsrc("Phone", saved_doc["phone"])],
                        [saved_doc["id_type"], saved_doc["id_value"], fsrc("ID", saved_doc["id_value"])],
                    ]

                    st.markdown(
                        _render_dark_table(rows, ["Field", "Value", "Source"]),
                        unsafe_allow_html=True,
                    )

    with tab2:
        st.markdown('<div class="panel-title">Document Summary</div>', unsafe_allow_html=True)

        for index, document in enumerate(processed_documents, start=1):
            label = f"{index}. {document['file_name']} | {_display_value(_build_full_name(document['details']))}"
            with st.expander(label, expanded=len(processed_documents) == 1):
                st.markdown(
                    f"""
                    <div class="classic-summary-box">
                        {html.escape(document['doc_summary'])}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                extra = document["details"].get("extra", {})
                if extra:
                    st.markdown('<div class="panel-title">Additional Information</div>', unsafe_allow_html=True)
                    detail_rows = "".join(
                        f'<div class="classic-detail-row"><strong>{key.replace("_", " ").title()}:</strong> {html.escape(str(value))}</div>'
                        for key, value in extra.items()
                    )
                    st.markdown(f'<div class="classic-detail-list">{detail_rows}</div>', unsafe_allow_html=True)

    with tab3:
        st.markdown('<div class="panel-title">Exact Text Read by Python</div>', unsafe_allow_html=True)

        for index, document in enumerate(processed_documents, start=1):
            with st.expander(f"{index}. {document['file_name']}", expanded=len(processed_documents) == 1):
                st.markdown(
                    f'<div class="summary-box text-box">{html.escape(document["display_raw_text"])}</div>',
                    unsafe_allow_html=True,
                )

    with tab4:
        st.markdown('<div class="panel-title">Action & Routing</div>', unsafe_allow_html=True)
        st.markdown(
            f"""
            <div class="routing-card">
                <div class="routing-grid">
                    <div class="route-pill">
                        <span>Selected Action</span>
                        <strong>{html.escape(active_action)}</strong>
                    </div>
                    <div class="route-pill">
                        <span>Documents Processed</span>
                        <strong>{len(processed_documents)}</strong>
                    </div>
                    <div class="route-pill">
                        <span>Detected Types</span>
                        <strong>{html.escape(', '.join(doc_types))}</strong>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if active_action == "Send via Email" and email_status:
            rows = [
                ["Sender Email", email_status.get("sender", "Not Found")],
                ["Receiver Email", email_status.get("recipient", "Not Found")],
                ["Emails Sent", email_status.get("sent_count", 0)],
                ["Documents Included", email_status.get("document_count", 0)],
                ["Mode", email_status.get("mode", "auto")],
                ["Delivery Method", email_status.get("delivery_method", "Not Found")],
            ]
            if email_status.get("subjects"):
                rows.append(["Subjects", " | ".join(email_status["subjects"])])
            if email_status.get("errors"):
                rows.append(["Errors", " | ".join(email_status["errors"])])

            st.markdown(
                _render_dark_table(rows, ["Field", "Value"]),
                unsafe_allow_html=True,
            )

else:
    st.markdown(
        """
    <div class="empty-state">
        <div class="panel-title" style="margin-top:0;">Ready to Process</div>
        <div style="color: var(--text-soft); line-height:1.8; font-size:1rem;">
            Choose a target format, upload one or multiple files, and start extraction.
            Existing extraction logic stays the same for every document.
        </div>
    </div>
    """,
        unsafe_allow_html=True,
    )
