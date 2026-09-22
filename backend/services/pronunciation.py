"""Pronunciation dictionary — reusable fixes for terms the engine says wrong.

Names, acronyms, brands and loanwords come out wrong and there is no way to
correct them short of editing the text every time (#827). This maps a term to a
respelling applied just before TTS.

Respelling rather than phonemes on purpose: every engine reads plain text, so
``bandeja -> ban-DEH-ha`` works on all of them, where a phoneme string only
works on the engines that accept one. It is cruder and it is portable.

Applied at generation time, not when the text is saved, so ``generations.text``
keeps what the author wrote. Editing an entry then changes future audio without
rewriting history, and the History tab never shows a reader ``ban-DEH-ha``.
"""

import logging
import re

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..database import PronunciationEntry

logger = logging.getLogger(__name__)

# Paralinguistic tags like [laugh] are engine syntax, not speech. A term that
# happens to appear inside one must not be rewritten.
_TAG_RE = re.compile(r"\[[^\]]*\]")


def get_entries(
    db: Session,
    language: str | None = None,
    profile_id: str | None = None,
    include_disabled: bool = False,
) -> list[PronunciationEntry]:
    """Entries that apply to a given language and profile.

    An entry with a NULL language or profile is a wildcard, so the filters ask
    for "matches, or unset" rather than equality.
    """
    q = db.query(PronunciationEntry)
    if not include_disabled:
        q = q.filter(PronunciationEntry.enabled.is_(True))
    if language is not None:
        q = q.filter(
            or_(PronunciationEntry.language.is_(None), PronunciationEntry.language == language)
        )
    if profile_id is not None:
        q = q.filter(
            or_(PronunciationEntry.profile_id.is_(None), PronunciationEntry.profile_id == profile_id)
        )
    else:
        q = q.filter(PronunciationEntry.profile_id.is_(None))
    return q.all()


