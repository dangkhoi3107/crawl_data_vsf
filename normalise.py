#!/usr/bin/env python3
"""Gộp dữ liệu thô từ data/interim/*.jsonl thành catalog theo schema Product (§6 handbook).

Đầu ra (trong --data-dir, mặc định ./data):
  products.jsonl       một Product mỗi dòng, đúng các trường của schema
  products.csv         cùng dữ liệu, attributes để dạng JSON
  dedup_report.csv     khách sạn Vinpearl được ghép với booking.com (điểm giống tên, điểm đến)
  stats.md             số lượng theo nguồn/hạng mục/điểm đến, độ phủ mô tả tiếng Việt, mẫu để đọc tay

Quy tắc gộp trùng (khách sạn Vinpearl có trên cả hai nguồn):
  tên, mô tả, ảnh, hạng phòng     → Vinpearl (nội dung của chính công ty)
  giá bán                          → Vinpearl (kênh bán trực tiếp); thiếu thì dùng booking.com
  giá booking.com                  → attributes.otaPrice (để so sánh giá đối thủ)
  toạ độ, hạng sao                 → Vinpearl; thiếu thì booking.com
  điểm đánh giá booking.com        → attributes.bookingReviewScore / bookingReviewCount
Hạng phòng booking.com của khách sạn đã gộp bị bỏ (trùng hạng phòng Vinpearl), trừ khi --keep-duplicate-rooms.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import sys
import uuid
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from collectors.common import Paths, default_data_dir, read_jsonl, setup_logging
from collectors.geo import normalise_destination
from collectors.textutil import clean_text, detect_lang, fold, iso_date, uniq

log = logging.getLogger("normalise")

NAMESPACE = uuid.UUID("7a1c9e1e-3b0e-4f5c-9d3a-2f6f0b9c4e21")
TAXONOMIES = ("hotel", "flight", "combo", "attraction", "golf")
PRODUCT_FIELDS = (
    "productId", "name", "taxonomy", "destination", "description", "attributes",
    "unitPrice", "currency", "available", "availableFrom", "availableTo", "imageUrl", "sourceRef",
)

OCEAN_RE = re.compile(r"hướng biển|nhìn ra biển|view biển|giáp biển|sát biển|bãi biển riêng|ocean ?view|sea ?view|beach ?front", re.I)
FAMILY_RE = re.compile(r"gia đình|trẻ em|trẻ nhỏ|family|kids|children|phòng thông nhau|connecting", re.I)
BRAND_RE = re.compile(r"vinpearl|vinholidays|vinwonders", re.I)
HOTEL_BRAND_RE = re.compile(r"^(melia |meliá )?(vinpearl|vinholidays)\b", re.I)  # tên bắt đầu bằng brand; không tính "Homestay gần Vinpearl"


def product_id(source_ref: str) -> str:
    return str(uuid.uuid5(NAMESPACE, source_ref))


def make_product(**kw) -> dict:
    p = {k: kw.get(k) for k in PRODUCT_FIELDS}
    p["name"] = clean_text(p["name"])
    p["description"] = clean_text(p["description"]) or None
    p["currency"] = p["currency"] or "VND"
    p["attributes"] = {k: v for k, v in (p["attributes"] or {}).items() if v not in (None, "", [], {})}
    p["productId"] = product_id(p["sourceRef"])
    if isinstance(p["unitPrice"], float):
        p["unitPrice"] = int(round(p["unitPrice"]))
    return p


def to_vnd(amount, currency: str | None, rates: dict[str, float]) -> tuple[int | None, bool]:
    if amount in (None, 0):
        return None, False
    cur = (currency or "VND").upper()
    if cur == "VND":
        return int(round(float(amount))), False
    rate = rates.get(cur)
    if not rate:
        return None, False
    return int(round(float(amount) * rate / 1000.0) * 1000), True


def latest_by_key(records: list[dict]) -> list[dict]:
    best: dict[str, dict] = {}
    for r in records:
        k = r.get("key")
        if not k:
            continue
        if k not in best or (r.get("crawledAt") or "") >= (best[k].get("crawledAt") or ""):
            best[k] = r
    return list(best.values())


# ---------------------------------------------------------------------- Vinpearl


def vinpearl_products(records: list[dict], today: date) -> tuple[list[dict], list[dict]]:
    """Trả về (products, property_index) – property_index dùng để ghép với booking.com."""
    products: list[dict] = []
    properties: list[dict] = []
    for r in records:
        if r.get("recordType") == "vinpearl_hotel":
            hotel_products = vinpearl_hotel_products(r)
            if hotel_products:
                products.extend(hotel_products)
                properties.append({"product": hotel_products[0], "record": r})
        elif r.get("recordType") == "vinpearl_tour":
            p = vinpearl_tour_product(r, today)
            if p:
                products.append(p)
    return products, properties


def vinpearl_hotel_products(r: dict) -> list[dict]:
    name = r.get("name")
    if not name:
        return []
    site = r.get("site") or {}
    hotel_ref = f"vinpearl:hotel:{r.get('hotelId') or fold(name).replace(' ', '-')}"
    destination = normalise_destination(site.get("destination"), r.get("address"), name)
    description = r.get("description") or ""
    about = "\n\n".join(x for x in (site.get("aboutTitle"), site.get("aboutText")) if x)
    if len(about) > len(description) * 1.2:
        description = about
    rooms = [x for x in r.get("rooms") or [] if x.get("name")]
    site_prices = {fold(x.get("name")): x for x in site.get("rooms") or []}
    room_prices = [x.get("price") or x.get("minPrice") for x in rooms if x.get("price") or x.get("minPrice")]
    best = r.get("bestPrice") or {}
    price = min(room_prices) if room_prices else best.get("salePrice")
    text_blob = " ".join([name, description] + [x["name"] for x in rooms])
    query = r.get("priceQuery") or {}
    prop = make_product(
        name=name,
        taxonomy="hotel",
        destination=destination,
        description=description,
        attributes={
            "level": "property",
            "brand": "Vinpearl",
            "hotelCode": r.get("hotelCode"),
            "address": r.get("address"),
            "latitude": r.get("latitude"),
            "longitude": r.get("longitude"),
            "starRating": r.get("starRating"),
            "starRatingType": "official" if r.get("starRating") else None,
            "tripAdvisorRating": r.get("tripAdvisorRating"),
            "reviewCount": r.get("reviewCount"),
            "amenities": r.get("amenities"),
            "policy": r.get("policy"),
            "roomTypeCount": len(rooms) or None,
            "oceanView": bool(OCEAN_RE.search(text_blob)) or None,
            "familyFriendly": bool(FAMILY_RE.search(text_blob) or any((x.get("maxChild") or 0) > 0 for x in rooms)) or None,
            "memberPrice": best.get("memberPrice"),
            "priceDate": (query.get("dates") or [None])[0],
            "priceNights": query.get("nights"),
            "priceAdults": query.get("adults"),
            "images": r.get("images"),
            "url": r.get("pageUrl"),
            "bookingUrl": r.get("bookingUrl"),
            "descriptionLang": detect_lang(description),
            "fieldSources": {
                "name": "booking-hotel-api.vinpearl.com",
                "description": "vinpearl.com" if description == about and about else "booking-hotel-api.vinpearl.com",
                "unitPrice": "booking-hotel-api.vinpearl.com",
            },
        },
        unitPrice=price,
        currency="VND",
        available=bool(room_prices),
        imageUrl=(r.get("images") or [None])[0],
        sourceRef=hotel_ref,
    )
    out = [prop]
    for room in rooms:
        room_name = room["name"]
        room_text = " ".join([room_name, room.get("description") or ""] + (room.get("amenities") or []))
        occupancy = room.get("maxOccupancy")
        site_room = site_prices.get(fold(room_name)) or {}
        room_price = room.get("price") or room.get("minPrice")
        out.append(
            make_product(
                name=f"{name} - {room_name}",
                taxonomy="hotel",
                destination=destination,
                description=room.get("description") or site_room.get("description") or room.get("shortDescription"),
                attributes={
                    "level": "room",
                    "brand": "Vinpearl",
                    "hotelName": name,
                    "roomName": room_name,
                    "roomCode": room.get("code"),
                    "parentProductId": prop["productId"],
                    "starRating": r.get("starRating"),
                    "latitude": r.get("latitude"),
                    "longitude": r.get("longitude"),
                    "maxOccupancy": occupancy,
                    "maxAdult": room.get("maxAdult"),
                    "maxChild": room.get("maxChild"),
                    "bedrooms": room.get("bedrooms"),
                    "bedType": room.get("bedType"),
                    "isVilla": room.get("isVilla") or None,
                    "roomSizeM2": room.get("sizeM2"),
                    "amenities": room.get("amenities"),
                    "includesBreakfast": room.get("includesBreakfast") or None,
                    "ratePlans": room.get("ratePlans"),
                    "pricesByDate": room.get("pricesByDate"),
                    "minPrice": room.get("minPrice"),
                    "listPrice": site_room.get("listPrice"),
                    "oceanView": bool(OCEAN_RE.search(room_text)) or None,
                    "familyFriendly": bool(FAMILY_RE.search(room_text) or (room.get("maxChild") or 0) > 0 or (occupancy or 0) >= 3) or None,
                    "priceDate": next(iter(room.get("pricesByDate") or {}), None),
                    "images": room.get("images"),
                    "url": r.get("pageUrl"),
                    "bookingUrl": r.get("bookingUrl"),
                    "descriptionLang": detect_lang(room.get("description")),
                },
                unitPrice=room_price,
                currency="VND",
                available=room_price is not None,
                imageUrl=(room.get("images") or [None])[0] or prop["imageUrl"],
                sourceRef=f"{hotel_ref}:room:{room.get('roomTypeId') or fold(room_name).replace(' ', '-')}",
            )
        )
    return out


def _member_tier(name: str) -> str | None:
    """'[VIN33 - Diamond] - ...' → 'VIN33 - Diamond'; '[Khách hàng đặc biệt] ...' → 'Khách hàng đặc biệt'."""
    m = re.match(r"^\[((?:VIN\s*33|VinClub|Khách hàng đặc biệt)[^\]]*)\]", name or "", re.I)
    return m.group(1).strip() if m else None


def vinpearl_taxonomy(r: dict) -> str:
    name = fold(r.get("name"))
    code = (r.get("tourCode") or "").upper()
    if "golf" in name or "tee time" in name:
        return "golf"
    if "combo" in name or code.startswith("GN") or re.search(r"\bgoi\b|nghi duong|\d+\s*n\s*\d+\s*d|khach san", name):
        return "combo"
    return "attraction"


def vinpearl_tour_product(r: dict, today: date) -> dict | None:
    name = r.get("name")
    if not name:
        return None
    sections = []
    for block in r.get("extraInfos") or []:
        if block.get("text"):
            sections.append(f"{block.get('title')}\n{block['text']}" if block.get("title") else block["text"])
    parts = [r.get("description"), r.get("highlight")] + sections
    description = "\n\n".join(x for x in parts if x) or r.get("shortDescription")
    sale_end = iso_date(r.get("saleEndDate"))
    available = bool(r.get("isEnabled", True)) and (sale_end is None or sale_end >= today.isoformat())
    audience = r.get("audience") or []
    text_blob = " ".join([name, description or ""] + audience)
    price = r.get("adultSalePrice") or r.get("adultOriginalPrice")
    return make_product(
        name=name,
        taxonomy=vinpearl_taxonomy(r),
        destination=normalise_destination(name, r.get("destinationName")),
        description=description,
        attributes={
            "brand": "Vinpearl",
            "tourCode": r.get("tourCode"),
            "province": r.get("destinationName"),
            "departure": r.get("departure"),
            "adultOriginalPrice": r.get("adultOriginalPrice"),
            "childPrice": r.get("childSalePrice") or r.get("childOriginalPrice"),
            "promo": r.get("shortDescription"),
            "audience": audience,
            "familyFriendly": ("Gia đình" in audience) or bool(FAMILY_RE.search(text_blob)) or None,
            "serviceIncluded": r.get("serviceIncluded"),
            "serviceExcluded": r.get("serviceExcluded"),
            "itinerary": r.get("tripItinerary"),
            "lengthOfTour": r.get("lengthOfTour") if r.get("lengthOfTour") not in ("0", 0) else None,
            "soldQuantity": r.get("soldQuantity"),
            "supplier": r.get("supplierName"),
            "vinpearlType": r.get("type"),
            "salesChannels": r.get("salesChannels"),
            "memberTier": _member_tier(name),
            "images": r.get("images"),
            "url": r.get("pageUrl"),
            "hasDetail": r.get("hasDetail"),
            "descriptionLang": detect_lang(description),
        },
        unitPrice=price,
        currency="VND",
        available=available,
        availableFrom=iso_date(r.get("saleStartDate")),
        availableTo=sale_end,
        imageUrl=(r.get("images") or [None])[0],
        sourceRef=f"vinpearl:tour:{r.get('tourCode') or r.get('id')}",
    )


# ---------------------------------------------------------------------- booking.com


def booking_hotel_products(r: dict, rates: dict[str, float]) -> tuple[dict | None, list[dict]]:
    name = r.get("name")
    if not name:
        return None, []
    addr = r.get("address") or {}
    destination = normalise_destination(r.get("city"), addr.get("locality"), addr.get("street"), r.get("province"), addr.get("region"), name)
    hotel_ref = f"booking:hotel:{r.get('hotelId') or fold(name).replace(' ', '-')}"
    rooms = r.get("rooms") or []
    converted_any = False
    room_prices = []
    for room in rooms:
        vnd, conv = to_vnd(room.get("minPrice"), room.get("currency"), rates)
        room["_vnd"] = vnd
        converted_any |= conv
        if vnd:
            room_prices.append(vnd)
    facilities = uniq((r.get("popularFacilities") or []) + (r.get("facilities") or []))
    text_blob = " ".join([name, r.get("description") or ""] + facilities + [x.get("name") or "" for x in rooms])
    price_query = r.get("priceQuery") or {}
    review = r.get("reviewScore")
    common = {
        "province": r.get("province"),
        "city": r.get("city"),
        "address": addr.get("street"),
        "latitude": r.get("latitude"),
        "longitude": r.get("longitude"),
        "starRating": r.get("starRating"),
        "starRatingType": r.get("starRatingType"),
        "reviewScore": review,
        "reviewScoreScale": r.get("reviewScoreScale") if review is not None else None,
        "reviewCount": r.get("reviewCount"),
        "propertyType": r.get("propertyType"),
        "brand": "Vinpearl" if HOTEL_BRAND_RE.search(fold(name)) else None,
    }
    prop = make_product(
        name=name,
        taxonomy="hotel",
        destination=destination,
        description=r.get("description") or r.get("descriptionShort"),
        attributes={
            "level": "property",
            **common,
            "amenities": facilities[:60],
            "highlights": r.get("highlights"),
            "roomTypeCount": len(rooms) or None,
            "oceanView": bool(OCEAN_RE.search(text_blob)) or None,
            "familyFriendly": bool(FAMILY_RE.search(text_blob)) or None,
            "priceDate": price_query.get("checkin"),
            "priceNights": _nights(price_query),
            "priceAdults": price_query.get("adults"),
            "priceConverted": converted_any or None,
            "images": r.get("images"),
            "url": r.get("url"),
            "descriptionLang": detect_lang(r.get("description")),
        },
        unitPrice=min(room_prices) if room_prices else None,
        currency="VND",
        available=bool(room_prices),
        imageUrl=(r.get("images") or [None])[0],
        sourceRef=hotel_ref,
    )
    room_products = []
    for room in rooms:
        room_name = room.get("name")
        if not room_name:
            continue
        facts = [room_name]
        if room.get("bed"):
            facts.append(room["bed"])
        if room.get("maxOccupancy"):
            facts.append(f"Tối đa {room['maxOccupancy']} khách")
        facts.extend((room.get("facilities") or [])[:25])
        room_desc = ". ".join(uniq(facts))
        if r.get("description"):
            room_desc = f"{room_desc}.\n\n{r['description']}"
        room_text = " ".join([room_name] + (room.get("facilities") or []))
        occ = room.get("maxOccupancy")
        room_products.append(
            make_product(
                name=f"{name} - {room_name}",
                taxonomy="hotel",
                destination=destination,
                description=room_desc,
                attributes={
                    "level": "room",
                    **common,
                    "hotelName": name,
                    "roomName": room_name,
                    "roomId": room.get("roomId"),
                    "parentProductId": prop["productId"],
                    "bed": room.get("bed"),
                    "maxOccupancy": occ,
                    "roomSizeM2": room.get("sizeM2"),
                    "amenities": room.get("facilities"),
                    "conditions": room.get("conditions"),
                    "oceanView": bool(OCEAN_RE.search(room_text)) or None,
                    "familyFriendly": bool(FAMILY_RE.search(room_text) or (occ or 0) >= 3) or None,
                    "priceDate": price_query.get("checkin"),
                    "priceNights": _nights(price_query),
                    "descriptionSource": "derived: thông tin phòng + mô tả khách sạn",
                    "url": r.get("url"),
                },
                unitPrice=room.get("_vnd"),
                currency="VND",
                available=bool(room.get("_vnd")),
                imageUrl=prop["imageUrl"],
                sourceRef=f"{hotel_ref}:room:{room.get('roomId') or fold(room_name).replace(' ', '-')}",
            )
        )
    return prop, room_products


def booking_attraction_product(r: dict, rates: dict[str, float]) -> dict | None:
    name = r.get("name")
    if not name:
        return None
    vnd, converted = to_vnd(r.get("price"), r.get("currency"), rates)
    parts = [r.get("subtitle"), r.get("description")]
    if r.get("highlights"):
        parts.append("Điểm nổi bật:\n" + "\n".join(f"- {h}" for h in r["highlights"]))
    description = "\n\n".join(x for x in parts if x)
    fname = fold(name)
    taxonomy = "golf" if "golf" in fname else "combo" if "combo" in fname else "attraction"
    return make_product(
        name=name,
        taxonomy=taxonomy,
        destination=normalise_destination(name, r.get("subtitle"), r.get("city")),
        description=description,
        attributes={
            "city": r.get("city"),
            "duration": r.get("duration"),
            "cancellation": r.get("cancellation"),
            "additionalInfo": r.get("additionalInfo"),
            "guideLanguages": r.get("guideLanguages"),
            "meetingPoints": r.get("meetingPoints"),
            "highlights": r.get("highlights"),
            "included": r.get("included"),
            "excluded": r.get("excluded"),
            "rating": r.get("rating"),
            "reviewCount": r.get("reviewCount"),
            "originalPrice": r.get("price") if converted else None,
            "originalCurrency": r.get("currency") if converted else None,
            "priceConverted": converted or None,
            "familyFriendly": bool(FAMILY_RE.search(description)) or None,
            "brand": "Vinpearl" if BRAND_RE.search(name) else None,
            "images": r.get("images"),
            "url": r.get("url"),
            "descriptionLang": r.get("descriptionLang") or detect_lang(description),
        },
        unitPrice=vnd,
        currency="VND",
        available=vnd is not None,
        imageUrl=(r.get("images") or [None])[0],
        sourceRef=f"booking:attraction:{r.get('productId')}",
    )


def _nights(q: dict) -> int | None:
    try:
        return (date.fromisoformat(q["checkout"]) - date.fromisoformat(q["checkin"])).days
    except (KeyError, TypeError, ValueError):
        return None


# ---------------------------------------------------------------------- dedup


def match_vinpearl_to_booking(vp_props: list[dict], bk_props: list[dict], threshold: float) -> list[tuple[dict, dict, float]]:
    from rapidfuzz import fuzz

    def norm(s: str) -> str:
        s = fold(s)
        s = re.sub(r"\b(affiliated by melia|by melia|resort and spa|hotel|khach san|the)\b", " ", s)
        return re.sub(r"\s+", " ", s).strip()

    by_dest: dict[str | None, list[dict]] = defaultdict(list)
    for b in bk_props:
        by_dest[b["destination"]].append(b)
    scored = []
    for v in vp_props:
        vn = norm(v["name"])
        for b in (by_dest.get(v["destination"]) or []) if v["destination"] else bk_props:
            if v["destination"] and b["destination"] and v["destination"] != b["destination"]:
                continue
            score = fuzz.token_sort_ratio(vn, norm(b["name"]))
            if score >= threshold:
                scored.append((score, v, b))
    scored.sort(key=lambda x: -x[0])
    used_v: set[str] = set()
    used_b: set[str] = set()
    matches = []
    for score, v, b in scored:
        if v["productId"] in used_v or b["productId"] in used_b:
            continue
        used_v.add(v["productId"])
        used_b.add(b["productId"])
        matches.append((v, b, score))
    return matches


def merge_property(vp: dict, bk: dict) -> None:
    """Gộp khách sạn booking.com vào bản ghi Vinpearl: Vinpearl giữ tên, mô tả, giá bán trực tiếp;
    booking.com lấp chỗ trống và thêm giá OTA để so sánh."""
    a, b = vp["attributes"], bk["attributes"]
    sources = a.setdefault("fieldSources", {})
    if not vp.get("unitPrice") and bk.get("unitPrice"):
        vp["unitPrice"] = bk["unitPrice"]
        vp["available"] = bk["available"]
        sources["unitPrice"] = sources["available"] = "booking.com"
        a["priceDate"] = b.get("priceDate")
    if bk.get("unitPrice"):
        a["otaPrice"] = {"source": "booking.com", "amount": bk["unitPrice"], "date": b.get("priceDate"), "nights": b.get("priceNights")}
    for field in ("latitude", "longitude", "starRating", "starRatingType", "province", "city", "propertyType"):
        if a.get(field) is None and b.get(field) is not None:
            a[field] = b[field]
            sources[field] = "booking.com"
    if b.get("reviewScore") is not None:
        a["bookingReviewScore"] = b["reviewScore"]
        a["bookingReviewCount"] = b.get("reviewCount")
    a["amenities"] = uniq((a.get("amenities") or []) + (b.get("amenities") or []))[:80] or None
    if not vp.get("description") and bk.get("description"):
        vp["description"] = bk["description"]
        sources["description"] = "booking.com"
    a["sameAs"] = uniq((a.get("sameAs") or []) + [bk["sourceRef"]])
    a["bookingComUrl"] = b.get("url")


# ---------------------------------------------------------------------- outputs


def write_outputs(products: list[dict], data: Path, matches: list[tuple[dict, dict, float]], dropped: Counter) -> None:
    jl = data / "products.jsonl"
    with open(jl, "w", encoding="utf-8") as f:
        for p in products:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    with open(data / "products.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(PRODUCT_FIELDS)
        for p in products:
            w.writerow(
                [json.dumps(p[k], ensure_ascii=False) if k == "attributes" else ("" if p[k] is None else p[k]) for k in PRODUCT_FIELDS]
            )
    with open(data / "dedup_report.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["score", "destination", "vinpearl_name", "vinpearl_sourceRef", "booking_name", "booking_sourceRef", "booking_url"])
        for v, b, s in matches:
            w.writerow([f"{s:.1f}", v["destination"], v["name"], v["sourceRef"], b["name"], b["sourceRef"], b["attributes"].get("url")])
    write_stats(products, data / "stats.md", matches, dropped)
    log.info("Đã ghi %d sản phẩm → %s (+ products.csv, dedup_report.csv, stats.md)", len(products), jl)


def write_stats(products: list[dict], path: Path, matches: list, dropped: Counter) -> None:
    by_src = Counter(p["sourceRef"].split(":")[0] for p in products)
    by_tax = Counter(p["taxonomy"] for p in products)
    by_level = Counter(p["attributes"].get("level", "-") for p in products if p["taxonomy"] == "hotel")
    by_dest = Counter(p["destination"] or "(không rõ)" for p in products)
    with_desc = [p for p in products if p.get("description")]
    vi_desc = [p for p in with_desc if p["attributes"].get("descriptionLang") == "vi"]
    priced = [p for p in products if p.get("unitPrice")]
    coords = [p for p in products if p["attributes"].get("latitude") is not None]
    lines = [
        "# Thống kê catalog",
        "",
        f"Tạo lúc {date.today().isoformat()} · **{len(products)} sản phẩm**",
        "",
        "| Chỉ số | Giá trị |",
        "|---|---|",
        f"| Có mô tả | {len(with_desc)} ({_pct(len(with_desc), len(products))}) |",
        f"| Mô tả tiếng Việt | {len(vi_desc)} ({_pct(len(vi_desc), len(products))}) |",
        f"| Độ dài mô tả trung vị | {_median([len(p['description']) for p in with_desc])} ký tự |",
        f"| Có giá | {len(priced)} ({_pct(len(priced), len(products))}) |",
        f"| Có toạ độ | {len(coords)} ({_pct(len(coords), len(products))}) |",
        f"| Khách sạn Vinpearl ghép được với booking.com | {len(matches)} |",
        "",
        "## Theo nguồn",
        "", *[f"- {k}: {v}" for k, v in by_src.most_common()],
        "", "## Theo taxonomy", "", *[f"- {k}: {v}" for k, v in by_tax.most_common()],
        "", "## Hotel theo cấp", "", *[f"- {k}: {v}" for k, v in by_level.most_common()],
        "", "## Top 30 điểm đến", "", *[f"- {k}: {v}" for k, v in by_dest.most_common(30)],
    ]
    if dropped:
        lines += ["", "## Bị loại", "", *[f"- {k}: {v}" for k, v in dropped.most_common()]]
    lines += ["", "## Mẫu để đọc tay (kiểm tra chất lượng tên + mô tả)", ""]
    sample_pool = [p for p in products if p["attributes"].get("level") != "room"]
    step = max(1, len(sample_pool) // 12)
    for p in sample_pool[::step][:12]:
        desc = (p.get("description") or "").replace("\n", " ")[:280]
        lines.append(f"- **{p['name']}** · {p['taxonomy']} · {p['destination']} · {p.get('unitPrice')} VND  \n  {desc}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _pct(a: int, b: int) -> str:
    return f"{100 * a / b:.1f}%" if b else "0%"


def _median(xs: list[int]) -> int:
    if not xs:
        return 0
    xs = sorted(xs)
    return xs[len(xs) // 2]


# ---------------------------------------------------------------------- main


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", type=Path, default=default_data_dir())
    ap.add_argument("--match-threshold", type=float, default=88.0, help="điểm giống tên tối thiểu để ghép Vinpearl ↔ booking.com")
    ap.add_argument("--keep-duplicate-rooms", action="store_true", help="giữ hạng phòng booking.com của khách sạn đã ghép với Vinpearl")
    ap.add_argument("--min-description", type=int, default=0, help="loại sản phẩm có mô tả ngắn hơn N ký tự")
    ap.add_argument("--vietnamese-only", action="store_true", help="loại sản phẩm có mô tả không phải tiếng Việt")
    ap.add_argument("--drop-member-variants", action="store_true", help="bỏ biến thể giá thành viên của Vinpearl ([VIN33 - Gold]…)")
    ap.add_argument("--usd-vnd", type=float, default=26300.0, help="tỷ giá dùng khi trang không trả VND")
    ap.add_argument("--eur-vnd", type=float, default=30500.0)
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)

    paths = Paths(a.data_dir).ensure()
    setup_logging(paths, a.verbose)
    rates = {"USD": a.usd_vnd, "EUR": a.eur_vnd}
    today = date.today()

    raw: dict[str, list[dict]] = defaultdict(list)
    for f in sorted(paths.interim.glob("*.jsonl")):
        recs = latest_by_key(list(read_jsonl(f)))
        raw[f.stem].extend(recs)
        log.info("Đọc %s: %d bản ghi", f.name, len(recs))
    if not raw:
        log.error("Không có dữ liệu trong %s. Chạy crawl.py trước.", paths.interim)
        return 1

    dropped: Counter = Counter()
    products: list[dict] = []

    vp_products, vp_props = vinpearl_products(raw.get("vinpearl", []), today)

    bk_props: list[dict] = []
    bk_rooms_by_parent: dict[str, list[dict]] = defaultdict(list)
    for r in raw.get("booking_hotels", []):
        prop, rooms = booking_hotel_products(r, rates)
        if prop is None:
            dropped["booking hotel không có tên"] += 1
            continue
        bk_props.append(prop)
        bk_rooms_by_parent[prop["productId"]].extend(rooms)

    matches = match_vinpearl_to_booking([x["product"] for x in vp_props], bk_props, a.match_threshold)
    merged_booking_ids: dict[str, str] = {}
    for v, b, score in matches:
        merge_property(v, b)
        merged_booking_ids[b["productId"]] = v["productId"]
    log.info("Ghép %d khách sạn Vinpearl với booking.com", len(matches))

    products.extend(vp_products)
    for prop in bk_props:
        if prop["productId"] in merged_booking_ids:
            dropped["booking hotel trùng với Vinpearl (đã gộp)"] += 1
            if not a.keep_duplicate_rooms:
                dropped["hạng phòng booking.com của khách sạn Vinpearl đã gộp"] += len(bk_rooms_by_parent[prop["productId"]])
                continue
            for room in bk_rooms_by_parent[prop["productId"]]:
                room["attributes"]["parentProductId"] = merged_booking_ids[prop["productId"]]
        else:
            products.append(prop)
        products.extend(bk_rooms_by_parent[prop["productId"]])

    for r in raw.get("booking_attractions", []):
        p = booking_attraction_product(r, rates)
        if p:
            products.append(p)
        else:
            dropped["attraction không có tên"] += 1

    final: list[dict] = []
    seen: set[str] = set()
    for p in products:
        if p["productId"] in seen:
            dropped["trùng sourceRef"] += 1
            continue
        if not p["name"]:
            dropped["thiếu tên"] += 1
            continue
        if p["taxonomy"] not in TAXONOMIES:
            dropped["taxonomy lạ"] += 1
            continue
        if a.min_description and len(p.get("description") or "") < a.min_description:
            dropped[f"mô tả < {a.min_description} ký tự"] += 1
            continue
        if a.drop_member_variants and p["attributes"].get("memberTier"):
            dropped["biến thể giá thành viên Vinpearl"] += 1
            continue
        if a.vietnamese_only and p["attributes"].get("descriptionLang") != "vi":
            dropped["mô tả không phải tiếng Việt"] += 1
            continue
        seen.add(p["productId"])
        final.append(p)

    write_outputs(final, paths.data, matches, dropped)
    return 0


if __name__ == "__main__":
    sys.exit(main())
