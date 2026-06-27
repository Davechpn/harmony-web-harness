from __future__ import annotations

_SUPPORTED_LOCALES = {
    "en", "fr", "pt", "af", "zu", "xh", "st", "tn", "ts", "ve", "nr", "ss",
}

_DEFAULT_LOCALE = "en"


def resolve_reply_locale(
    sender_locale: str,
    tenant_default: str = "en",
    allowed_locales: list[str] | None = None,
) -> str:
    """Return the locale the agent should reply in for this sender.

    Resolution order (most specific wins):
      1. sender's locale, if it's in the allowed set
      2. tenant default locale
      3. global default ("en")
    """
    allowed = set(allowed_locales) if allowed_locales else _SUPPORTED_LOCALES

    if sender_locale in allowed:
        return sender_locale
    if tenant_default in allowed:
        return tenant_default
    return _DEFAULT_LOCALE


def locale_instruction(reply_locale: str) -> str:
    """Return a model instruction string for the given reply locale."""
    if reply_locale == "en":
        return ""
    return f"Reply in the following language: {reply_locale}."
