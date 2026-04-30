# MODULE 7: ROUTER.PY - Automated folder creation & file routing
import json
import mimetypes
import os
import re
import shutil
import smtplib
import subprocess
import sys
import tempfile
from datetime import datetime
from email.message import EmailMessage

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


def save_uploaded_bytes(file_name, file_bytes, first_name, surname, father_name, unique_id, output_root):
    """
    Raw file bytes ko same output structure mein save karo.
    """
    fn = make_safe_name(first_name or "Unknown")
    sn = make_safe_name(surname or "Unknown")
    dad = make_safe_name(father_name or "Unknown")
    uid = make_safe_name(unique_id or "NoID")

    folder = os.path.join(output_root, fn, sn, f"{dad}_{uid}")
    os.makedirs(folder, exist_ok=True)

    file_path = os.path.join(folder, file_name)
    with open(file_path, "wb") as f:
        f.write(file_bytes)

    return folder, file_path


def save_uploaded_document(uploaded_file, first_name, surname, father_name, unique_id, output_root):
    """
    Streamlit upload ko same output structure mein save karo.
    """
    if hasattr(uploaded_file, "getvalue"):
        file_bytes = uploaded_file.getvalue()
    else:
        file_bytes = bytes(uploaded_file.getbuffer())

    return save_uploaded_bytes(
        uploaded_file.name,
        file_bytes,
        first_name,
        surname,
        father_name,
        unique_id,
        output_root,
    )


def _clean_delivery_value(value, default="Not Found"):
    if value is None:
        return default
    cleaned = str(value).strip()
    return cleaned or default


def _is_usable_email(value):
    text = str(value or "").strip()
    if not text or text.lower() == "not found":
        return False
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", text))


def _resolve_document_recipient(documents):
    recipients = []
    for document in documents or []:
        email = str(document.get("email") or "").strip()
        if _is_usable_email(email):
            recipients.append(email)

    unique_recipients = []
    seen = set()
    for recipient in recipients:
        key = recipient.lower()
        if key not in seen:
            seen.add(key)
            unique_recipients.append(recipient)

    return unique_recipients[0] if len(unique_recipients) == 1 else ""


def _guess_mime_type(file_name):
    mime_type, _encoding = mimetypes.guess_type(file_name)
    return mime_type or "application/octet-stream"


def _build_document_email_section(document):
    return "\n".join(
        [
            f"File Name: {_clean_delivery_value(document.get('file_name'))}",
            f"Extracted Name: {_clean_delivery_value(document.get('full_name'))}",
            f"First Name: {_clean_delivery_value(document.get('first_name'))}",
            f"Middle Name: {_clean_delivery_value(document.get('middle_name'))}",
            f"Last Name: {_clean_delivery_value(document.get('last_name'))}",
            f"Document Type: {_clean_delivery_value(document.get('document_type'))}",
            f"Date: {_clean_delivery_value(document.get('date'))}",
            f"Email: {_clean_delivery_value(document.get('email'))}",
            f"Phone: {_clean_delivery_value(document.get('phone'))}",
            "",
            "Short Summary:",
            _clean_delivery_value(document.get("summary")),
            "",
            "Raw Text:",
            _clean_delivery_value(document.get("raw_text")),
        ]
    )


def _build_single_document_email(document, recipient, sender):
    message = EmailMessage()
    document_type = _clean_delivery_value(document.get("document_type")).upper()
    file_name = _clean_delivery_value(document.get("file_name"))
    full_name = _clean_delivery_value(document.get("full_name"))

    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = f"ADMS | {file_name} | {document_type} | {full_name}"
    message.set_content(_build_document_email_section(document))

    file_bytes = document.get("file_bytes")
    if file_bytes:
        mime_type = _guess_mime_type(file_name)
        maintype, subtype = mime_type.split("/", 1)
        message.add_attachment(
            file_bytes,
            maintype=maintype,
            subtype=subtype,
            filename=file_name,
        )

    return message


def _build_combined_document_email(documents, recipient, sender):
    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = f"ADMS | Combined Document Summary | {len(documents)} document(s)"

    sections = []
    for index, document in enumerate(documents, start=1):
        sections.append(f"Document {index}\n{'=' * 20}\n{_build_document_email_section(document)}")

    message.set_content("\n\n".join(sections))

    for document in documents:
        file_bytes = document.get("file_bytes")
        file_name = _clean_delivery_value(document.get("file_name"))
        if not file_bytes or file_name == "Not Found":
            continue

        mime_type = _guess_mime_type(file_name)
        maintype, subtype = mime_type.split("/", 1)
        message.add_attachment(
            file_bytes,
            maintype=maintype,
            subtype=subtype,
            filename=file_name,
        )

    return message


