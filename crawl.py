#!/usr/bin/env python3
"""Thu thập catalog du lịch cho V-OTA RecSys.

Ví dụ:
  python crawl.py vinpearl                         # khách sạn + hạng phòng + vé/tour/combo Vinpearl
  python crawl.py booking-hotels                   # toàn bộ chỗ ở VN trên booking.com (resume được)
  python crawl.py booking-hotels --limit 50        # chạy thử 50 trang
  python crawl.py booking-attractions              # vé tham quan VN trên booking.com
  python crawl.py all                              # cả ba nguồn, xong thì normalise
  python crawl.py status                           # tiến độ từng nguồn
  python crawl.py reparse booking-hotels           # parse lại từ cache, không fetch
  python normalise.py                              # xuất data/products.jsonl + products.csv

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

from collectors import booking_base, vinpearl
from collectors.booking_attractions import BookingAttractions
from collectors.booking_hotels import BookingHotels
from collectors.common import BrowserOptions, Paths, RunLock, StateDB, default_data_dir, setup_logging

log = logging.getLogger("crawler")

SOURCES = ("vinpearl", "booking-hotels", "booking-attractions")
EXIT_BLOCKED = 75  # bị chặn liên tiếp nên tự dừng: nghỉ vài giờ rồi chạy lại (xem run_forever.sh)


def _browser_opts(a: argparse.Namespace) -> BrowserOptions:
    return BrowserOptions(
        headless=a.headless,
        block_resources=not a.load_images,
        fast=getattr(a, "fast", False),
        challenge_timeout=a.challenge_timeout,
        manual_wait=0 if a.headless else a.manual_wait,
        channel=a.browser_channel,
    )


def _crawl_opts(a: argparse.Namespace, default_delay: float) -> booking_base.CrawlOptions:
    return booking_base.CrawlOptions(
        browser=_browser_opts(a),
        delay=a.delay if a.delay is not None else default_delay,
        concurrency=a.concurrency,
        limit=a.limit,
        match=a.match,
        max_attempts=a.max_attempts,
        max_blocks=a.max_blocks,
        discover_only=a.discover_only,
        rediscover=a.rediscover,
        full_sitemap_scan=a.full_sitemap_scan,
        full_cache=a.full_cache,
    )


def _hotels_source(a: argparse.Namespace) -> BookingHotels:
    checkin = date.fromisoformat(a.checkin) if getattr(a, "checkin", None) else None
    if checkin is None and getattr(a, "checkin_offset_days", None) is not None:
        checkin = date.today() + timedelta(days=a.checkin_offset_days)
    return BookingHotels(checkin=checkin, nights=getattr(a, "nights", 1), adults=getattr(a, "adults", 2))


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


async def cmd_booking(paths: Paths, a: argparse.Namespace, which: str) -> dict:
    state = StateDB(paths)
    try:
        if which == "booking-hotels":
            src = _hotels_source(a)
            log.info("Giá lấy cho %s → +%d đêm, %d người lớn (VND)", src.checkin, src.nights, src.adults)
            opts = _crawl_opts(a, 3.0)
        else:
            src = BookingAttractions()
            opts = _crawl_opts(a, 3.0)
        result = await booking_base.crawl(paths, src, opts, state)
        log.info("[%s] Trạng thái: %s", src.name, result)
        return result
    finally:
        state.close()


async def cmd_all(paths: Paths, a: argparse.Namespace) -> None:
    await cmd_vinpearl(paths, a)
    await cmd_booking(paths, a, "booking-hotels")
    await cmd_booking(paths, a, "booking-attractions")
    import normalise

    normalise.main(["--data-dir", str(paths.data)])


def cmd_status(paths: Paths) -> None:
    state = StateDB(paths)
    counts = state.counts()
    state.close()
    if not counts:
        print("Chưa có dữ liệu trạng thái. Chạy một nguồn trước, ví dụ: python crawl.py booking-hotels --discover-only")
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
        src = _hotels_source(a) if a.source == "booking-hotels" else BookingAttractions()
        await booking_base.reparse(paths, src, state)
    finally:
        state.close()


def cmd_retry_failed(paths: Paths, a: argparse.Namespace) -> None:
    name = a.source.replace("-", "_")
    state = StateDB(paths)
    n = state.reset_failed(name)
    state.close()
    print(f"Đã đưa {n} URL lỗi của {name} về hàng đợi.")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data-dir", type=Path, default=default_data_dir(), help="thư mục dữ liệu (mặc định ./data)")
    p.add_argument("-v", "--verbose", action="store_true")

    browser = argparse.ArgumentParser(add_help=False)
    g = browser.add_argument_group("trình duyệt")
    g.add_argument("--headless", action="store_true", help="không mở cửa sổ trình duyệt (dễ bị chặn hơn)")
    g.add_argument("--browser-channel", default=None, help="vd. 'chrome' để dùng Google Chrome đã cài thay cho Chromium")
    g.add_argument("--load-images", action="store_true", help="tải cả ảnh/font (mặc định chặn cho nhẹ)")
    g.add_argument("--challenge-timeout", type=float, default=45.0, help="số giây chờ trang thử thách tự qua")
    g.add_argument("--manual-wait", type=float, default=300.0, help="số giây chờ bạn tự xử lý trong cửa sổ trình duyệt")
    g.add_argument("--delay", type=float, default=None, help="giây tối thiểu giữa 2 request cùng host (vinpearl 2, booking 3)")
    g.add_argument("--max-blocks", type=int, default=8, help="bị chặn liên tiếp bấy nhiêu lần thì dừng")
    g.add_argument("--fast", action="store_true", help="không chờ trang tải xong, chặn CSS/tracker (nhanh hơn, dữ liệu như cũ)")

    crawl = argparse.ArgumentParser(add_help=False)
    c = crawl.add_argument_group("crawl booking.com")
    c.add_argument("--limit", type=int, default=None, help="chỉ crawl N URL trong lượt này")
    c.add_argument("--match", default=None, help="regex lọc URL, vd. 'nha-trang|phu-quoc'")
    c.add_argument("--concurrency", type=int, default=1, help="số tab song song (vẫn chung giới hạn --delay)")
    c.add_argument("--max-attempts", type=int, default=3, help="số lần thử tối đa cho mỗi URL lỗi")
    c.add_argument("--discover-only", action="store_true", help="chỉ đọc sitemap và xếp hàng URL")
    c.add_argument("--rediscover", action="store_true", help="tải lại sitemap để thêm URL mới")
    c.add_argument("--full-sitemap-scan", action="store_true", help="quét mọi file sitemap thay vì dừng sau vùng VN")
    c.add_argument("--full-cache", action="store_true", help="lưu nguyên HTML (~450KB/trang) thay vì bản gọn (~45KB)")

    dates = argparse.ArgumentParser(add_help=False)
    d = dates.add_argument_group("giá phòng")
    d.add_argument("--checkin", default=None, help="ngày nhận phòng YYYY-MM-DD (mặc định hôm nay + 30 ngày)")
    d.add_argument("--checkin-offset-days", type=int, default=None, help="nhận phòng sau N ngày kể từ hôm nay")
    d.add_argument("--nights", type=int, default=1)
    d.add_argument("--adults", type=int, default=2)

    sub = p.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("vinpearl", parents=[browser], help="vinpearl.com + booking.vinpearl.com")
    v.add_argument("--refresh", action="store_true", help="bỏ qua cache, tải lại toàn bộ")
    v.add_argument("--skip-hotels", action="store_true")
    v.add_argument("--skip-tours", action="store_true")
    v.add_argument("--tour-limit", type=int, default=None, help="chỉ lấy chi tiết N tour đầu (chạy thử)")
    v.add_argument(
        "--price-dates", default=None,
        help="ngày hỏi giá phòng, cách nhau dấu phẩy: YYYY-MM-DD hoặc số ngày từ hôm nay (mặc định 30,14,60)",
    )
    v.add_argument("--adults", type=int, default=2)
    v.add_argument(
        "--site-pages", action="store_true",
        help="bổ sung trang vinpearl.com (Cloudflare – có thể phải tự xác minh trong cửa sổ trình duyệt)",
    )

    sub.add_parser("booking-hotels", parents=[browser, crawl, dates], help="chỗ ở tại Việt Nam trên booking.com")
    sub.add_parser("booking-attractions", parents=[browser, crawl], help="vé tham quan tại Việt Nam trên booking.com")
    sub.add_parser("all", parents=[browser, crawl, dates], help="chạy cả ba nguồn rồi normalise")
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
        elif a.cmd in ("booking-hotels", "booking-attractions"):
            with RunLock(paths, a.cmd.replace("-", "_")):
                result = asyncio.run(cmd_booking(paths, a, a.cmd))
        elif a.cmd == "all":
            with RunLock(paths, "vinpearl"), RunLock(paths, "booking_hotels"), RunLock(paths, "booking_attractions"):
                asyncio.run(cmd_all(paths, a))
        elif a.cmd == "status":
            cmd_status(paths)
        elif a.cmd == "reparse":
            with RunLock(paths, a.source.replace("-", "_")):
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
