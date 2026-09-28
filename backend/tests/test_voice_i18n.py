"""
Multi-language output — the half of "multi-language conversations" v1 missed.
"""
from app import voice_i18n


def test_locale_normalisation_handles_what_whisper_actually_returns():
    assert voice_i18n.normalize_locale("ur-PK") == "ur"
    assert voice_i18n.normalize_locale("English") == "en"
    assert voice_i18n.normalize_locale("klingon") == "en"
    assert voice_i18n.normalize_locale(None) == "en"


def test_known_message_is_translated():
    assert voice_i18n.t("no_customer_named", "ur") != voice_i18n.t("no_customer_named", "en")


def test_missing_translation_falls_back_to_english_not_to_the_key():
    text = voice_i18n.t("confirm_needed", "fr")
    assert text == voice_i18n.MESSAGES["en"]["confirm_needed"]


def test_placeholders_are_filled_in_every_locale():
    for locale in voice_i18n.MESSAGES:
        assert "Acme" in voice_i18n.t("customer_not_found", locale, name="Acme")


def test_a_missing_placeholder_does_not_raise():
    assert voice_i18n.t("customer_not_found", "en")  # no name= supplied


def test_language_instruction_is_empty_for_english_and_scoped_for_others():
    assert voice_i18n.language_instruction("en") == ""
    instruction = voice_i18n.language_instruction("ur")
    assert "Urdu" in instruction and "summary" in instruction
