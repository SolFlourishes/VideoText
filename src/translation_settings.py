"""Central application policy for optional cloud translation.

This module deliberately contains no credential, provider client, or environment
lookup. Model replacement is a maintenance decision after corpus evaluation.
"""

OPENAI_TRANSLATION_MODEL = "gpt-4.1-mini"

# The normal GUI exposes labels from this fixed list only.  The first choice is
# deliberately the recommended, corpus-tested application default.
RECOMMENDED_OPENAI_MODEL_LABEL = f"Recommended — {OPENAI_TRANSLATION_MODEL}"
VETTED_OPENAI_TRANSLATION_MODELS = (
    (RECOMMENDED_OPENAI_MODEL_LABEL, OPENAI_TRANSLATION_MODEL),
)

# User-facing locale labels are centralized data, while BCP-47 identifiers are
# retained internally and in provenance.  Additional validated locales can be
# appended without changing provider, export, or review architecture.
TRANSLATION_TARGET_LOCALES = (
    ("pt-BR", "Portuguese — Brazil"),
    ("en-CA", "English — Canada"),
    ("es-419", "Spanish — Latin America"),
    ("es-ES", "Spanish — Spain"),
    ("ko-KR", "Korean — South Korea"),
    ("nl-NL", "Dutch — Netherlands"),
    ("fr", "French"),
    ("it", "Italian"),
    ("ja", "Japanese"),
    ("zh", "Chinese"),
    ("ar", "Arabic"),
)


def translation_locale_display_name(locale: str) -> str:
    """Return the approved user-facing label for one stored locale code."""

    for code, label in TRANSLATION_TARGET_LOCALES:
        if code == locale:
            return label
    return locale


def resolve_vetted_openai_model(label: str) -> str:
    """Resolve one GUI-visible vetted choice without accepting arbitrary IDs."""

    for visible_label, model in VETTED_OPENAI_TRANSLATION_MODELS:
        if label == visible_label:
            return model
    raise ValueError("Select a vetted OpenAI translation model.")
