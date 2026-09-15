"""booking.com – hoạt động/vé tham quan tại Việt Nam (nguồn phụ, khoảng 13.500 URL).

Sitemap attraction không có bản tiếng Việt, nên lấy URL từ sitembk-attractions-en-gb.*.xml.gz,
lọc /attractions/vn/ và mở bản .vi.html. Phần giao diện là tiếng Việt, nhưng mô tả thường vẫn là
tiếng Anh do nhà cung cấp viết; normalise ghi lại ngôn ngữ mô tả để lọc khi cần.
"""

from __future__ import annotations

import re
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from .booking_base import SitemapSource
from .common import now_iso
from .textutil import (
    clean_text,
    detect_lang,
    first_float,
    first_int,
    fold,
    json_ld_blocks,
    meta_content,
    node_text,
    parse_price,
    uniq,
)

_CHUNK_RE = re.compile(r"sitembk-attractions-en-gb\.\d+\.xml\.gz$")
_URL_RE = re.compile(r"^https://www\.booking\.com/attractions/vn/([a-z0-9]+)-[^/]*?\.en-gb\.html$")


class BookingAttractions(SitemapSource):
    name = "booking_attractions"
    sitemap_index = "https://www.booking.com/sitembk-attractions-index.xml"
    ready_selector = "[data-testid='attr-content'], [data-testid='inline-ticket-config'], [data-testid='product-gallery']"
    expect_url = re.compile(r"/attractions/")
    people_selectors = ("[data-testid='review-card']", "[data-testid='reviews-list']", "[data-testid='review-item']")

    def __init__(self, currency: str = "VND"):
        self.currency = currency

    def chunk_filter(self, loc: str) -> bool:
        return bool(_CHUNK_RE.search(loc))

    def product_urls(self, locs: list[str]) -> list[str]:
        out = []
        for u in locs:
            if _URL_RE.match(u):
                out.append(u[: -len(".en-gb.html")] + ".vi.html")
        return out

    def priority(self, url: str) -> int:
        return 10 if re.search(r"vinwonders|vinpearl|safari|grand-world", url) else 100

    def ready_selector_missing(self, html: str) -> bool:
        return "attr-content" not in html

    def fetch_url(self, url: str) -> tuple[str, dict]:
        return f"{url}?{urlencode({'selected_currency': self.currency, 'lang': 'vi'})}", {"currency": self.currency}

    def parse(self, html: str, url: str, meta: dict) -> dict | None:
        return parse_attraction_html(html, url, meta)


