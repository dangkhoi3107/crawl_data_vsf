"""Vinpearl: khách sạn + từng hạng phòng (có giá), vé VinWonders, tour, combo, golf.

Nguồn:
  1. booking-hotel-api.vinpearl.com — HTTP thường, không bị Cloudflare chặn
       /availability/locations/all                  → danh sách khách sạn (hotelId, locationId, tên)
       /availability/locations/type-locations       → link trang vinpearl.com của từng khách sạn
       /availability/hotels/insider/best-prices     → mã khách sạn, hạng phòng rẻ nhất, giá thành viên
       /availability/rooms?hotelId&arrivalDate...   → mô tả, địa chỉ, toạ độ, hạng sao, điểm TripAdvisor,
                                                       tiện nghi, ảnh; từng hạng phòng: mô tả, diện tích,
                                                       giường, sức chứa, tiện nghi, ảnh, giá theo gói
     Hạng phòng hết chỗ vào một ngày sẽ không xuất hiện, nên hỏi nhiều ngày rồi gộp lại.
  2. booking-tour-api.vinpearl.com — có Cloudflare → gọi từ trong trang booking.vinpearl.com (trình duyệt)
       /api/frontend/tour?pageIndex&pageSize        → toàn bộ vé/tour/combo/golf đang bán trên web
       /api/frontend/tour/{slug}?Channel=<kênh>     → mô tả chi tiết, điểm nổi bật, bao gồm, lịch trình
  3. (tuỳ chọn --site-pages) vinpearl.com/vi/hotels/{slug}[/rooms] — có Cloudflare, có thể phải tự xác minh
     trong cửa sổ trình duyệt; bổ sung đoạn giới thiệu và giá công bố hiển thị trên website.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from urllib.parse import urlencode, urljoin

from bs4 import BeautifulSoup

from .common import (
    BlockBreaker,
    BrowserOptions,
    BrowserSession,
    ChallengeBlocked,
    HostRateLimiter,
    Http,
    JsonlWriter,
    PageGone,
    Paths,
    RawCache,
    read_jsonl,
    looks_like_challenge,
    now_iso,
    slim_html,
)
from .textutil import (
    clean_text,
    first_int,
    html_to_text,
    json_ld_blocks,
    meta_content,
    node_text,
    parse_price,
    uniq,
)

log = logging.getLogger("crawler.vinpearl")

SOURCE = "vinpearl"
SITE = "https://vinpearl.com"
BOOKING_SITE = "https://booking.vinpearl.com"
HOTEL_API = "https://booking-hotel-api.vinpearl.com"
TOUR_API = "https://booking-tour-api.vinpearl.com"
STATIC = "https://booking-static.vinpearl.com"
API_HEADERS = {"Accept": "application/json", "accept-language": "vi-VN", "x-display-currency": "VND"}
HOTEL_URL_RE = re.compile(r"^(?:https://vinpearl\.com)?/vi/hotels/([a-z0-9-]+)/?$")


def default_price_dates(today: date | None = None) -> list[date]:
    today = today or date.today()
    return [today + timedelta(days=d) for d in (30, 14, 60)]


@dataclass
class VinpearlOptions:
    browser: BrowserOptions
    delay: float = 2.0
    refresh: bool = False
    offline: bool = False  # reparse: chỉ đọc cache
    skip_hotels: bool = False
    skip_tours: bool = False
    tour_limit: int | None = None
    max_blocks: int = 5
    price_dates: list[date] = field(default_factory=default_price_dates)
    adults: int = 2
    site_pages: bool = False


class VinpearlCollector:
    def __init__(self, paths: Paths, opts: VinpearlOptions):
        self.paths = paths
        self.opts = opts
        self.cache = RawCache(paths, SOURCE)
        self.limiter = HostRateLimiter(opts.delay)
        self.http = Http(self.limiter)
        self.breaker = BlockBreaker(opts.max_blocks)
        self._session: BrowserSession | None = None
        self._site_page = None
        self._api_page = None
        self._previous_dates: dict[str, list[str]] = {}
        if opts.offline:  # reparse: nhớ thứ tự ngày hỏi giá của lần crawl trước
            for r in read_jsonl(paths.interim / f"{SOURCE}.jsonl"):
                if r.get("recordType") == "vinpearl_hotel" and r.get("hotelId"):
                    self._previous_dates[r["hotelId"]] = (r.get("priceQuery") or {}).get("dates") or []

    # ------------------------------------------------------------------ fetch helpers

    async def _http_json(self, key: str, url: str, browser_fallback: bool = True) -> object | None:
        cached = self.cache.read_json(key)
        if cached is not None and (self.opts.offline or not self.opts.refresh):
            return cached
        if self.opts.offline:
            return None
        try:
            r = await self.http.get(url, headers=API_HEADERS)
        except PermissionError as e:
            log.warning("%s", e)
            return None
        except Exception as e:
            log.warning("Lỗi gọi %s: %s", url, e)
            return None
        if r.status_code == 200 and "json" in r.headers.get("content-type", ""):
            data = r.json()
            self.cache.write_json(key, data)
            return data
        if r.status_code in (403, 429, 503) and browser_fallback:
            log.info("HTTP %s cho %s – thử qua trình duyệt", r.status_code, url)
            return await self._browser_json(key, url)
        log.warning("HTTP %s cho %s: %s", r.status_code, url, r.text[:200])
        return None

    async def _browser(self) -> BrowserSession:
        if self._session is None:
            self._session = await BrowserSession(self.paths, SOURCE, self.opts.browser).__aenter__()
        return self._session

    async def _ensure_api_page(self):
        if self._api_page is None:
            session = await self._browser()
            self._api_page = await session.new_page()
            await self.limiter.wait(BOOKING_SITE)
            await session.fetch_html(
                self._api_page, f"{BOOKING_SITE}/vi-VND/tours-and-experiences", "a[href*='/tour/'], footer"
            )
        return self._api_page

    async def _browser_json(self, key: str, url: str, quiet_404: bool = False) -> object | None:
        cached = self.cache.read_json(key)
        if cached is not None and (self.opts.offline or not self.opts.refresh):
            return cached
        if self.opts.offline or self.breaker.tripped:
            return None
        try:
            page = await self._ensure_api_page()
        except Exception as e:  # thử thách chưa qua, timeout mạng...
            self.breaker.blocked()
            log.warning("Không mở được booking.vinpearl.com: %s", str(e)[:200])
            self._api_page = None
            return None
        session = await self._browser()
        for _ in range(3):
            await self.limiter.wait(url)
            try:
                status, data = await session.fetch_json(page, url, API_HEADERS)
            except Exception as e:  # trang bị điều hướng/đóng
                log.warning("Lỗi gọi API %s: %s", url, e)
                self._api_page = None
                page = await self._ensure_api_page()
                continue
            if status == 200 and isinstance(data, (dict, list)):
                self.breaker.ok()
                self.cache.write_json(key, data)
                return data
            if status in (403, 429, 503):
                if self.breaker.blocked():
                    log.error("Bị chặn liên tiếp %d lần – dừng phần Vinpearl.", self.breaker.streak)
                    return None
                wait = self.breaker.cooldown()
                log.warning("API trả %s (%s) – nghỉ %.0fs", status, url, wait)
                self.limiter.penalise(url, wait)
                continue
            (log.debug if quiet_404 and status == 404 else log.warning)("API trả %s cho %s", status, url)
            return None
        return None

    async def _site_html(self, url: str, ready: str) -> str | None:
        cached = self.cache.read(url, "html")
        if cached is not None and looks_like_challenge(cached):
            cached = None  # cache hỏng từ lần chạy bị chặn
        if cached is not None and (self.opts.offline or not self.opts.refresh):
            return cached
        if self.opts.offline or self.breaker.tripped:
            return None
        if not await self.http.robots.allowed(url):
            log.warning("robots.txt không cho phép %s", url)
            return None
        session = await self._browser()
        if self._site_page is None:
            self._site_page = await session.new_page()
        await self.limiter.wait(url)
        try:
            res = await session.fetch_html(self._site_page, url, ready)
        except PageGone as e:
            log.info("Bỏ %s: %s", url, e)
            return None
        except ChallengeBlocked as e:
            self.breaker.blocked()
            log.warning("%s", e)
            self.limiter.penalise(url, self.breaker.cooldown())
            return None
        self.breaker.ok()
        self.cache.write(url, "html", slim_html(res.html))
        return res.html

    # ------------------------------------------------------------------ run

    async def run(self, writer: JsonlWriter) -> dict:
        stats = {"hotels": 0, "rooms": 0, "tours": 0}
        try:
            if not self.opts.skip_hotels:
                for rec in await self.collect_hotels():
                    writer.write(rec)
                    stats["hotels"] += 1
                    stats["rooms"] += len(rec.get("rooms") or [])
            if not self.opts.skip_tours:
                try:
                    async for rec in self.collect_tours():
                        writer.write(rec)
                        stats["tours"] += 1
                except (KeyboardInterrupt, SystemExit):
                    raise
                except Exception as e:  # phần tour lỗi không làm mất phần khách sạn đã lấy
                    log.error("Vinpearl tour lỗi: %s – giữ phần đã thu được, chạy lại để tiếp tục (có cache).", str(e)[:300])
                    stats["toursError"] = str(e)[:200]
        finally:
            await self.close()
        if self.breaker.tripped:
            stats["stopped"] = "blocked"
        return stats

    async def close(self) -> None:
        if self._session is not None:
            await self._session.__aexit__(None, None, None)
            self._session = None
        await self.http.close()

    # ------------------------------------------------------------------ hotels

    async def collect_hotels(self) -> list[dict]:
        hotels: dict[str, dict] = {}
        locations = await self._http_json("api-locations-all", f"{HOTEL_API}/availability/locations/all")
        for loc in (locations or {}).get("locations") or [] if isinstance(locations, dict) else []:
            if (loc.get("type") or "").lower() == "hotel" and loc.get("hotelId"):
                hotels[loc["hotelId"]] = {"hotelId": loc["hotelId"], "locationId": loc.get("locationId"), "apiName": clean_text(loc.get("hotelName"))}

        location_ids = sorted({h["locationId"] for h in hotels.values() if h.get("locationId")})
        if location_ids:
            tl = await self._http_json(
                "api-type-locations",
                f"{HOTEL_API}/availability/locations/type-locations?Get_list_hotels=true&LocationIds={','.join(location_ids)}",
            )
            for loc in (tl or {}).get("locations") or [] if isinstance(tl, dict) else []:
                h = hotels.get(loc.get("hotelId"))
                if h is not None and loc.get("urlSlug"):
                    h["pageUrl"] = loc["urlSlug"]

        best = await self._http_json("api-best-prices", f"{HOTEL_API}/availability/hotels/insider/best-prices")
        for item in (best or {}).get("data") or [] if isinstance(best, dict) else []:
            hid = item.get("hotelId")
            if not hid:
                continue
            h = hotels.setdefault(hid, {"hotelId": hid, "apiName": clean_text(item.get("hotelName"))})
            h["hotelCode"] = item.get("hotelCode")
            h["bestPriceDescription"] = html_to_text(item.get("hotelDesciption"))
            h["bestPriceImages"] = [_static_url(x) for x in item.get("imageLinks") or []]
            h["bestPrice"] = {
                "roomTypeName": clean_text(item.get("roomTypeName")),
                "ratePlanName": clean_text(item.get("ratePlanName")),
                "ratePlanDescription": clean_text(item.get("ratePlanDescription")),
                "salePrice": parse_price(item.get("salePrices"))[0],
                "memberPrice": parse_price(item.get("memberPrice"))[0],
                "bookingUrl": item.get("url"),
            }
        log.info("Vinpearl: %d khách sạn", len(hotels))

        records: list[dict] = []
        crawled_at = now_iso()
        for n, (hid, h) in enumerate(sorted(hotels.items(), key=lambda kv: kv[1].get("apiName") or ""), 1):
            responses = []
            for d in self._price_dates_for(hid):
                params = {
                    "hotelId": hid,
                    "arrivalDate": d.isoformat(),
                    "lengthOfStay": 1,
                    "numberOfRoom": 1,
                    "roomOccupancy": f"{self.opts.adults}_0_0",
                    "dateAdd": 0,
                    "channel": "Web",
                }
                data = await self._http_json(
                    f"api-rooms-{hid}-{d.isoformat()}-{self.opts.adults}a",
                    f"{HOTEL_API}/availability/rooms?{urlencode(params)}",
                    browser_fallback=False,
                )
                if isinstance(data, dict) and data.get("hotel"):
                    responses.append((d.isoformat(), data))
            site = await self._site_info(h) if self.opts.site_pages else {}
            rec = build_hotel_record(h, responses, site, crawled_at, self.opts.adults)
            log.info("Vinpearl %d/%d: %s – %d hạng phòng", n, len(hotels), rec["name"], len(rec["rooms"]))
            records.append(rec)
        return records

    def _price_dates_for(self, hotel_id: str) -> list[date]:
        """reparse vào ngày khác ngày crawl thì hôm nay + 30/14/60 không có trong cache (mất cả hạng phòng lẫn toạ độ),
        nên dùng các ngày đã cache của khách sạn, giữ thứ tự lần crawl trước (ngày đầu tiên quyết định giá)."""
        dates = self.opts.price_dates
        key = lambda d: f"api-rooms-{hotel_id}-{d.isoformat()}-{self.opts.adults}a"
        if not self.opts.offline or all(self.cache.has(key(d), "json") for d in dates):
            return dates
        cached = set()
        for f in (self.cache.dir / "json").glob(f"api-rooms-{hotel_id}-*-{self.opts.adults}a.json.gz"):
            m = re.search(r"-(\d{4}-\d{2}-\d{2})-\d+a\.json\.gz$", f.name)
            if m:
                cached.add(m.group(1))
        previous = [d for d in self._previous_dates.get(hotel_id, []) if d in cached]
        return [date.fromisoformat(d) for d in previous + sorted(cached - set(previous))]

    async def _site_info(self, h: dict) -> dict:
        m = HOTEL_URL_RE.match((h.get("pageUrl") or "").split("?")[0])
        if not m:
            return {}
        url = f"{SITE}/vi/hotels/{m.group(1)}"
        html = await self._site_html(url, "h1.hotel-title, .p-detail-about")
        if not html:
            return {}
        info = parse_hotel_page(html, url)
        rooms_html = await self._site_html(f"{url}/rooms", ".p-page-room__box, .room-content-title, .vp-footer-info")
        if rooms_html:
            info["rooms"], _, _ = parse_rooms_page(rooms_html)
        return info

    # ------------------------------------------------------------------ tours

    async def collect_tours(self):
        page_size = 100
        index = 1
        items: list[dict] = []
        total = None
        while True:
            url = f"{TOUR_API}/api/frontend/tour?pageIndex={index}&pageSize={page_size}"
            data = await self._browser_json(f"api-tour-list-p{index:03d}-s{page_size}", url)
            if not isinstance(data, dict):
                break
            payload = data.get("data") or {}
            result = payload.get("result") or []
            total = payload.get("totalCount") or total
            items.extend(result)
            if not result or (total and len(items) >= total):
                break
            index += 1
        seen: set[str] = set()
        unique = [t for t in items if t.get("id") and not (t["id"] in seen or seen.add(t["id"]))]
        if self.opts.tour_limit:
            unique = unique[: self.opts.tour_limit]
        log.info("Vinpearl: %d sản phẩm tour/vé/combo/golf (API báo tổng %s)", len(unique), total)
        crawled_at = now_iso()
        missing = 0
        for n, item in enumerate(unique, 1):
            slug = item.get("urlSlug")
            detail = None
            # Chi tiết chỉ trả về khi hỏi đúng kênh bán của sản phẩm (1 = website, 10/11 = kênh khác)
            channels = uniq([c for c in (item.get("channel") or []) if isinstance(c, int)] + [1])
            for ch in channels:
                if not slug or self.breaker.tripped:
                    break
                detail = await self._browser_json(
                    f"api-tour-detail-{slug}", f"{TOUR_API}/api/frontend/tour/{slug}?Channel={ch}", quiet_404=True
                )
                if isinstance(detail, dict) and detail.get("data"):
                    break
            if not (isinstance(detail, dict) and detail.get("data")):
                missing += 1
                detail = None
            if n % 50 == 0:
                log.info("Vinpearl tour: %d/%d", n, len(unique))
            yield _tour_record(item, detail.get("data") if detail else None, crawled_at)
        if missing:
            log.info("Vinpearl: %d sản phẩm không lấy được trang chi tiết – dùng thông tin từ danh sách", missing)


# ---------------------------------------------------------------------- hotel record


def build_hotel_record(h: dict, responses: list[tuple[str, dict]], site: dict, crawled_at: str, adults: int) -> dict:
    hotel = next((data["hotel"] for _, data in responses if data.get("hotel")), {})
    rooms: dict[str, dict] = {}
    for day, data in responses:
        for occ in data.get("rooms") or []:
            for rr in occ.get("roomRates") or []:
                rt = rr.get("roomtype") or {}
                rid = rt.get("id") or rt.get("code") or rt.get("name")
                if not rid:
                    continue
                room = rooms.get(rid)
                if room is None:
                    room = rooms[rid] = {
                        "roomTypeId": rt.get("id"),
                        "code": rt.get("code"),
                        "name": clean_text(rt.get("name")),
                        "shortDescription": clean_text(rt.get("shortDescription")),
                        "description": html_to_text(rt.get("description")),
                        "sizeM2": _to_float(rt.get("area")),
                        "maxOccupancy": rt.get("maxOccupancy"),
                        "defaultOccupancy": rt.get("defaultOccupancy"),
                        "maxAdult": rt.get("maxAdult"),
                        "maxChild": rt.get("maxChild"),
                        "bedrooms": rt.get("numberOfBedRoom"),
                        "bedType": clean_text(rt.get("bedType")),
                        "isVilla": rt.get("isVilla"),
                        "amenities": uniq(clean_text(a.get("name")) for a in rt.get("amenity") or [] if isinstance(a, dict)),
                        "images": uniq(_static_url(m.get("url")) for m in rt.get("media") or [] if isinstance(m, dict))[:12],
                        "pricesByDate": {},
                        "ratePlans": [],
                        "includesBreakfast": False,
                    }
                amounts = []
                for rate in rr.get("rates") or []:
                    if rate.get("isSoldOut"):
                        continue
                    amount = ((rate.get("totalAmountIncludeTax") or {}).get("amount") or {}).get("amount")
                    if amount:
                        amounts.append(float(amount))
                    plan = rate.get("ratePlan") or {}
                    if plan.get("name"):
                        room["ratePlans"] = uniq(room["ratePlans"] + [clean_text(plan["name"])])[:10]
                    if plan.get("includesBreakfast"):
                        room["includesBreakfast"] = True
                if amounts:
                    room["pricesByDate"][day] = int(min(amounts))
    for room in rooms.values():
        prices = list(room["pricesByDate"].values())
        room["minPrice"] = min(prices) if prices else None
        first = next((room["pricesByDate"][d] for d, _ in responses if d in room["pricesByDate"]), None)
        room["price"] = first

    page_url = h.get("pageUrl") or (f"{SITE}/vi/hotels/{hotel['urlSlug']}" if hotel.get("urlSlug") else None)
    hotel_id = h.get("hotelId") or hotel.get("id")
    return {
        "recordType": "vinpearl_hotel",
        "source": SOURCE,
        "key": f"hotel:{hotel_id}",
        "hotelId": hotel_id,
        "hotelCode": hotel.get("code") or h.get("hotelCode"),
        "locationId": hotel.get("locationId") or h.get("locationId"),
        "name": clean_text(hotel.get("name")) or h.get("apiName") or site.get("name"),
        "pageUrl": page_url,
        "bookingUrl": f"{BOOKING_SITE}/vi-VND/hotel/{hotel_id}" if hotel_id else None,
        "description": html_to_text(hotel.get("description")) or h.get("bestPriceDescription"),
        "shortDescription": clean_text(hotel.get("shortDescription")),
        "policy": clean_text(hotel.get("defaultRateDescription")),
        "address": clean_text(hotel.get("address")) or site.get("address"),
        "latitude": _to_float(hotel.get("latitude")),
        "longitude": _to_float(hotel.get("longtitude") or hotel.get("longitude")),
        "starRating": _to_float(hotel.get("star")),
        "tripAdvisorRating": _to_float(hotel.get("rating")),
        "reviewCount": hotel.get("reviewCount"),
        "hotline": hotel.get("hotline"),
        "amenities": uniq(clean_text(a.get("name")) for a in hotel.get("amenity") or [] if isinstance(a, dict)),
        "images": uniq(
            [_static_url(m.get("url")) for m in hotel.get("media") or [] if isinstance(m, dict)]
            + (h.get("bestPriceImages") or [])
        )[:20],
        "bestPrice": h.get("bestPrice"),
        "rooms": list(rooms.values()),
        "priceQuery": {"dates": [d for d, _ in responses], "adults": adults, "nights": 1, "currency": "VND"},
        "site": site or None,
        "crawledAt": crawled_at,
    }


# ---------------------------------------------------------------------- vinpearl.com page parsers (tuỳ chọn)


def parse_hotel_page(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    settings = _drupal_settings(soup)
    h1 = soup.select_one("h1.hotel-title") or soup.find("h1")
    about = soup.select_one(".p-detail-about")
    about_title = about_text = ""
    if about:
        t = about.select_one(".p-detail-about__title, h2")
        about_title = node_text(t)
        if t:
            t.extract()
        for junk in about.select("script, style, button, .btn"):
            junk.decompose()
        about_text = node_text(about)
    rating = rating_count = None
    for block in json_ld_blocks(soup):
        agg = block.get("aggregateRating")
        if isinstance(agg, dict):
            rating = _to_float(agg.get("ratingValue"))
            rating_count = first_int(str(agg.get("ratingCount") or agg.get("reviewCount") or ""))
    return {
        "pageUrl": url,
        "name": node_text(h1) or meta_content(soup, "og:title"),
        "aboutTitle": about_title,
        "aboutText": about_text,
        "metaDescription": meta_content(soup, "description", "og:description"),
        "ogImage": meta_content(soup, "og:image"),
        "destination": clean_text(settings.get("destination")) or None,
        "address": node_text(soup.select_one(".vp-footer-info .address .text")) or None,
        "rating": rating,
        "ratingCount": rating_count,
    }


def parse_rooms_page(html: str) -> tuple[list[dict], str | None, str | None]:
    soup = BeautifulSoup(html, "lxml")
    rooms: list[dict] = []
    seen: set[str] = set()
    hotel_id = location_id = None
    for box in soup.select(".p-page-room__box"):
        title = node_text(box.select_one(".room-content-title"))
        if not title or title.casefold() in seen:
            continue
        seen.add(title.casefold())
        tag = box.select_one("[data-tag-group-id]")
        if tag:
            hotel_id = hotel_id or tag.get("data-tag-group-id")
            location_id = location_id or tag.get("data-location-id") or tag.get("data-location-ct")
        list_price = from_price = None
        for line in box.select(".room-content-panel-text > div"):
            text = node_text(line)
            price, _ = parse_price(text, "VND")
            if re.search(r"công bố|niêm yết", text, re.I):
                list_price = price
            elif re.search(r"từ", text, re.I):
                from_price = price
        rooms.append(
            {
                "name": title,
                "description": node_text(box.select_one(".room-content-text")),
                "listPrice": list_price,
                "fromPrice": from_price,
                "anchor": box.get("id"),
            }
        )
    return rooms, hotel_id, location_id


# ---------------------------------------------------------------------- tour record


def _tour_record(item: dict, detail: dict | None, crawled_at: str) -> dict:
    d = detail or {}
    td = d.get("tourDetail") or {}
    extra = []
    for block in td.get("extraInfos") or []:
        if isinstance(block, dict):
            extra.append({"title": clean_text(block.get("title")), "text": html_to_text(block.get("content"))})
    itinerary = []
    for step in td.get("tripItinerary") or []:
        if isinstance(step, dict):
            itinerary.append({k: html_to_text(v) if isinstance(v, str) else v for k, v in step.items() if k.lower() != "id"})
    images = [_static_url((x or {}).get("fileUri")) for x in (d.get("slideShowImagesView") or [])]
    thumb = _static_url(((d.get("thumbImageView") or item.get("thumbImageView")) or {}).get("fileUri"))
    destination = d.get("destination") or item.get("destination") or {}
    return {
        "recordType": "vinpearl_tour",
        "source": SOURCE,
        "key": f"tour:{item.get('tourCode') or item.get('id')}",
        "id": item.get("id"),
        "tourCode": item.get("tourCode") or td.get("tourCode"),
        "name": clean_text(item.get("tourName") or td.get("tourName")),
        "urlSlug": item.get("urlSlug"),
        "pageUrl": f"{BOOKING_SITE}/vi-VND/tour/{item['urlSlug']}" if item.get("urlSlug") else None,
        "type": item.get("type"),
        "detailType": td.get("type"),
        "vwType": item.get("vwType"),
        "tag": item.get("tag"),
        "productTypes": item.get("productTypes"),
        "salesChannels": item.get("channel"),
        "destinationId": destination.get("id") if isinstance(destination, dict) else None,
        "destinationName": destination.get("name") if isinstance(destination, dict) else None,
        "departure": (item.get("departure") or {}).get("name") if isinstance(item.get("departure"), dict) else None,
        "adultOriginalPrice": item.get("adultOriginalPrice"),
        "adultSalePrice": item.get("adultSalePrice"),
        "childOriginalPrice": d.get("childOriginalPrice"),
        "childSalePrice": d.get("childSalePrice"),
        "lengthOfTour": item.get("lengthOfTour"),
        "shortDescription": clean_text(item.get("shortDescription") or td.get("shortDescription")),
        "description": html_to_text(td.get("description") or item.get("description")),
        "highlight": html_to_text(td.get("highlight")),
        "extraInfos": extra,
        "serviceIncluded": [html_to_text(x) if isinstance(x, str) else x for x in td.get("serviceIncluded") or []],
        "serviceExcluded": [html_to_text(x) if isinstance(x, str) else x for x in td.get("serviceExcluded") or []],
        "tripItinerary": itinerary,
        "cancellationPolicy": html_to_text(td.get("cancellationPolicy")),
        "audience": [clean_text(t.get("name")) for t in d.get("tourTypes") or [] if isinstance(t, dict)],
        "supplierName": d.get("supplierName"),
        "supplierCode": d.get("supplierCode"),
        "imageUrlSlug": d.get("imageUrlSlug") or item.get("imageUrlSlug"),
        "soldQuantity": item.get("soldQuantity"),
        "isEnabled": item.get("isEnabled"),
        "saleStartDate": item.get("saleStartDate"),
        "saleEndDate": item.get("saleEndDate"),
        "images": uniq([thumb] + images)[:15],
        "hasDetail": detail is not None,
        "crawledAt": crawled_at,
    }


def _drupal_settings(soup: BeautifulSoup) -> dict:
    tag = soup.find("script", attrs={"data-drupal-selector": "drupal-settings-json"})
    if not tag:
        return {}
    try:
        return json.loads(tag.string or tag.get_text() or "{}")
    except json.JSONDecodeError:
        return {}


def _static_url(uri: str | None) -> str | None:
    if not uri:
        return None
    uri = uri.strip()
    if uri.startswith("http"):
        return uri
    if uri.startswith(("booking-static.vinpearl.com", "statics.vinpearl.com")):
        return "https://" + uri.replace(" ", "%20")
    return urljoin(STATIC + "/", uri.replace(" ", "%20"))


def _to_float(v) -> float | None:
    if v in (None, ""):
        return None
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


async def run(paths: Paths, opts: VinpearlOptions) -> dict:
    out = paths.interim / f"{SOURCE}.jsonl"
    tmp = out.with_suffix(".jsonl.tmp")
    with JsonlWriter(tmp, "w") as writer:
        stats = await VinpearlCollector(paths, opts).run(writer)
    if writer.count == 0 and out.exists():
        tmp.unlink(missing_ok=True)
        log.warning("Không thu được bản ghi nào – giữ nguyên %s", out)
    else:
        if opts.skip_hotels or opts.skip_tours:
            _merge_keep_other(out, tmp, keep="vinpearl_hotel" if opts.skip_hotels else "vinpearl_tour")
        tmp.replace(out)
        log.info("Đã ghi %s", out)
    return stats


def _merge_keep_other(out, tmp, keep: str) -> None:
    """Chạy riêng hotel hoặc tour thì giữ lại phần còn lại từ lần chạy trước."""
    if not out.exists():
        return
    with open(out, encoding="utf-8") as src, open(tmp, "a", encoding="utf-8") as dst:
        for line in src:
            try:
                if json.loads(line).get("recordType") == keep:
                    dst.write(line)
            except json.JSONDecodeError:
                continue
