"""Khung crawl bằng trình duyệt, dùng chung cho booking.com và agoda.com.

Luồng: tìm URL (theo kế hoạch điểm đến, hoặc sitemap nếu --all-vietnam) → hàng đợi SQLite → worker Chromium
→ xoá dữ liệu về người (review) → cache raw → parse → interim JSONL. Dừng/chạy tiếp được, parse lại được.
"""

from __future__ import annotations

import asyncio
import gzip
import logging
import re
from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

from .common import (
    BlockBreaker,
    BrowserOptions,
    BrowserSession,
    ChallengeBlocked,
    FetchResult,
    HostRateLimiter,
    Http,
    JsonlWriter,
    PageGone,
    Paths,
    Progress,
    RawCache,
    StateDB,
    looks_like_challenge,
    now_iso,
    slim_html,
    strip_elements,
)
from .plan import DEFAULT_BUDGET, DESTINATIONS, Budget, Destination

log = logging.getLogger("crawler.browser")

SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


@dataclass
class CrawlOptions:
    browser: BrowserOptions
    delay: float = 3.0
    concurrency: int = 1
    limit: int | None = None
    match: str | None = None
    max_attempts: int = 3
    max_blocks: int = 8
    discover_only: bool = False
    rediscover: bool = False
    full_sitemap_scan: bool = False
    full_cache: bool = False
    all_vietnam: bool = False
    destinations: tuple[Destination, ...] = DESTINATIONS
    budget: Budget = field(default_factory=lambda: DEFAULT_BUDGET)


class SitemapSource:
    """Mô tả một nguồn. Lớp con định nghĩa cách tìm URL, URL thực mở, selector chờ và parser."""

    name: str = ""
    sitemap_index: str = ""
    ready_selector: str = "h1"
    expect_url: re.Pattern | None = None
    people_selectors: tuple[str, ...] = ()  # khối review / tên người đánh giá: xoá trước khi cache
    error_markers: tuple[str, ...] = (
        "Xin lỗi. Có lỗi xuất hiện",
        "Sorry, something went wrong",
        "Đã xảy ra lỗi",
    )

    # -- tìm URL
    def uses_sitemap(self, opts: CrawlOptions) -> bool:
        return bool(self.sitemap_index)

    async def discover_plan(self, ctx: "DiscoverContext") -> int:
        """Tìm URL theo kế hoạch điểm đến bằng trình duyệt. Mặc định: không có."""
        return 0

    def chunk_filter(self, loc: str) -> bool:
        return False

    def product_urls(self, locs: list[str]) -> list[str]:
        return []

    def priority(self, url: str) -> int:
        return 100

    def chunk_order(self, chunks: list[str]) -> list[str]:
        return chunks

    def stop_scan(self, locs: list[str], found: int) -> bool:
        return False

    # -- crawl
    def fetch_url(self, url: str) -> tuple[str, dict]:
        """URL thực sự mở (thêm tham số ngày, tiền tệ...) và meta cần cho reparse."""
        return url, {}

    def parse(self, html: str, url: str, meta: dict) -> dict | None:
        raise NotImplementedError

    def is_error_page(self, html: str) -> bool:
        head = html[:300_000]
        return any(m in head for m in self.error_markers) and self.ready_selector_missing(html)

    def ready_selector_missing(self, html: str) -> bool:
        return True

    def needs_refetch(self, html: str, final_url: str) -> bool:
        """True nếu trang về thiếu tham số (vd. trang thử thách chuyển hướng làm mất ngày) → mở lại một lần."""
        return False

    def sanitize(self, html: str, full_cache: bool) -> str:
        html = strip_elements(html, self.people_selectors)
        return html if full_cache else slim_html(html)


@dataclass
class DiscoverContext:
    paths: Paths
    src: SitemapSource
    opts: CrawlOptions
    state: StateDB
    cache: RawCache
    session: BrowserSession
    page: object
    limiter: HostRateLimiter
    http: Http

    async def open(self, url: str, ready: str) -> FetchResult | None:
        if not await self.http.robots.allowed(url):
            log.warning("[%s] robots.txt không cho phép %s", self.src.name, url)
            return None
        await self.limiter.wait(url)
        try:
            return await self.session.fetch_html(self.page, url, ready, error_markers=self.src.error_markers)
        except (ChallengeBlocked, PageGone) as e:
            log.warning("[%s] không mở được %s: %s", self.src.name, url, e)
            return None

    def done(self, key: str) -> bool:
        return not self.opts.rediscover and self.state.is_discovered(self.src.name, key)

    def mark_done(self, key: str, found: int) -> None:
        self.state.mark_discovered(self.src.name, key, found)


# ---------------------------------------------------------------------- sitemap discovery


