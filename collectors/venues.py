"""Địa điểm dùng vé/combo/golf Vinpearl → toạ độ.

API tour của Vinpearl không có toạ độ, nhưng mỗi vé có nhà cung cấp (supplierCode/supplierName) chính là nơi dùng vé
(VinWonders Nha Trang, Vinpearl Safari Phú Quốc…). Vì vậy chỉ cần toạ độ cho vài chục địa điểm, lưu ở venues.csv:

  key, name, destination   định danh, tên hiển thị, điểm đến chuẩn (geo.py)
  suppliers                supplierCode của Vinpearl, nhiều mã cách nhau bằng |
  aliases                  cụm từ không dấu tìm trong tên nhà cung cấp / tên vé / slug ảnh, cách nhau bằng |
  queries                  chuỗi tìm trên trip.com / OpenStreetMap, thử lần lượt
  latitude, longitude      toạ độ
  status                   ok      đã kiểm tra bằng mắt – script không bao giờ ghi đè
                           auto    script tự tìm, qua kiểm tra tên + khoảng cách – normalise dùng
                           review  không tìm thấy hoặc không qua kiểm tra – normalise KHÔNG dùng cho tới khi sửa thành ok
  source, candidate        nguồn toạ độ (trip.com:<id>, osm:<loại><id>, manual) và tên kết quả tìm được
  distanceKm, note         khoảng cách tới tâm điểm đến; lý do cần duyệt
  tickets, mapUrl          số vé đang khớp; link Google Maps để kiểm tra (script tự điền)

`python crawl.py venues` điền toạ độ cho các dòng chưa có: trip.com (nếu đã crawl trip-attractions) → OpenStreetMap
qua Photon (photon.komoot.io). Kết quả chỉ được nhận khi mọi từ của chuỗi tìm có trong tên/địa chỉ kết quả và kết quả
nằm trong bán kính điểm đến (geo.py), để tránh kiểu tìm "VinWonders Cửa Hội" mà ra VinWonders Nam Hội An.
"""

from __future__ import annotations

import csv
import logging
import re
from collections import Counter
from dataclasses import dataclass, field, fields
from pathlib import Path
from urllib.parse import urlencode

from .common import HostRateLimiter, Http, Paths, RawCache, read_jsonl
from .geo import (
    DESTINATION_CENTERS,
    destination_bbox,
    destination_in_text,
    destination_radius_km,
    km_from_destination,
    maps_url,
    normalise_destination,
)
from .textutil import clean_text, fold

log = logging.getLogger("crawler.venues")

VENUES_CSV = Path(__file__).with_name("venues.csv")
PHOTON_API = "https://photon.komoot.io/api/"
USABLE_STATUS = ("ok", "auto")


@dataclass
class Venue:
    key: str
    name: str
    destination: str = ""
    suppliers: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)
    latitude: float | None = None
    longitude: float | None = None
    status: str = ""
    source: str = ""
    candidate: str = ""
    distanceKm: float | None = None
    note: str = ""
    tickets: int = 0
    mapUrl: str = ""

    @property
    def usable(self) -> bool:
        return self.status in USABLE_STATUS and self.latitude is not None and self.longitude is not None

    @property
    def source_family(self) -> str:
        """'osm:W123' → 'osm', 'trip.com:123' → 'trip.com'; toạ độ điền tay (source trống hoặc 'manual') → 'manual'."""
        return self.source.split(":", 1)[0] if self.source else "manual"


FIELDS = tuple(f.name for f in fields(Venue))
_LIST_FIELDS = ("suppliers", "aliases", "queries")


def _split(v: str) -> list[str]:
    return [x.strip() for x in (v or "").split("|") if x.strip()]


def _float(v) -> float | None:
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


