"""Cross-dimension size normalization for secondhand clothing listings.

The core problem: the same physical garment gets listed under different
measurement systems depending on the seller and platform locale.
A 35x34 pant can appear as:

    "W35"  "35"  "W35 L34"  "35x34"  "W34 | FR 44"  "FR 45"  "44"
    "IT 50"  "50"  "L"  "Taille 45"

and a size-L shirt as:

    "L"  "L / 40 / 12"  "FR 41"  "42"  "IT 52"  "16 1/2"

Vinted's own size filter treats these as distinct buckets, which is why
exact-size searching silently drops equivalent listings. This module parses
a listing's size string into tokens, assigns each token a measurement
system, and matches it against a target size with explicit conversion
tables:

    pants:  FR/EU size = waist_inches + 10      (W35 -> FR 45)
            IT size    = waist_inches + 16      (W35 -> IT 51)
    shirts: FR collar  = letter (40/41 ~ M-L, 42 ~ L)
            IT jacket  = 52 ~ L
            US collar  = 16 ~ M/L, 16.5 ~ L

Match levels:
    EXACT      same size, possibly expressed in another system
    EQUIVALENT converted size that maps to the same body measurement
    CLOSE      one step off (workwear shrinks/stretches; check measurements)
    NONE       different size
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import IntEnum


class Match(IntEnum):
    NONE = 0
    CLOSE = 1
    EQUIVALENT = 2
    EXACT = 3


@dataclass
class SizeMatch:
    level: Match
    token: str
    note: str

    def __bool__(self) -> bool:
        return self.level is not Match.NONE


LETTER_SIZES = {"XXS", "XS", "S", "M", "L", "XL", "XXL", "3XL", "4XL"}

# Letter -> approximate waist-inch range for men's pants (relaxed cuts).
LETTER_WAIST = {
    "S": (28, 30),
    "M": (31, 33),
    "L": (34, 36),
    "XL": (37, 40),
}

_TOKEN_SPLIT = re.compile(r"[|/,;]")
_WXL = re.compile(r"\bW\s*(\d{2})(?:\s*[xX/\- ]\s*L?\s*(\d{2}))?\b", re.I)
_NXN = re.compile(r"\b(\d{2})\s*[xX]\s*(\d{2})\b")
_LONLY = re.compile(r"\bL\s*(\d{2})\b")
_SYS_NUM = re.compile(r"\b(FR|IT|EU|DE|UK|US)\s*\.?\s*(\d{2})\b", re.I)
_BARE_NUM = re.compile(r"\b(\d{2}(?:[.,]5)?)\b")
_COLLAR_FRAC = re.compile(r"\b(1[456])\s*(?:1/2|½|\.5|,5)?\b")


def tokenize(size_title: str) -> list[str]:
    """Split a listing size string into candidate tokens.

    "W32 | FR 42" -> ["W32", "FR 42"];  "L / 40 / 12" -> ["L", "40", "12"]
    """
    if not size_title:
        return []
    parts = [p.strip() for p in _TOKEN_SPLIT.split(size_title)]
    return [p for p in parts if p]


def _closeness(delta: int) -> Match:
    if delta == 0:
        return Match.EXACT
    if abs(delta) == 1:
        return Match.CLOSE
    return Match.NONE


@dataclass
class PantsTarget:
    waist_in: int = 35
    inseam_in: int = 34

    @property
    def fr_size(self) -> int:
        return self.waist_in + 10

    @property
    def it_size(self) -> int:
        return self.waist_in + 16

    def match(self, size_title: str) -> SizeMatch:
        best = SizeMatch(Match.NONE, size_title or "", "no size parsed")
        for tok in tokenize(size_title):
            m = self._match_token(tok)
            if m.level > best.level:
                best = m
        return best

    def _match_token(self, tok: str) -> SizeMatch:
        up = tok.upper().strip()

        # "W35", "W35 L34", "W35/34", "W35x34"
        m = _WXL.search(up)
        if m:
            waist = int(m.group(1))
            lvl = _closeness(waist - self.waist_in)
            if lvl is Match.NONE:
                return SizeMatch(Match.NONE, tok, "waist off by 2+")
            note = f"W{waist}"
            if m.group(2):
                inseam = int(m.group(2))
                if abs(inseam - self.inseam_in) > 2:
                    return SizeMatch(Match.NONE, tok, f"inseam L{inseam} too far from L{self.inseam_in}")
                note += f" L{inseam}"
                if inseam != self.inseam_in:
                    note += f" (inseam {inseam - self.inseam_in:+d}\")"
            if lvl is Match.CLOSE:
                note += " — one inch off, check flat waist measurement"
            return SizeMatch(lvl, tok, note)

        # "35x34"
        m = _NXN.search(up)
        if m:
            waist, inseam = int(m.group(1)), int(m.group(2))
            if 26 <= waist <= 44:
                lvl = _closeness(waist - self.waist_in)
                if lvl and abs(inseam - self.inseam_in) <= 2:
                    return SizeMatch(lvl, tok, f"{waist}x{inseam}")
                return SizeMatch(Match.NONE, tok, "waist/inseam mismatch")

        # "FR 44", "IT 50", "EU 45", "UK 35", "US 35"
        m = _SYS_NUM.search(up)
        if m:
            sys_, num = m.group(1).upper(), int(m.group(2))
            if sys_ in ("UK", "US"):
                lvl = _closeness(num - self.waist_in)
                return SizeMatch(lvl, tok, f"{sys_} {num} = W{num}") if lvl else SizeMatch(Match.NONE, tok, "")
            if sys_ in ("FR", "EU", "DE"):
                delta = num - self.fr_size
                lvl = _closeness(delta)
                if lvl is Match.EXACT:
                    return SizeMatch(Match.EQUIVALENT, tok, f"{sys_} {num} = W{num - 10} (converted)")
                if lvl is Match.CLOSE:
                    return SizeMatch(Match.CLOSE, tok, f"{sys_} {num} ≈ W{num - 10}, one size off — check measurements")
                return SizeMatch(Match.NONE, tok, "")
            if sys_ == "IT":
                delta = num - self.it_size
                lvl = _closeness(delta)
                if lvl is Match.EXACT:
                    return SizeMatch(Match.EQUIVALENT, tok, f"IT {num} = W{num - 16} (converted)")
                if lvl is Match.CLOSE:
                    return SizeMatch(Match.CLOSE, tok, f"IT {num} ≈ W{num - 16}, one size off")
                return SizeMatch(Match.NONE, tok, "")

        # Letter sizes: relaxed/streetwear cuts sized S-XL
        if up in LETTER_SIZES:
            rng = LETTER_WAIST.get(up)
            if rng and rng[0] <= self.waist_in <= rng[1]:
                return SizeMatch(Match.EQUIVALENT, tok, f"letter {up} ≈ W{rng[0]}–{rng[1]} — verify measurements")
            return SizeMatch(Match.NONE, tok, "letter size out of range")

        # Bare number: infer the system from its magnitude.
        m = _BARE_NUM.search(up)
        if m:
            num = int(float(m.group(1).replace(",", ".")))
            if 30 <= num <= 40:  # inches territory
                lvl = _closeness(num - self.waist_in)
                return SizeMatch(lvl, tok, f"{num} read as W{num}") if lvl else SizeMatch(Match.NONE, tok, "")
            if 40 < num <= 48:  # FR territory
                lvl = _closeness(num - self.fr_size)
                if lvl is Match.EXACT:
                    return SizeMatch(Match.EQUIVALENT, tok, f"{num} read as FR {num} = W{num - 10}")
                if lvl is Match.CLOSE:
                    return SizeMatch(Match.CLOSE, tok, f"{num} read as FR {num} ≈ W{num - 10}, one off")
            if 48 < num <= 58:  # IT territory
                lvl = _closeness(num - self.it_size)
                if lvl is Match.EXACT:
                    return SizeMatch(Match.EQUIVALENT, tok, f"{num} read as IT {num} = W{num - 16}")
                if lvl is Match.CLOSE:
                    return SizeMatch(Match.CLOSE, tok, f"{num} read as IT {num} ≈ W{num - 16}, one off")

        return SizeMatch(Match.NONE, tok, "unrecognized")


@dataclass
class ShirtTarget:
    letter: str = "L"
    # When hunting boxy/oversized fits, one letter size up is a feature,
    # not a compromise — rank it as a converted equivalent instead of CLOSE.
    oversize_ok: bool = False

    # Conversions for a men's size L top.
    _EXACT_LETTERS = {"L"}
    _CLOSE_LETTERS = {"M", "XL"}
    _FR_EXACT = {41, 42}      # FR collar sizes for L
    _FR_CLOSE = {40, 43}
    _IT_EXACT = {52}          # IT jacket size for L
    _IT_CLOSE = {50, 54}
    _COLLAR_IN_EXACT = {16}   # 16-16.5" collar ~ L

    def match(self, size_title: str) -> SizeMatch:
        # A waist notation anywhere in the label means the item is bottoms
        # (e.g. "W32 | FR 42") — its FR 42 is a waist size, not a shirt L.
        if re.search(r"\bW\s*\d{2}\b", size_title or "", re.I):
            return SizeMatch(Match.NONE, size_title or "", "waist-sized item, not a top")
        best = SizeMatch(Match.NONE, size_title or "", "no size parsed")
        for tok in tokenize(size_title):
            m = self._match_token(tok)
            if m.level > best.level:
                best = m
        return best

    def _match_token(self, tok: str) -> SizeMatch:
        up = tok.upper().strip()

        if up in LETTER_SIZES:
            if up in self._EXACT_LETTERS:
                return SizeMatch(Match.EXACT, tok, "L")
            if up == "XL" and self.oversize_ok:
                return SizeMatch(Match.EQUIVALENT, tok, "XL — oversized drape on an L frame")
            if up in self._CLOSE_LETTERS:
                return SizeMatch(Match.CLOSE, tok, f"{up} — brand may run big/small, check pit-to-pit")
            return SizeMatch(Match.NONE, tok, "letter size off")

        m = _SYS_NUM.search(up)
        num_str = m.group(2) if m else None
        if not num_str:
            m2 = _BARE_NUM.search(up)
            num_str = m2.group(1) if m2 else None
        if num_str:
            num = int(float(num_str.replace(",", ".")))
            if num in self._FR_EXACT:
                return SizeMatch(Match.EQUIVALENT, tok, f"FR/EU {num} = L (converted)")
            if num in self._FR_CLOSE:
                return SizeMatch(Match.CLOSE, tok, f"FR/EU {num} ≈ M/L boundary — check measurements")
            if num in self._IT_EXACT:
                return SizeMatch(Match.EQUIVALENT, tok, f"IT {num} = L (converted)")
            if num in self._IT_CLOSE:
                return SizeMatch(Match.CLOSE, tok, f"IT {num} ≈ one off from L")
            if num == 16:
                return SizeMatch(Match.EQUIVALENT, tok, 'collar 16-16.5" = L')
            if num == 15:
                return SizeMatch(Match.CLOSE, tok, 'collar 15.5" ≈ M/L')

        return SizeMatch(Match.NONE, tok, "unrecognized")
