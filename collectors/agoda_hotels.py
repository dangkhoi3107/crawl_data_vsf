"""agoda.com – chỗ ở theo điểm đến (handbook §3: ưu tiên cao, phủ tốt khách sạn nội địa Việt Nam).

Tìm URL: trang thành phố https://www.agoda.com/vi-vn/city/<slug>.html (render bằng JavaScript nên cần trình
duyệt) → N khách sạn đầu danh sách. Link /hotel/all/ bị robots.txt cấm nên bị bỏ.
Trang khách sạn: JSON-LD Hotel (tên, mô tả tiếng Việt, địa chỉ, điểm đánh giá, bản đồ → toạ độ), hạng sao,
tiện nghi, giá phòng rẻ nhất cho ngày đã chọn. Lấy ở cấp khách sạn; hạng phòng lấy từ booking.com / Vinpearl.
"""

from __future__ import annotations

import logging
import re
from datetime import date, timedelta
from urllib.parse import unquote, urlencode, urlsplit

from bs4 import BeautifulSoup

from .booking_base import DiscoverContext, SitemapSource
from .common import now_iso, slim_html
from .textutil import clean_text, first_int, json_ld_blocks, node_text, parse_price, uniq

log = logging.getLogger("crawler.agoda")

HOTEL_PATH_RE = re.compile(r"^/vi-vn/([a-z0-9_-]+)/hotel/([a-z0-9-]+)-vn\.html$")
LODGING_TYPES = {"hotel", "lodgingbusiness", "resort", "apartment", "hostel", "motel", "bedandbreakfast", "vacationrental"}
LANGUAGE_RE = re.compile(r"^(tiếng |trung quốc|tiếng$)", re.I)


class AgodaHotels(SitemapSource):
    name = "agoda_hotels"
    ready_selector = (
        "[data-element-name='cheapest-room-price-property-nav-bar'], [data-element-name='property-feature'], "
        "[data-selenium='hotel-header-name']"
    )
    expect_url = re.compile(r"/hotel/")
    people_selectors = (  # handbook: không lưu review / tên người đánh giá
        "[data-element-name='review-plate-snippet-redesign']",
        "[data-element-name='review-plate-snippet-reviewer-details']",
        "[data-element-name='review-plate-redesign-carousel']",
        "[data-element-name='review-comment-translation']",
        "[data-element-name='review-plate-snippet']",
        "[data-selenium='review-comments']",
        "#reviewSectionComments",
        ".Review-comment",
        "[data-element-name='facility-highlights']",  # "điểm nổi bật" = trích dẫn review của khách
        "[data-element-name='review-plate-redesign-categories']",
    )
    error_markers = ("pagenotfound", "Không tìm thấy trang")
    supports_fast = False  # trang khách sạn agoda không render nếu chặn CSS

    def __init__(self, checkin: date | None = None, nights: int = 1, adults: int = 2):
        self.checkin = checkin or (date.today() + timedelta(days=30))
        self.nights = max(1, nights)
        self.adults = adults

    def uses_sitemap(self, opts) -> bool:
        return False

    async def discover_plan(self, ctx: DiscoverContext) -> int:
        total = 0
        want = ctx.opts.budget.agoda_hotels
        for dest in ctx.opts.destinations:
            if not dest.agoda_city:
                continue
            key = f"city:{dest.agoda_city}:{want}"
            if ctx.done(key):
                continue
            res = await ctx.open(f"https://www.agoda.com/vi-vn/city/{dest.agoda_city}.html", "a[href*='/hotel/']")
            if res is None:
                continue
            ctx.cache.write(f"city-{dest.agoda_city}", "html", slim_html(res.html))
            urls = parse_city_links(res.html)[:want]
            rows = [
                (u, rank, {"destination": dest.name, "rank": rank, "via": "agoda-city", "city": dest.agoda_city})
                for rank, u in enumerate(urls, 1)
            ]
            ctx.state.add_many(self.name, rows)
            if urls:
                ctx.mark_done(key, len(rows))
            total += len(rows)
            log.info("[%s] %s: %d khách sạn", self.name, dest.name, len(rows))
        return total

    def fetch_url(self, url: str) -> tuple[str, dict]:
        params = {
            "checkIn": self.checkin.isoformat(),
            "los": self.nights,
            "adults": self.adults,
            "rooms": 1,
            "currency": "VND",
        }
        meta = {
            "checkin": self.checkin.isoformat(),
            "checkout": (self.checkin + timedelta(days=self.nights)).isoformat(),
            "adults": self.adults,
            "currency": "VND",
        }
        return f"{url}?{urlencode(params)}", meta

    def ready_selector_missing(self, html: str) -> bool:
        return "property-feature" not in html and "application/ld+json" not in html

    def parse(self, html: str, url: str, meta: dict) -> dict | None:
        return parse_agoda_html(html, url, meta)