async def discover_sitemap(paths: Paths, src: SitemapSource, opts: CrawlOptions, state: StateDB) -> int:
    cache = RawCache(paths, src.name)
    limiter = HostRateLimiter(max(1.0, opts.delay / 2))
    http = Http(limiter)
    added = 0
    try:
        index_xml = cache.read("sitemap-index", "xml")
        if index_xml is None or opts.rediscover:
            r = await http.get(src.sitemap_index)
            r.raise_for_status()
            index_xml = r.text
            cache.write("sitemap-index", "xml", index_xml)
        chunks = src.chunk_order([loc for loc in _locs(index_xml) if src.chunk_filter(loc)])
        log.info("[%s] %d file sitemap phù hợp", src.name, len(chunks))
        found = 0
        for n, chunk in enumerate(chunks, 1):
            key = chunk.rsplit("/", 1)[-1]
            body = cache.read_bytes(key, "xmlgz")
            if body is None or opts.rediscover:
                r = await http.get(chunk)
                if r.status_code != 200:
                    log.warning("[%s] sitemap %s trả %s", src.name, chunk, r.status_code)
                    continue
                body = r.content
                cache.write_bytes(key, "xmlgz", body)
            locs = _locs(_maybe_gunzip(body))
            urls = src.product_urls(locs)
            if urls:
                found += len(urls)
                added += state.add_many(src.name, ((u, src.priority(u)) for u in urls))
            log.info("[%s] sitemap %d/%d: %d URL phù hợp (tổng %d)", src.name, n, len(chunks), len(urls), found)
            if not opts.full_sitemap_scan and src.stop_scan(locs, found):
                log.info("[%s] Đã qua vùng dữ liệu Việt Nam trong sitemap – dừng quét", src.name)
                break
    finally:
        await http.close()
    return added


def _maybe_gunzip(body: bytes) -> str:
    if body[:2] == b"\x1f\x8b":
        body = gzip.decompress(body)
    return body.decode("utf-8", errors="replace")


def _locs(xml_text: str) -> list[str]:
    try:
        root = ET.fromstring(xml_text.encode("utf-8"))
        return [el.text.strip() for el in root.iter(f"{SITEMAP_NS}loc") if el.text]
    except ET.ParseError:
        return re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml_text)


# ---------------------------------------------------------------------- crawl


async def crawl(paths: Paths, src: SitemapSource, opts: CrawlOptions, state: StateDB) -> dict:
    if src.uses_sitemap(opts) and (opts.rediscover or not state.counts(src.name).get(src.name)):
        await discover_sitemap(paths, src, opts, state)

    cache = RawCache(paths, src.name)
    limiter = HostRateLimiter(opts.delay)
    http = Http(limiter)  # robots.txt
    breaker = BlockBreaker(opts.max_blocks)
    try:
        async with BrowserSession(paths, src.name, opts.browser) as session:
            ctx = DiscoverContext(paths, src, opts, state, cache, session, await session.new_page(), limiter, http)
            found = await src.discover_plan(ctx)
            if found:
                log.info("[%s] Kế hoạch: đã xếp hàng %d URL", src.name, found)
            if opts.discover_only:
                return state.counts(src.name).get(src.name, {})

            urls = state.pending(src.name, opts.max_attempts)
            if opts.match:
                rx = re.compile(opts.match, re.I)
                urls = [u for u in urls if rx.search(u)]
            if opts.limit:
                urls = urls[: opts.limit]
            if not urls:
                log.info("[%s] Không còn URL nào cần crawl. Trạng thái: %s", src.name, state.counts(src.name).get(src.name))
                return state.counts(src.name).get(src.name, {})

            result = await _run_queue(paths, src, opts, state, cache, session, ctx.page, limiter, http, breaker, urls)
    finally:
        await http.close()
    if breaker.tripped:
        result["stopped"] = "blocked"
    return result


