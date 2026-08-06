"""Text normalization helpers used for tolerant matching against HIS source data.

These never modify the original HIS value in place - callers keep the raw
value in one column and store the normalized form in a separate column,
per the "preserve original HIS data" requirement.
"""
import re

_WS_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[.\-_/\\]")


def normalize(value) -> str:
    """Case-insensitive, whitespace-collapsed, punctuation-flattened key for matching."""
    if value is None:
        return ""
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return ""
    text = _WS_RE.sub(" ", text)
    text = text.strip().lower()
    text = _PUNCT_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text).strip()
    return text


def clean_display(value) -> str:
    """Trim/collapse whitespace only, for values shown to a user (not lowercased)."""
    if value is None:
        return ""
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return ""
    return _WS_RE.sub(" ", text).strip()
