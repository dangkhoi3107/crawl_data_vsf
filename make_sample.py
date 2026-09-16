"""Sinh bộ dữ liệu mẫu nhỏ từ catalog đầy đủ, để người khác chạy thử mà không cần tải 12 MB.

Mẫu được chọn sao cho phủ đủ 7 biến thể sản phẩm, có khách sạn kèm hạng phòng và tuyến bay kèm chuyến
cụ thể (để thử liên kết parentProductId), và có cả các trường hợp đặc biệt: vé không bán (ticketed=false),
vé có giá theo hạng thành viên, sản phẩm có điều khoản tách riêng, sản phẩm có mô tả gốc tiếng Anh.

    python make_sample.py [--data-dir data] [--per-variant 4]
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def variant(o: dict) -> str:
    level = (o.get("attributes") or {}).get("level")
    return o["taxonomy"] + (f"/{level}" if level else "")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", type=Path, default=Path("data"))
    ap.add_argument("--per-variant", type=int, default=4, help="số sản phẩm mỗi biến thể (mặc định 4)")
    a = ap.parse_args()

    rows = [json.loads(line) for line in open(a.data_dir / "products.jsonl", encoding="utf-8")]
    by_id = {o["productId"]: o for o in rows}
    children: dict[str, list[dict]] = {}
    for o in rows:
        parent = (o.get("attributes") or {}).get("parentProductId")
        if parent:
            children.setdefault(parent, []).append(o)

    picked: dict[str, dict] = {}

    def take(o: dict, with_children: bool = False) -> None:
        picked.setdefault(o["productId"], o)
        parent = (o.get("attributes") or {}).get("parentProductId")
        if parent and parent in by_id:
            picked.setdefault(parent, by_id[parent])   # không để hạng phòng mất cha
        if with_children:
            for c in children.get(o["productId"], [])[:3]:
                picked.setdefault(c["productId"], c)

    # trường hợp đặc biệt, lấy trước để chắc chắn có mặt
    special = [
        ("có giá theo hạng thành viên", lambda o: (o.get("attributes") or {}).get("memberPrices")),
        ("điều khoản tách sang policies", lambda o: (o.get("attributes") or {}).get("policies")),
        ("mô tả gốc tiếng Anh, đã dựng lại tiếng Việt", lambda o: (o.get("attributes") or {}).get("descriptionOriginal")),
        ("điểm công cộng không bán vé", lambda o: (o.get("attributes") or {}).get("ticketed") is False),
        ("vé gắn địa điểm sử dụng", lambda o: (o.get("attributes") or {}).get("venue")),
    ]
    for _, match in special:
        for o in rows:
            if match(o):
                take(o)
                break

    # phủ đều các biến thể, ưu tiên sản phẩm có nhiều trường nhất
    def richness(o: dict) -> int:
        a = o.get("attributes") or {}
        return sum(1 for v in a.values() if v not in (None, "", [], {}))

    for v in sorted({variant(o) for o in rows}):
        pool = sorted([o for o in rows if variant(o) == v], key=richness, reverse=True)
        seen_dest: set[str] = set()
        n = 0
        for o in pool:
            if n >= a.per_variant:
                break
            if o["destination"] in seen_dest:      # trải trên nhiều điểm đến
                continue
            seen_dest.add(o["destination"])
            take(o, with_children=v in ("hotel/property", "flight/route"))
            n += 1

    sample = sorted(picked.values(), key=lambda o: (o["taxonomy"], o["name"]))
    out = a.data_dir / "sample"
    out.mkdir(exist_ok=True)
    with open(out / "products-sample.jsonl", "w", encoding="utf-8") as f:
        for o in sample:
            f.write(json.dumps(o, ensure_ascii=False) + "\n")

    flat_fields = ["productId", "name", "taxonomy", "destination", "unitPrice", "currency", "available",
                   "imageUrl", "sourceRef", "description"]
    with open(out / "products-sample.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(flat_fields + ["level", "latitude", "longitude", "starRating", "parentProductId"])
        for o in sample:
            at = o.get("attributes") or {}
            w.writerow([o.get(k) for k in flat_fields] +
                       [at.get(k) for k in ("level", "latitude", "longitude", "starRating", "parentProductId")])

    counts: dict[str, int] = {}
    for o in sample:
        counts[variant(o)] = counts.get(variant(o), 0) + 1
    print(f"đã ghi {out}/products-sample.jsonl — {len(sample)} sản phẩm")
    for k, v in sorted(counts.items()):
        print(f"   {k:16s} {v}")


if __name__ == "__main__":
    main()
