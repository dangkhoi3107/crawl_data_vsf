"""Xuất vị trí sản phẩm ra bản đồ: mỗi địa điểm (khách sạn, khu vui chơi, điểm tham quan, sân bay) một ghim.
Hạng phòng gộp vào ghim khách sạn, vé/combo gộp vào ghim địa điểm, vé máy bay gộp vào ghim sân bay đến.

  map/mymaps-khach-san.csv, mymaps-vui-choi.csv, mymaps-san-bay.csv
      import vào Google My Maps, mỗi file một lớp. My Maps không nhận file quá 2.000 dòng nên lớp lớn được tách
      thành -2, -3… File UTF-8 không BOM, cột latitude/longitude là số thập phân.
  map/places.geojson
      cùng các ghim kèm danh sách sản phẩm (web app: map.data.loadGeoJson của Maps JavaScript API). GeoJSON ghi
      toạ độ theo thứ tự [kinh độ, vĩ độ].
  map/can-kiem-tra.csv
      vị trí cần xem bằng mắt: địa điểm Vinpearl chưa có toạ độ dùng được hoặc mới tự tìm, toạ độ bị cảnh báo,
      vé chưa khớp địa điểm nào.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

from .geo import maps_url
from .textutil import fold

MY_MAPS_MAX_DATA_ROWS = 1999  # "Do not import files with more than 2,000 rows" – tính cả dòng tiêu đề cho chắc
LAYERS = {"khach-san": "Khách sạn", "vui-choi": "Vui chơi, combo, golf", "san-bay": "Sân bay"}
CATEGORY = {"attraction": "Vui chơi", "combo": "Combo", "golf": "Golf"}
CSV_FIELDS = (
    "name", "latitude", "longitude", "category", "destination", "description", "products", "priceFromVnd", "available",
    "starRating", "url", "imageUrl", "locationSource", "locationPrecision", "warning", "googleMapsUrl", "placeKey",
)
REVIEW_FIELDS = ("kind", "name", "destination", "latitude", "longitude", "problem", "googleMapsUrl", "howToFix", "ref")


def _fmt_vnd(v) -> str:
    return f"{int(v):,}".replace(",", ".") + "₫"


def _place_of(p: dict, by_id: dict[str, dict]) -> tuple[str, str, str, dict] | None:
    """→ (khoá ghim, lớp, tên ghim, sản phẩm đại diện), hoặc None nếu sản phẩm không có toạ độ."""
    a = p["attributes"]
    if a.get("latitude") is None or a.get("longitude") is None:
        return None
    if p["taxonomy"] == "hotel":
        anchor = by_id.get(a.get("parentProductId"), p) if a.get("level") == "room" else p
        return f"hotel:{anchor['productId']}", "khach-san", anchor["name"], anchor
    if p["taxonomy"] == "flight":
        code = a.get("destinationAirport") or next(iter(a.get("destinationAirports") or []), "")
        name = a.get("destinationAirportName") or f"Sân bay {code}"
        return f"airport:{fold(name)}", "san-bay", name, p
    if a.get("venue"):  # khoá có toạ độ: vé của địa điểm chưa duyệt có thể mượn toạ độ trip.com khác nhau
        return f"venue:{fold(a['venue'])}@{a['latitude']:.5f},{a['longitude']:.5f}", "vui-choi", a["venue"], p
    if a.get("poiRef"):
        return a["poiRef"], "vui-choi", a.get("poiName") or p["name"], p
    return f"product:{p['productId']}", "vui-choi", p["name"], p


def build_places(products: list[dict]) -> list[dict]:
    by_id = {p["productId"]: p for p in products}
    groups: dict[str, dict] = {}
    for p in products:
        found = _place_of(p, by_id)
        if found is None:
            continue
        key, layer, name, anchor = found
        g = groups.setdefault(key, {"placeKey": key, "layer": layer, "name": name, "anchor": anchor, "items": []})
        if g["anchor"]["attributes"].get("level") == "room" and anchor["attributes"].get("level") != "room":
            g["anchor"] = anchor
        g["items"].append(p)

    places = []
    for g in groups.values():
        items, anchor = g["items"], g["anchor"]
        aa = anchor["attributes"]
        prices = [x["unitPrice"] for x in items if isinstance(x.get("unitPrice"), (int, float)) and x["unitPrice"] > 0]
        price_from = min(prices) if prices else None
        if g["layer"] == "khach-san":
            rooms = [x for x in items if x["attributes"].get("level") == "room"]
            stars = aa.get("starRating")
            category = "Khách sạn" + (f" {stars:g}★" if isinstance(stars, (int, float)) else "")
            parts = [f"{len(rooms)} hạng phòng" if rooms else "khách sạn"]
            if price_from:
                parts.append(f"từ {_fmt_vnd(price_from)}/đêm")
            if aa.get("address"):
                parts.append(str(aa["address"]))
        elif g["layer"] == "san-bay":
            routes = [x for x in items if x["attributes"].get("level") == "route"]
            origins = sorted({x["attributes"]["originCity"] for x in items if x["attributes"].get("originCity")})
            category = "Sân bay"
            parts = [f"{len(routes)} tuyến bay đến"]
            if origins:
                parts.append("từ " + ", ".join(origins))
            if price_from:
                parts.append(f"vé một chiều từ {_fmt_vnd(price_from)}")
        else:
            kinds = Counter(x["taxonomy"] for x in items)
            category = ", ".join(CATEGORY.get(t, t) for t, _ in kinds.most_common())
            parts = [f"{len(items)} vé/combo"] if len(items) > 1 else []
            if price_from:
                parts.append(f"từ {_fmt_vnd(price_from)}")
            if aa.get("openingHours"):
                parts.append(f"mở cửa {aa['openingHours']}")
            if len(items) > 1:
                parts.append("vd. " + "; ".join(x["name"] for x in items[:3]))
            elif anchor.get("description"):
                parts.append(anchor["description"].replace("\n", " ")[:200])
        destinations = Counter(x["destination"] for x in items if x.get("destination"))
        lat, lng = aa["latitude"], aa["longitude"]
        places.append({
            **g,
            "latitude": round(lat, 6),
            "longitude": round(lng, 6),
            "category": category,
            "destination": destinations.most_common(1)[0][0] if destinations else anchor.get("destination"),
            "description": " · ".join(parts),
            "products": len(items),
            "priceFromVnd": price_from,
            "available": any(x.get("available") for x in items),
            "starRating": aa.get("starRating") if g["layer"] == "khach-san" else None,
            "url": aa.get("url") or next((x["attributes"]["url"] for x in items if x["attributes"].get("url")), None),
            "imageUrl": anchor.get("imageUrl") or next((x["imageUrl"] for x in items if x.get("imageUrl")), None),
            "locationSource": aa.get("locationSource"),
            "locationPrecision": aa.get("locationPrecision"),
            "warning": aa.get("locationWarning") or next((x["attributes"]["locationWarning"] for x in items if x["attributes"].get("locationWarning")), None),
            "googleMapsUrl": maps_url(lat, lng),
        })
    order = list(LAYERS)
    places.sort(key=lambda pl: (order.index(pl["layer"]), pl["destination"] or "", fold(pl["name"])))
    return places


def _cell(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return str(int(v)) if v.is_integer() else f"{v:.6f}".rstrip("0").rstrip(".")
    return str(v)


def write_layer_csvs(places: list[dict], out_dir: Path) -> list[str]:
    for old in out_dir.glob("mymaps-*.csv"):  # lần trước có thể tách nhiều phần hơn
        old.unlink()
    files = []
    for layer in LAYERS:
        rows = [pl for pl in places if pl["layer"] == layer]
        for part, start in enumerate(range(0, len(rows), MY_MAPS_MAX_DATA_ROWS), 1):
            path = out_dir / f"mymaps-{layer}{'' if part == 1 else f'-{part}'}.csv"
            with open(path, "w", encoding="utf-8", newline="") as f:
                w = csv.writer(f)
                w.writerow(CSV_FIELDS)
                for pl in rows[start:start + MY_MAPS_MAX_DATA_ROWS]:
                    w.writerow([_cell(pl.get(k)) for k in CSV_FIELDS])
            files.append(path.name)
    return files


def write_geojson(places: list[dict], path: Path) -> None:
    features = []
    for pl in places:
        props = {k: pl.get(k) for k in CSV_FIELDS if k not in ("latitude", "longitude")}
        props["layer"] = LAYERS[pl["layer"]]
        props["items"] = [
            {"productId": x["productId"], "name": x["name"], "taxonomy": x["taxonomy"], "level": x["attributes"].get("level"),
             "unitPrice": x.get("unitPrice"), "available": x.get("available")}
            for x in pl["items"]
        ]
        features.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [pl["longitude"], pl["latitude"]]},
                         "properties": props})
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f, ensure_ascii=False)


def review_rows(products: list[dict], venues: list) -> list[list]:
    rows: list[list] = []
    for v in venues:
        if v.tickets and not v.usable:
            rows.append(["địa điểm Vinpearl chưa có toạ độ dùng được", v.name, v.destination, v.latitude, v.longitude,
                         v.note or "chưa có toạ độ", maps_url(v.latitude, v.longitude),
                         "collectors/venues.csv: điền latitude, longitude đúng, source=manual, status=ok", v.key])
    warned: Counter = Counter()
    first: dict[tuple, dict] = {}
    for p in products:
        a = p["attributes"]
        if not a.get("locationWarning") or a.get("level") == "room":
            continue
        key = (a.get("venue") or p["sourceRef"], a["locationWarning"])
        warned[key] += 1
        first.setdefault(key, p)
    for key, n in warned.items():
        p = first[key]
        a = p["attributes"]
        if a.get("venue"):
            name, fix = f"{a['venue']} ({n} vé)", "tên vé nêu điểm đến khác địa điểm: kiểm tra alias/suppliers trong collectors/venues.csv"
            ref = p["sourceRef"]
        else:
            name, fix, ref = p["name"], "collectors/location_overrides.csv: thêm dòng sourceRef, latitude, longitude, note", p["sourceRef"]
        rows.append(["toạ độ bị cảnh báo", name, p["destination"], a.get("latitude"), a.get("longitude"), key[1],
                     maps_url(a.get("latitude"), a.get("longitude")), fix, ref])
    unmatched: Counter = Counter()
    for p in products:
        a = p["attributes"]
        if p["sourceRef"].startswith("vinpearl:tour:") and not a.get("venue") and a.get("latitude") is None:
            unmatched[(a.get("supplier") or "(không có nhà cung cấp)", p["destination"] or "")] += 1
    for (supplier, destination), n in unmatched.most_common():
        rows.append(["vé Vinpearl chưa khớp địa điểm", supplier, destination, None, None, f"{n} vé không có toạ độ", "",
                     "collectors/venues.csv: thêm địa điểm, hoặc thêm alias vào địa điểm có sẵn", ""])
    for v in venues:
        if v.tickets and v.status == "auto":
            rows.append(["địa điểm Vinpearl tự tìm (nên xem nhanh)", v.name, v.destination, v.latitude, v.longitude,
                         f"kết quả: {v.candidate}", maps_url(v.latitude, v.longitude),
                         "đúng: đặt status=ok · sai: sửa latitude, longitude, source=manual, status=ok", v.key])
    return rows


def write_map(products: list[dict], out_dir: Path, venues: list) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    places = build_places(products)
    files = write_layer_csvs(places, out_dir)
    write_geojson(places, out_dir / "places.geojson")
    rows = review_rows(products, venues)
    with open(out_dir / "can-kiem-tra.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(REVIEW_FIELDS)
        w.writerows([_cell(x) for x in row] for row in rows)
    return {"places": len(places), "files": files + ["places.geojson"], "review": len(rows)}
