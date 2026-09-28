"""
Saying it back in the language it was said in.

v1 got half of multi-language right: Whisper auto-detects, so an Urdu voice
note transcribed fine. Then the confirmation sentence, every error and every
"couldn't find that customer" came back in English. For the AI WhatsApp
Assistant's "multi-language conversations" promise that's the half that
faces the customer.

Two mechanisms, because the two kinds of text have different economics:

- **Model-generated text** (the plan summary) costs nothing extra to
  localise: `language_instruction()` appends one line to the planning
  prompt telling it which language to write `summary` in. Same call, same
  tokens, right language.

- **Fixed strings** (errors, status labels) are a closed set, so they live
  in the `MESSAGES` table below and are looked up. No model call to tell
  someone a phone number is missing.

Unknown language -> English. A missing translation falls back to the English
string rather than showing a bare key, so adding a language is additive and
can never break a working locale. `LANGUAGE_NAMES` exists so the prompt can
say "write in Urdu" rather than "write in ur", which measurably improves
compliance.
"""
from typing import Any

DEFAULT_LOCALE = "en"

LANGUAGE_NAMES: dict[str, str] = {
    "en": "English",
    "ur": "Urdu",
    "ar": "Arabic",
    "hi": "Hindi",
    "pa": "Punjabi",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "pt": "Portuguese",
    "id": "Indonesian",
    "tr": "Turkish",
    "zh": "Chinese",
}

# Keys are stable identifiers used in code; only English is required.
MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        "no_customer_named": "No customer named in the command.",
        "customer_not_found": 'No customer matching "{name}" was found.',
        "customer_ambiguous": '"{name}" matches more than one customer ({names}) — use their full name.',
        "no_email_on_file": "{name} has no email address on file.",
        "no_phone_on_file": "{name} has no phone number on file.",
        "nothing_understood": "Couldn't work out what to do from that.",
        "transcription_failed": "Couldn't make out the audio. Try again somewhere quieter.",
        "quota_exceeded": "This month's AI request allowance is used up. Upgrade the plan or wait for the reset.",
        "storage_exceeded": "Storage limit reached. Delete old recordings or upgrade the plan.",
        "not_permitted": "Your role isn't allowed to do that ({intent}). Ask an administrator.",
        "step_skipped": "Skipped because an earlier step in the command failed.",
        "confirm_needed": "Confirm before this is sent.",
        "executed": "Done.",
    },
    "ur": {
        "no_customer_named": "کمانڈ میں کسی کسٹمر کا نام نہیں لیا گیا۔",
        "customer_not_found": '"{name}" نام کا کوئی کسٹمر نہیں ملا۔',
        "customer_ambiguous": '"{name}" ایک سے زیادہ کسٹمرز سے میل کھاتا ہے ({names}) — پورا نام بولیں۔',
        "no_email_on_file": "{name} کا ای میل ایڈریس ریکارڈ میں نہیں ہے۔",
        "no_phone_on_file": "{name} کا فون نمبر ریکارڈ میں نہیں ہے۔",
        "nothing_understood": "سمجھ نہیں آیا کہ کیا کرنا ہے۔",
        "transcription_failed": "آواز صاف نہیں تھی۔ دوبارہ کوشش کریں۔",
        "quota_exceeded": "اس مہینے کی AI ریکویسٹ کی حد ختم ہو چکی ہے۔",
        "storage_exceeded": "اسٹوریج کی حد ختم ہو چکی ہے۔",
        "not_permitted": "آپ کے رول کو اس کام کی اجازت نہیں ({intent})۔",
        "step_skipped": "پچھلا مرحلہ ناکام ہونے کی وجہ سے چھوڑ دیا گیا۔",
        "confirm_needed": "بھیجنے سے پہلے تصدیق کریں۔",
        "executed": "ہو گیا۔",
    },
    "ar": {
        "no_customer_named": "لم يُذكر اسم عميل في الأمر.",
        "customer_not_found": 'لا يوجد عميل مطابق لـ "{name}".',
        "customer_ambiguous": '"{name}" يطابق أكثر من عميل ({names}) — استخدم الاسم الكامل.',
        "no_email_on_file": "لا يوجد بريد إلكتروني مسجل لـ {name}.",
        "no_phone_on_file": "لا يوجد رقم هاتف مسجل لـ {name}.",
        "nothing_understood": "لم أفهم المطلوب.",
        "transcription_failed": "تعذّر فهم التسجيل الصوتي.",
        "quota_exceeded": "انتهت حصة طلبات الذكاء الاصطناعي لهذا الشهر.",
        "storage_exceeded": "تم بلوغ حد التخزين.",
        "not_permitted": "صلاحيتك لا تسمح بهذا الإجراء ({intent}).",
        "step_skipped": "تم التخطي لأن خطوة سابقة فشلت.",
        "confirm_needed": "أكد قبل الإرسال.",
        "executed": "تم.",
    },
}


def normalize_locale(language: Any) -> str:
    """Whisper returns things like "en", "english", "ur-PK". Squash all of
    it to a bare two-letter code we have messages for, or English."""
    if not language:
        return DEFAULT_LOCALE
    code = str(language).strip().lower().replace("_", "-").split("-")[0]
    if code in LANGUAGE_NAMES:
        return code
    for short, name in LANGUAGE_NAMES.items():
        if code == name.lower():
            return short
    return DEFAULT_LOCALE


def t(key: str, locale: str = DEFAULT_LOCALE, **kwargs: Any) -> str:
    """Look up a fixed string. Falls back English -> raw key, and swallows
    formatting errors: a missing placeholder in one translation must not
    turn into a 500 on an error path."""
    locale = normalize_locale(locale)
    template = MESSAGES.get(locale, {}).get(key) or MESSAGES[DEFAULT_LOCALE].get(key) or key
    try:
        return template.format(**kwargs)
    except (KeyError, IndexError):
        return template


def language_instruction(locale: str) -> str:
    """One line appended to the planning prompt. Note it scopes the
    instruction to `summary` only — slot values (customer names, product
    descriptions) must stay in the language they were spoken in, or
    `_resolve_customer` stops matching rows in the database."""
    locale = normalize_locale(locale)
    if locale == DEFAULT_LOCALE:
        return ""
    name = LANGUAGE_NAMES.get(locale, locale)
    return (
        f'\n- Write the "summary" field in {name}, the language the speaker used. '
        f"Keep intent names, slot keys and proper nouns (customer names, product names, "
        f"quotation numbers) exactly as they are — translate only the sentence."
    )
