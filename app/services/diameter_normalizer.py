"""Diameter normalization for engineering memorials.

Converts free-text diameter notation (inches with fractions, millimeters,
mixed Brazilian/English variants) into a structured form that can be safely
rendered without losing the original unit. Specifically protects against the
common bug where ``1 1/4"`` was rendered as ``1.25mm`` because the template
hardcoded ``mm`` after the numeric placeholder.

Design rules
============

- The unit is **explicit** (`"in"` or `"mm"`). Never inferred from value range.
- No automatic mm↔in conversion. The normalized value preserves the original
  unit. Conversions are the caller's intentional decision.
- ``valor_formatado`` reproduces the original notation when possible
  (inch fractions stay as ``1 1/4"``; millimeter values use ``X mm``).
- ``valor`` is the numeric value (Decimal) so it can be persisted or
  reconciled with other sources without loss of precision.
- Parser is conservative: returns ``None`` for unparseable inputs rather than
  guessing, so callers can decide whether to fall back or flag a conflict.

Supported inputs include (non-exhaustive):

- ``1 1/4"``, ``1.1/4"``, ``1-1/4"`` (mixed numerals with fractions)
- ``1 1/4 pol``, ``1 1/4 polegadas`` (Portuguese verbose inch markers)
- ``3/4"``, ``1/2"`` (plain fractions)
- ``25 mm``, ``32mm`` (millimeters with/without space)
- ``25,5 mm`` (Brazilian decimal comma)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Final, Literal

DiameterUnit = Literal["in", "mm"]


@dataclass(frozen=True)
class NormalizedDiameter:
    """Structured representation of a diameter measurement.

    Attributes:
        valor: numeric value as Decimal (e.g. Decimal("1.25") for 1 1/4").
        unidade: unit literal ("in" or "mm"), never inferred from value.
        valor_formatado: display-friendly string preserving the original style.
        valor_original: exact substring extracted from source text.
    """

    valor: Decimal
    unidade: DiameterUnit
    valor_formatado: str
    valor_original: str


_FRACTION_INCH_REGEX: Final[re.Pattern[str]] = re.compile(
    r"""
    (?P<whole>\d+)            # leading integer part
    [\s.\-]+                  # space, dot, or hyphen between whole and fraction
    (?P<num>\d+)\s*/\s*(?P<den>\d+)
    \s*
    (?:"|''|pol(?:egadas?)?\b)
    """,
    re.IGNORECASE | re.VERBOSE,
)

_PLAIN_FRACTION_INCH_REGEX: Final[re.Pattern[str]] = re.compile(
    r"""
    (?<![\d.,])               # not preceded by digit/dot/comma
    (?P<num>\d+)\s*/\s*(?P<den>\d+)
    \s*
    (?:"|''|pol(?:egadas?)?\b)
    """,
    re.IGNORECASE | re.VERBOSE,
)

_DECIMAL_INCH_REGEX: Final[re.Pattern[str]] = re.compile(
    r"""
    (?P<num>\d+(?:[.,]\d+)?)
    \s*
    (?:"|''|pol(?:egadas?)?\b)
    """,
    re.IGNORECASE | re.VERBOSE,
)

_MM_REGEX: Final[re.Pattern[str]] = re.compile(
    r"""
    (?P<num>\d+(?:[.,]\d+)?)
    \s*
    mm\b
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _decimal_from_fraction(whole: str | None, num: str, den: str) -> Decimal | None:
    try:
        numerator = Decimal(num)
        denominator = Decimal(den)
        if denominator == 0:
            return None
        fractional = numerator / denominator
        if whole is None:
            return fractional
        return Decimal(whole) + fractional
    except InvalidOperation:
        return None


def _decimal_from_value(raw: str) -> Decimal | None:
    try:
        return Decimal(raw.replace(",", "."))
    except InvalidOperation:
        return None


def _format_fraction_inch(whole: str | None, num: str, den: str) -> str:
    if whole is None:
        return f'{num}/{den}"'
    return f'{whole} {num}/{den}"'


def _format_decimal(value: Decimal) -> str:
    # strip trailing zeros without using normalize() (which uses exponents)
    text = format(value, "f").rstrip("0").rstrip(".")
    return text or "0"


def normalize_diameter(text: str | None) -> NormalizedDiameter | None:
    """Parse a free-text diameter into a NormalizedDiameter, or return None.

    The parser **does not** convert between units. Inch inputs return ``unidade="in"``;
    millimeter inputs return ``unidade="mm"``. ``valor_formatado`` preserves the
    inch-fraction notation when the input was a fraction.
    """
    if text is None:
        return None
    cleaned = text.strip()
    if not cleaned:
        return None

    match = _FRACTION_INCH_REGEX.search(cleaned)
    if match:
        decimal_value = _decimal_from_fraction(
            match.group("whole"),
            match.group("num"),
            match.group("den"),
        )
        if decimal_value is None:
            return None
        formatted = _format_fraction_inch(
            match.group("whole"),
            match.group("num"),
            match.group("den"),
        )
        return NormalizedDiameter(
            valor=decimal_value,
            unidade="in",
            valor_formatado=formatted,
            valor_original=match.group(0).strip(),
        )

    match = _PLAIN_FRACTION_INCH_REGEX.search(cleaned)
    if match:
        decimal_value = _decimal_from_fraction(
            None,
            match.group("num"),
            match.group("den"),
        )
        if decimal_value is None:
            return None
        formatted = _format_fraction_inch(
            None,
            match.group("num"),
            match.group("den"),
        )
        return NormalizedDiameter(
            valor=decimal_value,
            unidade="in",
            valor_formatado=formatted,
            valor_original=match.group(0).strip(),
        )

    match = _MM_REGEX.search(cleaned)
    if match:
        decimal_value = _decimal_from_value(match.group("num"))
        if decimal_value is None:
            return None
        return NormalizedDiameter(
            valor=decimal_value,
            unidade="mm",
            valor_formatado=f"{_format_decimal(decimal_value)} mm",
            valor_original=match.group(0).strip(),
        )

    match = _DECIMAL_INCH_REGEX.search(cleaned)
    if match:
        decimal_value = _decimal_from_value(match.group("num"))
        if decimal_value is None:
            return None
        return NormalizedDiameter(
            valor=decimal_value,
            unidade="in",
            valor_formatado=f'{_format_decimal(decimal_value)}"',
            valor_original=match.group(0).strip(),
        )

    return None
