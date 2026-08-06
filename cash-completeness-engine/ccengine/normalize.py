"""GL account normalization for the cash-completeness engine.

Real-world GL keys arrive in several equivalent spellings -- with or without
a zero filler segment, as strings or as bare numbers exported from a
spreadsheet. Matching a bank register to a trial balance line only works if
both sides collapse to one canonical key first, so every module in
:mod:`ccengine` matches on the output of :func:`normalize_gl` and never on
the raw cell.

Canonical form
--------------
``XXX-XXX-XXXX`` (region - entity - natural account), e.g.::

    normalize_gl("615-001-00-1133")  -> "615-001-1133"
    normalize_gl("615-001-1133")     -> "615-001-1133"
    normalize_gl(6150011133)         -> "615-001-1133"

Inputs that do not carry exactly ten significant digits (after dropping
zero-only filler segments) are returned as their bare digit string, and
inputs with no digits at all (e.g. a mis-keyed ``"BAL"``) are returned
verbatim. Both stay deterministic, so two identical typos still match each
other -- and :func:`is_placeholder_gl` exists to flag them for review
instead of letting them pass as real accounts.

All account numbers appearing in examples and tests are fictional.
"""

from __future__ import annotations

import re
from typing import Union

GLLike = Union[str, int, float]

#: Number of significant digits in a canonical GL key.
_CANONICAL_DIGITS = 10

#: Segment lengths of the canonical form.
_SEGMENTS = (3, 3, 4)

#: Prefix that marks a mis-keyed placeholder row (e.g. a "BAL" line typed
#: into the GL column as 001-001-...). Fictional convention for this demo.
_PLACEHOLDER_PREFIX = "001-001-"

_DIGIT_RUN = re.compile(r"\d+")


def normalize_gl(value: GLLike) -> str:
    """Collapse a GL account key to its canonical ``XXX-XXX-XXXX`` form.

    Tolerant of strings, ints, whole floats (spreadsheet exports), stray
    whitespace, byte-order marks, and the optional ``-00-`` filler segment.

    Parameters
    ----------
    value:
        The GL key as it appears in the source file.

    Returns
    -------
    str
        The canonical ten-digit form when the input carries exactly ten
        significant digits; otherwise the bare digit string; otherwise (no
        digits at all) the stripped input verbatim.

    Raises
    ------
    ValueError
        If ``value`` is ``None``, blank, a boolean, or a non-whole float.
    """
    if value is None:
        raise ValueError("GL account is None")
    if isinstance(value, bool):
        raise ValueError(f"GL account cannot be a boolean: {value!r}")
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError(f"GL account float is not finite: {value!r}")
        if not value.is_integer():
            raise ValueError(
                f"GL account float must be a whole number, got {value!r}"
            )
        value = int(value)
    if isinstance(value, int):
        text = str(value)
    else:
        text = str(value).replace("\ufeff", "").strip()
    if not text:
        raise ValueError("GL account is blank")

    segments = _DIGIT_RUN.findall(text)
    if not segments:
        # No digits at all (e.g. a mis-keyed "BAL"). Pass through verbatim
        # so the row stays visible and identical typos still match.
        return text

    # Drop zero-only *interior* filler segments: 615-001-00-1133 and
    # 615-001-1133 are the same account. Leading/trailing segments are
    # positional and always kept.
    if len(segments) > 2:
        segments = (
            [segments[0]]
            + [s for s in segments[1:-1] if set(s) != {"0"}]
            + [segments[-1]]
        )
    digits = "".join(segments)

    # Unseparated twelve-digit exports (615001001133) carry the same filler
    # in positions 7-8; strip it when it is exactly "00".
    if len(digits) == _CANONICAL_DIGITS + 2 and digits[6:8] == "00":
        digits = digits[:6] + digits[8:]

    if len(digits) == _CANONICAL_DIGITS:
        a, b, c = _SEGMENTS
        return f"{digits[:a]}-{digits[a:a + b]}-{digits[a + b:]}"
    return digits


def is_placeholder_gl(value: GLLike) -> bool:
    """Return ``True`` when a GL key looks mis-keyed rather than real.

    This is the "typo line" detector: trial balances sometimes carry rows
    whose GL column holds a balance label or filler key instead of a real
    account. Such rows must be flagged for review, never matched or summed
    as if they were accounts.

    A key is flagged as a placeholder when any of the following hold:

    * it cannot be normalized at all (``None``, blank, non-whole float);
    * it contains no digits (e.g. ``"BAL"``);
    * its digits are all zeros;
    * its canonical form starts with ``001-001-`` (the demo's mis-keyed
      BAL-row convention).

    Parameters
    ----------
    value:
        The GL key as it appears in the source file.

    Returns
    -------
    bool
        ``True`` if the key is suspicious and needs human review.
    """
    try:
        norm = normalize_gl(value)
    except ValueError:
        return True
    digits = re.sub(r"\D", "", norm)
    if not digits:
        return True
    if set(digits) == {"0"}:
        return True
    if norm.startswith(_PLACEHOLDER_PREFIX):
        return True
    return False
