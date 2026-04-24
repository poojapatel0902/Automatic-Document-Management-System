# ============================================
# MODULE 1: INGESTION.PY
# File Router — Extension dekho, sahi module bhejo
# ============================================

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import ALL_SUPPORTED, SUPPORTED_FORMATS, Colors, cprint


def check_file(file_path):
    """
    File exist karti hai? Supported hai?
    Returns: (is_valid, error_message)
    """
    if not os.path.exists(file_path):
        return False, f"❌ File nahi mili: {file_path}"

    if not os.path.isfile(file_path):
        return False, f"❌ Yeh file nahi, folder hai: {file_path}"

    ext = os.path.splitext(file_path)[1].lower()
    if ext not in ALL_SUPPORTED:
        return False, f"❌ Unsupported format '{ext}'. Supported: {ALL_SUPPORTED}"

    return True, "✅ File valid hai!"


def get_file_type(file_path):
    """
    File ka type return karo
    Returns: 'document' | 'spreadsheet' | 'pdf' | 'image' | 'unknown'
    """
    ext = os.path.splitext(file_path)[1].lower()

    for file_type, extensions in SUPPORTED_FORMATS.items():
        if ext in extensions:
            return file_type

    return "unknown"


def get_file_info(file_path):
    """
    File ke baare mein saari info ek dict mein
    """
    stats = os.stat(file_path)
    size_kb = stats.st_size / 1024

    return {
        "file_name"  : os.path.basename(file_path),
        "file_path"  : os.path.abspath(file_path),
        "extension"  : os.path.splitext(file_path)[1].lower(),
        "file_type"  : get_file_type(file_path),
        "size_kb"    : round(size_kb, 2),
        "size_label" : f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb/1024:.1f} MB",
    }


def route_to_extractor(file_path):
    """
    ⭐ MAIN ROUTER FUNCTION ⭐
    File type dekho → Sahi extractor module call karo
    Returns: extracted text (string)
    """
    # Import modules here to avoid circular imports
    from modules.extractor import (
        extract_from_docx,
        extract_from_txt,
        extract_from_pdf,
        extract_from_excel,
    )
    from modules.ocr import extract_from_image

    file_type = get_file_type(file_path)
    ext       = os.path.splitext(file_path)[1].lower()

    cprint(f"\n📂 File     : {os.path.basename(file_path)}", Colors.CYAN)
    cprint(f"📄 Type     : {file_type} ({ext})", Colors.CYAN)

    # Route to correct extractor
    if ext == ".docx":
        return extract_from_docx(file_path)

    elif ext == ".txt":
        return extract_from_txt(file_path)

    elif ext == ".pdf":
        return extract_from_pdf(file_path)

    elif ext in [".xlsx", ".xls"]:
        return extract_from_excel(file_path)

    elif file_type == "image":
        return extract_from_image(file_path)

    else:
        cprint(f"⚠️  No extractor for {ext}", Colors.YELLOW)
        return ""


def ingest_document(file_path):
    """
    ⭐ MASTER INGESTION FUNCTION ⭐
    1. Validate file
    2. Get file info
    3. Route to extractor
    4. Return everything
    """
    cprint("\n" + "="*55, Colors.BOLD)
    cprint("   📥 DOCUMENT INGESTION STARTED", Colors.BOLD)
    cprint("="*55, Colors.BOLD)

    # Step 1: Validate
    is_valid, message = check_file(file_path)
    if not is_valid:
        cprint(message, Colors.RED)
        return None, None

    cprint(message, Colors.GREEN)

    # Step 2: File info
    info = get_file_info(file_path)
    cprint(f"📊 Size     : {info['size_label']}", Colors.BLUE)

    # Step 3: Extract text
    text = route_to_extractor(file_path)

    if not text or not text.strip():
        cprint("❌ Text nahi nikla!", Colors.RED)
        return info, ""

    cprint(f"✅ Text nikla! ({len(text)} characters)", Colors.GREEN)
    return info, text


# ============================================
# DIRECT TEST
# ============================================
if __name__ == "__main__":
    # Test with a sample file
    test_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "sample_docs", "english_pooja_patel.docx"
    )
    if os.path.exists(test_file):
        info, text = ingest_document(test_file)
        print(f"\nExtracted Text Preview:\n{text[:300]}...")
    else:
        print(f"Test file nahi mila: {test_file}")
        print("Pehle create_samples.py chalao!")
