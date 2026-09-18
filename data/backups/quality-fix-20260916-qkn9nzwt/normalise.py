#!/usr/bin/env python3
"""Gộp dữ liệu thô từ data/interim/*.jsonl thành catalog theo schema Product (§6 handbook).

Đầu ra (trong --data-dir, mặc định ./data):
  products.jsonl       một Product mỗi dòng, đúng 13 trường của schema
  products.csv         cùng dữ liệu, attributes để dạng JSON
  dedup_report.csv     các cụm sản phẩm trùng giữa nguồn (khách sạn, điểm tham quan) và điểm giống nhau
  stats.md             đối chiếu mục tiêu handbook, số lượng theo nguồn / loại / điểm đến, mẫu để đọc tay
  map/                 vị trí cho Google My Maps (CSV mỗi lớp) và web app (places.geojson), can-kiem-tra.csv

Quy tắc gộp trùng (handbook §3: "vinpearl.com for names and descriptions, the OTAs for pricing and availability"):
  tên, mô tả, ảnh, hạng phòng       → Vinpearl; không có Vinpearl thì booking.com, rồi agoda.com
  giá, tình trạng còn chỗ            → OTA: booking.com, không có thì agoda.com (trip.com với vé tham quan)
  giá Vinpearl                        → attributes.vinpearlPrice; mọi giá OTA → attributes.otaPrices
  hạng sao, địa chỉ                   → nguồn chính; thiếu thì lấy từ nguồn còn lại
  toạ độ khách sạn                    → nguồn chính; toạ độ nghi sai (trùng khách sạn khác địa chỉ, xa tâm điểm đến)
                                        thì lấy nguồn còn lại. Hạng phòng dùng toạ độ khách sạn
  toạ độ vé/combo/golf Vinpearl       → địa điểm dùng vé trong collectors/venues.csv (crawl.py venues), rồi trip.com
  toạ độ vé máy bay                   → sân bay đến (geo.AIRPORTS); sửa tay mọi loại: collectors/location_overrides.csv
  giờ mở cửa, thời lượng tham quan    → trip.com
Theo kế hoạch (collectors/plan.py): chỉ giữ sản phẩm OTA thuộc các điểm đến trong kế hoạch, tối đa N mỗi điểm đến;
sản phẩm Vinpearl luôn được giữ. Tắt bằng --no-plan.
"""

from __future__ import annotations

import argparse
import copy
import csv
import json
import logging
import math
import re
import sys
import uuid
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from collectors import mapexport
from collectors.common import Paths, default_data_dir, read_jsonl, setup_logging
from collectors.geo import AIRPORTS, clean_coords, destination_in_text, destination_radius_km, km_from_destination, normalise_destination
from collectors.plan import TARGET_MAX, TARGET_MIN, Budget, budget_with, select_destinations
from collectors.textutil import clean_text, detect_lang, first_int, fold, iso_date, uniq
from collectors.venues import Venue, VenueMatcher, load_venues

log = logging.getLogger("normalise")

NAMESPACE = uuid.UUID("7a1c9e1e-3b0e-4f5c-9d3a-2f6f0b9c4e21")
TAXONOMIES = ("hotel", "flight", "combo", "attraction", "golf")
PRODUCT_FIELDS = (
    "productId", "name", "taxonomy", "destination", "description", "attributes",
    "unitPrice", "currency", "available", "availableFrom", "availableTo", "imageUrl", "sourceRef",
)
SOURCE_ORDER = {"vinpearl": 0, "booking": 1, "agoda": 2}

OCEAN_RE = re.compile(r"hướng biển|nhìn ra biển|view biển|giáp biển|sát biển|bãi biển riêng|ocean ?view|sea ?view|beach ?front", re.I)
FAMILY_RE = re.compile(r"gia đình|trẻ em|trẻ nhỏ|family|kids|children|phòng thông nhau|connecting", re.I)
HOTEL_BRAND_RE = re.compile(r"^(melia |meliá )?(vinpearl|vinholidays)\b", re.I)  # "Homestay gần Vinpearl" không tính


# ---------------------------------------------------------------------- tiện ích


def product_id(source_ref: str) -> str:
    return str(uuid.uuid5(NAMESPACE, source_ref))


def make_product(meta: dict | None = None, **kw) -> dict:
    p = {k: kw.get(k) for k in PRODUCT_FIELDS}
    p["name"] = clean_text(p["name"])
    p["description"] = clean_text(p["description"]) or None
    p["currency"] = p["currency"] or "VND"
    p["attributes"] = _compact(p["attributes"] or {})
    p["productId"] = product_id(p["sourceRef"])
    if isinstance(p["unitPrice"], float):
        p["unitPrice"] = int(round(p["unitPrice"]))
    p["_meta"] = meta or {}
    return p


def _compact(d: dict) -> dict:
    return {k: v for k, v in d.items() if v not in (None, "", [], {})}


def to_vnd(amount, currency: str | None, rates: dict[str, float]) -> tuple[int | None, bool]:
    if amount in (None, 0, ""):
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


def _nights(q: dict) -> int | None:
    try:
        return (date.fromisoformat(q["checkout"]) - date.fromisoformat(q["checkin"])).days
    except (KeyError, TypeError, ValueError):
        return None