async def _run_queue(paths, src, opts, state, cache, session, first_page, limiter, http, breaker, urls) -> dict:
    progress = Progress(src.name, len(urls))
    refetch = {"enabled": True, "misses": 0}
    queue: asyncio.Queue[str] = asyncio.Queue()
    for u in urls:
        queue.put_nowait(u)
    log.info(
        "[%s] Bắt đầu %d URL · %d worker · tối thiểu %.1fs/request",
        src.name, len(urls), opts.concurrency, opts.delay,
    )

    with JsonlWriter(paths.interim / f"{src.name}.jsonl", "a") as writer:

        async def fetch(page, target):
            res = await session.fetch_html(page, target, src.ready_selector, src.expect_url, error_markers=src.error_markers)
            if refetch["enabled"] and src.needs_refetch(res.html, res.final_url):
                await limiter.wait(target)
                res = await session.fetch_html(page, target, src.ready_selector, src.expect_url, error_markers=src.error_markers)
                if src.needs_refetch(res.html, res.final_url):
                    refetch["misses"] += 1
                    if refetch["misses"] >= 3:
                        refetch["enabled"] = False
                        log.warning(
                            "[%s] Trang về không kèm ngày/giá dù đã mở lại (thường gặp ở --headless). "
                            "Tiếp tục lấy dữ liệu không giá; muốn có giá hãy chạy không --headless.", src.name,
                        )
                else:
                    refetch["misses"] = 0
            return res

        async def worker(wid: int) -> None:
            page = first_page if wid == 0 else await session.context.new_page()
            navigations = 0
            while not breaker.tripped:
                try:
                    url = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                if not await http.robots.allowed(url):
                    state.mark(src.name, url, "skipped", "robots.txt")
                    progress.tick("skipped")
                    continue
                target, meta = src.fetch_url(url)
                if navigations and navigations % opts.browser.pages_before_recycle == 0:
                    try:
                        await page.close()
                    except Exception:
                        pass
                    page = await session.context.new_page()
                await limiter.wait(target)
                navigations += 1
                try:
                    res = await fetch(page, target)
                except PageGone as e:
                    state.mark(src.name, url, "gone", str(e))
                    progress.tick("skipped")
                    breaker.ok()
                    continue
                except ChallengeBlocked as e:
                    state.mark(src.name, url, "blocked", str(e))
                    progress.tick("failed")
                    if breaker.blocked():
                        log.error(
                            "[%s] Bị chặn %d lần liên tiếp – dừng lượt chạy. Tiến độ đã lưu; nghỉ vài giờ rồi chạy lại "
                            "cùng lệnh (có thể tăng --delay).", src.name, breaker.streak,
                        )
                        return
                    wait = breaker.cooldown()
                    log.warning("[%s] Bị chặn (%d liên tiếp) – nghỉ %.0fs", src.name, breaker.streak, wait)
                    limiter.penalise(target, wait)
                    continue
                except Exception as e:  # lỗi mạng, timeout, trang crash
                    state.mark(src.name, url, "failed", f"{type(e).__name__}: {e}")
                    progress.tick("failed")
                    (log.warning if progress.failed <= 5 else log.debug)("[%s] lỗi %s: %s", src.name, url, str(e)[:300])
                    if "has been closed" in str(e):
                        try:
                            page = await session.context.new_page()
                        except Exception:
                            log.error("[%s] Trình duyệt đã đóng – dừng. Chạy lại cùng lệnh để tiếp tục.", src.name)
                            breaker.tripped = True
                            return
                    continue
                breaker.ok()
                if src.is_error_page(res.html):
                    state.mark(src.name, url, "failed", "trang lỗi tạm thời của website – sẽ thử lại")
                    progress.tick("failed")
                    limiter.penalise(target, 20)
                    continue
                stored = src.sanitize(res.html, opts.full_cache)
                cache.write(url, "html", stored)
                meta = {**meta, "fetchedUrl": target, "finalUrl": res.final_url, "fetchedAt": now_iso()}
                try:
                    record = src.parse(stored, url, meta)
                except Exception as e:
                    log.exception("[%s] parser lỗi %s", src.name, url)
                    state.mark(src.name, url, "failed", f"parse: {e}", meta)
                    progress.tick("failed")
                    continue
                if not record:
                    state.mark(src.name, url, "failed", "parse: không tìm thấy tên sản phẩm", meta)
                    progress.tick("failed")
                    continue
                plan = state.plan_of(src.name, url)
                if plan:
                    record["plan"] = plan
                writer.write(record)
                state.mark(src.name, url, "done", None, meta)
                progress.tick("done")

        async def run_workers() -> None:
            tasks = [asyncio.create_task(worker(i)) for i in range(max(1, opts.concurrency))]
            try:
                await asyncio.gather(*tasks)
            except (asyncio.CancelledError, KeyboardInterrupt):
                for t in tasks:
                    t.cancel()
                raise

        try:
            await run_workers()
            # Một lượt thử lại ngay cho URL lỗi tạm thời (mạng, timeout, trang lỗi) của chính lượt này
            url_set = set(urls)
            again = [u for u in state.pending(src.name, opts.max_attempts) if u in url_set]
            if again and not breaker.tripped:
                log.info("[%s] Thử lại %d URL lỗi trong lượt này", src.name, len(again))
                progress.total += len(again)
                for u in again:
                    queue.put_nowait(u)
                await run_workers()
        finally:
            progress.report()
    return state.counts(src.name).get(src.name, {})


async def reparse(paths: Paths, src: SitemapSource, state: StateDB) -> int:
    cache = RawCache(paths, src.name)
    out = paths.interim / f"{src.name}.jsonl"
    tmp = out.with_suffix(".jsonl.tmp")
    n = 0
    with JsonlWriter(tmp, "w") as writer:
        for url, meta in state.done_items(src.name):
            html = cache.read(url, "html")
            if html is None or looks_like_challenge(html):
                continue
            try:
                rec = src.parse(html, url, meta)
            except Exception:
                log.exception("[%s] parser lỗi %s", src.name, url)
                continue
            if rec:
                plan = state.plan_of(src.name, url)
                if plan:
                    rec["plan"] = plan
                writer.write(rec)
                n += 1
    tmp.replace(out)
    log.info("[%s] Parse lại %d trang từ cache → %s", src.name, n, out)
    return n
