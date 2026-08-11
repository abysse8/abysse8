"""Hidden-gem scoring for workwear x streetwear listings.

A gem is an item that is (a) actually your size once cross-dimension
equivalence is applied, (b) from a brand with real resale demand, and
(c) priced below what the brand usually trades at — ideally with few
favourites, meaning other buyers haven't found it yet.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from sizing import Match, SizeMatch

# Items to drop outright: wrong garment or wrong department for this hunt.
EXCLUDE_TITLE = re.compile(
    r"\b(shorts?|bermudas?|robe|dress|jupe|skirt|femme|women|débardeur|damen|mujer|enfant|kids)\b",
    re.I,
)

# Cheap cotton tops trade far below a brand's pants/outerwear money —
# scale "typical resale" down so a random tee doesn't score as a steal.
TEE_TITLE = re.compile(r"\b(t-?shirt|tee|polo|tank|débardeur|maillot)\b", re.I)

# Explicit measurements in the *title* outrank the seller-picked size bucket
# ("Carhartt 32X32" tagged as size L is a W32, not an L).
TITLE_WXL = re.compile(r"\b[wW]?(\d{2})\s*(?:[xX/]|[lL])\s*[lL]?\.?\s*(\d{2})\b")

# brand (lowercased) -> (tier, typical resale EUR for pants/heavy tops)
# tier 3 = grail, 2 = core workwear/streetwear, 1 = solid basics
BRANDS: dict[str, tuple[int, float]] = {
    "engineered garments": (3, 120),
    "orslow": (3, 110),
    "kapital": (3, 150),
    "stone island": (3, 140),
    "needles": (3, 110),
    "universal works": (2, 70),
    "norse projects": (2, 65),
    "carhartt wip": (2, 55),
    "carhartt": (2, 45),
    "stussy": (2, 55),
    "stüssy": (2, 55),
    "patagonia": (2, 55),
    "nike acg": (2, 60),
    "gramicci": (2, 45),
    "stan ray": (2, 45),
    "filson": (2, 90),
    "danton": (2, 60),
    "vetra": (2, 55),
    "le laboureur": (2, 50),
    "ben davis": (2, 40),
    "pointer brand": (2, 45),
    "edwin": (2, 50),
    "butter goods": (2, 45),
    "polar skate co": (2, 50),
    "dime": (2, 55),
    "obey": (1, 30),
    "dickies": (1, 30),
    "levi's": (1, 35),
    "levis": (1, 35),
    "wrangler": (1, 25),
    "lee": (1, 25),
    "l.l.bean": (1, 40),
    "ll bean": (1, 40),
    "timberland": (1, 35),
}

HEAT_KEYWORDS = {
    "double knee": 4,
    "chore": 3,
    "carpenter": 3,
    "fatigue": 3,
    "painter": 2,
    "cargo": 2,
    "selvedge": 3,
    "made in usa": 3,
    "made in france": 2,
    "deadstock": 3,
    "vintage": 2,
    "90s": 2,
    "flannel": 1,
    "flanelle": 1,
    "western": 2,
    "moleskine": 2,
    "moleskin": 2,
    "hickory": 3,
    "detroit": 3,
    "michigan": 3,
    "active jacket": 3,
}

CONDITION_BONUS = {
    "Neuf avec étiquette": 4,
    "Neuf sans étiquette": 3,
    "Très bon état": 2,
    "Bon état": 0,
    "Satisfaisant": -4,
}


@dataclass
class ScoredItem:
    item: dict
    size: SizeMatch
    score: float
    reasons: list[str]

    @property
    def title(self) -> str:
        return self.item.get("title", "")

    @property
    def url(self) -> str:
        return self.item.get("url", "")

    @property
    def price(self) -> float:
        try:
            return float(self.item.get("price", {}).get("amount", 0))
        except (TypeError, ValueError):
            return 0.0

    @property
    def brand(self) -> str:
        return self.item.get("brand_title") or "—"


def brand_info(item: dict) -> tuple[int, float]:
    name = (item.get("brand_title") or "").lower().strip()
    if name in BRANDS:
        return BRANDS[name]
    title = (item.get("title") or "").lower()
    for b, info in BRANDS.items():
        if b in title:
            return info
    return (0, 25)


def title_contradicts_pants(item: dict, waist_in: int, inseam_in: int) -> bool:
    """True when the title states measurements incompatible with the target."""
    m = TITLE_WXL.search(item.get("title") or "")
    if not m:
        return False
    w, l = int(m.group(1)), int(m.group(2))
    if not (26 <= w <= 46 and 26 <= l <= 38):
        return False  # probably not a size (year, model number…)
    return abs(w - waist_in) > 1 or abs(l - inseam_in) > 2


def score_item(item: dict, size: SizeMatch) -> ScoredItem:
    reasons: list[str] = []

    # Size fit: 0-30
    size_pts = {Match.EXACT: 30, Match.EQUIVALENT: 27, Match.CLOSE: 16}[size.level]
    reasons.append(f"size {size.note}")

    # Brand: 0-25. A brand tag not echoed anywhere in the title is often a
    # seller mistag (or bait) — keep the item but hold back points.
    tier, typical = brand_info(item)
    brand_pts = {3: 25, 2: 20, 1: 12, 0: 5}[tier]
    def _fold(s: str) -> str:
        s = unicodedata.normalize("NFD", s.lower())
        return re.sub(r"[^a-z0-9]", "", s)

    brand_name = (item.get("brand_title") or "").strip()
    title_fold = _fold(item.get("title") or "")
    brand_key = _fold(brand_name.split()[0])[:5] if brand_name else ""
    brand_verified = len(brand_key) >= 3 and brand_key in title_fold
    if tier and not brand_verified:
        brand_pts *= 0.4
        reasons.append("brand only in tag — verify photos")
    elif tier:
        reasons.append(f"brand tier {tier}")

    # Value vs typical resale: 0-25
    try:
        price = float(item.get("price", {}).get("amount", 0))
    except (TypeError, ValueError):
        price = 0.0
    if TEE_TITLE.search(item.get("title") or ""):
        typical *= 0.4
    value_pts = 0.0
    if price > 0:
        ratio = price / typical
        value_pts = max(0.0, min(25.0, (1.15 - ratio) * 25))
        if ratio <= 0.5:
            reasons.append(f"{price:.0f}€ vs ~{typical:.0f}€ typical — steal")
        elif ratio <= 0.85:
            reasons.append(f"{price:.0f}€ under typical ~{typical:.0f}€")

    # Style heat from title keywords: 0-12
    title = (item.get("title") or "").lower()
    heat = sum(pts for kw, pts in HEAT_KEYWORDS.items() if kw in title)
    heat_pts = min(12, heat)
    if heat_pts >= 4:
        reasons.append("workwear detail keywords")

    # Undiscovered: 0-8. Few favourites on a good brand = hidden.
    favs = item.get("favourite_count") or 0
    hidden_pts = 0
    if tier >= 1:
        hidden_pts = 6 if favs <= 3 else (3 if favs <= 10 else 0)
        if favs <= 3:
            reasons.append("barely any favourites yet")
    if not item.get("promoted"):
        hidden_pts += 2

    cond = (item.get("status") or "").strip()
    cond_pts = CONDITION_BONUS.get(cond, 0)
    if cond_pts >= 3:
        reasons.append(cond)

    total = size_pts + brand_pts + value_pts + heat_pts + hidden_pts + cond_pts
    return ScoredItem(item=item, size=size, score=round(total, 1), reasons=reasons)