def load_venues(path: Path = VENUES_CSV) -> list[Venue]:
    if not path.exists():
        return []
    out = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if not (row.get("key") or "").strip():
                continue
            out.append(
                Venue(
                    key=row["key"].strip(),
                    name=clean_text(row.get("name")),
                    destination=clean_text(row.get("destination")),
                    suppliers=[s.upper() for s in _split(row.get("suppliers"))],
                    aliases=[fold(s) for s in _split(row.get("aliases")) if fold(s)],
                    queries=_split(row.get("queries")),
                    latitude=_float(row.get("latitude")),
                    longitude=_float(row.get("longitude")),
                    status=(row.get("status") or "").strip().lower(),
                    source=(row.get("source") or "").strip(),
                    candidate=clean_text(row.get("candidate")),
                    distanceKm=_float(row.get("distanceKm")),
                    note=clean_text(row.get("note")),
                    tickets=int(_float(row.get("tickets")) or 0),
                )
            )
    return out


def save_venues(venues: list[Venue], path: Path = VENUES_CSV) -> None:
    tmp = path.with_suffix(".csv.tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(FIELDS)
        for v in venues:
            v.mapUrl = maps_url(v.latitude, v.longitude)
            row = []
            for name in FIELDS:
                val = getattr(v, name)
                if name in _LIST_FIELDS:
                    val = "|".join(val)
                elif name in ("latitude", "longitude") and val is not None:
                    val = f"{val:.6f}"
                elif name == "distanceKm" and val is not None:
                    val = f"{val:.1f}"
                row.append("" if val is None else val)
            w.writerow(row)
    tmp.replace(path)


# ---------------------------------------------------------------------- khớp vé → địa điểm


class VenueMatcher:
    """Mã nhà cung cấp → địa điểm; không có mã thì tìm alias trong tên nhà cung cấp, tên vé, slug ảnh (theo thứ tự)."""

    def __init__(self, venues: list[Venue]):
        self.by_supplier = {code: v for v in venues for code in v.suppliers}
        self.aliases = [
            (re.compile(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])"), alias, v) for v in venues for alias in v.aliases
        ]

    def match(self, *, supplier_code: str | None = None, supplier_name: str | None = None, name: str | None = None,
              slug: str | None = None, destination_hint: str | None = None) -> tuple[Venue | None, str | None]:
        """→ (địa điểm, cách khớp: 'supplier' / 'name' / 'slug').

        Alias khớp trong tên vé / slug mà tên vé đã nêu điểm đến khác với địa điểm thì bỏ qua: "[Grand World] …" của
        Phú Quốc không được rơi vào Mega Grand World Hà Nội. Nhiều địa điểm cùng khớp (alias "jjimjilbang" có ở cả
        Aquafield Nha Trang lẫn Ocean City) thì chọn theo destination_hint (điểm đến tính từ tỉnh trong API – yếu, chỉ
        dùng để phân định); vẫn nhập nhằng thì thử chuỗi tiếp theo, hết chuỗi thì không đoán."""
        if supplier_code and supplier_code.upper() in self.by_supplier:
            return self.by_supplier[supplier_code.upper()], "supplier"
        named = destination_in_text(name)
        for how, text in (("supplier", supplier_name), ("name", name), ("slug", (slug or "").replace("-", " "))):
            f = fold(text)
            if not f:
                continue
            hits = [(v, alias) for pat, alias, v in self.aliases if pat.search(f)]
            if how != "supplier" and named:
                hits = [h for h in hits if h[0].destination == named]
            if not hits:
                continue
            longest = max(len(alias) for _, alias in hits)
            top = {v.key: v for v, alias in hits if len(alias) == longest}
            if len(top) > 1 and destination_hint:
                top = {k: v for k, v in top.items() if v.destination == destination_hint} or top
            if len(top) == 1:
                return next(iter(top.values())), how
        return None, None


def ticket_fields(record: dict) -> dict:
    """Các trường dùng để khớp từ bản ghi interim vinpearl_tour."""
    return {
        "supplier_code": record.get("supplierCode"),
        "supplier_name": record.get("supplierName"),
        "name": record.get("name"),
        "slug": record.get("imageUrlSlug"),
        "destination_hint": normalise_destination(record.get("name"), record.get("destinationName")),
    }


# ---------------------------------------------------------------------- tìm toạ độ


@dataclass
class Candidate:
    lat: float
    lng: float
    name: str
    source: str        # trip.com:<poiId> / osm:<N|W|R><id>
    detail: str        # vd. tourism=theme_park
    text: str          # tên + địa chỉ, dùng kiểm tra từ khoá
    country: str = "VN"


# Kết quả là trạm xe buýt / đường / ga mang tên địa điểm ("Công viên VinWonder Wave Park" là trạm buýt): chỉ ở gần.
_NEARBY_ONLY = ("highway=", "public_transport=", "railway=", "aerialway=")


def _tokens(s: str | None) -> set[str]:
    return set(fold(s).split())


def _missing_tokens(query: str, text: str) -> set[str]:
    """Từ của chuỗi tìm không có trong kết quả; chấp nhận khác nhau chữ s cuối ("VinWonder" ~ "VinWonders")."""
    have = _tokens(text)
    have |= {t[:-1] for t in have if len(t) > 4 and t.endswith("s")} | {t + "s" for t in have if len(t) > 3}
    return _tokens(query) - have


def check_candidate(venue: Venue, cand: Candidate, query: str) -> tuple[str | None, float | None]:
    """→ (lý do loại hoặc None nếu đạt, khoảng cách tới tâm điểm đến)."""
    km = km_from_destination(venue.destination, cand.lat, cand.lng)
    if (cand.country or "VN").upper() != "VN":
        return f"'{cand.name}' không ở Việt Nam", km
    missing = _missing_tokens(query, cand.text)
    if missing:
        return f"kết quả '{cand.name}' thiếu từ: {' '.join(sorted(missing))}", km
    if cand.detail.startswith(_NEARBY_ONLY):
        return f"'{cand.name}' là {cand.detail}, chỉ ở gần địa điểm", km
    if venue.destination not in DESTINATION_CENTERS:
        return f"geo.py chưa có tâm của điểm đến '{venue.destination}'", km
    if km is not None and km > destination_radius_km(venue.destination):
        return f"'{cand.name}' cách tâm {venue.destination} {km:.0f} km", km
    return None, km


def trip_candidates(paths: Paths) -> list[Candidate]:
    latest: dict[str, dict] = {}
    for r in read_jsonl(paths.interim / "trip_attractions.jsonl"):
        if r.get("key") and (r["key"] not in latest or (r.get("crawledAt") or "") >= (latest[r["key"]].get("crawledAt") or "")):
            latest[r["key"]] = r
    out = []
    for r in latest.values():
        if r.get("latitude") is None or r.get("longitude") is None:
            continue
        text = " ".join(x for x in (r.get("name"), r.get("englishName"), r.get("district"), r.get("address"), r.get("province")) if x)
        out.append(Candidate(r["latitude"], r["longitude"], r.get("name") or "", f"trip.com:{r.get('poiId')}", "trip.com", text))
    return out


class Photon:
    """Geocoder OpenStreetMap. Trang Photon cho phép dùng API cho dự án nếu dùng vừa phải; mỗi truy vấn chỉ gửi một lần
    (cache ở data/raw/geocode/) và cách nhau ≥ 1 giây. robots.txt của photon.komoot.io chặn crawler trang web, còn đây
    là gọi API nên không kiểm tra robots."""

    def __init__(self, paths: Paths, offline: bool = False):
        self.cache = RawCache(paths, "geocode")
        self.offline = offline
        self.http: Http | None = None

    async def search(self, query: str, bbox: tuple[float, float, float, float] | None) -> list[Candidate] | None:
        """Kết quả tìm; None nếu --offline mà truy vấn chưa có trong cache (chưa tìm được, khác với tìm không thấy)."""
        params = {"q": query, "limit": 5}
        if bbox:
            params["bbox"] = ",".join(f"{x:.4f}" for x in bbox)
        url = f"{PHOTON_API}?{urlencode(params)}"
        data = self.cache.read_json(url)
        if data is None:
            if self.offline:
                return None
            if self.http is None:
                self.http = Http(HostRateLimiter(1.1), respect_robots=False)
            r = await self.http.get(url, headers={"Accept": "application/json"})
            if r.status_code != 200:
                log.warning("Photon trả %s cho %r", r.status_code, query)
                return []
            data = r.json()
            self.cache.write_json(url, data)
        out = []
        for feat in data.get("features") or []:
            props = feat.get("properties") or {}
            coords = (feat.get("geometry") or {}).get("coordinates") or []
            if len(coords) != 2 or not props.get("name"):
                continue
            text = " ".join(str(props[k]) for k in ("name", "street", "locality", "district", "city", "county", "state") if props.get(k))
            out.append(Candidate(float(coords[1]), float(coords[0]), props["name"], f"osm:{props.get('osm_type', '')}{props.get('osm_id', '')}",
                                 f"{props.get('osm_key')}={props.get('osm_value')}", text, props.get("countrycode") or ""))
        return out

    async def close(self) -> None:
        if self.http is not None:
            await self.http.close()


async def locate(venue: Venue, trip: list[Candidate], photon: Photon) -> None:
    queries = venue.queries or [venue.name]
    first_reject: tuple[Candidate, str, float | None] | None = None

    def accept(cand: Candidate, km: float | None, how: str) -> None:
        venue.latitude, venue.longitude = round(cand.lat, 6), round(cand.lng, 6)
        venue.status, venue.source, venue.distanceKm = "auto", cand.source, km
        venue.candidate = f"{cand.name} ({cand.detail})"
        venue.note = f"tự tìm qua {how}; kiểm tra bằng mắt rồi đặt status=ok"

    for query in queries:  # trip.com trước: toạ độ trang điểm tham quan thường sát cổng vào
        passing = []
        for cand in trip:
            reason, km = check_candidate(venue, cand, query)
            if reason is None:
                passing.append((len(_tokens(cand.name) - _tokens(query)), cand, km))
        if passing:
            _, cand, km = min(passing, key=lambda x: x[0])
            accept(cand, km, "trip.com")
            return
    bbox = destination_bbox(venue.destination)
    unsearched = False
    for query in queries:
        cands = await photon.search(query, bbox)
        if cands is None:
            unsearched = True
            continue
        for cand in cands:
            reason, km = check_candidate(venue, cand, query)
            if reason is None:
                accept(cand, km, "OpenStreetMap")
                return
            first_reject = first_reject or (cand, reason, km)
    if unsearched and (venue.usable or first_reject is None):
        # offline / mất mạng giữa chừng: không kết luận "không tìm thấy", giữ dòng như cũ để lần sau tìm tiếp
        if not venue.usable:
            venue.note = "chưa tìm được trên OpenStreetMap (offline hoặc lỗi mạng) – chạy lại crawl.py venues"
        return
    venue.status = "review"
    if first_reject:
        cand, reason, km = first_reject
        venue.latitude, venue.longitude = round(cand.lat, 6), round(cand.lng, 6)
        venue.source, venue.candidate, venue.distanceKm = cand.source, f"{cand.name} ({cand.detail})", km
        venue.note = f"chưa đạt kiểm tra: {reason}"
    else:
        venue.latitude = venue.longitude = venue.distanceKm = None
        venue.source = venue.candidate = ""
        venue.note = f"không tìm thấy trên trip.com / OpenStreetMap với: {' | '.join(queries)}"


def _slug(s: str) -> str:
    return fold(s).replace(" ", "-")[:60] or "venue"


async def run(paths: Paths, *, refresh: bool = False, only: set[str] | None = None, offline: bool = False,
              path: Path = VENUES_CSV) -> dict:
    venues = load_venues(path)
    matcher = VenueMatcher(venues)
    latest: dict[str, dict] = {}
    for r in read_jsonl(paths.interim / "vinpearl.jsonl"):
        if r.get("recordType") == "vinpearl_tour" and r.get("key"):
            latest[r["key"]] = r
    tickets = list(latest.values())
    if tickets and not any(t.get("supplierCode") for t in tickets):
        log.warning("Bản ghi Vinpearl chưa có supplierCode – chạy 'python crawl.py reparse vinpearl' để khớp chính xác hơn.")

    # nhà cung cấp mới chưa có trong bảng → thêm dòng, tìm toạ độ như các dòng khác
    counts: Counter = Counter()
    unknown: dict[str, Counter] = {}
    unknown_names: dict[str, str] = {}
    for t in tickets:
        venue, _ = matcher.match(**ticket_fields(t))
        if venue:
            counts[venue.key] += 1
        elif t.get("supplierCode") and t.get("supplierName"):
            code = t["supplierCode"].upper()
            unknown.setdefault(code, Counter())[normalise_destination(t.get("name"), t.get("destinationName")) or ""] += 1
            unknown_names[code] = clean_text(t["supplierName"])
    keys = {v.key for v in venues}
    for code, dests in unknown.items():
        name = unknown_names[code].title()
        key = _slug(name)
        while key in keys:
            key += "-2"
        keys.add(key)
        venues.append(Venue(key=key, name=name, destination=dests.most_common(1)[0][0], suppliers=[code],
                            aliases=[fold(unknown_names[code])], queries=[name], note="nhà cung cấp mới – kiểm tra tên/điểm đến"))
        counts[key] = sum(dests.values())
        log.info("Thêm địa điểm mới từ nhà cung cấp %s: %s (%s)", code, name, dests.most_common(1)[0][0])
    for v in venues:
        v.tickets = counts.get(v.key, 0)

    trip = trip_candidates(paths)
    photon = Photon(paths, offline=offline)
    stats: Counter = Counter()
    try:
        for v in venues:
            if only and v.key not in only:
                continue
            if v.status == "ok":
                stats["ok (đã duyệt)"] += 1
                continue
            if v.status in USABLE_STATUS + ("review",) and not refresh:
                stats[f"{v.status} (giữ nguyên)"] += 1
                continue
            try:
                await locate(v, trip, photon)
            except Exception as e:  # lỗi mạng: giữ nguyên dòng; các dòng sau chỉ dùng trip.com + cache, lần sau chạy lại
                log.warning("Không gọi được Photon cho %s (%s) – các địa điểm còn lại chỉ dùng trip.com và cache.", v.name, str(e)[:200])
                stats["lỗi mạng"] += 1
                photon.offline = True
                await locate(v, trip, photon)
            stats[v.status or "chưa tìm"] += 1
    finally:
        await photon.close()
        save_venues(venues, path)

    review = [v for v in venues if v.tickets and not v.usable]
    for v in venues:
        mark = {"ok": "✓", "auto": "~", "review": "!"}.get(v.status, "?")
        where = f"{v.latitude:.5f},{v.longitude:.5f}" if v.latitude is not None else "–"
        log.info("%s %-38s %-16s %4d vé  %-22s %s", mark, v.name[:38], v.destination[:16], v.tickets, where,
                 v.candidate[:60] if v.status != "review" else v.note[:90])
    log.info("Địa điểm: %s. Đã ghi %s", dict(stats), path)
    if review:
        log.warning("%d địa điểm có vé nhưng chưa có toạ độ dùng được: %s. Mở %s, xem cột mapUrl/note, "
                    "điền latitude, longitude đúng rồi đặt status=ok.", len(review), ", ".join(v.name for v in review), path.name)
    unmatched = len(tickets) - sum(counts.values())
    if unmatched:
        log.info("%d vé không khớp địa điểm nào (thiếu nhà cung cấp và tên không chứa alias) – xem data/map/can-kiem-tra.csv sau khi normalise.", unmatched)
    return {"venues": len(venues), "review": len(review), **stats}