def _extract_plain_email_body(message):
    if message.is_multipart():
        body_part = message.get_body(preferencelist=("plain",))
        if body_part is not None:
            return body_part.get_content()
    return message.get_content()


def _extract_email_attachments(message):
    attachments = []
    for part in message.iter_attachments():
        attachments.append(
            {
                "filename": part.get_filename() or "attachment.bin",
                "file_bytes": part.get_payload(decode=True) or b"",
            }
        )
    return attachments


def _send_messages_via_outlook(messages, sender_email, include_attachments=True):
    """
    Outlook desktop COM ke through mail bhejne ki fallback delivery.
    SMTP password missing ho to sender/receiver-only flow ko support karta hai.
    """
    sent_subjects = []
    sender_email = str(sender_email or "").strip()
    mail_temp_root = os.path.join(OUTPUT_DIR, "_email_tmp")
    os.makedirs(mail_temp_root, exist_ok=True)

    powershell_script = r"""
param([string]$PayloadPath)

$ErrorActionPreference = "Stop"
$payload = Get-Content -LiteralPath $PayloadPath -Raw | ConvertFrom-Json
$outlook = New-Object -ComObject Outlook.Application
$namespace = $outlook.GetNamespace("MAPI")
$mail = $outlook.CreateItem(0)
$mail.To = $payload.recipient
$mail.Subject = $payload.subject
$mail.Body = $payload.body

if ($payload.sender) {
    foreach ($account in $namespace.Accounts) {
        try {
            if ($account.SmtpAddress -and $account.SmtpAddress.ToLower() -eq $payload.sender.ToLower()) {
                $mail.SendUsingAccount = $account
                break
            }
        } catch {
        }
    }
}

foreach ($attachment in $payload.attachments) {
    if (Test-Path -LiteralPath $attachment) {
        $null = $mail.Attachments.Add($attachment)
    }
}

$mail.Send()
"""

    for message in messages:
        attachment_paths = []
        temp_dir = tempfile.mkdtemp(prefix="adms_outlook_", dir=mail_temp_root)
        try:
            if include_attachments:
                for attachment in _extract_email_attachments(message):
                    attachment_path = os.path.join(temp_dir, attachment["filename"])
                    with open(attachment_path, "wb") as attachment_file:
                        attachment_file.write(attachment["file_bytes"])
                    attachment_paths.append(attachment_path)

            payload = {
                "sender": sender_email,
                "recipient": str(message.get("To") or "").strip(),
                "subject": str(message.get("Subject") or "").strip(),
                "body": _extract_plain_email_body(message),
                "attachments": attachment_paths,
            }
            payload_path = os.path.join(temp_dir, "email_payload.json")
            script_path = os.path.join(temp_dir, "send_email.ps1")

            with open(payload_path, "w", encoding="utf-8") as payload_file:
                json.dump(payload, payload_file, ensure_ascii=False)

            with open(script_path, "w", encoding="utf-8") as script_file:
                script_file.write(powershell_script)

            completed = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    script_path,
                    payload_path,
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if completed.returncode != 0:
                error_text = (completed.stderr or completed.stdout or "").strip()
                if not error_text:
                    error_text = "Microsoft Outlook desktop delivery failed."
                raise RuntimeError(error_text)

            sent_subjects.append(str(message.get("Subject") or "").strip())
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    return sent_subjects


AUTO_SMTP_PROVIDERS = {
    "gmail.com": {"host": "smtp.gmail.com", "port": 587, "use_ssl": False},
    "googlemail.com": {"host": "smtp.gmail.com", "port": 587, "use_ssl": False},
    "outlook.com": {"host": "smtp.office365.com", "port": 587, "use_ssl": False},
    "hotmail.com": {"host": "smtp.office365.com", "port": 587, "use_ssl": False},
    "live.com": {"host": "smtp.office365.com", "port": 587, "use_ssl": False},
    "msn.com": {"host": "smtp.office365.com", "port": 587, "use_ssl": False},
    "yahoo.com": {"host": "smtp.mail.yahoo.com", "port": 465, "use_ssl": True},
    "yahoo.in": {"host": "smtp.mail.yahoo.com", "port": 465, "use_ssl": True},
    "icloud.com": {"host": "smtp.mail.me.com", "port": 587, "use_ssl": False},
    "me.com": {"host": "smtp.mail.me.com", "port": 587, "use_ssl": False},
    "mac.com": {"host": "smtp.mail.me.com", "port": 587, "use_ssl": False},
    "zoho.com": {"host": "smtp.zoho.com", "port": 587, "use_ssl": False},
    "zohomail.com": {"host": "smtp.zoho.com", "port": 587, "use_ssl": False},
    "zoho.in": {"host": "smtp.zoho.in", "port": 587, "use_ssl": False},
}