def parse_attraction_html(html: str, url: str, meta: dict | None = None) -> dict | None:
    meta = meta or {}
    soup = BeautifulSoup(html, "lxml")
    name = node_text(soup.find("h1"))
    if not name:
        return None
    m = re.search(r"/attractions/vn/([a-z0-9]+)-", url)
    product_id = m.group(1) if m else url

    content = soup.select_one("[data-testid='attr-content']")
    sections = _split_sections(content)
    intro = sections.pop("", [])
    cancellation_lines = []
    while intro and re.match(r"^(Miễn phí hủy|Hủy miễn phí|Không hoàn tiền|Free cancellation|Non-refundable)", intro[0], re.I):
        cancellation_lines.append(intro.pop(0))
    duration = None
    body = []
    for line in intro:
        dm = re.match(r"^(?:Thời gian|Thời lượng|Duration)\s*:\s*(.+)$", line)
        if dm and duration is None:
            duration = dm.group(1).strip()
        else:
            body.append(line)
    content_text = "\n\n".join(body)
    cancellation = ". ".join(cancellation_lines) or None

    subtitle = ""
    h1 = soup.find("h1")
    if h1:
        for sib in h1.find_all_next(["p", "div"], limit=6):
            t = node_text(sib)
            if t and t != name and len(t) > 30 and "\n" not in t:
                subtitle = t
                break

    highlights = _pick(sections, "vì sao nên đến đây", "why you should go", "điểm nổi bật", "highlights")
    included = _pick(sections, "bao gồm", "includes", "what's included")
    excluded = [x for x in _pick(sections, "không bao gồm những gì", "không bao gồm", "not included") if fold(x) != "khong bao gom"]
    additional = [x for x in _pick(sections, "thông tin thêm", "additional info") if fold(x) not in ("xem them", "show more")]
    accessibility = _pick(sections, "hỗ trợ cho người đi lại khó khăn", "accessibility")
    languages = _pick(sections, "tour có hướng dẫn bằng ngôn ngữ bạn chọn", "live tour guide")
    meeting_points = uniq(sections.get("first:điểm khởi hành") or sections.get("first:meeting point") or [])[:5]
    end_points = uniq(sections.get("first:điểm kết thúc") or sections.get("first:end point") or [])[:5]

    price_text = re.sub(r"\s*\n\s*", " ", node_text(soup.select_one("[data-testid='cheapest-price-label']")))
    price, currency = parse_price(_price_fragment(price_text), meta.get("currency"))

    title = clean_text(soup.title.get_text()) if soup.title else ""
    city = None
    tm = re.match(rf"^{re.escape(name)}\s+(.*?)\s+-\s+Booking\.com$", title)
    if tm:
        city = tm.group(1).strip() or None

    images = uniq(
        (img.get("src") or img.get("data-src") or "")
        for img in soup.select("[data-testid='product-gallery'] img, [data-testid^='gridImage'] img")
    )
    images = [i for i in images if i.startswith("http")][:15]
    og = meta_content(soup, "og:image")
    if og and og not in images:
        images.insert(0, og)

    rating = review_count = None
    for block in json_ld_blocks(soup):
        agg = block.get("aggregateRating")
        if isinstance(agg, dict):
            rating = first_float(str(agg.get("ratingValue") or ""))
            review_count = first_int(str(agg.get("reviewCount") or agg.get("ratingCount") or ""))
            break

    description = content_text or meta_content(soup, "og:description", "description")
    return {
        "recordType": "booking_attraction",
        "source": "booking_attractions",
        "key": f"attraction:{product_id}",
        "productId": product_id,
        "url": url,
        "name": name,
        "subtitle": subtitle,
        "description": description,
        "descriptionLang": detect_lang(description),
        "duration": duration,
        "cancellation": cancellation,
        "highlights": highlights,
        "included": included,
        "excluded": excluded,
        "additionalInfo": additional,
        "accessibility": accessibility,
        "guideLanguages": languages,
        "meetingPoints": meeting_points,
        "endPoints": end_points,
        "city": city,
        "price": price,
        "currency": currency,
        "priceText": price_text,
        "rating": rating,
        "reviewCount": review_count,
        "images": images,
        "crawledAt": meta.get("fetchedAt") or now_iso(),
    }


def _price_fragment(text: str) -> str:
    """'Giá thấp nhất (US$83,08) lần đầu có vào 17 thg 9' → 'US$83,08' (tránh bắt nhầm ngày)."""
    if not text:
        return ""
    m = re.search(r"\(([^)]*\d[^)]*)\)", text)
    if m:
        return m.group(1)
    m = re.search(r"((?:VND|US\$|€|£|₫)\s*[\d.,]+|[\d.,]+\s*(?:VND|₫|đ))", text)
    return m.group(1) if m else text


_STOP = ("các câu hỏi thường gặp", "frequently asked questions")  # đã chuẩn hoá bằng _hkey


def _split_sections(content) -> dict[str, list[str]]:
    """Chia khối nội dung theo tiêu đề h2/h3 → {tiêu đề (chữ thường): [dòng...]}; phần trước tiêu đề đầu tiên có khoá ''."""
    if content is None:
        return {}
    headings = {_hkey(node_text(h)) for h in content.find_all(["h2", "h3"]) if node_text(h)}
    out: dict[str, list[str]] = {"": []}
    current = ""
    expect_first = False
    for line in node_text(content).split("\n"):
        line = line.strip()
        if not line:
            continue
        key = _hkey(line)
        if key in headings:
            if key in _STOP:
                break
            current = key
            out.setdefault(current, [])
            expect_first = True
            continue
        if current == "vị trí" or line.startswith(("Xin lỗi, chúng tôi không có hình ảnh", "Dữ liệu bản đồ", "Dữ liệu Bản đồ")):
            continue
        out[current].append(line)
        if expect_first:  # dòng đầu tiên sau mỗi lần xuất hiện tiêu đề (vd. địa chỉ điểm khởi hành)
            out.setdefault(f"first:{current}", []).append(line)
            expect_first = False
    return out


def _hkey(text: str) -> str:
    return text.strip().rstrip("?:：").strip().casefold()


def _pick(sections: dict[str, list[str]], *labels: str) -> list[str]:
    for label in labels:
        items = sections.get(_hkey(label))
        if items:
            return uniq(items)[:20]
    return []
