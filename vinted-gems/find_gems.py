#!/usr/bin/env python3
"""Search Vinted for workwear/streetwear in your true size, across all
measurement systems, and rank the hidden gems.

Usage:
    python find_gems.py --pants 35x34 --shirt L --max-price 80 \
        --out report.md --json results.json

Sizes are matched by parsing each listing's size label (W/L inches, FR/EU,
IT, letter sizes, collar sizes) rather than trusting the platform's size
filter, so a 35x34 pant also surfaces listings tagged FR 45, IT 51 or "L".
"""

from __future__ import annotations

import argparse
import json
import sys
import time

from client import VintedClient
from gems import (
    EXCLUDE_KEEP_TANKS,
    EXCLUDE_TITLE,
    ScoredItem,
    score_item,
    title_contradicts_pants,
)
from sizing import PantsTarget, ShirtTarget

PANTS_QUERIES = [
    "carhartt double knee",
    "carhartt carpenter pant",
    "carhartt simple pant",
    "carhartt single knee",
    "dickies 874",
    "dickies double knee",
    "stan ray fatigue pant",
    "stan ray painter pant",
    "gramicci pant",
    "engineered garments fatigue",
    "orslow pant",
    "polar big boy",
    "butter goods pant",
    "dime baggy pant",
    "pantalon travail vintage moleskine",
    "pantalon cargo vintage",
    "levis 501 W35",
    "wrangler carpenter",
]

# --style fun: colourful streetwear — playful but wearable.
FUN_TOP_QUERIES = [
    "stussy shirt",
    "stussy 8 ball",
    "stussy hawaiian",
    "brain dead shirt",
    "butter goods",
    "patta t-shirt",
    "obey shirt vintage",
    "gramicci shirt",
    "polar skate co",
    "dime t-shirt",
    "palace t-shirt",
    "carhartt wip s/s shirt",
    "chemise vintage colorée",
    "tie dye shirt vintage",
]

FUN_LAYER_QUERIES = [
    "nike windbreaker vintage",
    "veste coach jacket",
    "stussy jacket",
    "butter goods jacket",
    "carhartt wip veste colorée",
    "patagonia fleece colorful",
    "polaire vintage colorée",
    "adidas track jacket vintage",
]

# --style dark: club-ready dark workwear / techwear / avant. Shirts with
# structure (heavy seams, canvas, denim, flannel) plus dark outer layers.
DARK_SHIRT_QUERIES = [
    "chemise noire workwear",
    "carhartt shirt black",
    "surchemise noire",
    "black flannel shirt heavy",
    "chemise denim noir",
    "rick owens shirt",
    "drkshdw",
    "y-3 shirt",
    "yohji yamamoto shirt",
    "helmut lang shirt",
    "issey miyake shirt homme",
    "washed black shirt oversize",
]

DARK_OUTER_QUERIES = [
    "carhartt detroit jacket black",
    "carhartt active jacket noir",
    "chore jacket noir",
    "veste travail noire moleskine",
    "nike acg jacket black",
    "stone island shadow",
    "veste techwear",
    "cargo jacket nylon black",
    "arcteryx jacket black",
    "maharishi jacket",
    "cp company overshirt",
    "acronym",
]

SHIRT_QUERIES = [
    "carhartt chemise",
    "carhartt work shirt",
    "dickies work shirt",
    "stussy shirt",
    "stussy chemise",
    "wrangler western shirt",
    "chemise flanelle vintage",
    "ben davis shirt",
    "patagonia shirt",
    "universal works shirt",
    "engineered garments shirt",
    "norse projects shirt",
]


def parse_pants(spec: str) -> PantsTarget:
    try:
        w, l = spec.lower().replace("*", "x").split("x")
        return PantsTarget(waist_in=int(w), inseam_in=int(l))
    except ValueError:
        sys.exit(f"bad --pants spec {spec!r}, expected e.g. 35x34")