def _sender_env_key(sender_email):
    normalized = re.sub(r"[^a-z0-9]+", "_", str(sender_email or "").lower()).strip("_")
    return normalized


def _resolve_email_password(sender_email):
    sender_key = _sender_env_key(sender_email)
    candidates = [
        f"ADMS_EMAIL_PASSWORD__{sender_key}",
        f"ADMS_SMTP_PASSWORD__{sender_key}",
        "ADMS_EMAIL_PASSWORD",
        "ADMS_SMTP_PASSWORD",
        "EMAIL_APP_PASSWORD",
        "APP_PASSWORD",
    ]
    for env_name in candidates:
        value = os.getenv(env_name, "").strip()
        if value:
            return value, env_name
    return "", ""


def _normalize_outlook_error(error_text):
    text = str(error_text or "").strip()
    lowered = text.lower()

    if (
        "class not registered" in lowered
        or "regdb_e_classnotreg" in lowered
        or "nocomclassidentified" in lowered
        or "retrieving the com class factory" in lowered
    ):
        return (
            "Microsoft Outlook desktop is not installed or its COM integration is unavailable "
            "on this computer."
        )

    if "permission denied" in lowered and "_email_tmp" in lowered:
        return "Outlook could not attach the uploaded file automatically on this computer."

    if "new-object" in lowered and "outlook.application" in lowered:
        return "Microsoft Outlook desktop could not be opened on this computer."

    # Collapse multiline PowerShell traces into a single readable sentence.
    first_line = text.splitlines()[0].strip() if text else ""
    return first_line or "Microsoft Outlook desktop delivery failed."


def _infer_smtp_settings(sender_email):
    sender_email = str(sender_email or "").strip().lower()
    if "@" not in sender_email:
        return {}

    domain = sender_email.split("@", 1)[1]
    if domain in AUTO_SMTP_PROVIDERS:
        return dict(AUTO_SMTP_PROVIDERS[domain])

    return {
        "host": f"smtp.{domain}",
        "port": 587,
        "use_ssl": False,
    }


def _resolve_email_delivery_settings(email_settings):
    sender_email = str(
        email_settings.get("sender_email")
        or email_settings.get("username")
        or email_settings.get("from_email")
        or ""
    ).strip()
    receiver_email = str(
        email_settings.get("receiver_email")
        or email_settings.get("recipient")
        or ""
    ).strip()

    inferred = _infer_smtp_settings(sender_email)
    password, password_source = _resolve_email_password(sender_email)

    return {
        "sender_email": sender_email,
        "receiver_email": receiver_email,
        "username": sender_email,
        "from_email": sender_email,
        "recipient": receiver_email,
        "host": os.getenv("SMTP_HOST", inferred.get("host", "")).strip(),
        "port": int(os.getenv("SMTP_PORT", inferred.get("port", 587)) or 587),
        "use_ssl": inferred.get("use_ssl", False),
        "use_starttls": not inferred.get("use_ssl", False),
        "password": password,
        "password_source": password_source,
    }


def _open_smtp_client(email_settings):
    host = str(email_settings.get("host") or "").strip()
    port = int(email_settings.get("port") or 587)
    username = str(email_settings.get("username") or "").strip()
    password = str(email_settings.get("password") or "")
    use_ssl = bool(email_settings.get("use_ssl")) or port == 465
    use_starttls = email_settings.get("use_starttls")

    if use_starttls is None:
        use_starttls = not use_ssl

    if use_ssl:
        client = smtplib.SMTP_SSL(host, port, timeout=30)
    else:
        client = smtplib.SMTP(host, port, timeout=30)
        client.ehlo()
        if use_starttls:
            client.starttls()

    client.ehlo()
    if username and password:
        client.login(username, password)
    return client


