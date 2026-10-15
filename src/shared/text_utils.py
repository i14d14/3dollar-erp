from __future__ import annotations
import unicodedata
from typing import Optional


# Mapping of common Chinese/CJK full-width punctuation to standard half-width ASCII
_PUNCTUATION_MAP = {
    "（": "(",
    "）": ")",
    "：": ":",
    "，": ",",
    "；": ";",
    "！": "!",
    "？": "?",
    "【": "[",
    "】": "]",
    "［": "[",
    "］": "]",
    "｛": "{",
    "｝": "}",
    "“": '"',
    "”": '"',
    "‘": "'",
    "’": "'",
    "～": "~",
    "—": "-",
    "－": "-",
    "＿": "_",
    "／": "/",
    "＼": "\\",
    "｜": "|",
    "　": " ",  # Full-width space (Ideographic Space U+3000)
}


def to_half_width(text: Optional[str]) -> str:
    """Normalize text by converting full-width ASCII/Latin characters, numbers,
    and common full-width punctuation marks into half-width standard characters.

    Standard CJK ideographs (Chinese characters) remain unaffected.
    """
    if text is None:
        return ""
    
    s = str(text)
    if not s:
        return ""

    # 1. NFKC normalization converts full-width numbers (０-９), letters (Ａ-Ｚ, ａ-ｚ),
    # and standard compatibility variants into half-width ASCII.
    normalized = unicodedata.normalize("NFKC", s)

    # 2. Convert common CJK full-width punctuation marks to standard half-width
    for full_char, half_char in _PUNCTUATION_MAP.items():
        if full_char in normalized:
            normalized = normalized.replace(full_char, half_char)

    return normalized
