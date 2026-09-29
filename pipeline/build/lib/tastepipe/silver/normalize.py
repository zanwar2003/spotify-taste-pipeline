"""Text normalization for entity resolution.

The goal is to make *the same recording* compare equal across re-releases
("Song - 2011 Remaster", "Song (Remastered)", "Song") while keeping *different
recordings* apart (a live take, a remix, a re-recording).
"""

from __future__ import annotations

import re
import unicodedata

ISRC_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{3}\d{7}$")
SPOTIFY_ID_RE = re.compile(r"^[0-9A-Za-z]{22}$")

# Suffix segments that describe a *different recording*: kept as a version tag.
_VERSION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("live", re.compile(r"\blive\b|\bunplugged\b|\bin concert\b")),
    ("remix", re.compile(r"\bremix\b|\brework\b|\bbootleg\b|\bmashup\b")),
    ("acoustic", re.compile(r"\bacoustic\b|\bstripped\b")),
    ("instrumental", re.compile(r"\binstrumental\b|\bkaraoke\b")),
    ("demo", re.compile(r"\bdemo\b|\bsession\b")),
    ("altered", re.compile(r"\bsped up\b|\bslowed\b|\breverb\b|\bnightcore\b|\b8d\b")),
    ("rerecording", re.compile(r"\b\w+'s version\b|\bre-?recorded\b")),
]

# Segments that describe the same recording re-released: dropped.
_NOISE_RE = re.compile(
    r"\bremaster(?:ed)?\b|\bmono\b|\bstereo\b|\bdeluxe\b|\bbonus track\b|\balbum version\b"
    r"|\bsingle version\b|\bradio edit\b|\bexplicit\b|\bclean\b|\bexpanded\b|^\d{4}$"
)
_FEAT_RE = re.compile(r"^(?:feat\b|ft\b|featuring\b|with\b)")

_SEGMENT_RE = re.compile(r"\s*[\(\[]([^\)\]]*)[\)\]]|\s+-\s+(.*)$")
_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)


def _fold(text: str) -> str:
    """Casefold, strip accents, unify '&' and whitespace."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.casefold().replace("&", " and ").replace("\u2019", "'").replace("\u2018", "'")
    return text


def _squash(text: str) -> str:
    text = _PUNCT_RE.sub(" ", text.replace("'", ""))
    return re.sub(r"\s+", " ", text).strip()


def normalize_title(title: str) -> tuple[str, str]:
    """Return (normalized_title, version_tag). version_tag is '' for the original cut."""
    folded = _fold(title)
    tags: list[str] = []

    def classify(match: re.Match[str]) -> str:
        segment = (match.group(1) if match.group(1) is not None else match.group(2)).strip()
        if _FEAT_RE.match(segment):
            return ""
        for tag, pattern in _VERSION_PATTERNS:
            if pattern.search(segment):
                tags.append(tag)
                return ""
        if _NOISE_RE.search(segment):
            return ""
        # Unknown segment, e.g. "(I Can't Get No) Satisfaction": part of the real title.
        return f" {segment} " if match.group(1) is not None else f" {segment}"

    base = _SEGMENT_RE.sub(classify, folded)
    return _squash(base), "+".join(sorted(set(tags)))


def normalize_artist(name: str) -> str:
    return _squash(_fold(name))


def clean_isrc(value: str | None) -> str | None:
    """Return an upper-case, hyphen-free ISRC if it is well-formed, else None."""
    if not value:
        return None
    candidate = value.replace("-", "").replace(" ", "").upper()
    return candidate if ISRC_RE.match(candidate) else None