def send_processed_documents_email(documents, email_settings):
    """
    Processed document payloads ko SMTP se mail karo.
    """
    resolved_settings = _resolve_email_delivery_settings(email_settings or {})
    recipient = resolved_settings["recipient"] or _resolve_document_recipient(documents)
    resolved_settings["recipient"] = recipient
    resolved_settings["receiver_email"] = recipient
    sender = resolved_settings["from_email"]
    mode = str(email_settings.get("mode") or "auto").strip().lower()

    if mode == "auto":
        mode = "combined" if len(documents or []) > 1 else "per_document"

    missing_fields = []
    if not sender:
        missing_fields.append("sender email")
    if not recipient:
        missing_fields.append("receiver email or one extracted document email")

    if missing_fields:
        return {
            "success": False,
            "sent_count": 0,
            "document_count": len(documents or []),
            "mode": mode,
            "sender": sender,
            "recipient": recipient,
            "errors": [f"Missing automatic email settings: {', '.join(missing_fields)}."],
        }

    if not documents:
        return {
            "success": False,
            "sent_count": 0,
            "document_count": 0,
            "mode": mode,
            "sender": sender,
            "recipient": recipient,
            "errors": ["No documents available for email delivery."],
        }

    if mode not in {"combined", "per_document"}:
        mode = "combined"

    if mode == "per_document":
        messages = [
            _build_single_document_email(document, recipient, sender)
            for document in documents
        ]
    else:
        messages = [_build_combined_document_email(documents, recipient, sender)]

    smtp_ready = bool(
        resolved_settings.get("host")
        and str(resolved_settings.get("port") or "").strip()
        and resolved_settings.get("password")
    )
    sent_subjects = []
    smtp_error = ""

    if smtp_ready:
        try:
            with _open_smtp_client(resolved_settings) as client:
                for message in messages:
                    client.send_message(message)
                    sent_subjects.append(message["Subject"])
            return {
                "success": True,
                "sent_count": len(messages),
                "document_count": len(documents),
                "mode": mode,
                "sender": sender,
                "recipient": recipient,
                "password_source": resolved_settings.get("password_source", ""),
                "delivery_method": "smtp",
                "subjects": sent_subjects,
                "errors": [],
            }
        except Exception as exc:
            smtp_error = str(exc).strip()
            if sent_subjects:
                return {
                    "success": False,
                    "sent_count": len(sent_subjects),
                    "document_count": len(documents),
                    "mode": mode,
                    "sender": sender,
                    "recipient": recipient,
                    "delivery_method": "smtp",
                    "errors": [smtp_error],
                    "subjects": sent_subjects,
                }

    try:
        sent_subjects = _send_messages_via_outlook(messages, sender, include_attachments=True)
        return {
            "success": True,
            "sent_count": len(messages),
            "document_count": len(documents),
            "mode": mode,
            "sender": sender,
            "recipient": recipient,
            "delivery_method": "outlook",
            "subjects": sent_subjects,
            "errors": [],
        }
    except Exception as exc:
        attachment_related = any(_extract_email_attachments(message) for message in messages)
        if attachment_related:
            try:
                sent_subjects = _send_messages_via_outlook(messages, sender, include_attachments=False)
                return {
                    "success": True,
                    "sent_count": len(messages),
                    "document_count": len(documents),
                    "mode": mode,
                    "sender": sender,
                    "recipient": recipient,
                    "delivery_method": "outlook_no_attachment",
                    "subjects": sent_subjects,
                    "errors": [
                        "Email sent without attachment because Outlook could not attach the uploaded file automatically."
                    ],
                }
            except Exception:
                pass

        errors = []
        if smtp_error:
            errors.append(f"SMTP failed: {smtp_error}")
        else:
            env_hint = (
                f"Set ADMS_EMAIL_PASSWORD__{_sender_env_key(sender)} or ADMS_EMAIL_PASSWORD, "
                "or configure Microsoft Outlook desktop with this sender account."
            )
            errors.append(
                "Automatic email delivery could not start because no background login was available. "
                + env_hint
            )
        outlook_error = _normalize_outlook_error(exc)
        if outlook_error:
            errors.append(f"Outlook failed: {outlook_error}")

        return {
            "success": False,
            "sent_count": 0,
            "document_count": len(documents),
            "mode": mode,
            "sender": sender,
            "recipient": recipient,
            "delivery_method": "unavailable",
            "errors": errors,
            "subjects": [],
        }