def uploaded_within(item: dict, hours: float) -> bool:
    """True when the listing's first photo was uploaded in the last N hours."""
    photos = item.get("photos") or []
    ts = ((photos[0].get("high_resolution") or {}).get("timestamp")) if photos else None
    return bool(ts) and (time.time() - ts) <= hours * 3600


def run_queries(
    client, queries, target, max_price, pages,
    dark=False, fun=False, fresh_hours=None, exclude=EXCLUDE_TITLE,
):
    seen: set[int] = set()
    gems: list[ScoredItem] = []
    order = "newest_first" if fresh_hours else "relevance"
    for q in queries:
        for page in range(1, pages + 1):
            try:
                items = client.search(q, price_to=max_price, page=page, order=order)
            except Exception as e:  # noqa: BLE001 - keep sweeping other queries
                print(f"  ! {q!r} page {page}: {e}", file=sys.stderr)
                break
            for it in items:
                iid = it.get("id")
                if not iid or iid in seen:
                    continue
                seen.add(iid)
                if fresh_hours and not uploaded_within(it, fresh_hours):
                    continue
                if exclude.search(it.get("title") or ""):
                    continue
                m = target.match(it.get("size_title") or "")
                if not m:
                    continue
                if isinstance(target, PantsTarget) and title_contradicts_pants(
                    it, target.waist_in, target.inseam_in
                ):
                    continue
                gems.append(score_item(it, m, dark=dark, fun=fun))
            if len(items) < 20:  # thin page — no point paging deeper
                break
        print(f"  {q!r}: {len(seen)} unique items so far", file=sys.stderr)
    gems.sort(key=lambda g: g.score, reverse=True)
    return gems


