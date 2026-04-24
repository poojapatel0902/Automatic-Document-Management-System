# MODULE 7: ROUTER.PY - Automated folder creation & file routing
import os, sys, json, shutil, re
from datetime import datetime
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import Colors, cprint, OUTPUT_DIR

def make_safe_name(name):
    if not name: return "Unknown"
    safe = re.sub(r'[<>:"/\\|?*\n\r\t]', '', str(name))
    safe = re.sub(r'\s+', '_', safe.strip())
    return safe[:50] or "Unknown"

def create_folder_structure(entities):
    fn     = make_safe_name(entities.get("first_name")  or "Unknown_FirstName")
    sn     = make_safe_name(entities.get("surname")     or "Unknown_Surname")
    dad    = make_safe_name(entities.get("father_name") or "Unknown_Father")
    uid    = entities.get("unique_id", {})
    uid_v  = make_safe_name(uid.get("value") or "NoID")
    folder = os.path.join(OUTPUT_DIR, fn, sn, f"{dad}_{uid_v}")
    os.makedirs(folder, exist_ok=True)
    cprint(f"\n  📁 Created: output/{fn}/{sn}/{dad}_{uid_v}", Colors.GREEN)
    return folder

def copy_file_to_folder(source, dest_folder):
    filename  = os.path.basename(source)
    dest_path = os.path.join(dest_folder, filename)
    if os.path.exists(dest_path):
        name, ext = os.path.splitext(filename)
        filename  = f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
        dest_path = os.path.join(dest_folder, filename)
    shutil.copy2(source, dest_path)
    cprint(f"  ✅ File saved: {filename}", Colors.GREEN)
    return dest_path

def generate_report(file_info, entities, summary, saved_path, lang, translated):
    uid = entities.get("unique_id", {})
    return {
        "timestamp"     : datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "file_info"     : {"name": file_info.get("file_name"), "type": file_info.get("file_type"), "size": file_info.get("size_label"), "path": file_info.get("file_path")},
        "language_info" : {"original": lang, "translated": translated},
        "entities"      : {
            "first_name": entities.get("first_name"), "surname": entities.get("surname"),
            "father_name": entities.get("father_name"),
            "unique_id"  : {"type": uid.get("type"), "value": uid.get("value")},
            "dob": entities.get("dob"), "email": entities.get("email"),
            "phone": entities.get("phone"), "department": entities.get("department"),
        },
        "summary"       : summary,
        "saved_path"    : saved_path,
        "folder_path"   : saved_path.replace(OUTPUT_DIR, "output").replace("\\","/"),
    }

def save_report_json(report, folder):
    path = os.path.join(folder, "_processing_report.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    cprint(f"  ✅ JSON report saved!", Colors.GREEN)
    return path

def print_final_result(report):
    e   = report["entities"]
    uid = e.get("unique_id", {})
    print(f"""
╔══════════════════════════════════════════════════╗
║       🎉 DOCUMENT PROCESSED SUCCESSFULLY!        ║
╠══════════════════════════════════════════════════╣
║  File       : {str(report['file_info']['name']):<35}║
║  Language   : {str(report['language_info']['original']):<35}║
║  Translated : {str(report['language_info']['translated']):<35}║
╠══════════════════════════════════════════════════╣
║  First Name : {str(e.get('first_name')  or 'Not found'):<35}║
║  Surname    : {str(e.get('surname')     or 'Not found'):<35}║
║  Father Name: {str(e.get('father_name') or 'Not found'):<35}║
║  Unique ID  : {str((uid.get('type') or '?')+': '+(uid.get('value') or 'N/A')):<35}║
║  Department : {str(e.get('department') or 'Not found'):<35}║
╠══════════════════════════════════════════════════╣
║  SUMMARY    :                                    ║""")
    for i in range(0, len(report['summary']), 48):
        print(f"║    {report['summary'][i:i+48]:<48}║")
    print(f"""╠══════════════════════════════════════════════════╣
║  SAVED TO   :                                    ║
║    {report['folder_path'][:48]:<48}║
╚══════════════════════════════════════════════════╝""")

def route_document(file_info, entities, summary, lang="en", translated=False):
    cprint("\n" + "="*50, Colors.BOLD)
    cprint("   📦 ROUTING DOCUMENT TO FOLDER", Colors.BOLD)
    cprint("="*50, Colors.BOLD)
    folder     = create_folder_structure(entities)
    saved_path = copy_file_to_folder(file_info["file_path"], folder)
    report     = generate_report(file_info, entities, summary, saved_path, lang, translated)
    save_report_json(report, folder)
    print_final_result(report)
    return report


def save_uploaded_document(uploaded_file, first_name, surname, father_name, unique_id, output_root):
    """
    Streamlit upload ko same output structure mein save karo.
    """
    fn = make_safe_name(first_name or "Unknown")
    sn = make_safe_name(surname or "Unknown")
    dad = make_safe_name(father_name or "Unknown")
    uid = make_safe_name(unique_id or "NoID")

    folder = os.path.join(output_root, fn, sn, f"{dad}_{uid}")
    os.makedirs(folder, exist_ok=True)

    file_path = os.path.join(folder, uploaded_file.name)
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    return folder, file_path
