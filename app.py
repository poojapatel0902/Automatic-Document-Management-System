import pandas as pd
import streamlit as st

from modules.extractor import extract_text_from_file
from modules.nlp_parser import smart_merge, smart_parse
from modules.ocr import prepare_display_details
from modules.router import save_uploaded_document
from modules.summarizer import summarize_document


OUTPUT_ROOT = r"D:\Pooja\project\AI_DMS\output"


st.set_page_config(page_title="AI-DMS Pro", page_icon="⚡", layout="wide")

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
    --line: rgba(111, 130, 177, 0.24);
    --blue: #4f73ff;
    --violet: #7d4dff;
    --green: #29d48a;
    --green-bg: rgba(25, 117, 79, 0.22);
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
    font-size: 1.4rem;
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
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.05);
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

div[data-testid="stForm"] .stMarkdown p {
    color: var(--text-main);
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
    box-shadow: none !important;
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

div[data-baseweb="select"] > div {
    min-height: 54px;
    border-radius: 14px !important;
    border: 1px solid rgba(111, 130, 177, 0.18) !important;
    background: linear-gradient(180deg, #1b2745 0%, #18233f 100%) !important;
    color: var(--text-main) !important;
    font-size: 1.06rem !important;
    font-weight: 600 !important;
}

div[data-baseweb="select"] svg {
    fill: #b8c4e7 !important;
}

div[data-baseweb="popover"] {
    background: transparent !important;
}

div[data-baseweb="popover"] > div {
    background: linear-gradient(180deg, #1b2745 0%, #121c35 100%) !important;
    border: 1px solid rgba(111, 130, 177, 0.22) !important;
    border-radius: 16px !important;
    box-shadow: 0 20px 40px rgba(3, 8, 20, 0.42) !important;
    overflow: hidden !important;
}

div[data-baseweb="popover"] ul,
div[data-baseweb="popover"] [role="listbox"] {
    background: transparent !important;
    padding-top: 0.3rem !important;
    padding-bottom: 0.3rem !important;
}

div[data-baseweb="popover"] li,
div[data-baseweb="popover"] [role="option"] {
    background: transparent !important;
    color: #e9efff !important;
    font-size: 1.02rem !important;
    font-weight: 500 !important;
}

div[data-baseweb="popover"] li:hover,
div[data-baseweb="popover"] [role="option"]:hover,
div[data-baseweb="popover"] [role="option"][aria-selected="true"] {
    background: rgba(79, 115, 255, 0.22) !important;
    color: #ffffff !important;
}

div[data-baseweb="popover"] li + li,
div[data-baseweb="popover"] [role="option"] + [role="option"] {
    border-top: 1px solid rgba(111, 130, 177, 0.08) !important;
}

div[role="radiogroup"] {
    gap: 0.35rem;
}

div[role="radiogroup"] label {
    padding: 0.2rem 0;
}

div[role="radiogroup"] label p {
    color: var(--text-main) !important;
    font-size: 1.06rem !important;
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
    font-size: 1rem !important;
}

[data-testid="stFileUploader"] small,
[data-testid="stFileUploader"] span,
[data-testid="stFileUploader"] p {
    color: #cdd8fb !important;
    opacity: 1 !important;
}

[data-testid="stFileUploaderFile"] {
    background: rgba(27, 39, 69, 0.92) !important;
    border: 1px solid rgba(111, 130, 177, 0.18) !important;
    border-radius: 14px !important;
}

[data-testid="stFileUploaderFile"] * {
    color: #dce4f7 !important;
    opacity: 1 !important;
}

[data-testid="stFileUploaderFileName"] {
    color: #f7f8fc !important;
    font-size: 1rem !important;
    font-weight: 600 !important;
}

[data-testid="stFileUploaderFileData"] {
    color: #9fb1e5 !important;
    font-size: 0.94rem !important;
}

section[data-testid="stFileUploaderDropzone"] button {
    border-radius: 12px !important;
    border: 1px solid rgba(79, 115, 255, 0.46) !important;
    background: rgba(41, 59, 113, 0.35) !important;
    color: white !important;
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

.stButton > button:hover,
div[data-testid="stFormSubmitButton"] button:hover {
    filter: brightness(1.08);
    transform: translateY(-1px);
}

.stButton > button:focus,
div[data-testid="stFormSubmitButton"] button:focus {
    box-shadow: 0 0 0 2px rgba(125, 77, 255, 0.28) !important;
}

div[data-baseweb="tab-list"] {
    gap: 1.8rem;
    border-bottom: 1px solid rgba(111, 130, 177, 0.18);
    margin-top: 0.2rem;
}

button[data-baseweb="tab"] {
    background: transparent !important;
    border: none !important;
    color: var(--text-soft) !important;
    font-size: 1.1rem !important;
    font-weight: 600 !important;
    padding: 1rem 0.1rem 1rem !important;
}

button[data-baseweb="tab"][aria-selected="true"] {
    color: #7f97ff !important;
}

div[data-baseweb="tab-highlight"] {
    background: linear-gradient(90deg, #3b82f6, #7d4dff) !important;
    height: 3px !important;
    border-radius: 999px 999px 0 0 !important;
}

.summary-box {
    background: linear-gradient(180deg, rgba(17, 25, 46, 0.98), rgba(14, 21, 38, 0.98));
    border: 1px solid rgba(111, 130, 177, 0.2);
    border-left: 4px solid #4f73ff;
    border-radius: 18px;
    padding: 1.3rem 1.5rem;
    font-size: 1.12rem;
    line-height: 1.85;
    color: #eef3ff;
    box-shadow: 0 20px 42px rgba(4, 10, 20, 0.22);
}

.info-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    gap: 14px;
    margin-top: 0.8rem;
}

.info-item {
    background: linear-gradient(180deg, rgba(18, 27, 50, 0.96), rgba(15, 22, 41, 0.96));
    border: 1px solid rgba(111, 130, 177, 0.16);
    border-radius: 16px;
    padding: 0.95rem 1rem;
}

.info-label {
    display: block;
    font-size: 0.84rem;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    color: var(--text-muted);
    margin-bottom: 0.35rem;
    font-weight: 700;
}

.info-value {
    color: var(--text-main);
    font-size: 1.08rem;
    font-weight: 600;
    line-height: 1.55;
    word-break: break-word;
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

.saved-card b {
    color: #dce4f7;
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

div[data-testid="stDataFrame"] {
    border: 1px solid rgba(111, 130, 177, 0.18);
    border-radius: 18px;
    overflow: hidden;
    background: rgba(18, 27, 50, 0.88);
}

div[data-testid="stDataFrame"] [data-testid="stTable"] {
    background: transparent;
}

[data-testid="stNotification"] {
    display: none;
}

[data-testid="stToolbar"] {
    right: 1rem;
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
    <div class="hero-subtitle">Upload document, extract information and manage automatically</div>
</div>
""",
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown(
        """
    <div class="brand-card">
        <div class="brand-icon">◔</div>
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

    uploaded_file = st.file_uploader(
        f"Upload {target_format}",
        type=allowed_types,
        help=f"Only {', '.join(t.upper() for t in allowed_types)} accepted",
    )

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


if uploaded_file is not None and process_btn:
    with st.spinner("Reading document..."):
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

    badge_colors = {
        "certificate": "#0ea5e9",
        "ticket": "#8b5cf6",
        "employee_form": "#10b981",
        "marksheet": "#ec4899",
        "report": "#f59e0b",
        "generic": "#6b7280",
    }

    dtype = display_doc_type
    dcolor = badge_colors.get(dtype, "#6b7280")

    st.markdown(
        """
    <div class="status-banner">
        <div class="status-icon">✓</div>
        <div class="status-copy">
            <strong>Extraction Complete</strong>
            <span>Your document has been processed successfully.</span>
        </div>
    </div>
    """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
    <div class="doc-chip" style="border-color:{dcolor}33;">
        <span>Document Type:</span> {dtype.upper()}
    </div>
    """,
        unsafe_allow_html=True,
    )

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

        def val(field):
            value = details.get(field, "")
            return "" if value == "Not Found" else value

        with st.form("confirm_form"):
            c1, c2 = st.columns(2)

            with c1:
                fn_in = st.text_input("First Name", value=val("First Name"), placeholder="e.g. Pooja")
                sn_in = st.text_input("Surname", value=val("Surname"), placeholder="e.g. Patel")
                fa_in = st.text_input("Father's Name", value=val("Father's Name"), placeholder="e.g. Bhadreshkumar")

            with c2:
                dp_in = st.text_input("Department", value=val("Department"), placeholder="e.g. Software Development")
                em_in = st.text_input("Email", value=val("Email"), placeholder="e.g. pooja@gmail.com")

                id_type = details.get("ID_Type", "ID")
                id_in = st.text_input(
                    f"ID / {id_type}",
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
                st.error("❌ First Name zaroori hai!")
            else:
                fn = fn_in.strip() or "Unknown"
                sn = sn_in.strip() or "Unknown"
                dad = fa_in.strip() or "Unknown"
                dp = dp_in.strip() or "Unknown"
                em = em_in.strip() or "Not Found"
                uid = id_in.strip() or "NoID"

                folder, _saved_path = save_uploaded_document(
                    uploaded_file,
                    fn,
                    sn,
                    dad,
                    uid,
                    OUTPUT_ROOT,
                )

                st.markdown(
                    f"""
                <div class="saved-card">
                    <b>Saved to:</b> <code>{folder}</code><br><br>
                    <b>Name:</b> {fn} {sn} &nbsp;|&nbsp;
                    <b>Dept:</b> {dp} &nbsp;|&nbsp;
                    <b>{id_type}:</b> {uid}
                </div>
                """,
                    unsafe_allow_html=True,
                )

                st.markdown('<div class="panel-title">Data Source Summary</div>', unsafe_allow_html=True)

                def fsrc(field, fval):
                    dv = doc_det.get(field, "Not Found")
                    if dv != "Not Found" and fval == dv:
                        return "🟢 AI (Document)"
                    if fval not in ("Not Found", "", "Unknown", "NoID"):
                        return "🟡 Manual"
                    return "❌ Not Found"

                rows = [
                    ["First Name", fn, fsrc("First Name", fn)],
                    ["Surname", sn, fsrc("Surname", sn)],
                    ["Father's Name", dad, fsrc("Father's Name", dad)],
                    ["Department", dp, fsrc("Department", dp)],
                    ["Email", em, fsrc("Email", em)],
                    [id_type, uid, fsrc("ID", uid)],
                ]

                st.dataframe(
                    pd.DataFrame(rows, columns=["Field", "Value", "Source"]),
                    use_container_width=True,
                    hide_index=True,
                )

    with tab2:
        st.markdown('<div class="panel-title">Document Summary</div>', unsafe_allow_html=True)

        st.markdown(
            f"""
            <div class="summary-box">
                {doc_summary}
            </div>
            """,
            unsafe_allow_html=True,
        )

        extra = details.get("extra", {})
        if extra:
            st.markdown('<div class="panel-title">Additional Information</div>', unsafe_allow_html=True)
            info_cards = "".join(
                f"""
                <div class="info-item">
                    <span class="info-label">{key.replace('_', ' ').title()}</span>
                    <div class="info-value">{value}</div>
                </div>
                """
                for key, value in extra.items()
            )
            st.markdown(f'<div class="info-grid">{info_cards}</div>', unsafe_allow_html=True)

    with tab3:
        st.markdown('<div class="panel-title">Exact Text Read by Python</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="summary-box text-box">{raw_text}</div>', unsafe_allow_html=True)

    with tab4:
        st.markdown('<div class="panel-title">Action & Routing</div>', unsafe_allow_html=True)
        st.markdown(
            f"""
            <div class="routing-card">
                <div class="routing-grid">
                    <div class="route-pill">
                        <span>Selected Action</span>
                        <strong>{send_method}</strong>
                    </div>
                    <div class="route-pill">
                        <span>Detected Type</span>
                        <strong>{dtype}</strong>
                    </div>
                    <div class="route-pill">
                        <span>Uploaded File</span>
                        <strong>{uploaded_file.name}</strong>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

elif process_btn and uploaded_file is None:
    st.warning(f"⚠️ Please upload a {target_format} file first!")

else:
    st.markdown(
        """
    <div class="empty-state">
        <div class="panel-title" style="margin-top:0;">Ready to Process</div>
        <div style="color: var(--text-soft); line-height:1.8; font-size:1rem;">
            Choose a target format from the sidebar, upload your file, and start extraction.
            The logic stays exactly the same — this view is only a redesigned UI shell.
        </div>
    </div>
    """,
        unsafe_allow_html=True,
    )