def haversine_m(a: dict, b: dict) -> float | None:
    la1, lo1, la2, lo2 = a.get("latitude"), a.get("longitude"), b.get("latitude"), b.get("longitude")
    if None in (la1, lo1, la2, lo2):
        return None
    p1, p2 = math.radians(la1), math.radians(la2)
    dp, dl = p2 - p1, math.radians(lo2 - lo1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6_371_000 * 2 * math.asin(math.sqrt(h))


_GENERIC_NAME = re.compile(r"\b(khu nghi duong|khach san|hotel|the|va|and|affiliated by|by|former name[^)]*|ten truoc day[^)]*)\b")


def name_keys(*names: str | None) -> list[str]:
    """Các biến thể tên để so khớp: tên đầy đủ, bỏ phần trong ngoặc, phần trong ngoặc (tên tiếng Anh của agoda)."""
    out = []
    for n in names:
        if not n:
            continue
        variants = [n, re.sub(r"\(.*\)", " ", n)] + re.findall(r"\(([^()]+)\)", n)
        for v in variants:
            k = re.sub(r"\s+", " ", _GENERIC_NAME.sub(" ", fold(v))).strip()
            if k and k not in out:
                out.append(k)
    return out


def _digits(s: str) -> set[str]:
    return set(re.findall(r"\d+", s))


def name_score(a: list[str], b: list[str]) -> float:
    from rapidfuzz import fuzz

    best = 0.0
    for x in a:
        for y in b:
            if _digits(x) != _digits(y):
                continue
            best = max(best, fuzz.token_sort_ratio(x, y))
    return best


def duration_minutes(text: str | None) -> int | None:
    """'3–5 tiếng đồng hồ' → 180; '1–2 ngày' → 480 (một ngày tham quan ~8 tiếng); '30 phút' → 30."""
    if not text:
        return None
    t = fold(text)
    n = first_int(t)
    if n is None:
        return None
    if "ngay" in t or "day" in t:
        return n * 480
    if "tieng" in t or "gio" in t or "hour" in t:
        return n * 60
    if "phut" in t or "min" in t:
        return n
    return None


# ---------------------------------------------------------------------- Vinpearl


def vinpearl_hotel(r: dict) -> tuple[dict | None, list[dict]]:
    name = r.get("name")
    if not name:
        return None, []
    site = r.get("site") or {}
    hotel_ref = f"vinpearl:hotel:{r.get('hotelId') or fold(name).replace(' ', '-')}"
    destination = normalise_destination(name, site.get("destination"), r.get("address"))  # tên Vinpearl chứa điểm đến
    description = r.get("description") or ""
    about = "\n\n".join(x for x in (site.get("aboutTitle"), site.get("aboutText")) if x)
    if len(about) > len(description) * 1.2:
        description = about
    rooms_raw = [x for x in r.get("rooms") or [] if x.get("name")]
    site_prices = {fold(x.get("name")): x for x in site.get("rooms") or []}
    room_prices = [x.get("price") or x.get("minPrice") for x in rooms_raw if x.get("price") or x.get("minPrice")]
    best = r.get("bestPrice") or {}
    price = min(room_prices) if room_prices else best.get("salePrice")
    text_blob = " ".join([name, description] + [x["name"] for x in rooms_raw])
    query = r.get("priceQuery") or {}
    lat, lng = clean_coords(r.get("latitude"), r.get("longitude"))
    prop = make_product(
        meta={"src": "vinpearl"},
        name=name,
        taxonomy="hotel",
        destination=destination,
        description=description,
        attributes={
            "level": "property",
            "brand": "Vinpearl",
            "hotelCode": r.get("hotelCode"),
            "address": r.get("address"),
            "latitude": lat,
            "longitude": lng,
            "starRating": r.get("starRating"),
            "starRatingType": "official" if r.get("starRating") else None,
            "tripAdvisorRating": r.get("tripAdvisorRating"),
            "tripAdvisorReviewCount": r.get("reviewCount"),
            "amenities": r.get("amenities"),
            "policy": r.get("policy"),
            "roomTypeCount": len(rooms_raw) or None,
            "oceanView": bool(OCEAN_RE.search(text_blob)) or None,
            "familyFriendly": bool(FAMILY_RE.search(text_blob) or any((x.get("maxChild") or 0) > 0 for x in rooms_raw)) or None,
            "memberPrice": best.get("memberPrice"),
            "priceDate": (query.get("dates") or [None])[0],
            "priceNights": query.get("nights"),
            "priceAdults": query.get("adults"),
            "images": r.get("images"),
            "url": r.get("pageUrl"),
            "bookingUrl": r.get("bookingUrl"),
            "descriptionLang": detect_lang(description),
            "fieldSources": {
                "name": "vinpearl",
                "description": "vinpearl.com" if description == about and about else "vinpearl",
                "unitPrice": "vinpearl",
            },
        },
        unitPrice=price,
        currency="VND",
        available=bool(room_prices),
        imageUrl=(r.get("images") or [None])[0],
        sourceRef=hotel_ref,
    )
    rooms = []
    for room in rooms_raw:
        room_name = room["name"]
        room_text = " ".join([room_name, room.get("description") or ""] + (room.get("amenities") or []))
        occupancy = room.get("maxOccupancy")
        site_room = site_prices.get(fold(room_name)) or {}
        room_price = room.get("price") or room.get("minPrice")
        room_desc = room.get("description") or site_room.get("description") or room.get("shortDescription") or ""
        derived_desc = len(room_desc) < 80  # vd. "Deluxe Twin Terrace": quá ngắn để embedding → ghép thêm thông tin phòng
        if derived_desc:
            facts = [f"{room_name} tại {name}", room_desc if fold(room_desc) != fold(room_name) else ""]
            if room.get("sizeM2"):
                facts.append(f"Diện tích {room['sizeM2']:g} m²")
            if room.get("bedType"):
                facts.append(f"Giường: {room['bedType']}")
            if occupancy:
                facts.append(f"Tối đa {occupancy} khách")
            if room.get("amenities"):
                facts.append("Tiện nghi: " + ", ".join(room["amenities"][:12]))
            room_desc = ". ".join(x for x in facts if x) + "."
        rooms.append(
            make_product(
                meta={"src": "vinpearl", "roomName": room_name},
                name=f"{name} - {room_name}",
                taxonomy="hotel",
                destination=destination,
                description=room_desc,
                attributes={
                    "level": "room",
                    "brand": "Vinpearl",
                    "hotelName": name,
                    "roomName": room_name,
                    "roomCode": room.get("code"),
                    "parentProductId": prop["productId"],
                    "starRating": r.get("starRating"),
                    "latitude": lat,
                    "longitude": lng,
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
                    "listPrice": site_room.get("listPrice"),
                    "oceanView": bool(OCEAN_RE.search(room_text)) or None,
                    "familyFriendly": bool(FAMILY_RE.search(room_text) or (room.get("maxChild") or 0) > 0 or (occupancy or 0) >= 3) or None,
                    "priceDate": next(iter(room.get("pricesByDate") or {}), None),
                    "images": room.get("images"),
                    "url": r.get("pageUrl"),
                    "bookingUrl": r.get("bookingUrl"),
                    "descriptionSource": "derived: thông tin phòng (mô tả gốc quá ngắn)" if derived_desc else None,
                    "descriptionLang": detect_lang(room_desc),
                    "fieldSources": {"unitPrice": "vinpearl"},
                },
                unitPrice=room_price,
                currency="VND",
                available=room_price is not None,
                imageUrl=(room.get("images") or [None])[0] or prop["imageUrl"],
                sourceRef=f"{hotel_ref}:room:{room.get('roomTypeId') or fold(room_name).replace(' ', '-')}",
            )
        )
    return prop, rooms


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


POLICY_TITLE_RE = re.compile(r"điều khoản|chính sách|hoàn\s*h|hướng dẫn|lưu ý|quy định|terms|cancellation|how to use|policy", re.I)


def vinpearl_tour_product(r: dict, today: date) -> dict | None:
    name = r.get("name")
    if not name:
        return None
    # Tách "trải nghiệm" (Mô tả, Thông tin chung, Bao gồm) khỏi "chính sách" (Điều khoản, Hoàn huỷ, Hướng dẫn sử dụng):
    # mô tả dùng để embedding chỉ nên nói về sản phẩm.
    content, policies = [], {}
    for block in r.get("extraInfos") or []:
        title, text = block.get("title") or "", block.get("text") or ""
        if not text:
            continue
        if POLICY_TITLE_RE.search(title):
            policies.setdefault(title, text[:2000])
        else:
            content.append((title, text))
    vi_content = [b for b in content if detect_lang(b[1]) == "vi"]
    content = vi_content or content  # có bản tiếng Việt thì bỏ bản tiếng Anh trùng nội dung
    sections = [f"{t}\n{x}" if t and fold(t) in ("bao gom", "includes") else x for t, x in content]
    parts = [r.get("description"), r.get("highlight")] + sections
    description = "\n\n".join(x for x in parts if x) or r.get("shortDescription")
    sale_end = iso_date(r.get("saleEndDate"))
    price = next((p for p in (r.get("adultSalePrice"), r.get("adultOriginalPrice")) if isinstance(p, (int, float)) and p > 0), None)
    # giá 0 / thiếu trang chi tiết: không coi là miễn phí hay đặt được
    available = (price is not None and bool(r.get("isEnabled", True)) and (sale_end is None or sale_end >= today.isoformat()))
    audience = r.get("audience") or []
    text_blob = " ".join([name, description or ""] + audience)
    return make_product(
        meta={"src": "vinpearl", "supplierCode": r.get("supplierCode"), "supplierName": r.get("supplierName"),
              "imageUrlSlug": r.get("imageUrlSlug")},
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
            "detailMissing": True if not r.get("hasDetail") else None,
            "priceMissing": True if price is None else None,
            "policies": policies,
            "descriptionLang": detect_lang(description),
            "fieldSources": {"unitPrice": "vinpearl"},
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


def booking_hotel(r: dict, rates: dict[str, float]) -> tuple[dict | None, list[dict]]:
    name = r.get("name")
    if not name:
        return None, []
    plan = r.get("plan") or {}
    addr = r.get("address") or {}
    destination = normalise_destination(
        r.get("city"), addr.get("locality"), addr.get("street"), r.get("province"), addr.get("region"), plan.get("destination"), name
    )
    hotel_ref = f"booking:hotel:{r.get('hotelId') or fold(name).replace(' ', '-')}"
    rooms_raw = r.get("rooms") or []
    converted_any = False
    room_prices = []
    for room in rooms_raw:
        vnd, conv = to_vnd(room.get("minPrice"), room.get("currency"), rates)
        room["_vnd"] = vnd
        converted_any |= conv
        if vnd:
            room_prices.append(vnd)
    facilities = uniq((r.get("popularFacilities") or []) + (r.get("facilities") or []))
    text_blob = " ".join([name, r.get("description") or ""] + facilities + [x.get("name") or "" for x in rooms_raw])
    price_query = r.get("priceQuery") or {}
    review = r.get("reviewScore")
    lat, lng = clean_coords(r.get("latitude"), r.get("longitude"))
    common = {
        "province": r.get("province"),
        "city": r.get("city"),
        "address": addr.get("street"),
        "latitude": lat,
        "longitude": lng,
        "starRating": r.get("starRating"),
        "starRatingType": r.get("starRatingType"),
        "propertyType": r.get("propertyType"),
        "brand": "Vinpearl" if HOTEL_BRAND_RE.search(fold(name)) else None,
    }
    meta = {"src": "booking", "plan": plan}
    prop = make_product(
        meta=meta,
        name=name,
        taxonomy="hotel",
        destination=destination,
        description=r.get("description") or r.get("descriptionShort"),
        attributes={
            "level": "property",
            **common,
            "reviewScore": review,
            "reviewScoreScale": r.get("reviewScoreScale") if review is not None else None,
            "reviewCount": r.get("reviewCount"),
            "amenities": facilities[:60],
            "highlights": r.get("highlights"),
            "roomTypeCount": len(rooms_raw) or None,
            "oceanView": bool(OCEAN_RE.search(text_blob)) or None,
            "familyFriendly": bool(FAMILY_RE.search(text_blob)) or None,
            "priceDate": price_query.get("checkin"),
            "priceNights": _nights(price_query),
            "priceAdults": price_query.get("adults"),
            "priceConverted": converted_any or None,
            "images": r.get("images"),
            "url": r.get("url"),
            "descriptionLang": detect_lang(r.get("description") or r.get("descriptionShort")),
            "fieldSources": {"name": "booking.com", "description": "booking.com", "unitPrice": "booking.com"},
        },
        unitPrice=min(room_prices) if room_prices else None,
        currency="VND",
        available=bool(room_prices),
        imageUrl=(r.get("images") or [None])[0],
        sourceRef=hotel_ref,
    )
    rooms = []
    for room in rooms_raw:
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
        rooms.append(
            make_product(
                meta={"src": "booking", "roomName": room_name},
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
                    "descriptionLang": detect_lang(room_desc),
                    "url": r.get("url"),
                    "fieldSources": {"unitPrice": "booking.com"},
                },
                unitPrice=room.get("_vnd"),
                currency="VND",
                available=bool(room.get("_vnd")),
                imageUrl=prop["imageUrl"],
                sourceRef=f"{hotel_ref}:room:{room.get('roomId') or fold(room_name).replace(' ', '-')}",
            )
        )
    return prop, rooms


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
    return make_product(
        meta={"src": "booking_attraction"},
        name=name,
        taxonomy="golf" if "golf" in fname else "combo" if "combo" in fname else "attraction",
        destination=normalise_destination(name, r.get("subtitle"), r.get("city")),
        description=description,
        attributes={
            "city": r.get("city"),
            "duration": r.get("duration"),
            "durationMinutes": duration_minutes(r.get("duration")),
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
            "images": r.get("images"),
            "url": r.get("url"),
            "descriptionLang": r.get("descriptionLang") or detect_lang(description),
            "fieldSources": {"unitPrice": "booking.com"},
        },
        unitPrice=vnd,
        currency="VND",
        available=vnd is not None,
        imageUrl=(r.get("images") or [None])[0],
        sourceRef=f"booking:attraction:{r.get('productId')}",
    )


# ---------------------------------------------------------------------- agoda.com


def agoda_hotel(r: dict, rates: dict[str, float]) -> dict | None:
    name = r.get("name")
    if not name:
        return None
    plan = r.get("plan") or {}
    addr = r.get("address") or {}
    destination = normalise_destination(
        addr.get("region"), addr.get("locality"), addr.get("street"), (r.get("citySlug") or "").replace("-", " "),
        plan.get("destination"), name,
    )
    price, converted = to_vnd(r.get("minPrice"), r.get("currency"), rates)
    facilities = r.get("facilities") or []
    text_blob = " ".join([name, r.get("description") or ""] + facilities)
    q = r.get("priceQuery") or {}
    review = r.get("reviewScore")
    lat, lng = clean_coords(r.get("latitude"), r.get("longitude"))
    return make_product(
        meta={"src": "agoda", "plan": plan},
        name=name,
        taxonomy="hotel",
        destination=destination,
        description=r.get("description"),
        attributes={
            "level": "property",
            "nameEn": r.get("nameEn"),
            "address": ", ".join(x for x in (addr.get("street"), addr.get("locality"), addr.get("region")) if x) or None,
            "city": addr.get("region"),
            "latitude": lat,
            "longitude": lng,
            "starRating": r.get("starRating"),
            "starRatingType": "official" if r.get("starRating") else None,
            "reviewScore": review,
            "reviewScoreScale": r.get("reviewScoreScale") if review is not None else None,
            "reviewCount": r.get("reviewCount"),
            "amenities": facilities[:60],
            "oceanView": bool(OCEAN_RE.search(text_blob)) or None,
            "familyFriendly": bool(FAMILY_RE.search(text_blob)) or None,
            "brand": "Vinpearl" if any(HOTEL_BRAND_RE.search(k) for k in name_keys(name, r.get("nameEn"))) else None,
            "priceDate": q.get("checkin"),
            "priceNights": _nights(q),
            "priceAdults": q.get("adults"),
            "priceConverted": converted or None,
            "images": r.get("images"),
            "url": r.get("url"),
            "descriptionLang": detect_lang(r.get("description")),
            "fieldSources": {"name": "agoda.com", "description": "agoda.com", "unitPrice": "agoda.com"},
        },
        unitPrice=price,
        currency="VND",
        available=price is not None,
        imageUrl=(r.get("images") or [None])[0],
        sourceRef=f"agoda:hotel:{r.get('slug')}:{r.get('citySlug')}",
    )


# ---------------------------------------------------------------------- trip.com


def trip_attraction_product(r: dict) -> dict | None:
    name = r.get("name")
    if not name:
        return None
    plan = r.get("plan") or {}
    tags = r.get("tags") or []
    description = r.get("introduction")
    derived = False
    if not description:
        facts = [name]
        if tags:
            facts.append("Loại hình: " + ", ".join(tags))
        if r.get("address"):
            facts.append("Địa chỉ: " + r["address"])
        if r.get("openingHours"):
            facts.append("Giờ mở cửa: " + r["openingHours"])
        if r.get("suggestedDuration"):
            facts.append("Thời gian tham quan đề xuất: " + r["suggestedDuration"])
        description = ". ".join(facts)
        derived = True
    fname = fold(name)
    text_blob = " ".join([name, description] + tags + [r.get("rankInfo") or ""])
    lat, lng = clean_coords(r.get("latitude"), r.get("longitude"))
    return make_product(
        meta={"src": "trip_attraction", "plan": plan},
        name=name,
        taxonomy="golf" if "golf" in fname else "combo" if "combo" in fname else "attraction",
        destination=normalise_destination(r.get("district"), r.get("address"), r.get("province"), plan.get("destination"), name),
        description=description,
        attributes={
            "nameEn": r.get("englishName") if r.get("englishName") != name else None,
            "address": r.get("address"),
            "district": r.get("district"),
            "province": r.get("province"),
            "latitude": lat,
            "longitude": lng,
            "tags": tags,
            "openingHours": r.get("openingHours"),
            "openingHoursDetail": r.get("openingHoursDetail"),
            "suggestedDuration": r.get("suggestedDuration"),
            "durationMinutes": duration_minutes(r.get("suggestedDuration")),
            "entryPolicies": r.get("entryPolicies"),
            "rating": r.get("rating"),
            "ratingScale": r.get("ratingScale") if r.get("rating") is not None else None,
            "reviewCount": r.get("reviewCount"),
            "popularityScore": r.get("hotScore"),
            "ranking": r.get("rankInfo"),
            "ticketed": r.get("price") is not None,
            "familyFriendly": bool(FAMILY_RE.search(text_blob)) or None,
            "images": r.get("images"),
            "url": r.get("url"),
            "descriptionSource": "derived: loại hình, địa chỉ, giờ mở cửa, thời lượng" if derived else None,
            "descriptionLang": detect_lang(description),
            "fieldSources": {"name": "trip.com", "description": "trip.com", "unitPrice": "trip.com"},
        },
        unitPrice=r.get("price"),
        currency="VND",
        available=r.get("price") is not None,
        imageUrl=(r.get("images") or [None])[0],
        sourceRef=f"trip:attraction:{r.get('poiId')}",
    )


def _hhmm(ts: str | None) -> str | None:
    m = re.match(r"^\d{4}-\d{2}-\d{2}T(\d{2}:\d{2})", ts or "")
    return m.group(1) if m else None  # trip.com ghi giờ địa phương (dù có hậu tố Z)


def _fmt_vnd(v) -> str:
    return f"{int(v):,}".replace(",", ".") + "₫"


def _fmt_duration(minutes: int | None) -> str | None:
    if not minutes:
        return None
    h, m = divmod(minutes, 60)
    return f"{h} giờ {m} phút" if h and m else f"{h} giờ" if h else f"{m} phút"


def airport_location(destination_code: str | None, origin_code: str | None) -> dict:
    """Toạ độ sân bay đến (ghim trên bản đồ) + sân bay đi (vẽ đường bay)."""
    out: dict = {}
    dest = AIRPORTS.get((destination_code or "").upper())
    if dest:
        out.update(latitude=dest[1], longitude=dest[2], destinationAirportName=dest[0], locationSource="ourairports",
                   locationPrecision="airport")
    origin = AIRPORTS.get((origin_code or "").upper())
    if origin:
        out.update(originLatitude=origin[1], originLongitude=origin[2])
    return out


def trip_route_products(r: dict, flights_per_route: int) -> list[dict]:
    from_city, to_city = r.get("fromCity"), r.get("toCity")
    if not from_city or not to_city:
        return []
    # tên hiển thị theo điểm đến chuẩn ("Đảo Phú Quốc" → "Phú Quốc"); giữ tên gốc nếu không khớp
    from_city = normalise_destination(from_city) or from_city
    to_city = normalise_destination(to_city) or to_city
    flights = [f for f in r.get("flights") or [] if f.get("flightNumber")]
    prices = [f["price"] for f in flights if f.get("price")]
    one_way = r.get("oneWay") or {}
    round_trip = r.get("roundTrip") or {}
    monthly = [m for m in one_way.get("monthly") or [] if m.get("price")]
    cheapest_month = min(monthly, key=lambda m: m["price"])["month"] if monthly else None
    dates = sorted((f.get("departureTime") or "")[:10] for f in flights if f.get("departureTime"))
    from_airports = ", ".join(r.get("fromAirports") or []) or r.get("fromCode", "").upper()
    to_airports = ", ".join(r.get("toAirports") or []) or r.get("toCode", "").upper()
    price = min(prices) if prices else one_way.get("lowPrice")
    destination = normalise_destination(to_city)
    facts = [f"Vé máy bay một chiều từ {from_city} ({from_airports}) đến {to_city} ({to_airports})."]
    if r.get("airlines"):
        facts.append("Hãng khai thác: " + ", ".join(r["airlines"]) + ".")
    if r.get("minDurationMinutes"):
        facts.append(f"Thời gian bay khoảng {_fmt_duration(r['minDurationMinutes'])}.")
    if price:
        facts.append(f"Giá một chiều từ {_fmt_vnd(price)}" + (f", khứ hồi từ {_fmt_vnd(round_trip['lowPrice'])}." if round_trip.get("lowPrice") else "."))
    if cheapest_month:
        facts.append(f"Tháng có giá trung bình rẻ nhất: {cheapest_month}.")
    route_ref = f"trip:route:{r.get('fromCode')}-{r.get('toCode')}"
    route = make_product(
        meta={"src": "trip_flight", "plan": r.get("plan") or {}, "fromDestination": normalise_destination(from_city)},
        name=f"Vé máy bay {from_city} - {to_city}",
        taxonomy="flight",
        destination=destination,
        description=" ".join(facts),
        attributes={
            "level": "route",
            "originCity": from_city,
            "destinationCity": to_city,
            "originDestination": normalise_destination(from_city),
            "originAirports": r.get("fromAirports"),
            "destinationAirports": r.get("toAirports"),
            "airlines": r.get("airlines"),
            "durationMinutes": r.get("minDurationMinutes"),
            "roundTripFrom": round_trip.get("lowPrice"),
            "monthlyPrices": {m["month"]: m["price"] for m in monthly},
            "cheapestMonth": cheapest_month,
            "flightCount": len({f["flightNumber"] for f in flights}),
            **airport_location((r.get("toAirports") or [r.get("toCode")])[0], (r.get("fromAirports") or [r.get("fromCode")])[0]),
            "priceObservedAt": (r.get("crawledAt") or "")[:10] or None,
            "url": r.get("url"),
            "descriptionSource": "derived: dữ liệu chuyến bay trip.com",
            "descriptionLang": "vi",
            "fieldSources": {"unitPrice": "trip.com"},
        },
        unitPrice=price,
        currency="VND",
        available=bool(prices),
        availableFrom=dates[0] if dates else None,
        availableTo=dates[-1] if dates else None,
        imageUrl=None,
        sourceRef=route_ref,
    )
    by_number: dict[str, list[dict]] = defaultdict(list)
    for f in flights:
        by_number[f["flightNumber"]].append(f)
    ranked = sorted(by_number.items(), key=lambda kv: min((x.get("price") or 10**12) for x in kv[1]))
    out = [route]
    for number, legs in ranked[:flights_per_route]:
        cheapest = min(legs, key=lambda x: x.get("price") or 10**12)
        leg_dates = sorted((x.get("departureTime") or "")[:10] for x in legs if x.get("departureTime"))
        dep, arr = _hhmm(cheapest.get("departureTime")), _hhmm(cheapest.get("arrivalTime"))
        desc = (
            f"Chuyến bay {'thẳng ' if cheapest.get('nonstop') else ''}{cheapest.get('airline')} {number} từ "
            f"{cheapest.get('fromAirport') or from_city} ({cheapest.get('from')}) đến {cheapest.get('toAirport') or to_city} "
            f"({cheapest.get('to')}), cất cánh {dep}, hạ cánh {arr}, thời gian bay {_fmt_duration(cheapest.get('durationMinutes'))}."
        )
        if cheapest.get("price"):
            desc += f" Giá một chiều từ {_fmt_vnd(cheapest['price'])} (ngày {leg_dates[0] if leg_dates else '?'})."
        out.append(
            make_product(
                meta={"src": "trip_flight", "plan": r.get("plan") or {}, "fromDestination": normalise_destination(from_city)},
                name=f"{cheapest.get('airline')} {number}: {from_city} - {to_city} ({dep})",
                taxonomy="flight",
                destination=destination,
                description=desc,
                attributes={
                    "level": "flight",
                    "parentProductId": route["productId"],
                    "flightNumber": number,
                    "airline": cheapest.get("airline"),
                    "airlineCode": cheapest.get("airlineCode"),
                    "originCity": from_city,
                    "destinationCity": to_city,
                    "originDestination": normalise_destination(from_city),
                    "originAirport": cheapest.get("from"),
                    "destinationAirport": cheapest.get("to"),
                    "departureTimeLocal": dep,
                    "arrivalTimeLocal": arr,
                    "durationMinutes": cheapest.get("durationMinutes"),
                    "nonstop": cheapest.get("nonstop"),
                    **airport_location(cheapest.get("to"), cheapest.get("from")),
                    "datesSeen": leg_dates[:14],
                    "priceObservedAt": (r.get("crawledAt") or "")[:10] or None,
                    "url": r.get("url"),
                    "descriptionSource": "derived: dữ liệu chuyến bay trip.com",
                    "descriptionLang": "vi",
                    "fieldSources": {"unitPrice": "trip.com"},
                },
                unitPrice=cheapest.get("price"),
                currency="VND",
                available=cheapest.get("price") is not None,
                availableFrom=leg_dates[0] if leg_dates else None,
                availableTo=leg_dates[-1] if leg_dates else None,
                imageUrl=None,
                sourceRef=f"trip:flight:{cheapest.get('from')}-{cheapest.get('to')}:{number}",
            )
        )
    return out


# ---------------------------------------------------------------------- gộp khách sạn


def cluster_hotels(props: list[dict], threshold: float) -> tuple[list[list[dict]], list[tuple]]:
    """Ghép khách sạn giữa Vinpearl / booking / agoda. Mỗi cụm có tối đa 1 bản của mỗi nguồn.
    Ghép khi (luôn cùng điểm đến): cách nhau ≤ 300 m và tên giống ≥ 75; ≤ 1 km và tên giống ≥ threshold;
    ≤ 5 km và tên gần như trùng (≥ 97, toạ độ các nguồn có thể lệch vài km); thiếu toạ độ (hoặc toạ độ nghi sai, xem
    flag_suspect_hotel_coords) và tên giống ≥ threshold + 4."""
    keys = {p["productId"]: name_keys(p["name"], p["attributes"].get("nameEn")) for p in props}
    by_dest: dict[str | None, list[dict]] = defaultdict(list)
    for p in props:
        by_dest[p["destination"]].append(p)
    pairs = []
    for dest, group in by_dest.items():
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                if a["_meta"]["src"] == b["_meta"]["src"]:
                    continue
                score = name_score(keys[a["productId"]], keys[b["productId"]])
                if score < 75:
                    continue
                dist = haversine_m(a["attributes"], b["attributes"]) if _coords_trusted(a) and _coords_trusted(b) else None
                ok = (
                    dist is not None
                    and ((dist <= 300 and score >= 75) or (dist <= 1000 and score >= threshold) or (dist <= 5000 and score >= 97))
                ) or (dist is None and score >= threshold + 4)
                if ok:
                    pairs.append((score, -(dist or 0), a, b, dist))
    pairs.sort(key=lambda x: (x[0], x[1]), reverse=True)
    cluster_of = {p["productId"]: [p] for p in props}
    report = []
    for score, _, a, b, dist in pairs:
        ca, cb = cluster_of[a["productId"]], cluster_of[b["productId"]]
        if ca is cb:
            continue
        if {m["_meta"]["src"] for m in ca} & {m["_meta"]["src"] for m in cb}:
            continue
        ca.extend(cb)
        for m in cb:
            cluster_of[m["productId"]] = ca
        report.append((score, dist, a, b))
    clusters, seen = [], set()
    for p in props:
        c = cluster_of[p["productId"]]
        if id(c) not in seen:
            seen.add(id(c))
            clusters.append(sorted(c, key=lambda m: SOURCE_ORDER[m["_meta"]["src"]]))
    return clusters, report


def merge_hotel_cluster(members: list[dict], rooms_of: dict[str, list[dict]], rooms_per_hotel: int) -> tuple[dict, list[dict]]:
    primary = members[0]
    by = {m["_meta"]["src"]: m for m in members}
    vp, bk, ag = by.get("vinpearl"), by.get("booking"), by.get("agoda")
    out = copy.deepcopy(primary)
    a = out["attributes"]
    fs = a.setdefault("fieldSources", {})
    others = members[1:]

    if not vp and bk and ag and a.get("descriptionLang") != "vi" and ag["attributes"].get("descriptionLang") == "vi":
        out["description"] = ag["description"]
        a["descriptionLang"] = "vi"
        fs["description"] = "agoda.com"

    ota = {}
    if bk and bk.get("unitPrice"):
        ota["booking.com"] = bk
    if ag and ag.get("unitPrice"):
        ota["agoda.com"] = ag
    if ota:
        chosen_name, chosen = next(iter(ota.items()))
        if vp and vp.get("unitPrice"):
            a["vinpearlPrice"] = vp["unitPrice"]
        out["unitPrice"] = chosen["unitPrice"]
        out["available"] = True
        fs["unitPrice"] = fs["available"] = chosen_name
        a["priceDate"] = chosen["attributes"].get("priceDate")
        a["priceNights"] = chosen["attributes"].get("priceNights")
        a["otaPrices"] = {k: v["unitPrice"] for k, v in ota.items()}

    coord_src = primary if _coords_trusted(primary) else next((m for m in others if _coords_trusted(m)), None)
    coord_src = coord_src or next((m for m in members if m["attributes"].get("latitude") is not None), None)
    for field in LOCATION_FIELDS:
        a.pop(field, None)
    if coord_src is not None:
        ca = coord_src["attributes"]
        a["latitude"], a["longitude"] = ca["latitude"], ca["longitude"]
        a["locationSource"] = ca.get("locationSource") or _src_label(coord_src)
        a["locationPrecision"] = "exact"
        if coord_src is not primary:
            fs["latitude"] = fs["longitude"] = a["locationSource"]
        if coord_src["_meta"].get("coordSuspect"):
            a["locationWarning"] = coord_src["_meta"]["coordSuspect"]
        elif primary["_meta"].get("coordSuspect"):
            a["locationNote"] = f"toạ độ {_src_label(primary)} nghi sai ({primary['_meta']['coordSuspect']}) nên dùng {a['locationSource']}"

    for field in ("starRating", "starRatingType", "address", "province", "city", "propertyType"):
        if a.get(field) is None:
            donor = next((m for m in others if m["attributes"].get(field) is not None), None)
            if donor:
                a[field] = donor["attributes"][field]
                fs[field] = _src_label(donor)
    for m, prefix in ((bk, "booking"), (ag, "agoda")):
        if m and m is not primary and m["attributes"].get("reviewScore") is not None:
            a[f"{prefix}ReviewScore"] = m["attributes"]["reviewScore"]
            a[f"{prefix}ReviewCount"] = m["attributes"].get("reviewCount")
    a["amenities"] = uniq(sum((m["attributes"].get("amenities") or [] for m in members), []))[:80] or None
    for flag in ("oceanView", "familyFriendly"):
        if any(m["attributes"].get(flag) for m in members):
            a[flag] = True
    if not a.get("images"):
        donor = next((m for m in others if m["attributes"].get("images")), None)
        if donor:
            a["images"] = donor["attributes"]["images"]
            out["imageUrl"] = out["imageUrl"] or donor["imageUrl"]
    if others:
        a["sameAs"] = [m["sourceRef"] for m in others]
    if bk and bk is not primary:
        a["bookingComUrl"] = bk["attributes"].get("url")
    if ag and ag is not primary:
        a["agodaUrl"] = ag["attributes"].get("url")
    out["attributes"] = _compact(a)

    # hạng phòng
    if vp:
        rooms = [copy.deepcopy(x) for x in rooms_of.get(vp["productId"], [])]
        if bk:
            _price_rooms_from_ota(rooms, rooms_of.get(bk["productId"], []))
    elif bk:
        rooms = select_rooms(rooms_of.get(bk["productId"], []), rooms_per_hotel)
    else:
        rooms = []
    for room in rooms:
        ra = room["attributes"]
        ra["parentProductId"] = out["productId"]
        for field in LOCATION_FIELDS:  # hạng phòng luôn theo toạ độ khách sạn đã chọn
            if out["attributes"].get(field) is None:
                ra.pop(field, None)
            else:
                ra[field] = out["attributes"][field]
    return out, rooms


def _src_label(p: dict) -> str:
    return {"vinpearl": "vinpearl", "booking": "booking.com", "agoda": "agoda.com"}.get(p["_meta"]["src"], p["_meta"]["src"])


def _room_key(name: str) -> str:
    return re.sub(r"\b(phong|room|co|voi|giuong|bed|size|loai)\b", " ", fold(name)).strip()


def _price_rooms_from_ota(vp_rooms: list[dict], ota_rooms: list[dict]) -> None:
    """OTA thắng về giá: hạng phòng Vinpearl khớp tên với hạng phòng booking.com thì lấy giá booking.com."""
    from rapidfuzz import fuzz

    pairs = []
    for v in vp_rooms:
        for o in ota_rooms:
            if not o.get("unitPrice"):
                continue
            a, b = _room_key(v["_meta"]["roomName"]), _room_key(o["_meta"]["roomName"])
            if _digits(a) != _digits(b):
                continue
            score = fuzz.token_set_ratio(a, b)
            if score >= 85:
                pairs.append((score, v, o))
    pairs.sort(key=lambda x: x[0], reverse=True)
    used_v, used_o = set(), set()
    for score, v, o in pairs:
        if v["productId"] in used_v or o["productId"] in used_o:
            continue
        used_v.add(v["productId"])
        used_o.add(o["productId"])
        va = v["attributes"]
        if v.get("unitPrice"):
            va["vinpearlPrice"] = v["unitPrice"]
        v["unitPrice"] = o["unitPrice"]
        v["available"] = True
        va.setdefault("fieldSources", {})["unitPrice"] = "booking.com"
        va["otaRoomName"] = o["_meta"]["roomName"]
        va["priceDate"] = o["attributes"].get("priceDate")


def select_rooms(rooms: list[dict], n: int) -> list[dict]:
    chosen, seen = [], set()
    for room in sorted(rooms, key=lambda x: (x.get("unitPrice") is None, x.get("unitPrice") or 0)):
        key = _room_key(room["_meta"]["roomName"])
        if key in seen:
            continue
        seen.add(key)
        chosen.append(copy.deepcopy(room))
        if len(chosen) >= n:
            break
    return chosen


# ---------------------------------------------------------------------- vé Vinpearl ↔ điểm tham quan trip.com


POI_FIELDS = ("openingHours", "openingHoursDetail", "suggestedDuration", "durationMinutes", "latitude", "longitude", "address", "tags")


def merge_pois(tickets: list[dict], pois: list[dict]) -> tuple[list[dict], list[tuple]]:
    """Điểm tham quan trip.com trùng tên với vé Vinpearl → gộp vào vé (Vinpearl giữ tên/mô tả, giá theo trip.com);
    các vé Vinpearl khác có chứa tên điểm đó → bổ sung giờ mở cửa, thời lượng, toạ độ."""
    from rapidfuzz import fuzz

    kept, report = [], []
    by_dest: dict[str | None, list[dict]] = defaultdict(list)
    for t in tickets:
        by_dest[t["destination"]].append(t)
    for poi in pois:
        pkeys = name_keys(poi["name"], poi["attributes"].get("nameEn"))
        exact, related = None, []
        for t in by_dest.get(poi["destination"], []):
            tkey = name_keys(re.sub(r"^\[[^\]]*\]\s*-?\s*", "", t["name"]))
            score = name_score(pkeys, tkey)
            if score >= 92 and (exact is None or score > exact[0]):
                exact = (score, t)
            elif any(fuzz.token_set_ratio(pk, tk) == 100 and len(pk.split()) >= 2 for pk in pkeys for tk in tkey):
                related.append(t)
        for t in related + ([exact[1]] if exact else []):
            ta = t["attributes"]
            for f in POI_FIELDS:
                if ta.get(f) in (None, [], "") and poi["attributes"].get(f) not in (None, [], ""):
                    ta[f] = poi["attributes"][f]
            ta["poiRef"] = poi["sourceRef"]
            ta["poiName"] = poi["name"]
            ta["tripRating"] = poi["attributes"].get("rating")
            ta["tripReviewCount"] = poi["attributes"].get("reviewCount")
        if exact:
            t = exact[1]
            ta = t["attributes"]
            if poi.get("unitPrice"):
                if t.get("unitPrice"):
                    ta["vinpearlPrice"] = t["unitPrice"]
                t["unitPrice"] = poi["unitPrice"]
                t["available"] = True
                ta.setdefault("fieldSources", {})["unitPrice"] = "trip.com"
                ta["otaPrices"] = {"trip.com": poi["unitPrice"]}
            ta["sameAs"] = uniq((ta.get("sameAs") or []) + [poi["sourceRef"]])
            ta["tripUrl"] = poi["attributes"].get("url")
            report.append((exact[0], None, t, poi))
        else:
            kept.append(poi)
    return kept, report


# ---------------------------------------------------------------------- vị trí


LOCATION_OVERRIDES_CSV = Path(__file__).resolve().parent / "collectors" / "location_overrides.csv"
LOCATION_SOURCE = {"vinpearl": "vinpearl", "booking": "booking.com", "agoda": "agoda.com", "trip_attraction": "trip.com",
                   "booking_attraction": "booking.com"}
LOCATION_FIELDS = ("latitude", "longitude", "locationSource", "locationPrecision", "locationWarning")


def load_location_overrides(path: Path | None = None) -> dict[str, tuple[float, float]]:
    """collectors/location_overrides.csv: sourceRef,latitude,longitude,note – toạ độ sửa tay, thắng mọi nguồn."""
    out: dict[str, tuple[float, float]] = {}
    path = path or LOCATION_OVERRIDES_CSV
    if not path.exists():
        return out
    with open(path, encoding="utf-8-sig", newline="") as f:
        for n, row in enumerate(csv.DictReader(f), 2):
            ref = (row.get("sourceRef") or "").strip()
            if not ref:
                continue
            lat, lng = clean_coords(row.get("latitude"), row.get("longitude"))
            if lat is None:
                log.warning("%s dòng %d: toạ độ không hợp lệ (%s, %s) – bỏ qua", path.name, n, row.get("latitude"), row.get("longitude"))
                continue
            out[ref] = (lat, lng)
    return out


def apply_location_overrides(products: list[dict], overrides: dict[str, tuple[float, float]]) -> int:
    n = 0
    for p in products:
        if p["sourceRef"] in overrides:
            a = p["attributes"]
            a["latitude"], a["longitude"] = overrides[p["sourceRef"]]
            a["locationSource"], a["locationPrecision"] = "manual", "exact"
            p["_meta"]["locationOverride"] = True
            p["_meta"].pop("coordSuspect", None)
            n += 1
    return n


def _same_address(x: str | None, y: str | None) -> bool:
    tx, ty = set(fold(x).split()), set(fold(y).split())
    if not tx or not ty:
        return True  # thiếu địa chỉ thì không đủ căn cứ để nghi
    return len(tx & ty) / len(tx | ty) >= 0.8


def flag_suspect_hotel_coords(props: list[dict]) -> Counter:
    """Đánh dấu toạ độ khách sạn nghi sai: không dùng để ghép trùng, khi gộp thì ưu tiên toạ độ nguồn khác.
    - cách tâm điểm đến xa hơn bán kính trong geo.py (vd. API ghi Vinpearl Hà Tĩnh cách thành phố 34 km);
    - API Vinpearl ghi trùng toạ độ (≤ 30 m) cho hai khách sạn khác địa chỉ (vd. Vinpearl Empire Nha Trang ở
      Lê Thánh Tôn trùng Vinpearl Luxury Nha Trang trên đảo Hòn Tre). Chỉ xét Vinpearl: căn hộ trên OTA ở chung
      một toà nhà vốn trùng toạ độ."""
    stats: Counter = Counter()
    vinpearl = []
    for p in props:
        a = p["attributes"]
        if a.get("latitude") is None:
            continue
        km = km_from_destination(p["destination"], a["latitude"], a["longitude"])
        if km is not None and km > destination_radius_km(p["destination"]):
            p["_meta"]["coordSuspect"] = f"cách tâm {p['destination']} {km:.0f} km"
            stats["khách sạn: toạ độ xa tâm điểm đến"] += 1
        if p["_meta"]["src"] == "vinpearl":
            vinpearl.append(p)
    for i, x in enumerate(vinpearl):
        for y in vinpearl[i + 1:]:
            d = haversine_m(x["attributes"], y["attributes"])
            if d is not None and d <= 30 and not _same_address(x["attributes"].get("address"), y["attributes"].get("address")):
                for p, other in ((x, y), (y, x)):
                    if "coordSuspect" not in p["_meta"]:
                        p["_meta"]["coordSuspect"] = f"trùng toạ độ với {other['name']} (khác địa chỉ)"
                        stats["khách sạn: trùng toạ độ khách sạn khác"] += 1
    return stats


def _coords_trusted(p: dict) -> bool:
    return p["attributes"].get("latitude") is not None and not p["_meta"].get("coordSuspect")


def assign_venue_locations(tickets: list[dict], venues: list[Venue]) -> Counter:
    """Vé/combo/golf Vinpearl → địa điểm dùng vé (collectors/venues.csv): toạ độ nếu địa điểm đã có toạ độ dùng được
    (status ok/auto). Điểm đến theo địa điểm khi khớp qua nhà cung cấp, hoặc tên vé không nêu điểm đến (tỉnh trong API
    hay sai: Vinpearl Golf Léman ở TP.HCM bị ghi Hải Phòng, vé Grand World Hà Nội bị tính là Phú Quốc)."""
    stats: Counter = Counter()
    matcher = VenueMatcher(venues)
    for v in venues:
        v.tickets = 0  # đếm lại theo dữ liệu hiện tại (cột tickets trong CSV là của lần chạy crawl.py venues gần nhất)
    for t in tickets:
        m, a = t["_meta"], t["attributes"]
        venue, how = matcher.match(supplier_code=m.get("supplierCode"), supplier_name=m.get("supplierName"),
                                   name=t["name"], slug=m.get("imageUrlSlug"), destination_hint=t["destination"])
        if venue is None:
            stats["vé không khớp địa điểm nào"] += 1
            continue
        a["venue"] = venue.name
        venue.tickets += 1
        if venue.destination and venue.destination != t["destination"] and (how == "supplier" or not destination_in_text(t["name"])):
            a["originalDestination"] = t["destination"]
            t["destination"] = venue.destination
            stats["vé đổi điểm đến theo địa điểm"] += 1
        if m.get("locationOverride"):
            continue
        if venue.usable:
            a["latitude"], a["longitude"] = venue.latitude, venue.longitude
            a["locationSource"], a["locationPrecision"] = venue.source_family, "venue"
            stats["vé có toạ độ địa điểm"] += 1
        else:
            stats["vé thuộc địa điểm chưa có toạ độ dùng được"] += 1
    return stats


def link_pois_to_venues(pois: list[dict], venues: list[Venue]) -> None:
    """Điểm tham quan trip.com đang là nguồn toạ độ của một địa điểm (source trip.com:<id>) → chung ghim với vé ở đó."""
    by_ref = {f"trip:attraction:{v.source.split(':', 1)[1]}": v for v in venues if v.usable and v.source.startswith("trip.com:")}
    for p in pois:
        venue = by_ref.get(p["sourceRef"])
        if venue:
            p["attributes"]["venue"] = venue.name


def finalize_locations(products: list[dict]) -> None:
    """Toạ độ luôn đủ cặp; ghi nguồn/độ chính xác còn thiếu; cảnh báo toạ độ xa tâm điểm đến (trừ sân bay)."""
    for p in products:
        a = p["attributes"]
        if a.get("latitude") is None or a.get("longitude") is None:
            for f in LOCATION_FIELDS:
                a.pop(f, None)
            continue
        src = p["_meta"].get("src")
        if "locationSource" not in a:
            a["locationSource"] = "trip.com" if a.get("poiRef") else LOCATION_SOURCE.get(src, src)
        if "locationPrecision" not in a:
            a["locationPrecision"] = "poi" if a.get("poiRef") else "exact"
        if a["locationPrecision"] != "airport" and "locationWarning" not in a:
            km = km_from_destination(p["destination"], a["latitude"], a["longitude"])
            if km is not None and km > destination_radius_km(p["destination"]):
                a["locationWarning"] = f"cách tâm {p['destination']} {km:.0f} km"


# ---------------------------------------------------------------------- kế hoạch


def apply_plan(products: list[dict], plan_names: set[str], budget: Budget, dropped: Counter) -> list[dict]:
    caps = {"booking": budget.booking_hotels, "agoda": budget.agoda_hotels, "trip_attraction": budget.trip_attractions,
            "booking_attraction": 10}
    groups: dict[tuple, list[dict]] = defaultdict(list)
    keep: list[dict] = []
    kept_ids: set[str] = set()
    for p in products:
        src = p["_meta"].get("src")
        level = p["attributes"].get("level")
        if level in ("room", "flight"):
            continue  # đi theo sản phẩm cha
        if src == "vinpearl" or p["attributes"].get("brand") == "Vinpearl":
            keep.append(p)
            kept_ids.add(p["productId"])
            continue
        if src == "trip_flight":
            if p["destination"] in plan_names and p["_meta"].get("fromDestination") in plan_names:
                keep.append(p)
                kept_ids.add(p["productId"])
            else:
                dropped["tuyến bay ngoài kế hoạch"] += 1
            continue
        if p["destination"] not in plan_names:
            dropped[f"{src}: ngoài {len(plan_names)} điểm đến kế hoạch"] += 1
            continue
        groups[(src, p["destination"])].append(p)
    for (src, dest), items in groups.items():
        items.sort(key=lambda p: ((p["_meta"].get("plan") or {}).get("rank") or 10**6, -(p["attributes"].get("reviewCount") or 0)))
        cap = caps.get(src, 10**6)
        for p in items[:cap]:
            keep.append(p)
            kept_ids.add(p["productId"])
        if len(items) > cap:
            dropped[f"{src}: vượt {cap}/điểm đến"] += len(items) - cap
    for p in products:
        if p["attributes"].get("level") in ("room", "flight"):
            if p["attributes"].get("parentProductId") in kept_ids:
                keep.append(p)
            else:
                dropped[f"{p['attributes']['level']} của sản phẩm bị loại"] += 1
    return keep


# ---------------------------------------------------------------------- đầu ra


def write_outputs(products: list[dict], data: Path, report_rows: list[list], dropped: Counter, plan_names: set[str],
                  location_stats: Counter | None = None, venues: list[Venue] | None = None) -> None:
    clean = [{k: p[k] for k in PRODUCT_FIELDS} for p in products]
    jl = data / "products.jsonl"
    with open(jl, "w", encoding="utf-8") as f:
        for p in clean:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    with open(data / "products.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(PRODUCT_FIELDS)
        for p in clean:
            w.writerow([json.dumps(p[k], ensure_ascii=False) if k == "attributes" else ("" if p[k] is None else p[k]) for k in PRODUCT_FIELDS])
    with open(data / "dedup_report.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["kind", "score", "distance_m", "destination", "kept_name", "kept_sourceRef", "merged_name", "merged_sourceRef"])
        w.writerows(report_rows)
    map_info = mapexport.write_map(clean, data / "map", venues or [])
    write_stats(clean, data / "stats.md", len(report_rows), dropped, plan_names, location_stats or Counter(), map_info)
    log.info("Đã ghi %d sản phẩm → %s (+ products.csv, dedup_report.csv, stats.md, map/)", len(clean), jl)


def write_stats(products: list[dict], path: Path, merged: int, dropped: Counter, plan_names: set[str],
                location_stats: Counter | None = None, map_info: dict | None = None) -> None:
    n = len(products)
    by_src = Counter(p["sourceRef"].split(":")[0] for p in products)
    by_tax = Counter(p["taxonomy"] for p in products)
    by_level = Counter(f"{p['taxonomy']}/{p['attributes'].get('level', '-')}" for p in products)
    by_dest = Counter(p["destination"] or "(không rõ)" for p in products)
    with_desc = [p for p in products if p.get("description")]
    vi_desc = [p for p in with_desc if p["attributes"].get("descriptionLang") == "vi"]
    priced = [p for p in products if p.get("unitPrice")]
    available = [p for p in products if p.get("available")]
    coords = [p for p in products if p["attributes"].get("latitude") is not None]
    dest_ok = [d for d, c in by_dest.items() if d in plan_names and c >= 20]
    tax_needed = {"hotel", "flight", "attraction", "combo"}

    def ok(flag: bool) -> str:
        return "✅" if flag else "⚠️"

    lines = [
        "# Thống kê catalog",
        "",
        f"Tạo lúc {date.today().isoformat()} · **{n} sản phẩm**",
        "",
        "## Đối chiếu handbook §3",
        "",
        "| Mục tiêu | Thực tế | |",
        "|---|---|---|",
        f"| 2.000–5.000 sản phẩm | {n} | {ok(TARGET_MIN <= n <= TARGET_MAX)} |",
        f"| 10–15 điểm đến (≥ 20 sản phẩm mỗi nơi) | {len(dest_ok)} | {ok(10 <= len(dest_ok) <= 15)} |",
        f"| Đủ hotel, flight, attraction, combo | {', '.join(sorted(by_tax))} | {ok(tax_needed <= set(by_tax))} |",
        f"| Mô tả được nhận diện là tiếng Việt | {len(vi_desc)} ({_pct(len(vi_desc), n)}) | {ok(len(vi_desc) >= 0.7 * n)} |",
        f"| Có giá | {len(priced)} ({_pct(len(priced), n)}) | {ok(len(priced) >= 0.8 * n)} |",
        f"| Còn bán / đặt được (§12 availability ≥ 95% trong gợi ý) | {len(available)} ({_pct(len(available), n)}) | |",
        f"| Có toạ độ | {len(coords)} ({_pct(len(coords), n)}) | |",
        f"| Sản phẩm trùng giữa các nguồn đã gộp | {merged} | |",
        "",
        "Nhãn ngôn ngữ được ước lượng từ tỷ lệ ký tự có dấu trong mô tả; không xác nhận tên hoặc toàn bộ nội dung đã là tiếng Việt. Cần đọc tay các mẫu bên dưới.",
        "",
        "## Điểm đến × loại sản phẩm",
        "",
        "| Điểm đến | hotel | flight | attraction | combo | golf | tổng |",
        "|---|---|---|---|---|---|---|",
    ]
    matrix: dict[str, Counter] = defaultdict(Counter)
    for p in products:
        matrix[p["destination"] or "(không rõ)"][p["taxonomy"]] += 1
    for dest, _ in by_dest.most_common():
        c = matrix[dest]
        mark = "" if dest in plan_names else " *(ngoài kế hoạch)*"
        lines.append(f"| {dest}{mark} | {c['hotel']} | {c['flight']} | {c['attraction']} | {c['combo']} | {c['golf']} | {sum(c.values())} |")
    lines += [
        "",
        "## Theo nguồn", "", *[f"- {k}: {v}" for k, v in by_src.most_common()],
        "", "## Theo loại / cấp", "", *[f"- {k}: {v}" for k, v in sorted(by_level.items())],
        "", f"Độ dài mô tả trung vị: {_median([len(p['description']) for p in with_desc])} ký tự",
    ]
    if dropped:
        lines += ["", "## Bị loại", "", *[f"- {k}: {v}" for k, v in dropped.most_common()]]
    lines += location_section(products, location_stats or Counter(), map_info or {})
    lines += ["", "## Mẫu để đọc tay (kiểm tra chất lượng tên + mô tả)", ""]
    pool = [p for p in products if p["attributes"].get("level") not in ("room", "flight")]
    step = max(1, len(pool) // 15)
    for p in pool[::step][:15]:
        desc = (p.get("description") or "").replace("\n", " ")[:280]
        lines.append(f"- **{p['name']}** · {p['taxonomy']} · {p['destination']} · {p.get('unitPrice')} VND  \n  {desc}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def location_section(products: list[dict], location_stats: Counter, map_info: dict) -> list[str]:
    by_kind: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    sources: Counter = Counter()
    precision: Counter = Counter()
    for p in products:
        a = p["attributes"]
        row = by_kind[f"{p['taxonomy']}/{a.get('level', '-')}"]
        row[0] += 1
        if a.get("latitude") is not None:
            row[1] += 1
            sources[a.get("locationSource")] += 1
            precision[a.get("locationPrecision")] += 1
    warnings = [p for p in products if p["attributes"].get("locationWarning") and p["attributes"].get("level") != "room"]
    lines = ["", "## Vị trí (toạ độ)", "", "| Loại / cấp | Sản phẩm | Có toạ độ | |", "|---|---|---|---|"]
    for kind, (total, with_coords) in sorted(by_kind.items()):
        lines.append(f"| {kind} | {total} | {with_coords} | {_pct(with_coords, total)} |")
    lines += [
        "",
        "Nguồn toạ độ: " + ", ".join(f"{k} {v}" for k, v in sources.most_common()),
        "",
        "Độ chính xác: " + ", ".join(f"{k} {v}" for k, v in precision.most_common())
        + " (exact = vị trí riêng của sản phẩm; venue = khu vui chơi/sân golf dùng vé; poi = điểm tham quan trip.com; airport = sân bay đến)",
    ]
    if location_stats:
        lines += ["", *[f"- {k}: {v}" for k, v in location_stats.most_common()]]
    if warnings:
        lines += ["", f"Cảnh báo toạ độ ({len(warnings)} sản phẩm, không tính hạng phòng):", ""]
        lines += [f"- {p['name']} · {p['destination']} · {p['attributes']['locationWarning']}" for p in warnings[:20]]
    if map_info:
        lines += ["", f"Bản đồ: {map_info.get('places', 0)} ghim trong `map/` ({', '.join(map_info.get('files', []))}). "
                      f"Cần kiểm tra tay: {map_info.get('review', 0)} dòng trong `map/can-kiem-tra.csv`."]
    return lines


def _pct(a: int, b: int) -> str:
    return f"{100 * a / b:.1f}%" if b else "0%"


def _median(xs: list[int]) -> int:
    return sorted(xs)[len(xs) // 2] if xs else 0


# ---------------------------------------------------------------------- main


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", type=Path, default=default_data_dir())
    ap.add_argument("--destinations", default=None, help="điểm đến kế hoạch (mặc định cả 15 trong collectors/plan.py)")
    ap.add_argument("--per-destination", type=int, default=None, help="số khách sạn/điểm tham quan tối đa mỗi điểm đến")
    ap.add_argument("--no-plan", action="store_true", help="giữ mọi sản phẩm đã crawl, không lọc theo kế hoạch")
    ap.add_argument("--rooms-per-hotel", type=int, default=None, help="số hạng phòng OTA giữ lại mỗi khách sạn (mặc định 3)")
    ap.add_argument("--flights-per-route", type=int, default=None, help="số chuyến bay cụ thể mỗi tuyến (mặc định 5)")
    ap.add_argument("--match-threshold", type=float, default=88.0, help="điểm giống tên tối thiểu để ghép khách sạn giữa các nguồn")
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
    destinations = select_destinations(a.destinations)
    plan_names = {d.name for d in destinations}
    budget = budget_with(a.per_destination, ota_rooms_per_hotel=a.rooms_per_hotel, flights_per_route=a.flights_per_route)

    raw: dict[str, list[dict]] = defaultdict(list)
    for f in sorted(paths.interim.glob("*.jsonl")):
        recs = latest_by_key(list(read_jsonl(f)))
        raw[f.stem].extend(recs)
        log.info("Đọc %s: %d bản ghi", f.name, len(recs))
    if not raw:
        log.error("Không có dữ liệu trong %s. Chạy crawl.py trước.", paths.interim)
        return 1

    dropped: Counter = Counter()
    report_rows: list[list] = []

    # khách sạn: 3 nguồn → cụm → 1 sản phẩm + hạng phòng
    props: list[dict] = []
    rooms_of: dict[str, list[dict]] = {}
    tickets: list[dict] = []
    for r in raw.get("vinpearl", []):
        if r.get("recordType") == "vinpearl_hotel":
            prop, rooms = vinpearl_hotel(r)
            if prop:
                props.append(prop)
                rooms_of[prop["productId"]] = rooms
        elif r.get("recordType") == "vinpearl_tour":
            t = vinpearl_tour_product(r, today)
            if t:
                tickets.append(t)
    for r in raw.get("booking_hotels", []):
        prop, rooms = booking_hotel(r, rates)
        if prop:
            props.append(prop)
            rooms_of[prop["productId"]] = rooms
    for r in raw.get("agoda_hotels", []):
        prop = agoda_hotel(r, rates)
        if prop:
            props.append(prop)

    pois = [p for p in (trip_attraction_product(r) for r in raw.get("trip_attractions", [])) if p]
    location_stats = flag_suspect_hotel_coords(props)  # trước khi sửa tay: toạ độ gốc vẫn là bằng chứng cho khách sạn kia
    n_override = apply_location_overrides(props + tickets + pois, load_location_overrides())
    if n_override:
        location_stats["toạ độ sửa tay (location_overrides.csv)"] = n_override

    clusters, pairs = cluster_hotels(props, a.match_threshold)
    products: list[dict] = []
    for members in clusters:
        merged, rooms = merge_hotel_cluster(members, rooms_of, budget.ota_rooms_per_hotel)
        products.append(merged)
        products.extend(rooms)
        dropped["khách sạn trùng giữa các nguồn (đã gộp)"] += len(members) - 1
    for score, dist, x, y in pairs:
        report_rows.append(["hotel", f"{score:.1f}", "" if dist is None else f"{dist:.0f}", x["destination"], x["name"], x["sourceRef"], y["name"], y["sourceRef"]])
    log.info("Khách sạn: %d bản ghi → %d sau khi gộp", len(props), len(clusters))

    # vé / điểm tham quan
    venues = load_venues()
    location_stats.update(assign_venue_locations(tickets, venues))
    pois, poi_pairs = merge_pois(tickets, pois)
    link_pois_to_venues(pois, venues)
    dropped["điểm tham quan trip.com trùng vé Vinpearl (đã gộp)"] += len(poi_pairs)
    for score, _, t, poi in poi_pairs:
        report_rows.append(["attraction", f"{score:.1f}", "", t["destination"], t["name"], t["sourceRef"], poi["name"], poi["sourceRef"]])
    products.extend(tickets)
    products.extend(pois)
    for r in raw.get("booking_attractions", []):
        p = booking_attraction_product(r, rates)
        if p:
            products.append(p)

    # vé máy bay
    for r in raw.get("trip_flights", []):
        products.extend(trip_route_products(r, budget.flights_per_route))

    if not a.no_plan:
        products = apply_plan(products, plan_names, budget, dropped)

    final: list[dict] = []
    seen: set[str] = set()
    for p in products:
        if p["productId"] in seen:
            dropped["trùng sourceRef"] += 1
            continue
        if not p["name"] or p["taxonomy"] not in TAXONOMIES:
            dropped["thiếu tên / loại lạ"] += 1
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

    finalize_locations(final)
    write_outputs(final, paths.data, report_rows, dropped, plan_names, location_stats, venues)
    n = len(final)
    if not a.no_plan and not TARGET_MIN <= n <= TARGET_MAX:
        log.warning("Catalog có %d sản phẩm – handbook nhắm %d–%d. Xem data/stats.md.", n, TARGET_MIN, TARGET_MAX)
    return 0


if __name__ == "__main__":
    sys.exit(main())
