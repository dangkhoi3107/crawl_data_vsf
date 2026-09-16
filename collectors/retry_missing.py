"""Retry incomplete saved records only; preserve populated fields and their original fetch time."""
from __future__ import annotations

import copy
import json
import logging
import re
import shutil
import tempfile
from datetime import date
from pathlib import Path

from . import booking_base, vinpearl
from .agoda_hotels import AgodaHotels
from .common import JsonlWriter, Paths, RawCache, StateDB, now_iso, read_jsonl
from .geo import clean_coords

log = logging.getLogger("crawler.retry_missing")


def latest_records(paths: Paths, source: str) -> list[dict]:
    latest = {}
    for r in read_jsonl(paths.interim / f"{source}.jsonl"):
        key = r.get("key")
        if key and (key not in latest or (r.get("crawledAt") or "") >= (latest[key].get("crawledAt") or "")):
            latest[key] = r
    return list(latest.values())


def missing_fields(r: dict, source: str) -> list[str]:
    missing = []
    if source == "vinpearl":
        if r.get("recordType") != "vinpearl_tour":
            return []
        if not any(isinstance(r.get(k), (int, float)) and r[k] > 0 for k in ("adultSalePrice", "adultOriginalPrice")):
            missing.append("price")
        if not r.get("hasDetail"):
            missing.append("detail")
    elif source == "agoda_hotels":
        if r.get("minPrice") is None:
            missing.append("price")
        if not r.get("description"):
            missing.append("description")
        if clean_coords(r.get("latitude"), r.get("longitude"))[0] is None:
            missing.append("coordinates")
    else:
        raise ValueError(f"Nguồn chưa hỗ trợ retry-missing: {source}")
    return missing


def select_missing(paths: Paths, source: str, limit: int | None = None) -> list[dict]:
    records = [r for r in latest_records(paths, source) if missing_fields(r, source)]
    return records[:limit] if limit is not None else records


def fill_missing(old: dict, fresh: dict, source: str) -> dict:
    """Chỉ bổ sung trường thiếu. Không đổi crawledAt của trường cũ; lưu thời gian riêng cho trường bổ sung."""
    out = copy.deepcopy(old)
    filled = []
    if source == "agoda_hotels":
        if old.get("minPrice") is None and isinstance(fresh.get("minPrice"), (int, float)) and fresh["minPrice"] > 0:
            for k in ("minPrice", "currency", "priceText", "priceQuery"):
                out[k] = copy.deepcopy(fresh.get(k))
                filled.append(k)
        if not old.get("description") and fresh.get("description"):
            out["description"] = fresh["description"]
            filled.append("description")
        lat, lng = clean_coords(fresh.get("latitude"), fresh.get("longitude"))
        if clean_coords(old.get("latitude"), old.get("longitude"))[0] is None and lat is not None:
            out.update(latitude=lat, longitude=lng)
            filled += ["latitude", "longitude"]
    else:
        # Identity and dates of existing data are not replaced by a detail response.
        protected = {"key", "source", "recordType", "id", "tourCode", "name", "urlSlug", "pageUrl", "crawledAt"}
        for k, value in fresh.items():
            if k in protected or value in (None, "", [], {}):
                continue
            empty = old.get(k) in (None, "", [], {})
            if k in ("adultSalePrice", "adultOriginalPrice"):
                empty = not isinstance(old.get(k), (int, float)) or old[k] <= 0
                if not isinstance(value, (int, float)) or value <= 0:
                    continue
            if k == "hasDetail":
                empty = not old.get(k)
            if empty:
                out[k] = copy.deepcopy(value)
                filled.append(k)
    if filled:
        at = fresh.get("crawledAt") or now_iso()
        out["fieldFetchedAt"] = {**old.get("fieldFetchedAt", {}), **{k: at for k in filled}}
        out["lastEnrichedAt"] = at
    return out


def backup_selected(paths: Paths, source: str, selected: list[dict], state: StateDB | None = None) -> Path:
    parent = paths.data / "backups"
    parent.mkdir(parents=True, exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix=f"retry-missing-{source}-", dir=parent))
    shutil.copy2(paths.interim / f"{source}.jsonl", backup / f"{source}.jsonl")
    (backup / "selection.json").write_text(json.dumps(selected, ensure_ascii=False, indent=2), encoding="utf-8")
    cache = RawCache(paths, source)
    for r in selected:
        key, ext = (r.get("url"), "html") if source == "agoda_hotels" else (f"api-tour-detail-{r.get('urlSlug')}", "json")
        if key:
            p = cache.path(key, ext)
            if p.exists():
                target = backup / "raw" / p.name
                target.parent.mkdir(exist_ok=True)
                shutil.copy2(p, target)
    if state is not None:
        import sqlite3
        with sqlite3.connect(backup / "crawl_state.sqlite") as conn:
            state.conn.backup(conn)
    log.info("Đã sao lưu: %s", backup)
    return backup