def _match_case(source: str, replacement: str) -> str:
    """Carry the matched text's capitalisation onto the replacement.

    A term at the start of a sentence is capitalised there and nowhere else, so
    storing one lowercase entry has to cover both.

    "All caps" counts *cased* characters, not ``str.isupper()``: that returns
    True for ``C++``, which has one cased letter, and shouting the replacement
    would turn ``C plus plus`` into ``C PLUS PLUS``. An acronym like ``WCAG``
    has four and is genuinely all caps.
    """
    cased = [c for c in source if c.isalpha()]
    if len(cased) > 1 and all(c.isupper() for c in cased):
        return replacement.upper()
    if source[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def _tag_spans(text: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in _TAG_RE.finditer(text)]


def build_pattern(terms: list[str]) -> re.Pattern | None:
    """One alternation over every term, longest first.

    Longest-first matters twice. It lets a multi-word entry beat the
    single-word entry inside it, and because this is a single pass, a
    replacement can never be re-matched by another rule — so
    ``bandeja -> ban-DEH-ha`` and ``ha -> hah`` cannot compound into
    ``ban-DEH-hah``, which is what a loop of per-term substitutions would do.

    Lookarounds rather than ``\\b`` so terms that start or end with punctuation
    still anchor on a word boundary.
    """
    usable = [t for t in terms if t and t.strip()]
    if not usable:
        return None

    plain = [t for t in usable if not _is_arabic(t)]
    groups: list[str] = []

    # Arabic terms, split by which attached prefixes they may carry. Each
    # group's stems are folded and deduplicated, longest first.
    stems: dict[str, set[str]] = {"art": set(), "long": set(), "short": set()}
    for t in usable:
        if not _is_arabic(t):
            continue
        category, stem = _arabic_category(t)
        stems[category].add(stem)
    for category in ("art", "long", "short"):
        if not stems[category]:
            continue
        ordered = sorted(stems[category], key=len, reverse=True)
        alternation = "|".join(_arabic_regex(s) for s in ordered)
        groups.append(
            rf"(?P<lead_{category}>{_ARABIC_LEADS[category]})(?P<core_{category}>{alternation})"
        )

    if plain:
        ordered = sorted(set(plain), key=len, reverse=True)
        groups.append(rf"(?P<plain>{'|'.join(re.escape(t) for t in ordered)})")

    return re.compile(rf"(?<!\w)(?:{'|'.join(groups)})(?!\w)", re.IGNORECASE | re.UNICODE)


# ── Arabic ───────────────────────────────────────────────────────────
#
# Plain word-boundary matching misses most Arabic in real text, for two
# reasons. Diacritics: ``محمد`` must match ``مُحَمَّد``, and ``أحمد`` must match
# the common hamza-less spelling ``احمد``. Attached prefixes: the conjunctions
# و/ف, the prepositions ب/ل/ك and the article ال are written joined to the
# next word, so ``الرياض`` also appears as ``بالرياض``, ``والرياض`` and
# ``للرياض``. The prefix is kept in the output; only the term is replaced.
#
# Prefixes are ambiguous — ``كمال`` is a name, not ك + ``مال`` — so the bare
# prepositions ب/ل/ك are only accepted before terms of four or more letters.
# Short terms match on their own or behind the article, which is never
# ambiguous.

_ARABIC_LETTER = re.compile(r"[ء-يٱ-ۓ]")
_ARABIC_MARKS = "ؐ-ًؚ-ٰٟۖ-ۭـ"
_ARABIC_MARK_RE = re.compile(f"[{_ARABIC_MARKS}]")
_M = f"[{_ARABIC_MARKS}]*"

# Letters that are written interchangeably; folded for comparison and
# matched as a class.
_ARABIC_FOLD = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ة": "ه"})  # noqa: RUF001
_ARABIC_CLASS = {"ا": "[اأإآٱ]", "ي": "[يى]", "ه": "[هة]"}  # noqa: RUF001

_WF = f"(?:[وف]{_M})?"
_ARTICLE = f"(?:{_WF}(?:[بك]{_M})?[اٱ]{_M}ل{_M}|{_WF}ل{_M}ل{_M})"
_ARABIC_LEADS = {
    "art": _ARTICLE,
    "long": f"(?:{_ARTICLE}|{_WF}(?:[بلك]{_M})?)",
    "short": f"(?:{_ARTICLE})?",
}

# The article at the end of a matched prefix: ``ال`` or, after ل, just ``ل``.
_TRAILING_ARTICLE = re.compile(f"(?:[اٱ]{_M})?ل{_M}$")
_LEADING_ARTICLE = re.compile(f"^[اأٱ]{_M}ل{_M}")


def _is_arabic(term: str) -> bool:
    return bool(_ARABIC_LETTER.search(term))


def _fold_arabic(text: str) -> str:
    return _ARABIC_MARK_RE.sub("", text).translate(_ARABIC_FOLD)


def _arabic_category(term: str) -> tuple[str, str]:
    """Which prefixes a term may carry, and the stem the pattern matches."""
    folded = _fold_arabic(term.strip())
    if folded.startswith("ال") and len(folded) > 2:
        return "art", folded[2:]
    letters = sum(1 for c in folded if not c.isspace())
    return ("long" if letters >= 4 else "short"), folded


def _arabic_regex(folded: str) -> str:
    """Match *folded* with any diacritics, and either spelling of a folded letter."""
    return "".join(_ARABIC_CLASS.get(c, re.escape(c)) + _M for c in folded)


def _term_key(term: str):
    return ("ar", _fold_arabic(term.strip())) if _is_arabic(term) else term.lower()


def _arabic_substitute(m: re.Match, by_term: dict) -> tuple[str, PronunciationEntry] | None:
    groups = m.groupdict()
    for category in ("art", "long", "short"):
        core = groups.get(f"core_{category}")
        if core is None:
            continue
        lead = groups.get(f"lead_{category}") or ""
        stem = _fold_arabic(core)
        if category == "art":
            entry = by_term.get(("ar", "ال" + stem))
            if entry is None:
                return None
            # The text already carries the article, possibly as ``لل``.
            if _fold_arabic(entry.replacement).startswith("ال"):
                return lead + _LEADING_ARTICLE.sub("", entry.replacement), entry
            return _TRAILING_ARTICLE.sub("", lead) + entry.replacement, entry
        entry = by_term.get(("ar", stem))
        if entry is None:
            return None
        return lead + entry.replacement, entry
    return None


def apply_pronunciations(
    text: str,
    language: str | None,
    db: Session,
    profile_id: str | None = None,
) -> tuple[str, list[dict]]:
    """Rewrite *text* using the dictionary.

    Returns the rewritten text and a record of what was replaced, so a caller
    can log or surface it — a silent rewrite of someone's script is worse than
    no rewrite at all.
    """
    if not text or not text.strip():
        return text, []

    entries = get_entries(db, language=language, profile_id=profile_id)
    if not entries:
        return text, []

    # A profile-scoped entry beats a global one for the same term; a
    # language-specific entry beats a wildcard. Sorting the losers first lets
    # the later assignment win.
    by_term: dict = {}
    for e in sorted(
        entries,
        key=lambda e: ((e.profile_id is not None), (e.language is not None)),
    ):
        by_term[_term_key(e.term)] = e

    pattern = build_pattern([e.term for e in by_term.values()])
    if pattern is None:
        return text, []

    skip = _tag_spans(text)
    applied: list[dict] = []

    def substitute(m: re.Match) -> str:
        if any(start <= m.start() < end for start, end in skip):
            return m.group(0)
        if m.groupdict().get("plain") is None:
            found = _arabic_substitute(m, by_term)
            if found is None:
                return m.group(0)
            out, entry = found
            applied.append({"term": m.group(0), "replacement": out, "entry_id": entry.id})
            return out
        entry = by_term.get(m.group(0).lower())
        if entry is None:
            return m.group(0)
        out = _match_case(m.group(0), entry.replacement)
        applied.append({"term": m.group(0), "replacement": out, "entry_id": entry.id})
        return out

    result = pattern.sub(substitute, text)
    if applied:
        # Terms are user-supplied and are often names, so the values stay at
        # DEBUG; INFO carries only how many were rewritten.
        logger.info("Pronunciation dictionary rewrote %d term(s)", len(applied))
        logger.debug(
            "Pronunciation substitutions: %s",
            ", ".join(f"{a['term']}->{a['replacement']}" for a in applied),
        )
    return result, applied


def find_duplicate(
    db: Session,
    term: str,
    language: str | None,
    profile_id: str | None,
    exclude_id: str | None = None,
) -> PronunciationEntry | None:
    """An existing entry for the same term in the same scope.

    An early check so the caller can return a useful 409 naming the existing
    entry. The database enforces the same rule via ``uq_pronunciation_scope``,
    which is what actually holds under concurrent creates.

    Compares ``lower(term)`` rather than ``ilike``: a term is a literal, and
    ``ilike`` would read ``%`` and ``_`` in it as wildcards, so ``band_ja``
    would collide with ``bandeja``. Trimmed first, because the route stores the
    trimmed value and an untrimmed lookup would miss its own duplicate.
    """
    normalized = term.strip().lower()
    q = db.query(PronunciationEntry).filter(func.lower(PronunciationEntry.term) == normalized)
    q = (
        q.filter(PronunciationEntry.language.is_(None))
        if language is None
        else q.filter(PronunciationEntry.language == language)
    )
    q = (
        q.filter(PronunciationEntry.profile_id.is_(None))
        if profile_id is None
        else q.filter(PronunciationEntry.profile_id == profile_id)
    )
    if exclude_id:
        q = q.filter(PronunciationEntry.id != exclude_id)
    return q.first()
