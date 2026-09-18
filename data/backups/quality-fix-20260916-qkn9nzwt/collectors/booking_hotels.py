"""booking.com – chỗ ở tại Việt Nam, trang tiếng Việt, kèm bảng hạng phòng và giá.

Tìm URL (mặc định, theo handbook): với mỗi điểm đến trong collectors/plan.py, mở trang tìm kiếm
searchresults.vi.html?ss=<điểm đến>&order=popularity và lấy N khách sạn phổ biến nhất; thêm một lượt tìm
"Vinpearl" để không sót khách sạn thương hiệu Vinpearl.
Tìm URL (--all-vietnam): sitemap công khai sitembk-hotel-vi.*.xml.gz → toàn bộ /hotel/vn/ (~34.000).
Mỗi trang khách sạn được mở kèm ngày nhận/trả phòng để có bảng giá theo hạng phòng.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from urllib.parse import urlencode

from bs4 import BeautifulSoup

import logging
from urllib.parse import quote_plus, urlsplit

from .booking_base import DiscoverContext, SitemapSource
from .common import now_iso, slim_html
from .textutil import (
    clean_text,
    first_int,
    fold,
    json_ld_blocks,
    meta_content,
    node_text,
    parse_price,
    uniq,
)

LODGING_TYPES = {
    "hotel", "lodgingbusiness", "resort", "apartment", "hostel", "motel", "bedandbreakfast",
    "campground", "vacationrental", "house", "accommodation", "guesthouse",
}
log = logging.getLogger("crawler.booking")
VINPEARL_RE = re.compile(r"\b(vinpearl|vinholidays)\b")
_COUNTRY_RE = re.compile(r"sitembk-hotel-vi\.(\d+)\.xml\.gz$")
_HOTEL_URL_RE = re.compile(r"^https://www\.booking\.com/hotel/([a-z]{2})/[^/?#]+\.vi\.html$")


class BookingHotels(SitemapSource):
    name = "booking_hotels"
    sitemap_index = "https://www.booking.com/sitembk-hotel-index.xml"
    ready_selector = "#hp_hotel_name, [data-testid='property-description'], h2.pp-header__title, #hprt-table"
    expect_url = re.compile(r"/hotel/vn/")
    people_selectors = (  # handbook: không lưu review / tên người đánh giá
        "[data-testid='FeaturedReviewGalleryDesktop-wrapper']",
        "[data-testid='featuredreview']",
        "[data-testid='featuredreviewcard-text']",
        "[data-testid='featuredreviewcard-avatar']",
        "[data-testid='review-card']",
        "#review_list_page_container",
        ".c-review-block",
    )

    def __init__(self, checkin: date | None = None, nights: int = 1, adults: int = 2, currency: str = "VND",
                 all_vietnam: bool = False):
        self.all_vietnam = all_vietnam
        self.checkin = checkin or (date.today() + timedelta(days=30))
        self.nights = max(1, nights)
        self.adults = adults
        self.currency = currency

    # -- discovery theo kế hoạch
    def uses_sitemap(self, opts) -> bool:
        # luôn quét sitemap (chỉ ~4 file) để lấy mọi khách sạn thương hiệu Vinpearl; --all-vietnam thì lấy hết
        return True

    def search_url(self, query: str, offset: int) -> str:
        checkout = self.checkin + timedelta(days=self.nights)
        params = {
            "ss": query,
            "checkin": self.checkin.isoformat(),
            "checkout": checkout.isoformat(),
            "group_adults": self.adults,
            "group_children": 0,
            "no_rooms": 1,
            "selected_currency": self.currency,
            "order": "popularity",
            "offset": offset,
        }
        return "https://www.booking.com/searchresults.vi.html?" + urlencode(params, quote_via=quote_plus)

    async def discover_plan(self, ctx: DiscoverContext) -> int:
        jobs = [(d.name, d.booking_query, ctx.opts.budget.booking_hotels) for d in ctx.opts.destinations]
        total = 0
        for dest, query, want in jobs:
            key = f"search:{query}:{want}:{self.checkin.isoformat()}"
            if ctx.done(key):
                continue
            found: list[tuple[str, str]] = []
            offset = 0
            for _ in range(8):
                if len(found) >= want:
                    break
                res = await ctx.open(self.search_url(query, offset), "[data-testid='property-card']")
                if res is None:
                    break
                ctx.cache.write(f"search-{fold(query).replace(' ', '-')}-{offset}", "html", slim_html(res.html))
                seen = {u for u, _ in found}
                cards = [c for c in parse_search_cards(res.html) if c[0] not in seen]
                if not cards and offset == 0:
                    # lần đầu qua trang thử thách, booking.com chuyển hướng làm mất tham số → mở lại một lần
                    res = await ctx.open(self.search_url(query, offset), "[data-testid='property-card']")
                    cards = parse_search_cards(res.html) if res else []
                if not cards:
                    break
                found.extend(cards)
                offset += 25
            rows = []
            for rank, (url, name) in enumerate(found[:want], 1):
                is_vinpearl = bool(VINPEARL_RE.search(fold(name)))
                plan = {"destination": dest, "rank": rank, "via": "booking-search", "query": query}
                rows.append((url, 0 if is_vinpearl else rank, plan))
            ctx.state.add_many(self.name, rows)
            if found:  # trang tìm kiếm lỗi thì để lượt sau tìm lại
                ctx.mark_done(key, len(rows))
            total += len(rows)
            log.info("[%s] %s: %d khách sạn", self.name, dest, len(rows))
        return total

    # -- discovery theo sitemap (--all-vietnam)
    def chunk_filter(self, loc: str) -> bool:
        return bool(_COUNTRY_RE.search(loc))

    def chunk_order(self, chunks: list[str]) -> list[str]:
        # File sitemap xếp theo mã quốc gia (a→z); 'vn' nằm gần cuối nên quét từ cuối lên.
        return sorted(chunks, key=lambda c: int(_COUNTRY_RE.search(c).group(1)), reverse=True)

    def product_urls(self, locs: list[str]) -> list[str]:
        urls = [u for u in locs if u.startswith("https://www.booking.com/hotel/vn/") and u.endswith(".vi.html")]
        if self.all_vietnam:
            return urls
        return [u for u in urls if re.search(r"/(vinpearl|vinholidays|melia-vinpearl)[a-z0-9-]*\.vi\.html$", u)]

    def stop_scan(self, locs: list[str], found: int) -> bool:
        if not found or not locs:
            return False
        countries = {m.group(1) for u in (locs[0], locs[len(locs) // 2], locs[-1]) if (m := _HOTEL_URL_RE.match(u))}
        return bool(countries) and max(countries) < "vn"

    def priority(self, url: str) -> int:
        return 0 if re.search(r"/(vinpearl|vinholidays|melia-vinpearl)", url) else 100

    def fetch_url(self, url: str) -> tuple[str, dict]:
        checkout = self.checkin + timedelta(days=self.nights)
        params = {
            "checkin": self.checkin.isoformat(),
            "checkout": checkout.isoformat(),
            "group_adults": self.adults,
            "group_children": 0,
            "no_rooms": 1,
            "selected_currency": self.currency,
            "lang": "vi",
        }
        meta = {"checkin": params["checkin"], "checkout": params["checkout"], "adults": self.adults, "currency": self.currency}
        return f"{url}?{urlencode(params)}", meta

    def ready_selector_missing(self, html: str) -> bool:
        return "property-description" not in html and "hp_hotel_name" not in html

    def needs_refetch(self, html: str, final_url: str) -> bool:
        # Lần đầu qua trang thử thách, booking.com chuyển hướng về URL sạch → mất ngày → không có giá.
        return "checkin=" not in final_url and "rooms_table_nodates" in html

    # -- parsing
    def parse(self, html: str, url: str, meta: dict) -> dict | None:
        return parse_hotel_html(html, url, meta)


def parse_search_cards(html: str) -> list[tuple[str, str]]:
    """Trang kết quả tìm kiếm → [(URL trang khách sạn chuẩn .vi.html, tên)] theo thứ tự hiển thị."""
    soup = BeautifulSoup(html, "lxml")
    out: list[tuple[str, str]] = []
    for card in soup.select("[data-testid='property-card']"):
        link = card.select_one("a[data-testid='title-link']") or card.select_one("a[href*='/hotel/vn/']")
        if link is None or not link.get("href"):
            continue
        path = urlsplit(link["href"]).path
        m = re.match(r"^/hotel/vn/([^/.]+)(?:\.[a-z-]+)?\.html$", path)
        if not m:
            continue
        url = f"https://www.booking.com/hotel/vn/{m.group(1)}.vi.html"
        if url not in (u for u, _ in out):
            out.append((url, node_text(card.select_one("[data-testid='title']")) or m.group(1)))
    return out


def parse_hotel_html(html: str, url: str, meta: dict | None = None) -> dict | None:
    meta = meta or {}
    soup = BeautifulSoup(html, "lxml")
    raw = html

    ld = next(
        (b for b in json_ld_blocks(soup) if _ld_type(b) & LODGING_TYPES or ("address" in b and "name" in b and "aggregateRating" in b)),
        {},
    )
    name = clean_text(ld.get("name")) or node_text(soup.select_one("h2.pp-header__title, #hp_hotel_name, h2.d2fee87262"))
    if not name:
        og = meta_content(soup, "og:title")
        name = re.sub(r",.*$", "", og) if og else ""
    if not name:
        return None

    hotel_id = _search(raw, r"b_hotel_id\W{1,4}(\d+)") or _search(raw, r'"hotel_id"\s*:\s*"?(\d+)')
    if not hotel_id:
        inp = soup.select_one("input[name='hotel_id']")
        hotel_id = inp.get("value") if inp else None

    desc_el = soup.select_one("[data-testid='property-description']") or soup.select_one("#property_description_content")
    description = node_text(desc_el) or clean_text(ld.get("description"))

    lat = lng = None
    latlng = soup.select_one("[data-atlas-latlng]")
    if latlng and "," in latlng.get("data-atlas-latlng", ""):
        a, b = latlng["data-atlas-latlng"].split(",", 1)
        lat, lng = _to_float(a), _to_float(b)
    if lat is None:
        lat = _to_float(_search(raw, r"b_map_center_latitude\W{1,4}(-?\d+\.\d+)"))
        lng = _to_float(_search(raw, r"b_map_center_longitude\W{1,4}(-?\d+\.\d+)"))

    stars = None
    star_type = None
    stars_el = soup.select_one("[data-testid='rating-stars']")
    squares_el = soup.select_one("[data-testid='rating-squares']")
    for el, kind in ((stars_el, "official"), (squares_el, "booking_estimate")):
        if el is None:
            continue
        label = el.get("aria-label") or ""
        n = first_int(label) or len(el.find_all("span", recursive=False)) or None
        if n:
            stars, star_type = n, kind
            break

    agg = ld.get("aggregateRating") if isinstance(ld.get("aggregateRating"), dict) else {}
    address = ld.get("address") if isinstance(ld.get("address"), dict) else {}

    crumbs = [node_text(a) for a in soup.select("[data-testid='breadcrumb-link'], [data-testid='breadcrumb-current']")]
    if not crumbs:
        crumbs = [node_text(a) for a in soup.select("#breadcrumb li, .bui-breadcrumb__item")]
    crumbs = [c for c in crumbs if c]
    property_type = None
    province = city = None
    for c in crumbs:
        m = re.match(r"^Tất cả\s+(.+)$", c, re.I)
        if m:
            property_type = m.group(1).strip().lower()
    folded = [fold(c) for c in crumbs]
    if "viet nam" in folded:
        after = crumbs[folded.index("viet nam") + 1 :]
        if after and re.match(r"^(uu dai|deals)", fold(after[-1])):
            after = after[:-1]
        if after:
            province = after[0]
            city = after[-1] if len(after) > 1 else None

    popular = uniq(node_text(li) for li in soup.select("[data-testid='property-most-popular-facilities-wrapper'] li"))
    all_facilities = _facility_items(soup)
    highlights = uniq(
        node_text(li)
        for li in soup.select("[data-testid='property-highlights'] li, .property-highlights li")
    )

    images = []
    for img in soup.select("img[src*='/xdata/images/hotel/'], img[data-src*='/xdata/images/hotel/']"):
        src = img.get("src") or img.get("data-src") or ""
        src = re.sub(r"/max\d+(x\d+)?/|/square\d+/", "/max1024x768/", src.split("&o=")[0])
        images.append(src)
    if isinstance(ld.get("image"), str):
        images.insert(0, re.sub(r"/max\d+(x\d+)?/", "/max1024x768/", ld["image"]))
    images = uniq(images)[:15]

    rooms = parse_room_table(soup, meta.get("currency") or "VND")
    prices = [r["minPrice"] for r in rooms if r.get("minPrice")]

    return {
        "recordType": "booking_hotel",
        "source": "booking_hotels",
        "key": f"hotel:{hotel_id or url}",
        "hotelId": hotel_id,
        "url": url,
        "name": name,
        "propertyType": property_type,
        "description": description,
        "descriptionShort": clean_text(ld.get("description")),
        "address": {
            "street": clean_text(address.get("streetAddress")),
            "locality": clean_text(address.get("addressLocality")),
            "region": clean_text(address.get("addressRegion")),
            "country": clean_text(address.get("addressCountry")),
            "postalCode": clean_text(address.get("postalCode")),
        },
        "breadcrumbs": crumbs,
        "province": province,
        "city": city,
        "latitude": lat,
        "longitude": lng,
        "starRating": stars,
        "starRatingType": star_type,
        "reviewScore": _to_float(agg.get("ratingValue")),
        "reviewScoreScale": _to_float(agg.get("bestRating")) or 10.0,
        "reviewCount": first_int(str(agg.get("reviewCount") or "")),
        "popularFacilities": popular,
        "facilities": all_facilities,
        "highlights": highlights,
        "images": images,
        "rooms": rooms,
        "minPrice": min(prices) if prices else None,
        "priceQuery": {k: meta.get(k) for k in ("checkin", "checkout", "adults", "currency")},
        "crawledAt": meta.get("fetchedAt") or now_iso(),
    }


def parse_room_table(soup: BeautifulSoup, default_currency: str) -> list[dict]:
    rooms: dict[str, dict] = {}
    current: dict | None = None
    rows = soup.select(
        "#hprt-table tbody tr, table.hprt-table tbody tr, tr.js-rt-block-row, "
        "#maxotelRoomArea tbody tr, .roomstable tbody tr"
    )
    seen_rows: set[int] = set()
    for row in rows:
        if id(row) in seen_rows:
            continue
        seen_rows.add(id(row))
        name_el = row.select_one("[data-testid='rt-name-link'], .hprt-roomtype-link, .hprt-roomtype-icon-link")
        block_id = row.get("data-block-id") or ""
        room_id = None
        rid_el = row.select_one("[data-room-id]")
        if rid_el is not None:
            room_id = rid_el.get("data-room-id")
        if not room_id and block_id:
            room_id = block_id.split("_", 1)[0]
        if name_el is not None and not room_id:
            m = re.search(r"(\d{4,})", name_el.get("id") or "") or re.search(r"#RD(\d+)", name_el.get("href") or "")
            room_id = m.group(1) if m else None
        if name_el is not None:
            room_id = room_id or name_el.get("data-room-id") or node_text(name_el)
            current = rooms.setdefault(
                room_id,
                {
                    "roomId": room_id,
                    "name": node_text(name_el),
                    "bed": node_text(row.select_one(".hprt-roomtype-bed, .rt-bed-types")) or _bed_text(row, node_text(name_el)),
                    "facilities": [],
                    "sizeM2": None,
                    "maxOccupancy": None,
                    "prices": [],
                    "conditions": [],
                },
            )
            facilities = uniq(
                node_text(x)
                for x in row.select(".hprt-facilities-facility, .hprt-facilities-block .bui-badge, .hprt-facilities-block li")
            )
            current["facilities"] = uniq(current["facilities"] + facilities)
            for f in facilities:
                if re.search(r"\d+\s*m²", f):
                    current["sizeM2"] = first_int(f)
        elif room_id and room_id in rooms:
            current = rooms[room_id]
        if current is None:
            continue
        occ_text = node_text(
            row.select_one(
                ".hprt-roomtype-occupancy-info, .hprt-occupancy-occupancy-info .bui-u-sr-only, "
                ".hprt-occupancy-occupancy-info, .c-occupancy-icons"
            )
        )
        if not occ_text:
            occ_text = next(
                (e.get("aria-label") for e in row.select("[role='img'][aria-label]") if re.search(r"người|adult|guest", e.get("aria-label", ""), re.I)),
                "",
            )
        occ = _guest_count(occ_text)
        if occ:
            current["maxOccupancy"] = max(current["maxOccupancy"] or 0, occ)
        price_el = row.select_one(
            ".bui-price-display__value, .prco-valign-middle-helper, [data-testid='price-and-discounted-price'], .hprt-price-price"
        )
        if price_el is not None:
            amount, currency = parse_price(node_text(price_el), default_currency)
            if amount:
                current["prices"].append({"amount": amount, "currency": currency or default_currency, "maxOccupancy": occ})
        conds = uniq(re.sub(r"\s*\n\s*", " ", node_text(li)) for li in row.select(".hprt-conditions li, .hprt-conditions-bui li"))
        if conds and not current["conditions"]:
            current["conditions"] = conds[:6]
    out = []
    for r in rooms.values():
        amounts = [p["amount"] for p in r["prices"]]
        r["minPrice"] = min(amounts) if amounts else None
        r["currency"] = r["prices"][0]["currency"] if r["prices"] else default_currency
        r["rateCount"] = len(r.pop("prices"))
        out.append(r)
    return out


def _guest_count(text: str) -> int | None:
    """'Sức chứa: 2 người lớn' → 2; '2 người lớn, 2 trẻ em' → 4."""
    nums = re.findall(r"(\d+)\s*(?:người|trẻ|khách|adult|child|guest)", text or "", re.I)
    if nums:
        return sum(int(n) for n in nums)
    return first_int(text)


def _bed_text(row, room_name: str) -> str | None:
    for el in row.find_all(["span", "div", "li"]):
        if el.find(["span", "div", "li"]):
            continue
        t = node_text(el)
        if t and t != room_name and len(t) < 80 and re.search(r"\d+\s+(giường|nệm|bed)", t, re.I):
            return t
    return None


def _facility_items(soup: BeautifulSoup) -> list[str]:
    """Mục "Tiện nghi" dưới bảng phòng (không lấy khối "Thắc mắc của du khách")."""
    block = soup.select_one("[data-testid='property-facilities-block-container']")
    items = [node_text(li) for li in block.select("li")] if block else []
    if not items:
        for sec in soup.select("[data-testid='property-section--content']"):
            heading = sec.find_previous(["h2", "h3"])
            if heading is None or not fold(node_text(heading)).startswith("tien nghi"):
                continue
            items = [node_text(li) for li in sec.select("li")]
            if not items:
                items = [
                    node_text(el)
                    for el in sec.find_all(["span", "div"])
                    if not el.find(["span", "div"]) and 2 < len(node_text(el)) < 60
                ]
            break
    skip = {"các tiện nghi được ưa chuộng nhất", "tiện nghi", "hiển thị tất cả"}
    return uniq(i for i in items if i and i.casefold() not in skip)[:80]


def _ld_type(block: dict) -> set[str]:
    t = block.get("@type")
    if isinstance(t, list):
        return {str(x).lower() for x in t}
    return {str(t).lower()} if t else set()


def _search(text: str, pattern: str) -> str | None:
    m = re.search(pattern, text)
    return m.group(1) if m else None


def _to_float(v) -> float | None:
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "."))
    except ValueError:
        return None
