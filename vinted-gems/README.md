# vinted-gems

Find workwear × streetwear hidden gems on Vinted **in your true size**, even
when sellers list the same garment under different measurement systems.

## The size problem this fixes

Vinted's size filter treats every notation as a separate bucket. A 35×34
pant might be listed as any of:

| notation | system | same garment? |
|---|---|---|
| `W35` / `W35 L34` / `35x34` | US/UK inches | yes — exact |
| `FR 45` / `45` | French/EU (= W + 10) | yes — converted |
| `IT 51` / `51` | Italian (= W + 16) | yes — converted |
| `L` | letter (relaxed cuts) | usually (W34–36) |
| `W34 \| FR 44`, `46` | one size off | maybe — check measurements |

Filtering by "W35" alone silently drops all the converted listings — which
is where the underpriced gems hide, because fewer buyers find them.

This tool searches **by text query with no size filter**, then parses each
listing's size label (`"W32 | FR 42"`, `"L / 40 / 12"`, `"Taille 44"`, …)
and matches it against your target with explicit conversion tables. Matches
are graded `EXACT` → `EQUIVALENT` (converted) → `CLOSE` (one size off; vintage
workwear shrinks and stretches, so always compare flat measurements).

## Gem scoring

Each size-matched item is scored 0–100:

- **fit** (30) — exact > converted > one-off
- **brand** (25) — grail (Engineered Garments, orSlow, Kapital…) > core
  (Carhartt WIP, Stan Ray, Stüssy, Gramicci…) > basics (Dickies, Wrangler…)
- **value** (25) — price vs the brand's typical resale
- **style heat** (12) — double knee, chore, fatigue, selvedge, made in USA…
- **undiscovered** (8) — few favourites, not a promoted listing

## Usage

```bash
pip install requests
python find_gems.py --pants 35x34 --shirt L --max-price 80 \
    --out report.md --json results.json
```

Options: `--domain vinted.fr` (any Vinted TLD), `--pages N` to sweep deeper,
`--top N` results per section.

Edit `PANTS_QUERIES` / `SHIRT_QUERIES` in `find_gems.py` to taste and the
brand/keyword tables in `gems.py` to tune scoring.

## Notes

- Uses Vinted's public web API with the anonymous session token the site
  itself issues; be polite (built-in 1 req/s throttle).
- Tests: `python -m pytest test_sizing.py -q`
