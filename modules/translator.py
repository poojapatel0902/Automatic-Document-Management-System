# ============================================
# MODULE 5: TRANSLATOR.PY
# Language Detection + Translation to English
# ============================================

import os, sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import Colors, cprint, SUPPORTED_LANGUAGES
from modules.multilingual import process_multilingual_text, transliterate_name_to_english

def detect_language(text):
    """Auto-detect language from text"""
    # Simple Unicode-based detection (no library needed)
    if not text: return "en"
    counts = {
        "hi": sum(1 for c in text if '\u0900' <= c <= '\u097F'),
        "gu": sum(1 for c in text if '\u0A80' <= c <= '\u0AFF'),
        "ar": sum(1 for c in text if '\u0600' <= c <= '\u06FF'),
        "zh": sum(1 for c in text if '\u4E00' <= c <= '\u9FFF'),
        "ja": sum(1 for c in text if '\u3040' <= c <= '\u30FF'),
    }
    total = max(len(text), 1)
    ratios = {k: v/total for k, v in counts.items()}
    detected = max(ratios, key=ratios.get)
    if ratios[detected] > 0.10:
        lang_name = SUPPORTED_LANGUAGES.get(detected, detected)
        cprint(f"  🌐 Language detected: {lang_name} ({detected})", Colors.CYAN)
        return detected
    # Try langdetect if available
    try:
        from langdetect import detect
        lang = detect(text[:1000])
        cprint(f"  🌐 Language detected: {SUPPORTED_LANGUAGES.get(lang, lang)} ({lang})", Colors.CYAN)
        return lang
    except Exception:
        pass
    cprint(f"  🌐 Language: English (en) — default", Colors.CYAN)
    return "en"

def translate_text(text, source_lang="auto", target_lang="en"):
    """Translate text to English using deep-translator"""
    if not text or not text.strip():
        return text, "en"
    if source_lang == "auto":
        source_lang = detect_language(text)
    if source_lang == "en":
        cprint("  ✅ Already in English — no translation needed", Colors.GREEN)
        return text, "en"
    cprint(f"  🔄 Translating {source_lang} → {target_lang}...", Colors.YELLOW)
    try:
        from deep_translator import GoogleTranslator
        chunks = [text[i:i+4500] for i in range(0, len(text), 4500)]
        t = GoogleTranslator(source=source_lang, target=target_lang)
        result = "\n".join(filter(None, [t.translate(c) for c in chunks]))
        cprint(f"  ✅ Translation complete!", Colors.GREEN)
        return result, target_lang
    except ImportError:
        cprint("  ⚠️  deep-translator not installed: pip install deep-translator", Colors.YELLOW)
        return text, source_lang
    except Exception as e:
        cprint(f"  ⚠️  Translation error: {e}", Colors.YELLOW)
        return text, source_lang

def detect_and_translate(text):
    """One-step: detect language + translate to English"""
    detected = detect_language(text)
    if detected == "en":
        return text, "en", False
    translated, final = translate_text(text, source_lang=detected)
    return translated, detected, (final == "en")
