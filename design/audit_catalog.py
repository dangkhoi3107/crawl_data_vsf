#!/usr/bin/env python3
"""Read-only catalog audit. Supports a JSON array or JSONL, using only stdlib."""
import argparse
from collections import Counter
import json
from pathlib import Path

FIELDS = {
    "productId", "name", "taxonomy", "destination", "description", "attributes",
    "unitPrice", "currency", "available", "sourceRef", "imageUrl",
    "availableFrom", "availableTo",
}


def audit(path):
    text = path.read_text(encoding="utf-8")
    rows = json.loads(text) if text.lstrip().startswith("[") else [
        json.loads(line) for line in text.splitlines() if line.strip()
    ]
    ids = {r.get("productId") for r in rows}
    findings = {}

    def record(kind, row):
        findings.setdefault(kind, []).append({
            "productId": row.get("productId"), "name": row.get("name"),
            "sourceRef": row.get("sourceRef"),
        })

    for r in rows:
        a = r.get("attributes") or {}
        if set(r) != FIELDS:
            record("top_level_fields_differ", r)
        if a.get("parentProductId") and a["parentProductId"] not in ids:
            record("parent_absent_from_this_file", r)
        if a.get("level") == "room" and not a.get("parentProductId"):
            record("room_without_parent", r)
        if r.get("unitPrice") is None:
            record("missing_price", r)
        if r.get("available") and r.get("unitPrice") is None:
            record("available_without_price", r)
        if not r.get("imageUrl"):
            record("missing_image", r)
        if r.get("unitPrice") is not None and not (a.get("priceObservedAt") or a.get("observedAt")):
            record("no_quote_observation_time_in_product", r)
        if (isinstance(a.get("vinpearlPrice"), (int, float))
                and isinstance(r.get("unitPrice"), (int, float))
                and r["unitPrice"] > a["vinpearlPrice"]):
            record("selected_price_above_stored_vinpearl_price_review_context", r)
        if r.get("taxonomy") == "combo" and not a.get("components"):
            record("combo_without_structured_components", r)
        if r.get("taxonomy") == "flight" and a.get("level") == "flight" and not a.get("departureAt"):
            record("flight_without_dated_departureAt", r)
        if r.get("availableFrom") and r.get("availableTo") and r["availableFrom"] > r["availableTo"]:
            record("inverted_date_range", r)

    duplicates = {}
    for key in ("productId", "sourceRef"):
        duplicates[key] = {v: n for v, n in Counter(r.get(key) for r in rows).items() if n > 1}
    return {
        "input": str(path.resolve()), "products": len(rows),
        "taxonomy_and_level": dict(Counter(f"{r['taxonomy']}:{r.get('attributes', {}).get('level') or '-'}" for r in rows)),
        "null_counts": dict(Counter(k for r in rows for k, v in r.items() if v is None)),
        "duplicates": duplicates,
        "finding_counts": {k: len(v) for k, v in findings.items()},
        "findings": findings,
        "interpretation": [
            "Findings are review signals, not proof of incorrect source data.",
            "Missing parents may exist outside a partial sample.",
            "A smaller stored price is not necessarily comparable: date, occupancy, room and policies must match.",
            "Missing observation timestamps in Product may still exist in raw/interim data.",
            "No network calls, product mutations or current availability verification were performed.",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.input), ensure_ascii=False, indent=2))
