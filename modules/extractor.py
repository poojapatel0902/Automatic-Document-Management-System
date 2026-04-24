# ============================================
# MODULE 2: EXTRACTOR.PY
# Text Extraction — DOCX, TXT, PDF, Excel
# ============================================

import os
import sys
import tempfile
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import Colors, cprint

def extract_from_docx(file_path):
    try:
        import docx
        doc  = docx.Document(file_path)
        text = ""
        for para in doc.paragraphs:
            if para.text.strip():
                text += para.text + "\n"
        for table in doc.tables:
            for row in table.rows:
                row_text = []
                for cell in row.cells:
                    if cell.text.strip():
                        row_text.append(cell.text.strip())
                if row_text:
                    text += " | ".join(row_text) + "\n"
        cprint(f"  ✅ DOCX: {len(text)} chars extracted", Colors.GREEN)
        return text.strip()
    except Exception as e:
        cprint(f"  ❌ DOCX Error: {e}", Colors.RED)
        return ""


def extract_text_from_file(uploaded_file):
    """
    Streamlit uploaded file se raw text nikalo.
    """
    text = ""
    ext = uploaded_file.name.lower().split(".")[-1]

    try:
        if ext == "docx":
            import docx

            doc = docx.Document(uploaded_file)

            for para in doc.paragraphs:
                if para.text.strip():
                    text += para.text + "\n"

            for table in doc.tables:
                for row in table.rows:
                    row_data = [c.text.strip() for c in row.cells if c.text.strip()]
                    if row_data:
                        text += " | ".join(row_data) + "\n"

        elif ext == "pdf":
            import pdfplumber

            with pdfplumber.open(uploaded_file) as pdf:
                for page in pdf.pages:
                    extracted = page.extract_text()
                    if extracted:
                        text += extracted + "\n"

        elif ext in ["xlsx", "xls"]:
            import openpyxl

            wb = openpyxl.load_workbook(uploaded_file)
            sheet = wb.active

            headers = []
            first_row = True

            for row in sheet.iter_rows(values_only=True):
                if not any(row):
                    continue

                if first_row:
                    headers = [str(h) if h else "" for h in row]
                    first_row = False
                else:
                    for h, v in zip(headers, row):
                        if v is not None:
                            text += f"{h}: {v}\n"
                    text += "\n"

        elif ext == "txt":
            text = uploaded_file.getvalue().decode("utf-8", errors="ignore")

        elif ext in ["jpg", "jpeg", "png", "bmp", "webp"]:
            from modules.ocr import extract_from_image

            tmp_path = None
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as tmp:
                    tmp.write(uploaded_file.getbuffer())
                    tmp_path = tmp.name
                text = extract_from_image(tmp_path)
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass

        else:
            text = "Unsupported file format."

    except Exception as e:
        text = f"Error extracting text: {e}"

    return text

def extract_from_txt(file_path):
    encodings = ["utf-8", "utf-16", "latin-1", "cp1252"]
    for encoding in encodings:
        try:
            with open(file_path, "r", encoding=encoding) as f:
                text = f.read()
            cprint(f"  ✅ TXT ({encoding}): {len(text)} chars", Colors.GREEN)
            return text.strip()
        except (UnicodeDecodeError, UnicodeError):
            continue
        except Exception as e:
            cprint(f"  ❌ TXT Error: {e}", Colors.RED)
            return ""
    return ""

def extract_from_pdf(file_path):
    try:
        import pdfplumber
        text = ""
        with pdfplumber.open(file_path) as pdf:
            total_pages = len(pdf.pages)
            for i, page in enumerate(pdf.pages):
                page_text = page.extract_text()
                if page_text:
                    text += f"\n[Page {i+1}/{total_pages}]\n" + page_text + "\n"
        if text.strip():
            cprint(f"  ✅ PDF: {len(text)} chars extracted", Colors.GREEN)
            return text.strip()
        cprint("  ⚠️  PDF has no text layer — trying OCR...", Colors.YELLOW)
        return ""
    except Exception as e:
        cprint(f"  ❌ PDF Error: {e}", Colors.RED)
        return ""

def extract_from_excel(file_path):
    try:
        import openpyxl
        wb   = openpyxl.load_workbook(file_path)
        text = ""
        for sheet_name in wb.sheetnames:
            sheet = wb[sheet_name]
            text += f"\n[Sheet: {sheet_name}]\n"
            headers   = []
            first_row = True
            for row in sheet.iter_rows(values_only=True):
                if not any(row):
                    continue
                if first_row:
                    headers = [str(h) if h else "" for h in row]
                    text += " | ".join(headers) + "\n" + "-"*60 + "\n"
                    first_row = False
                else:
                    row_parts = [f"{h}: {v}" for h, v in zip(headers, row) if v is not None]
                    if row_parts:
                        text += "\n".join(row_parts) + "\n\n"
        cprint(f"  ✅ Excel: {len(text)} chars extracted", Colors.GREEN)
        return text.strip()
    except Exception as e:
        cprint(f"  ❌ Excel Error: {e}", Colors.RED)
        return ""