def parse_city_links(html: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    out: list[str] = []
    for a in soup.select("a[href*='/hotel/']"):
        path = urlsplit(a.get("href", "")).path
        if "/hotel/all/" in path or not HOTEL_PATH_RE.match(path):
            continue
        url = "https://www.agoda.com" + path
        if url not in out:
            out.append(url)
    return out


def parse_agoda_html(html: str, url: str, meta: dict | None = None) -> dict | None:
    meta = meta or {}
    soup = BeautifulSoup(html, "lxml")
    ld = next((b for b in json_ld_blocks(soup) if _ld_type(b) & LODGING_TYPES), {})
    name = clean_text(ld.get("name")) or node_text(soup.select_one("[data-selenium='hotel-header-name'], h1"))
    if not name:
        return None
    m = HOTEL_PATH_RE.match(urlsplit(url).path)
    slug, city_slug = (m.group(1), m.group(2)) if m else (url, None)

    address = ld.get("address") if isinstance(ld.get("address"), dict) else {}
    agg = ld.get("aggregateRating") if isinstance(ld.get("aggregateRating"), dict) else {}

    lat = lng = None
    cm = re.search(r"center=(-?\d+(?:\.\d+)?)(?:%2c|,)(-?\d+(?:\.\d+)?)", unquote(ld.get("hasMap") or ""), re.I)
    if cm:
        lat, lng = float(cm.group(1)), float(cm.group(2))

    description = clean_text(ld.get("description")) or node_text(
        soup.select_one("[data-element-name='property-short-description']")
    )
    if not address.get("streetAddress"):
        address["streetAddress"] = node_text(soup.select_one("[data-selenium='hotel-address-map']"))
    stars = _star_rating(soup, description)

    nav = soup.select_one("[data-element-name='cheapest-room-price-property-nav-bar']")
    price_text = re.sub(r"\s+", " ", node_text(nav)).replace("Xem giá", "").strip()
    price = first_int(nav.get("data-element-cheapest-room-price")) if nav is not None else None
    currency = "VND" if price else None
    if price is None and re.search(r"\d", price_text):
        price, currency = parse_price(price_text, "VND")
    if price is None:
        prices = []
        for el in soup.select("[data-element-name='final-price'], [data-selenium='display-price'], [data-element-name='room-price']"):
            amount, cur = parse_price(node_text(el), "VND")
            if amount:
                prices.append(amount)
                currency = cur
        price = min(prices) if prices else None

    facilities = uniq(
        re.sub(r"\s*\n\s*", " ", node_text(el))
        for el in soup.select("[data-element-name='property-feature']")
    )
    facilities = [f for f in facilities if f and not LANGUAGE_RE.match(f)][:80]
    name_en = None
    nm = re.search(r"\(([^()]*(?:\([^()]*\))?[^()]*)\)\s*$", name)
    if nm and re.fullmatch(r"[\x20-\x7E]+", nm.group(1)):
        name_en = nm.group(1).strip()

    images = []
    if isinstance(ld.get("image"), str):
        images.append(("https:" + ld["image"]) if ld["image"].startswith("//") else ld["image"])
    for img in soup.select("img[src*='hotelImages']"):
        src = img.get("src") or ""
        images.append(("https:" + src) if src.startswith("//") else src)
    images = [i for i in uniq(images) if i.startswith("http")][:15]

    return {
        "recordType": "agoda_hotel",
        "source": "agoda_hotels",
        "key": f"hotel:{slug}:{city_slug}",
        "url": url,
        "slug": slug,
        "citySlug": city_slug,
        "name": name,
        "description": description,
        "address": {
            "street": clean_text(address.get("streetAddress")),
            "locality": clean_text(address.get("addressLocality")),
            "region": clean_text(address.get("addressRegion")),
            "country": clean_text(address.get("addressCountry")),
            "postalCode": clean_text(address.get("postalCode")),
        },
        "latitude": lat,
        "longitude": lng,
        "starRating": stars,
        "reviewScore": _to_float(agg.get("ratingValue")),
        "reviewScoreScale": _to_float(agg.get("bestRating")) or 10.0,
        "reviewCount": first_int(str(agg.get("reviewCount") or "")),
        "nameEn": name_en,
        "facilities": facilities,
        "images": images,
        "minPrice": price,
        "currency": currency or "VND",
        "priceText": price_text,
        "priceQuery": {k: meta.get(k) for k in ("checkin", "checkout", "adults", "currency")},
        "crawledAt": meta.get("fetchedAt") or now_iso(),
    }


def _star_rating(soup: BeautifulSoup, description: str) -> float | None:
    for el in soup.select("[data-element-name='mosaic-hotel-rating-container'][aria-label], [aria-label*='sao trên']"):
        m = re.search(r"([1-5](?:[.,]5)?)\s*sao", el.get("aria-label", ""))
        if m:
            return float(m.group(1).replace(",", "."))
    box = soup.select_one("[data-selenium='star-rating-container'], [data-element-name='star-rating']")
    if box is not None:
        label = " ".join(filter(None, [box.get("aria-label"), box.get("title")] +
                                [e.get("aria-label") or e.get("title") for e in box.select("[aria-label], [title]")]))
        n = first_int(label)
        if n and 1 <= n <= 5:
            return float(n)
        icons = box.select("svg, i, [class*='star' i]")
        if 1 <= len(icons) <= 5:
            return float(len(icons))
    m = re.search(r"\b([1-5])\s*sao\b", description or "", re.I)
    return float(m.group(1)) if m else None


def _ld_type(block: dict) -> set[str]:
    t = block.get("@type")
    if isinstance(t, list):
        return {str(x).lower() for x in t}
    return {str(t).lower()} if t else set()


def _to_float(v) -> float | None:
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None
