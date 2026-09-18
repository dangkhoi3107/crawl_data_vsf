"""Booking Flights: dated one-way searches, rendered detail sheets, no private API.

DOM selectors verified on Booking SGN-HAN, 2026-10-17, on 2026-09-18.
Only domestic airports with a known timezone are published. Unknown/changed DOM
fails closed. Search pages and detail fragments are cached before parsing.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
import gzip
import hashlib
import json
import logging
import re
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from .common import (BrowserOptions, BrowserSession, ChallengeBlocked, HostRateLimiter,
                     Http, JsonlWriter, RawCache, StateDB, now_iso)
from .plan import DESTINATIONS

SOURCE = "booking_flights"
BASE = "https://flights.booking.com"
AIRPORT_CITIES = {a: d.name for d in DESTINATIONS for a in d.airports}
TZ = ZoneInfo("Asia/Ho_Chi_Minh")
log = logging.getLogger("crawler.booking_flights")
CARDS = '[id^="flight-card-"]'
DETAIL = '[data-testid="flightdetails_sheet"]'
READY = f'{CARDS}, [role="alert"]'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:24]


def flight_dates(months=None, dates=None, today=None):
    """Expand calendar dates, reject explicit past dates, skip elapsed month days."""
    today = today or datetime.now(TZ).date()
    result = set()
    for month in (months or "").split(","):
        if not month.strip():
            continue
        if not re.fullmatch(r"\d{4}-\d{2}", month.strip()):
            raise ValueError("Tháng phải có dạng YYYY-MM")
        start = date.fromisoformat(month.strip() + "-01")
        result.update(date(start.year, start.month, d) for d in range(1, calendar.monthrange(start.year, start.month)[1] + 1)
                      if date(start.year, start.month, d) >= today)
    for value in (dates or "").split(","):
        if value.strip():
            day = date.fromisoformat(value.strip())
            if day < today:
                raise ValueError(f"Ngày bay đã qua: {day}")
            result.add(day)
    if not months and not dates:
        result.add(today + timedelta(days=30))
    if not result:
        raise ValueError("Không có ngày bay tương lai trong phạm vi yêu cầu")
    return sorted(result)


def flight_routes(raw=None, destinations=DESTINATIONS):
    airports = sorted({a for d in destinations for a in d.airports})
    routes = [tuple(x.strip().upper().split("-")) for x in raw.split(",")] if raw else [
        (a, b) for a in airports for b in airports if a != b]
    for route in routes:
        if len(route) != 2 or route[0] == route[1] or any(a not in AIRPORT_CITIES for a in route):
            raise ValueError(f"Tuyến không hợp lệ/ngoài sân bay nội địa đã biết: {route}")
    return sorted(set(routes))


def search_url(origin, destination, day, adults=1, cabin="ECONOMY", page=1):
    if adults < 1 or adults > 9:
        raise ValueError("adults phải trong 1..9")
    params = {"type": "ONEWAY", "adults": adults, "cabinClass": cabin, "children": "",
              "from": origin + ".AIRPORT", "to": destination + ".AIRPORT",
              "fromCountry": "VN", "toCountry": "VN", "depart": str(day),
              "sort": "BEST", "travelPurpose": "leisure", "locale": "en-us",
              "selected_currency": "VND", "page": page}
    return f"{BASE}/flights/{origin}.AIRPORT-{destination}.AIRPORT/?{urlencode(params)}"


def context_from_url(url):
    q = parse_qs(urlsplit(url).query, keep_blank_values=True)
    return {"originAirport": q["from"][0].split(".")[0], "destinationAirport": q["to"][0].split(".")[0],
            "departureDate": q["depart"][0], "adults": int(q["adults"][0]),
            "children": [], "cabinClass": q["cabinClass"][0], "tripType": q["type"][0]}


def clean_url(url):
    parts = urlsplit(url)
    keep = {k: v[0] for k, v in parse_qs(parts.query, keep_blank_values=True).items()
            if k in {"type", "adults", "cabinClass", "children", "from", "to", "depart", "sort",
                     "locale", "selected_currency", "page", "fromCountry", "toCountry", "travelPurpose"}}
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(keep), ""))


def sanitize_fragment(html):
    """Product DOM only: discard scripts, links/session attributes and images."""
    soup = BeautifulSoup(html, "lxml")
    for node in soup.select("script, style, svg, img, iframe, input, form"):
        node.decompose()
    for node in soup.find_all(True):
        node.attrs = {k: v for k, v in node.attrs.items() if k in {"data-testid", "role", "aria-label"}}
    return str(soup)


def text_at(soup, testid):
    node = soup.find(attrs={"data-testid": testid})
    return node.get_text(" ", strip=True) if node else ""


def money(text):
    # Parser intentionally accepts only the observed English VND presentation.
    m = re.fullmatch(r"VND\s*([\d,]+(?:\.\d{1,2})?)", text.strip())
    if not m:
        raise ValueError(f"Giá/currency chưa hỗ trợ hoặc chưa xác minh: {text!r}")
    try:
        amount = Decimal(m[1].replace(",", ""))
    except InvalidOperation as exc:
        raise ValueError("Giá không hợp lệ") from exc
    if amount <= 0:
        raise ValueError("Giá vé phải lớn hơn 0")
    return int(amount) if amount == amount.to_integral_value() else float(amount)


def timestamp(text, reference):
    """Resolve explicit month/day near query date; never infer date from time alone."""
    m = re.fullmatch(r"(?:[A-Za-z]{3},\s*)?([A-Za-z]{3}) (\d{1,2})\s*·\s*(\d{1,2}:\d{2} [AP]M)", text)
    if not m:
        raise ValueError(f"Thiếu ngày/giờ hoặc định dạng mới: {text!r}")
    months = {v: k for k, v in enumerate(calendar.month_abbr) if v}
    month = months.get(m[1])
    if not month:
        raise ValueError("Tháng không nhận diện được")
    time = datetime.strptime(m[3], "%I:%M %p").time()
    candidates = []
    for year in (reference.year - 1, reference.year, reference.year + 1):
        try:
            day = date(year, month, int(m[2]))
        except ValueError:
            continue
        if 0 <= (day - reference).days <= 7:
            candidates.append(datetime.combine(day, time, TZ))
    if len(candidates) != 1:
        raise ValueError("Ngày trên trang không khớp ngày tìm kiếm")
    return candidates[0]


def parse_detail(payload):
    """One rendered detail sheet -> one itinerary offer; reject partial schedules."""
    ctx = payload["context"]
    if ctx["tripType"] != "ONEWAY" or ctx.get("children"):
        raise ValueError("Chỉ hỗ trợ một chiều, người lớn ở phiên bản này")
    soup = BeautifulSoup(payload["html"], "lxml")
    segments = soup.find_all(attrs={"data-testid": re.compile(r"^timeline_segment_\d+$")})
    if len(segments) != 1:
        raise ValueError("Không tìm thấy đúng một hành trình một chiều")
    legs = segments[0].find_all(attrs={"data-testid": re.compile(r"^timeline_leg_\d+$")})
    if not legs:
        raise ValueError("Thiếu chi tiết chặng bay")
    departure_day = date.fromisoformat(ctx["departureDate"])
    parsed = []
    for leg in legs:
        origin = text_at(leg, "timeline_location_airport_departure").split(" · ")[0].strip()
        destination = text_at(leg, "timeline_location_airport_arrival").split(" · ")[0].strip()
        if origin not in AIRPORT_CITIES or destination not in AIRPORT_CITIES:
            raise ValueError("Chặng nối qua sân bay chưa có timezone: giữ raw, không đoán giờ")
        departure = timestamp(text_at(leg, "timeline_location_timestamp_departure"), departure_day)
        arrival = timestamp(text_at(leg, "timeline_location_timestamp_arrival"), departure.date())
        if arrival <= departure:
            raise ValueError("Ngày/giờ đến không sau ngày/giờ đi")
        number_class = text_at(leg, "timeline_leg_info_flight_number_and_class").split(" · ")
        number = number_class[0].replace(" ", "")
        if not re.fullmatch(r"[A-Z0-9]{2}\d{1,4}[A-Z]?", number):
            raise ValueError("Thiếu số hiệu chuyến bay")
        if parsed and (parsed[-1]["destinationAirport"] != origin or parsed[-1]["arrivalAt"] > departure.isoformat()):
            raise ValueError("Các chặng không nối tiếp hợp lệ")
        parsed.append({"originAirport": origin, "destinationAirport": destination, "flightNumber": number,
                       "airline": text_at(leg, "timeline_leg_info_carrier") or None,
                       "departureAt": departure.isoformat(), "arrivalAt": arrival.isoformat(),
                       "timezone": "Asia/Ho_Chi_Minh", "cabinText": number_class[1] if len(number_class) > 1 else None,
                       "durationMinutes": int((arrival - departure).total_seconds() / 60)})
    if (parsed[0]["originAirport"] != ctx["originAirport"] or parsed[-1]["destinationAirport"] != ctx["destinationAirport"]
            or parsed[0]["departureAt"][:10] != ctx["departureDate"]):
        raise ValueError("Kết quả không khớp sân bay/ngày được yêu cầu")
    price_text = text_at(soup, "upt_price")
    price = money(price_text)
    observed = payload["observedAt"]
    if datetime.fromisoformat(observed.replace("Z", "+00:00")).tzinfo is None:
        raise ValueError("observedAt phải có timezone")
    baggage = [n.get_text(" ", strip=True) for n in soup.find_all(attrs={"data-testid": re.compile(r"^included_baggage_\d+$")})]
    service_key = ";".join(f"{s['originAirport']}-{s['destinationAirport']}:{s['flightNumber']}" for s in parsed)
    key = digest({"context": ctx, "legs": parsed, "baggage": baggage, "card": payload.get("cardText"),
                  "price": price, "url": clean_url(payload["url"])})
    return {"offerId": "booking:offer:" + key, "serviceKey": service_key,
            "source": "booking.com", "context": ctx, "segments": parsed,
            "departureAt": parsed[0]["departureAt"], "arrivalAt": parsed[-1]["arrivalAt"],
            "nonstop": len(parsed) == 1, "totalPrice": price, "currency": "VND",
            "priceUnit": "party_itinerary", "priceKind": "quote", "priceText": price_text,
            "taxesIncluded": True if "Includes taxes and fees" in payload.get("priceBreakdownText", "") else None,
            "includedBaggage": baggage, "fareAndExtrasText": text_at(soup, "flightdetails_ancillaries") or None,
            "cardText": payload.get("cardText"), "bookingUrl": clean_url(payload["url"]),
            "observedAt": observed, "availabilityStatus": "available", "evidenceKey": payload["evidenceKey"]}


@dataclass
class Options:
    browser: BrowserOptions
    routes: list[tuple[str, str]] = field(default_factory=list)
    dates: list[date] = field(default_factory=list)
    adults: int = 1
    cabin: str = "ECONOMY"
    delay: float = 4
    max_attempts: int = 3
    max_pages: int = 0
    limit: int | None = None
    discover_only: bool = False
    refresh: bool = False


def plan_jobs(state, opts):
    urls = [search_url(a, b, d, opts.adults, opts.cabin) for a, b in opts.routes for d in opts.dates]
    state.add_many(SOURCE, ((u, 50, {"destination": AIRPORT_CITIES[context_from_url(u)["destinationAirport"]]}) for u in urls))
    return urls


def in_scope(url, opts):
    ctx = context_from_url(url)
    return ((ctx["originAirport"], ctx["destinationAirport"]) in opts.routes
            and date.fromisoformat(ctx["departureDate"]) in opts.dates
            and ctx["adults"] == opts.adults and ctx["cabinClass"] == opts.cabin)


async def collect_page(page, session, url, cache, limiter, http):
    """Cache product-only fragments before parse; never press Continue/booking."""
    await limiter.wait(url)
    fetched = await session.fetch_html(page, url, READY)
    initial = BeautifulSoup(fetched.html, "lxml")
    content = initial.find(id="basiclayout") or initial.find("main")
    cache.write_json("initial-" + digest([url, now_iso()]), {
        "kind": "search_initial", "url": url, "finalUrl": clean_url(fetched.final_url),
        "observedAt": now_iso(), "title": fetched.title,
        "html": sanitize_fragment(str(content)) if content else "",
    })
    await page.locator(CARDS).first.wait_for(state="visible", timeout=45000)
    ctx = context_from_url(url)
    if context_from_url(page.url) != ctx:
        raise ValueError("Trang chuyển hướng sai context")
    cards = page.locator(CARDS)
    count = await cards.count()
    batch_time = now_iso()
    batch_key = "page-" + digest([url, batch_time])
    # Store the list fragments, not the complete signed-in page or tracking scripts.
    cache.write_json(batch_key, {"kind": "search", "url": url, "context": ctx, "observedAt": batch_time,
                               "cards": [sanitize_fragment(await cards.nth(i).inner_html()) for i in range(count)]})
    offers, errors = [], []
    for i in range(count):
        try:
            await limiter.wait(url)
            card_text = await cards.nth(i).inner_text()
            await cards.nth(i).get_by_test_id("flight_card_bound_select_flight").click()
            sheet = page.locator(DETAIL)
            await sheet.wait_for(state="visible", timeout=20000)
            await sheet.get_by_test_id("upt_price").wait_for(state="visible", timeout=20000)
            # Price/rules sometimes finish loading after the timeline.
            await page.get_by_role("button", name="Continue", exact=True).wait_for(state="visible", timeout=20000)
            detail_url = clean_url(page.url)
            observed = now_iso()
            key = "detail-" + digest([detail_url, observed, i])
            payload = {"kind": "detail", "url": detail_url, "searchUrl": url, "context": ctx,
                       "observedAt": observed, "evidenceKey": key, "cardText": card_text,
                       "html": sanitize_fragment(await sheet.inner_html())}
            cache.write_json(key, payload)
            offers.append(parse_detail(payload))
        except ChallengeBlocked:
            raise
        except Exception as exc:
            errors.append(f"card {i}: {type(exc).__name__}: {str(exc)[:180]}")
        finally:
            if await page.locator(DETAIL).is_visible():
                await page.get_by_role("button", name="Close", exact=True).click()
                await page.locator(DETAIL).wait_for(state="hidden", timeout=10000)
    next_button = page.get_by_role("button", name="Next", exact=True)
    has_next = await next_button.count() > 0 and await next_button.is_enabled()
    record = {"recordType": "booking_flight_search", "source": SOURCE, "key": "search:" + digest(url),
            "url": url, "context": ctx, "crawledAt": batch_time, "offers": offers,
            "cardsSeen": count, "errors": errors, "hasNextPage": has_next,
            "pageComplete": bool(count) and not errors,
            "availabilityStatus": "available" if offers else "unknown"}
    cache.write_json("result-" + digest([url, batch_time]), record)
    return record


async def run(paths, opts):
    state = StateDB(paths)
    cache = RawCache(paths, SOURCE)
    limiter = HostRateLimiter(max(opts.delay, 1))
    http = Http(limiter)
    result = {"done": 0, "failed": 0, "offers": 0, "limited": False}
    try:
        urls = plan_jobs(state, opts)
        if opts.refresh:
            # Only reset this request scope, including already discovered pages.
            selected = [u for u, _, _ in state.urls_with_plan(SOURCE) if in_scope(u, opts)]
            state.conn.executemany("UPDATE items SET status='pending', attempts=0 WHERE source=? AND url=?", [(SOURCE, u) for u in selected])
            state.conn.commit()
        if opts.discover_only:
            return {"plannedSearches": len(urls), **state.counts(SOURCE).get(SOURCE, {})}
        browser_opts = replace(opts.browser, fast=False)
        async with BrowserSession(paths, SOURCE, browser_opts) as session:
            page = await session.new_page()
            attempted = set()
            with JsonlWriter(paths.interim / f"{SOURCE}.jsonl", "a") as writer:
                while True:
                    pending = [u for u in state.pending(SOURCE, opts.max_attempts) if in_scope(u, opts) and u not in attempted]
                    if not pending:
                        break
                    if opts.limit and len(attempted) >= opts.limit:
                        result["limited"] = True
                        break
                    url = pending[0]
                    attempted.add(url)
                    page_no = int(parse_qs(urlsplit(url).query)["page"][0])
                    if opts.max_pages and page_no > opts.max_pages:
                        result["limited"] = True
                        continue
                    if not await http.robots.allowed(url):
                        state.mark(SOURCE, url, "skipped", "robots.txt")
                        result["skipped"] = result.get("skipped", 0) + 1
                        continue
                    try:
                        rec = await collect_page(page, session, url, cache, limiter, http)
                        rec["plan"] = state.plan_of(SOURCE, url)
                        writer.write(rec)
                        status = "done" if rec["pageComplete"] else "failed"
                        state.mark(SOURCE, url, status, "; ".join(rec["errors"]) or None, {"fetchedAt": rec["crawledAt"]})
                        result[status] += 1
                        result["offers"] += len(rec["offers"])
                        if rec["hasNextPage"]:
                            ctx = rec["context"]
                            next_url = search_url(ctx["originAirport"], ctx["destinationAirport"], ctx["departureDate"], opts.adults, opts.cabin, page_no + 1)
                            state.add_many(SOURCE, [(next_url, 50, rec["plan"])])
                        log.info("Booking flight %s page %d: %d/%d offers, %s", rec["context"], page_no, len(rec["offers"]), rec["cardsSeen"], status)
                    except ChallengeBlocked as exc:
                        state.mark(SOURCE, url, "blocked", str(exc))
                        result["stopped"] = "blocked"
                        break
                    except Exception as exc:
                        state.mark(SOURCE, url, "failed", f"{type(exc).__name__}: {str(exc)[:240]}")
                        result["failed"] += 1
                        log.warning("Booking flight failed: %s", str(exc)[:240])
        result["queue"] = state.counts(SOURCE).get(SOURCE, {})
        report = paths.data / "booking-flights-status.json"
        report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result
    finally:
        state.close()
        await http.close()


def reparse(paths):
    """Rebuild complete page observations from manifests and raw detail evidence."""
    cache = RawCache(paths, SOURCE)
    records = []
    failures = 0
    for path in sorted((cache.dir / "json").glob("result-*.json.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            record = json.load(fh)
        offers = []
        for old in record["offers"]:
            try:
                offers.append(parse_detail(cache.read_json(old["evidenceKey"])))
            except (ValueError, KeyError, TypeError):
                failures += 1
                # A parser regression must not silently replace a good catalog.
        record["offers"] = offers
        record["plan"] = {"destination": AIRPORT_CITIES[record["context"]["destinationAirport"]]}
        records.append(record)
    out = paths.interim / f"{SOURCE}.jsonl"
    if not records or failures:
        return {"reparsed": 0, "failed": failures}
    tmp = out.with_suffix(".jsonl.tmp")
    with JsonlWriter(tmp, "w") as writer:
        for rec in sorted(records, key=lambda r: r["crawledAt"]):
            writer.write(rec)
    tmp.replace(out)
    return {"reparsed": sum(len(r["offers"]) for r in records), "failed": failures}