def fmt_md(gems: list[ScoredItem], heading: str, top: int) -> str:
    lines = [f"## {heading}", "", "| score | item | size | price | why |", "|--:|---|---|--:|---|"]
    for g in gems[:top]:
        why = "; ".join(g.reasons[:3])
        lines.append(
            f"| {g.score:.0f} | [{g.title[:60]}]({g.url}) | {g.size.token} | {g.price:.0f}€ | {why} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--style",
        choices=["classic", "dark", "fun"],
        default="classic",
        help="classic: workwear x streetwear pants + shirts; "
        "dark: club-ready dark shirts + outer layers with photo-darkness scoring; "
        "fun: colourful streetwear with photo-vividness scoring",
    )
    ap.add_argument("--domain", default="vinted.fr")
    ap.add_argument("--pants", default="35x34", help="waist x inseam in inches")
    ap.add_argument("--shirt", default="L")
    ap.add_argument("--max-price", type=float, default=80)
    ap.add_argument("--pages", type=int, default=1, help="pages per query")
    ap.add_argument(
        "--fresh-hours",
        type=float,
        default=None,
        help="only listings uploaded in the last N hours (sorts newest first)",
    )
    ap.add_argument(
        "--query",
        action="append",
        default=None,
        help="custom search query (repeatable); replaces the style's query sets "
        "and matches against the shirt size target",
    )
    ap.add_argument(
        "--include-tanks",
        action="store_true",
        help="keep tank tops / débardeurs (excluded by default)",
    )
    ap.add_argument("--top", type=int, default=20, help="results per section")
    ap.add_argument("--out", default=None, help="write markdown report here")
    ap.add_argument("--json", dest="json_out", default=None)
    args = ap.parse_args()

    client = VintedClient(domain=args.domain)
    pants_target = parse_pants(args.pants)
    shirt_target = ShirtTarget(letter=args.shirt.upper())

    if args.query:
        shirt_target = ShirtTarget(letter=args.shirt.upper(), oversize_ok=True)
        exclude = EXCLUDE_KEEP_TANKS if args.include_tanks else EXCLUDE_TITLE
        print(f"custom hunt: {args.query} …", file=sys.stderr)
        pants = run_queries(
            client, args.query, shirt_target, args.max_price, args.pages,
            fun=(args.style == "fun"), dark=(args.style == "dark"),
            fresh_hours=args.fresh_hours, exclude=exclude,
        )
        shirts = []
        sections = [fmt_md(pants, f"Custom hunt ({len(pants)} size matches)", args.top)]
        title = f"# Vinted custom hunt — tops {args.shirt}"
    elif args.style == "fun":
        shirt_target = ShirtTarget(letter=args.shirt.upper(), oversize_ok=True)
        print("searching fun tops …", file=sys.stderr)
        pants = run_queries(
            client, FUN_TOP_QUERIES, shirt_target, args.max_price, args.pages,
            fun=True, fresh_hours=args.fresh_hours,
        )
        print("searching fun layers …", file=sys.stderr)
        shirts = run_queries(
            client, FUN_LAYER_QUERIES, shirt_target, args.max_price, args.pages,
            fun=True, fresh_hours=args.fresh_hours,
        )
        sections = [
            fmt_md(pants, f"Fun tops ({len(pants)} size matches)", args.top),
            fmt_md(shirts, f"Fun layers ({len(shirts)} size matches)", args.top),
        ]
        title = f"# Vinted fun gems — tops {args.shirt} (XL surfaced for oversize)"
    elif args.style == "dark":
        shirt_target = ShirtTarget(letter=args.shirt.upper(), oversize_ok=True)
        print("searching dark shirts …", file=sys.stderr)
        pants = run_queries(
            client, DARK_SHIRT_QUERIES, shirt_target, args.max_price, args.pages,
            dark=True, fresh_hours=args.fresh_hours,
        )
        print("searching dark outer layers …", file=sys.stderr)
        shirts = run_queries(
            client, DARK_OUTER_QUERIES, shirt_target, args.max_price, args.pages,
            dark=True, fresh_hours=args.fresh_hours,
        )
        sections = [
            fmt_md(pants, f"Rugged dark shirts ({len(pants)} size matches)", args.top),
            fmt_md(shirts, f"Dark outer layers ({len(shirts)} size matches)", args.top),
        ]
        title = f"# Vinted dark gems — tops {args.shirt} (XL surfaced for oversize)"
    else:
        print(f"searching pants {args.pants} …", file=sys.stderr)
        pants = run_queries(
            client, PANTS_QUERIES, pants_target, args.max_price, args.pages,
            fresh_hours=args.fresh_hours,
        )
        print(f"searching shirts {args.shirt} …", file=sys.stderr)
        shirts = run_queries(
            client, SHIRT_QUERIES, shirt_target, args.max_price, args.pages,
            fresh_hours=args.fresh_hours,
        )
        sections = [
            fmt_md(pants, f"Pants ({len(pants)} size matches)", args.top),
            fmt_md(shirts, f"Shirts & tops ({len(shirts)} size matches)", args.top),
        ]
        title = f"# Vinted gems — pants {args.pants}, tops {args.shirt}"

    report = "\n".join(
        [
            title,
            "",
            f"Sizes matched across systems: W{pants_target.waist_in} = "
            f"FR {pants_target.fr_size} = IT {pants_target.it_size}; "
            f"{args.shirt} tops = FR 41/42 = IT 52 = collar 16-16.5\".",
            "",
            *sections,
        ]
    )

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(report)
    else:
        print(report)

    if args.json_out:
        payload = [
            {
                "id": g.item.get("id"),
                "title": g.title,
                "url": g.url,
                "brand": g.brand,
                "price_eur": g.price,
                "size_title": g.item.get("size_title"),
                "size_match": g.size.level.name,
                "size_note": g.size.note,
                "score": g.score,
                "reasons": g.reasons,
                "favourites": g.item.get("favourite_count"),
                "condition": g.item.get("status"),
                "photo": (g.item.get("photos") or [{}])[0].get("url"),
                "section": "pants" if g in pants else "shirts",
            }
            for g in pants + shirts
        ]
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
