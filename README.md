<<<<<<< HEAD
# 🤖 AI-Powered Document Management System
### Pavitrasoft Technologies — Demo Project

---

## 📋 What This System Does

Automatically reads ANY document → extracts names → detects language →
translates → summarizes → routes to correct folder!

```
📄 Upload Document
      ↓
📥 Step 1: INGEST      → Detect file type
      ↓
📄 Step 2: EXTRACT     → Read text (DOCX/PDF/XLSX/TXT/Image)
      ↓
🌐 Step 3: TRANSLATE   → Auto-detect & translate to English
      ↓
🧠 Step 4: NLP         → Extract Name, ID, Department etc.
      ↓
📝 Step 5: SUMMARIZE   → 3-sentence AI summary
      ↓
📁 Step 6: ROUTE       → Save to: output/FirstName/Surname/Father_ID/
```

---

## 📁 Project Structure

```
AI_DMS/
├── main.py                  ← RUN THIS! Master pipeline
├── config.py                ← All settings
├── requirements.txt         ← Install libraries
├── create_samples.py        ← Creates test documents
│
├── modules/
│   ├── ingestion.py         ← File router
│   ├── extractor.py         ← Text extraction
│   ├── ocr.py               ← Image OCR
│   ├── nlp_parser.py        ← Name/ID extraction
│   ├── translator.py        ← Language translation
│   ├── summarizer.py        ← AI summarization
│   └── router.py            ← Folder routing
│
├── sample_documents/        ← Test files (7 languages)
│   ├── english_pooja_patel.docx
│   ├── hindi_rahul_sharma.docx
│   ├── gujarati_hardik_pandya.docx
│   ├── french_priya_shah.txt
│   ├── spanish_raj_mehta.txt
│   ├── employee_performance_report.xlsx
│   └── neha_singh_report.pdf
│
├── output/                  ← Auto-created routed folders
│   ├── Neha/Singh/Manoj_Singh_BE-303/
│   ├── Raj/Mehta/Sunil_Mehta_FIN-101/
│   └── _batch_summary.json
│
└── logs/                    ← Processing logs
```

---

## ⚙️ Setup — First Time Only

### Step 1: Install Python libraries
```bash
pip install -r requirements.txt
```

### Step 2: Create sample documents
```bash
python create_samples.py
```

### Step 3: Run the system!
```bash
# Process all sample documents
python main.py

# Process single file
python main.py --file "path/to/your/document.pdf"

# Process custom folder
python main.py --folder "D:\YourFolder"
```

---

## 📄 Supported File Types

| Format   | Extension        | Method Used     |
|----------|-----------------|-----------------|
| Word     | .docx           | python-docx     |
| PDF      | .pdf            | pdfplumber      |
| Excel    | .xlsx           | openpyxl        |
| Text     | .txt            | built-in        |
| Image    | .jpg .png       | pytesseract OCR |

---

## 🌐 Supported Languages

| Language  | Code | Auto-detected |
|-----------|------|---------------|
| English   | en   | ✅            |
| Hindi     | hi   | ✅ (Unicode)  |
| Gujarati  | gu   | ✅ (Unicode)  |
| Marathi   | mr   | ✅ (Unicode)  |
| French    | fr   | ✅ (Keywords) |
| German    | de   | ✅ (Keywords) |
| Spanish   | es   | ✅ (Keywords) |

> Translation requires internet (Google Translate API via deep-translator)

---

## 📁 Output Folder Structure

For a document belonging to "Pooja Patel" (Father: Bhadhreshkumar, ID: DEV-402):

```
output/
  └── Pooja/
        └── Patel/
              └── Bhadhreshkumar_DEV-402/
                    ├── patel_pooja.docx        ← original file
                    └── _report.json            ← processing report
```

---

## 📊 JSON Report Sample

```json
{
  "timestamp": "2025-04-01 10:30:00",
  "file": "english_pooja_patel.docx",
  "original_lang": "en",
  "was_translated": false,
  "entities": {
    "first_name": "Pooja",
    "surname": "Patel",
    "father_name": "Bhadhreshkumar Patel",
    "unique_id": { "type": "Emp ID", "value": "DEV-402" },
    "department": "Software Development",
    "email": "pooja.patel@company.com"
  },
  "summary": "Pooja Patel is a Frontend Engineer at Pavitrasoft...",
  "folder": "output/Pooja/Patel/Bhadhreshkumar_Patel_DEV-402"
}
```

---

## 🚀 Next Steps (Phase 3 of your project)

1. ✅ Document Reading   — Done!
2. ✅ Name Extraction    — Done!
3. ✅ Language Detection — Done!
4. ✅ AI Summarization   — Done!
5. ✅ Auto Routing       — Done!
6. 🔜 Email Sending     — Next: sender.py
7. 🔜 Web UI            — Then: Flask/Streamlit app

---

Built with ❤️ by Pooja Patel | Pavitrasoft Technologies
=======
# Automatic-Document-Management-System
The Automatic Document Management System is an AI-powered platform that lets users upload documents and automatically extracts key details like name, date, and document type. It also creates a short summary and can automatically send the file to the required person through email or WhatsApp, saving time and reducing manual work.
>>>>>>> dac9de21e462293e3e9f4dc72a5f9b1ede15925f