class MissingAgodaHotels(AgodaHotels):
    def __init__(self, selected: list[dict], checkin: date | None = None, nights: int = 1, adults: int = 2):
        super().__init__(checkin, nights, adults)
        self.previous = {r["url"]: r for r in selected}
        self.explicit_checkin = checkin
        self.improved = set()

    async def discover_plan(self, ctx) -> int:
        return 0  # Không tìm thêm URL và không mở lại các trang thành phố.

    def fetch_url(self, url: str) -> tuple[str, dict]:
        if self.explicit_checkin:
            return super().fetch_url(url)
        q = self.previous[url].get("priceQuery") or {}
        if not q.get("checkin") or not q.get("checkout"):
            raise ValueError("Thiếu ngày lấy giá đã lưu; hãy truyền --checkin YYYY-MM-DD")
        checkin, checkout = date.fromisoformat(q["checkin"]), date.fromisoformat(q["checkout"])
        return AgodaHotels(checkin, (checkout - checkin).days, q.get("adults") or 2).fetch_url(url)

    def parse(self, html: str, url: str, meta: dict) -> dict | None:
        fresh = super().parse(html, url, meta)
        if not fresh:
            return None
        result = fill_missing(self.previous[url], fresh, self.name)
        if result != self.previous[url]:
            self.improved.add(result["key"])
        return result


async def retry_agoda(paths: Paths, selected: list[dict], opts: booking_base.CrawlOptions,
                      checkin: date | None = None, nights: int = 1, adults: int = 2) -> dict:
    src = MissingAgodaHotels(selected, checkin, nights, adults)
    for url in src.previous:
        target, q = src.fetch_url(url)  # Kiểm tra ngày trước khi đổi hàng đợi.
        if date.fromisoformat(q["checkin"]) < date.today():
            raise ValueError("Ngày nhận phòng đã qua; hãy truyền --checkin YYYY-MM-DD trong tương lai")
    state = StateDB(paths)
    try:
        backup_selected(paths, src.name, selected, state)
        state.add_many(src.name, [(r["url"], 0, r.get("plan")) for r in selected])
        state.conn.executemany("UPDATE items SET status='pending', attempts=0, last_error=NULL WHERE source=? AND url=?",
                               [(src.name, r["url"]) for r in selected])
        state.conn.commit()
        opts = copy.copy(opts)
        opts.match = "^(?:" + "|".join(re.escape(url) for url in src.previous) + ")$"
        opts.limit = None
        result = await booking_base.crawl(paths, src, opts, state)
        result["selected"] = len(selected)
        result["improved"] = len(src.improved)
        return result
    finally:
        state.close()


def detail_record(old: dict, detail: dict) -> dict:
    """Convert a real detail payload without reloading the entire tour listing."""
    td = detail.get("tourDetail") or {}
    if detail.get("id") and old.get("id") and detail["id"] != old["id"]:
        raise ValueError("API trả id của vé khác")
    if td.get("tourCode") and old.get("tourCode") and td["tourCode"] != old["tourCode"]:
        raise ValueError("API trả tourCode của vé khác")
    item = {"id": old.get("id"), "tourCode": old.get("tourCode"), "tourName": old.get("name"),
            "urlSlug": old.get("urlSlug"), "type": old.get("type"), "channel": old.get("salesChannels")}
    for k in ("adultSalePrice", "adultOriginalPrice", "isEnabled", "saleStartDate", "saleEndDate", "soldQuantity"):
        if k in detail:
            item[k] = detail[k]
    return vinpearl._tour_record(item, detail, now_iso())


async def retry_vinpearl(paths: Paths, selected: list[dict], opts: vinpearl.VinpearlOptions) -> dict:
    backup_selected(paths, "vinpearl", selected)
    opts = copy.copy(opts)
    opts.refresh = True
    collector = vinpearl.VinpearlCollector(paths, opts)
    result = {"selected": len(selected), "attempted": 0, "improved": 0, "failed": 0}
    try:
        with JsonlWriter(paths.interim / "vinpearl.jsonl", "a") as writer:
            for old in selected:
                if collector.breaker.tripped:
                    break
                result["attempted"] += 1
                slug = old.get("urlSlug")
                if not slug:
                    log.warning("%s thiếu urlSlug; giữ bản ghi cũ", old["key"])
                    result["failed"] += 1
                    continue
                channels = list(dict.fromkeys([x for x in old.get("salesChannels") or [] if isinstance(x, int)] + [1]))
                detail = None
                try:
                    for ch in channels:
                        if collector.breaker.tripped:
                            break
                        data = await collector._browser_json(f"api-tour-detail-{slug}",
                            f"{vinpearl.TOUR_API}/api/frontend/tour/{slug}?Channel={ch}", quiet_404=True)
                        if isinstance(data, dict) and isinstance(data.get("data"), dict) and data["data"].get("tourDetail"):
                            detail = data["data"]
                            break
                    if detail is None:
                        result["failed"] += 1
                        log.info("%s vẫn chưa lấy được chi tiết; giữ bản ghi cũ", old["key"])
                        continue
                    rec = fill_missing(old, detail_record(old, detail), "vinpearl")
                    if rec != old:
                        writer.write(rec)
                        result["improved"] += 1
                except Exception as exc:
                    result["failed"] += 1
                    log.warning("%s: %s; giữ bản ghi cũ", old["key"], str(exc)[:200])
    finally:
        await collector.close()
    if collector.breaker.tripped:
        result["stopped"] = "blocked"
    return result
