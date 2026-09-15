#!/usr/bin/env python3
"""Thu thập catalog du lịch cho V-OTA RecSys, theo handbook §3.

Chạy trọn kế hoạch (15 điểm đến, ~2.000–5.000 sản phẩm, vài giờ):
  python crawl.py handbook

Hoặc từng nguồn:
  python crawl.py vinpearl              # khách sạn + hạng phòng + vé/tour/combo/golf Vinpearl
  python crawl.py trip-flights          # vé máy bay nội địa giữa các điểm đến (trip.com)
  python crawl.py trip-attractions      # điểm tham quan: giờ mở cửa, thời lượng, toạ độ (trip.com)
  python crawl.py booking-hotels        # N khách sạn phổ biến mỗi điểm đến + hạng phòng + giá (booking.com)
  python crawl.py agoda-hotels          # N khách sạn phổ biến mỗi điểm đến + giá (agoda.com)
  python crawl.py venues                # toạ độ địa điểm vé/combo/golf Vinpearl → collectors/venues.csv
  python normalise.py                   # → data/products.jsonl, products.csv, stats.md, map/ (Google My Maps, GeoJSON)

Tiện ích:
  python crawl.py status                # tiến độ từng nguồn
  python crawl.py reparse booking-hotels
  python crawl.py retry-failed agoda-hotels

Dừng bất kỳ lúc nào bằng Ctrl+C; chạy lại đúng lệnh đó để tiếp tục.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import re
import sys
from datetime import date, timedelta
from pathlib import Path

from collectors import booking_base, trip, venues, vinpearl
from collectors.agoda_hotels import AgodaHotels
from collectors.booking_attractions import BookingAttractions
from collectors.booking_hotels import BookingHotels
from collectors.common import BrowserOptions, Paths, RunLock, StateDB, default_data_dir, setup_logging
from collectors.plan import budget_with, select_destinations

log = logging.getLogger("crawler")

BROWSER_SOURCES = ("booking-hotels", "agoda-hotels", "booking-attractions")
TRIP_SOURCES = ("trip-flights", "trip-attractions")
SOURCES = ("vinpearl",) + TRIP_SOURCES + BROWSER_SOURCES
EXIT_BLOCKED = 75  # bị chặn liên tiếp nên tự dừng: nghỉ vài giờ rồi chạy lại (xem run_forever.sh)


def _name(cmd: str) -> str:
    return cmd.replace("-", "_")


def _browser_opts(a: argparse.Namespace) -> BrowserOptions:
    return BrowserOptions(
        headless=a.headless,
        block_resources=not a.load_images,
        fast=getattr(a, "fast", False),
        challenge_timeout=a.challenge_timeout,
        manual_wait=0 if a.headless else a.manual_wait,
        channel=a.browser_channel,
    )


def _plan(a: argparse.Namespace):
    return select_destinations(getattr(a, "destinations", None)), budget_with(getattr(a, "per_destination", None))


def _crawl_opts(a: argparse.Namespace, default_delay: float) -> booking_base.CrawlOptions:
    destinations, budget = _plan(a)
    return booking_base.CrawlOptions(
        browser=_browser_opts(a),
        delay=a.delay if a.delay is not None else default_delay,
        concurrency=getattr(a, "concurrency", 1),
        limit=getattr(a, "limit", None),
        match=getattr(a, "match", None),
        max_attempts=getattr(a, "max_attempts", 3),
        max_blocks=a.max_blocks,
        discover_only=getattr(a, "discover_only", False),
        rediscover=getattr(a, "rediscover", False),
        full_sitemap_scan=getattr(a, "full_sitemap_scan", False),
        full_cache=getattr(a, "full_cache", False),
        all_vietnam=getattr(a, "all_vietnam", False),
        destinations=destinations,
        budget=budget,
    )


def _checkin(a: argparse.Namespace) -> date | None:
    if getattr(a, "checkin", None):
        return date.fromisoformat(a.checkin)
    if getattr(a, "checkin_offset_days", None) is not None:
        return date.today() + timedelta(days=a.checkin_offset_days)
    return None


def _browser_source(which: str, a: argparse.Namespace):
    if which == "booking-hotels":
        return BookingHotels(checkin=_checkin(a), nights=getattr(a, "nights", 1), adults=getattr(a, "adults", 2),
                             all_vietnam=getattr(a, "all_vietnam", False))
    if which == "agoda-hotels":
        return AgodaHotels(checkin=_checkin(a), nights=getattr(a, "nights", 1), adults=getattr(a, "adults", 2))
    return BookingAttractions()


def _price_dates(a: argparse.Namespace) -> list[date]:
    raw = getattr(a, "price_dates", None)
    if not raw:
        return vinpearl.default_price_dates()
    out = []
    for part in raw.split(","):
        part = part.strip()
        if re.fullmatch(r"\+?\d+", part):
            out.append(date.today() + timedelta(days=int(part)))
        elif part:
            out.append(date.fromisoformat(part))
    return out


async def cmd_vinpearl(paths: Paths, a: argparse.Namespace, offline: bool = False) -> dict:
    opts = vinpearl.VinpearlOptions(
        browser=_browser_opts(a),
        delay=a.delay if a.delay is not None else 2.0,
        refresh=getattr(a, "refresh", False),
        offline=offline,
        skip_hotels=getattr(a, "skip_hotels", False),
        skip_tours=getattr(a, "skip_tours", False),
        tour_limit=getattr(a, "tour_limit", None),
        max_blocks=a.max_blocks,
        price_dates=_price_dates(a),
        adults=getattr(a, "adults", 2),
        site_pages=getattr(a, "site_pages", False),
    )
    stats = await vinpearl.run(paths, opts)
    log.info("Vinpearl: %s", stats)
    return stats


async def cmd_browser(paths: Paths, a: argparse.Namespace, which: str) -> dict:
    state = StateDB(paths)
    try:
        src = _browser_source(which, a)
        if hasattr(src, "checkin"):
            log.info("[%s] Giá lấy cho %s, %d đêm, %d người lớn (VND)", src.name, src.checkin, src.nights, src.adults)
        result = await booking_base.crawl(paths, src, _crawl_opts(a, 3.0), state)
        log.info("[%s] Trạng thái: %s", src.name, result)
        return result
    finally:
        state.close()


async def cmd_trip(paths: Paths, a: argparse.Namespace, which: str) -> dict:
    destinations, budget = _plan(a)
    opts = trip.TripOptions(
        delay=a.delay if a.delay is not None else 2.5,
        limit=getattr(a, "limit", None),
        max_attempts=getattr(a, "max_attempts", 3),
        max_blocks=a.max_blocks,
        rediscover=getattr(a, "rediscover", False),
        discover_only=getattr(a, "discover_only", False),
        destinations=destinations,
        budget=budget,
    )
    state = StateDB(paths)
    try:
        result = await trip.run(paths, _name(which), opts, state)
        log.info("[%s] Trạng thái: %s", _name(which), result)
        return result
    finally:
        state.close()


def cmd_handbook(paths: Paths, a: argparse.Namespace) -> dict:
    """Chạy trọn kế hoạch theo thứ tự handbook: Vinpearl trước, rồi các OTA, cuối cùng normalise."""
    stopped = {}
    steps = [("vinpearl", lambda: cmd_vinpearl(paths, a))]
    steps += [(s, (lambda s=s: cmd_trip(paths, a, s))) for s in TRIP_SOURCES]
    steps += [(s, (lambda s=s: cmd_browser(paths, a, s))) for s in ("booking-hotels", "agoda-hotels")]
    for name, step in steps:
        log.info("===== %s =====", name)
        with RunLock(paths, _name(name)):
            result = asyncio.run(step())
        if isinstance(result, dict) and result.get("stopped") == "blocked":
            stopped[name] = "blocked"
            log.warning("[%s] bị chặn và đã dừng – chạy tiếp các nguồn khác; chạy lại lệnh sau để hoàn tất.", name)
    log.info("===== venues =====")
    try:  # chỉ gọi mạng cho địa điểm chưa có toạ độ; lỗi thì normalise vẫn chạy với bảng hiện có
        asyncio.run(venues.run(paths))
    except Exception as e:
        log.warning("Không cập nhật được toạ độ địa điểm Vinpearl: %s", str(e)[:200])
    import normalise

    normalise.main(["--data-dir", str(paths.data)])
    return {"stopped": "blocked"} if stopped else {}


def cmd_status(paths: Paths) -> None:
    state = StateDB(paths)
    counts = state.counts()
    state.close()
    if not counts:
        print("Chưa có dữ liệu trạng thái. Chạy thử: python crawl.py handbook --destinations 'Nha Trang' --per-destination 5")
    for src, c in sorted(counts.items()):
        total = sum(c.values())
        done = c.get("done", 0)
        pct = 100 * done / total if total else 0
        parts = " · ".join(f"{k} {v}" for k, v in sorted(c.items()))
        print(f"{src:22s} {done:>7d}/{total:<7d} ({pct:5.1f}%)  {parts}")
    for f in sorted(paths.interim.glob("*.jsonl")):
        with open(f, encoding="utf-8") as fh:
            n = sum(1 for line in fh if line.strip())
        print(f"interim/{f.name:28s} {n} bản ghi")


async def cmd_reparse(paths: Paths, a: argparse.Namespace) -> None:
    if a.source == "vinpearl":
        await cmd_vinpearl(paths, a, offline=True)
        return
    state = StateDB(paths)
    try:
        if a.source in TRIP_SOURCES:
            trip.reparse(paths, _name(a.source), state)
        else:
            await booking_base.reparse(paths, _browser_source(a.source, a), state)
    finally:
        state.close()


def cmd_retry_failed(paths: Paths, a: argparse.Namespace) -> None:
    state = StateDB(paths)
    n = state.reset_failed(_name(a.source))
    state.close()
    print(f"Đã đưa {n} URL lỗi của {_name(a.source)} về hàng đợi.")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data-dir", type=Path, default=default_data_dir(), help="thư mục dữ liệu (mặc định ./data)")
    p.add_argument("-v", "--verbose", action="store_true")

    browser = argparse.ArgumentParser(add_help=False)
    g = browser.add_argument_group("trình duyệt / tốc độ")
    g.add_argument("--headless", action="store_true", help="không mở cửa sổ trình duyệt (booking.com sẽ không có giá)")
    g.add_argument("--browser-channel", default=None, help="vd. 'chrome' để dùng Google Chrome đã cài thay cho Chromium")
    g.add_argument("--load-images", action="store_true", help="tải cả ảnh/font (mặc định chặn cho nhẹ)")
    g.add_argument("--challenge-timeout", type=float, default=45.0, help="số giây chờ trang thử thách tự qua")
    g.add_argument("--manual-wait", type=float, default=300.0, help="số giây chờ bạn tự xử lý trong cửa sổ trình duyệt")
    g.add_argument("--delay", type=float, default=None, help="giây tối thiểu giữa 2 request cùng host (vinpearl 2, trip 2.5, booking/agoda 3)")
    g.add_argument("--max-blocks", type=int, default=8, help="bị chặn liên tiếp bấy nhiêu lần thì dừng")
    g.add_argument("--fast", action="store_true", help="không chờ trang tải xong, chặn CSS/tracker (nhanh gấp đôi, dữ liệu như cũ)")

    plan = argparse.ArgumentParser(add_help=False)
    pl = plan.add_argument_group("kế hoạch (collectors/plan.py)")
    pl.add_argument("--destinations", default=None, help="chỉ các điểm đến này, vd. 'Nha Trang,Phú Quốc' (mặc định cả 15)")
    pl.add_argument("--per-destination", type=int, default=None, help="số khách sạn/điểm tham quan mỗi điểm đến (mặc định 30/20/25)")

    crawl = argparse.ArgumentParser(add_help=False)
    c = crawl.add_argument_group("hàng đợi")
    c.add_argument("--limit", type=int, default=None, help="chỉ crawl N URL trong lượt này")
    c.add_argument("--match", default=None, help="regex lọc URL, vd. 'vinpearl'")
    c.add_argument("--concurrency", type=int, default=1, help="số tab song song (vẫn chung giới hạn --delay)")
    c.add_argument("--max-attempts", type=int, default=3, help="số lần thử tối đa cho mỗi URL lỗi")
    c.add_argument("--discover-only", action="store_true", help="chỉ tìm URL và xếp hàng, chưa crawl")
    c.add_argument("--rediscover", action="store_true", help="tìm URL lại (sau khi đổi kế hoạch / muốn thêm sản phẩm mới)")
    c.add_argument("--full-cache", action="store_true", help="lưu nguyên HTML (~450KB/trang) thay vì bản gọn (~45KB)")

    dates = argparse.ArgumentParser(add_help=False)
    d = dates.add_argument_group("giá phòng")
    d.add_argument("--checkin", default=None, help="ngày nhận phòng YYYY-MM-DD (mặc định hôm nay + 30 ngày)")
    d.add_argument("--checkin-offset-days", type=int, default=None, help="nhận phòng sau N ngày kể từ hôm nay")
    d.add_argument("--nights", type=int, default=1)
    d.add_argument("--adults", type=int, default=2)

    sub = p.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("handbook", parents=[browser, plan, crawl, dates], help="chạy trọn kế hoạch handbook rồi normalise")
    h.add_argument("--price-dates", default=None, help="ngày hỏi giá phòng Vinpearl (xem lệnh vinpearl)")
    h.add_argument("--tour-limit", type=int, default=None, help="chỉ lấy chi tiết N tour Vinpearl đầu (chạy thử)")
    h.add_argument("--skip-tours", action="store_true", help="bỏ phần vé/tour Vinpearl")
    sub.add_parser("all", parents=[browser, plan, crawl, dates], help="tên cũ của handbook")

    v = sub.add_parser("vinpearl", parents=[browser], help="Vinpearl: khách sạn, hạng phòng, vé/tour/combo/golf")
    v.add_argument("--refresh", action="store_true", help="bỏ qua cache, tải lại toàn bộ")
    v.add_argument("--skip-hotels", action="store_true")
    v.add_argument("--skip-tours", action="store_true")
    v.add_argument("--tour-limit", type=int, default=None, help="chỉ lấy chi tiết N tour đầu (chạy thử)")
    v.add_argument("--price-dates", default=None, help="ngày hỏi giá phòng: YYYY-MM-DD hoặc số ngày từ hôm nay (mặc định 30,14,60)")
    v.add_argument("--adults", type=int, default=2)
    v.add_argument("--site-pages", action="store_true", help="bổ sung trang vinpearl.com (Cloudflare – có thể phải tự xác minh)")

    for s in TRIP_SOURCES:
        sub.add_parser(s, parents=[browser, plan, crawl], help=f"trip.com – {'vé máy bay' if s == 'trip-flights' else 'điểm tham quan'} (HTTP, không cần trình duyệt)")
    bh = sub.add_parser("booking-hotels", parents=[browser, plan, crawl, dates], help="booking.com – khách sạn theo điểm đến")
    bh.add_argument("--all-vietnam", action="store_true", help="thêm toàn bộ ~34.000 chỗ ở VN từ sitemap (không theo handbook)")
    bh.add_argument("--full-sitemap-scan", action="store_true", help="với --all-vietnam: quét mọi file sitemap")
    sub.add_parser("agoda-hotels", parents=[browser, plan, crawl, dates], help="agoda.com – khách sạn theo điểm đến")
    sub.add_parser("booking-attractions", parents=[browser, crawl], help="booking.com – vé tham quan (nguồn phụ, ngoài kế hoạch)")

    ve = sub.add_parser("venues", help="toạ độ địa điểm vé/combo/golf Vinpearl: trip.com → OpenStreetMap, ghi collectors/venues.csv")
    ve.add_argument("--refresh", action="store_true", help="tìm lại cả dòng auto/review (không bao giờ ghi đè dòng status=ok)")
    ve.add_argument("--only", default=None, help="chỉ các key này, cách nhau bằng dấu phẩy")
    ve.add_argument("--offline", action="store_true", help="không gọi mạng: chỉ dùng trip.com đã crawl + cache")

    sub.add_parser("status", help="xem tiến độ")
    r = sub.add_parser("reparse", parents=[browser, dates], help="parse lại từ cache raw")
    r.add_argument("source", choices=SOURCES)
    rf = sub.add_parser("retry-failed", help="đưa URL lỗi về hàng đợi")
    rf.add_argument("source", choices=SOURCES[1:])
    return p


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    paths = Paths(a.data_dir).ensure()
    setup_logging(paths, a.verbose)
    result = None
    try:
        if a.cmd == "vinpearl":
            with RunLock(paths, "vinpearl"):
                result = asyncio.run(cmd_vinpearl(paths, a))
        elif a.cmd in TRIP_SOURCES:
            with RunLock(paths, _name(a.cmd)):
                result = asyncio.run(cmd_trip(paths, a, a.cmd))
        elif a.cmd in BROWSER_SOURCES:
            with RunLock(paths, _name(a.cmd)):
                result = asyncio.run(cmd_browser(paths, a, a.cmd))
        elif a.cmd in ("handbook", "all"):
            result = cmd_handbook(paths, a)
        elif a.cmd == "venues":
            only = {k.strip() for k in a.only.split(",") if k.strip()} if a.only else None
            result = asyncio.run(venues.run(paths, refresh=a.refresh, only=only, offline=a.offline))
        elif a.cmd == "status":
            cmd_status(paths)
        elif a.cmd == "reparse":
            with RunLock(paths, _name(a.source)):
                asyncio.run(cmd_reparse(paths, a))
        elif a.cmd == "retry-failed":
            cmd_retry_failed(paths, a)
    except KeyboardInterrupt:
        log.warning("Đã dừng theo yêu cầu. Tiến độ đã lưu – chạy lại cùng lệnh để tiếp tục.")
        return 130
    if isinstance(result, dict) and result.get("stopped") == "blocked":
        return EXIT_BLOCKED
    return 0


if __name__ == "__main__":
    sys.exit(main())
