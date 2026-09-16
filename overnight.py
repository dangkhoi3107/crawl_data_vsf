#!/usr/bin/env python3
"""Run the 15-destination plan until a local deadline; report unmet checks honestly.

Linux: python overnight.py --until 07:00 --checkin 2026-10-15
Read-only inspection: python overnight.py --check-only
Uses the existing collectors and normalizer. Does not generate product data.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sqlite3
import subprocess
import sys
import time
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

from collectors.common import Paths, RunLock, default_data_dir
from collectors.plan import DEFAULT_BUDGET, DESTINATIONS, TARGET_MAX, TARGET_MIN

ROOT = Path(__file__).resolve().parent
SOURCES = ("trip_flights", "trip_attractions", "agoda_hotels", "booking_hotels", "vinpearl")
log = logging.getLogger("overnight")


def read_rows(path: Path) -> tuple[list[dict], int]:
    rows, bad = [], 0
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError("not an object")
                rows.append(value)
            except (ValueError, TypeError):
                bad += 1
    return rows, bad


def inspect(data: Path, checkin: str) -> dict:
    queues, retryable, discovery = {}, {}, {}
    db = data / "state" / "crawl_state.sqlite"
    if db.exists():
        with sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True) as conn:
            for src, status, count in conn.execute("SELECT source,status,COUNT(*) FROM items GROUP BY source,status"):
                queues.setdefault(src, {})[status] = count
            for src, count in conn.execute("SELECT source,COUNT(*) FROM items WHERE status='pending' OR (status='failed' AND attempts<3) GROUP BY source"):
                retryable[src] = count
            discovery = {(s, k): n for s, k, n in conn.execute("SELECT source,key,found FROM discovery")}

    source_info, issues = {}, []
    newest_input = 0.0
    for src in SOURCES:
        path = data / "interim" / f"{src}.jsonl"
        rows, bad = read_rows(path)
        unique = {r.get("key"): r for r in rows if r.get("key")}
        source_info[src] = {"records": len(unique), "queue": queues.get(src, {}),
                            "retryable": retryable.get(src, 0), "coverage_shortfalls": [], "bad_lines": bad,
                            "records_by_destination": dict(Counter((r.get("plan") or {}).get("destination") or "unassigned" for r in unique.values()))}
        if path.exists():
            newest_input = max(newest_input, path.stat().st_mtime)
        if not unique:
            issues.append(f"{src}: chưa có bản ghi có key")
        if bad:
            issues.append(f"{src}: {bad} dòng JSON lỗi")
        q = queues.get(src, {})
        if q.get("pending", 0) or q.get("failed", 0):
            issues.append(f"{src}: pending={q.get('pending', 0)}, failed={q.get('failed', 0)}")
        if src == "vinpearl":
            kinds = {r.get("recordType") for r in rows}
            if not {"vinpearl_hotel", "vinpearl_tour"} <= kinds:
                issues.append("vinpearl: thiếu nhóm khách sạn hoặc tour/vé")
                source_info[src]["missing_kind"] = True

    for dest in DESTINATIONS:
        expected = [
            ("booking_hotels", f"search:{dest.booking_query}:{DEFAULT_BUDGET.booking_hotels}:{checkin}", DEFAULT_BUDGET.booking_hotels),
        ]
        if dest.agoda_city:
            expected.append(("agoda_hotels", f"city:{dest.agoda_city}:{DEFAULT_BUDGET.agoda_hotels}", DEFAULT_BUDGET.agoda_hotels))
        if dest.trip_city:
            expected.append(("trip_attractions", f"list:{dest.trip_city}:{DEFAULT_BUDGET.trip_attractions}", DEFAULT_BUDGET.trip_attractions))
        for src, key, want in expected:
            found = discovery.get((src, key), 0) or 0
            collected = source_info[src]["records_by_destination"].get(dest.name, 0)
            if found < want or collected < want:
                gap = f"{dest.name}: tìm được {found}/{want} URL, đã lưu {collected}/{want} bản ghi riêng biệt theo kế hoạch"
                source_info[src]["coverage_shortfalls"].append(gap)
                issues.append(f"{src}: {gap}")

    output = data / "products.jsonl"
    products, bad = read_rows(output)
    if bad:
        issues.append(f"products.jsonl: {bad} dòng JSON lỗi")
    if not output.exists() or output.stat().st_mtime < newest_input:
        issues.append("Catalog chưa được chuẩn hóa từ dữ liệu mới nhất")
    if not TARGET_MIN <= len(products) <= TARGET_MAX:
        issues.append(f"Số sản phẩm {len(products)} chưa nằm trong {TARGET_MIN}–{TARGET_MAX}")
    taxonomies = Counter(p.get("taxonomy") for p in products)
    for kind in ("hotel", "flight", "attraction", "combo"):
        if not taxonomies[kind]:
            issues.append(f"Thiếu loại sản phẩm: {kind}")
    destinations = Counter(p.get("destination") for p in products)
    for dest in DESTINATIONS:
        if destinations[dest.name] < 20:
            issues.append(f"{dest.name}: {destinations[dest.name]}/20 sản phẩm")
    ids = [p.get("productId") for p in products]
    if len(set(ids)) != len(ids) or any(not i for i in ids):
        issues.append("Có productId thiếu hoặc trùng")
    missing_text = sum(not p.get("name") or not p.get("description") for p in products)
    if missing_text:
        issues.append(f"{missing_text} sản phẩm thiếu tên hoặc mô tả")
    return {"checked_at": datetime.now().isoformat(timespec="seconds"), "checkin": checkin,
            "checks_passed": not issues, "products": len(products), "sources": source_info,
            "taxonomies": dict(taxonomies), "destinations": dict(destinations), "issues": issues,
            "quality_notes": {
                "missing_price": sum(p.get("unitPrice") is None for p in products),
                "missing_coordinates": sum(p.get("attributes", {}).get("latitude") is None or p.get("attributes", {}).get("longitude") is None for p in products),
                "location_warnings": sum(bool(p.get("attributes", {}).get("locationWarning")) for p in products),
                "derived_descriptions": sum(bool(p.get("attributes", {}).get("descriptionSource")) for p in products),
            },
            "review_note": "Đạt các kiểm tra này chưa chứng minh giá hiện hành, còn chỗ, ghép trùng và tọa độ đều chính xác; vẫn cần duyệt dữ liệu."}


def report(data: Path, checkin: str) -> dict:
    result = inspect(data, checkin)
    title = "ĐẠT CÁC KIỂM TRA TỰ ĐỘNG — CẦN DUYỆT" if result["checks_passed"] else "CHƯA ĐẠT — CÒN MỤC THIẾU"
    lines = [f"# {title}", "", f"Kiểm tra: {result['checked_at']}", f"Sản phẩm: {result['products']}", "",
             "## Theo nguồn", ""]
    for src, info in result["sources"].items():
        lines.append(f"- {src}: {info['records']} bản ghi; hàng đợi {info['queue']}")
    lines += ["", "## Mục chưa đạt", ""] + [f"- {x}" for x in result["issues"]]
    lines += ["", "## Chỉ số cần duyệt", ""] + [f"- {k}: {v}" for k, v in result["quality_notes"].items()]
    lines += ["", result["review_note"], ""]
    for suffix, content in (("json", json.dumps(result, ensure_ascii=False, indent=2)), ("md", "\n".join(lines))):
        path = data / f"overnight-status.{suffix}"
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(path)
    log.info("%s: %d sản phẩm, %d mục chưa đạt. Xem %s", title, result["products"], len(result["issues"]), data / "overnight-status.md")
    return result


def stop_child(child: subprocess.Popen) -> None:
    if child.poll() is not None:
        return
    # A separate group includes Chromium children; do not signal another crawler.
    for sig, grace in ((signal.SIGINT, 60), (signal.SIGTERM, 10), (signal.SIGKILL, 5)):
        try:
            os.killpg(child.pid, sig)
        except ProcessLookupError:
            return
        try:
            child.wait(timeout=grace)
            return
        except subprocess.TimeoutExpired:
            pass
    raise RuntimeError("Không dừng được tiến trình con")


def run_step(args: list[str], deadline: float, minutes: float = 60) -> int:
    remaining = min(deadline - time.time(), minutes * 60)
    if remaining <= 0:
        return 124
    log.info("Chạy: %s", " ".join(args))
    child = subprocess.Popen([sys.executable, "-u", *args], cwd=ROOT, start_new_session=True)
    try:
        try:
            return child.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            log.warning("Hết thời gian cho bước này; dừng và giữ tiến độ.")
            stop_child(child)
            return 124
    except BaseException:
        stop_child(child)
        raise


def needs_work(info: dict) -> bool:
    return bool(not info["records"] or info["retryable"] or info["coverage_shortfalls"] or info.get("missing_kind"))


def source_args(src: str, data: Path, checkin: str, price_dates: str, rediscover: bool) -> list[str]:
    args = [str(ROOT / "crawl.py"), "--data-dir", str(data), src.replace("_", "-"),
            "--delay", "4", "--manual-wait", "60", "--max-blocks", "3"]
    if src == "vinpearl":
        args += ["--price-dates", price_dates]
    else:
        args += ["--max-attempts", "3"]
        if rediscover:
            args.append("--rediscover")
    if src in ("booking_hotels", "agoda_hotels"):
        args += ["--concurrency", "2", "--checkin", checkin]
    if src == "booking_hotels":
        args.append("--fast")
    return args


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--until", default="07:00", help="giờ địa phương dừng crawl; mặc định 07:00 lần tới")
    parser.add_argument("--checkin", default=(date.today() + timedelta(days=30)).isoformat())
    parser.add_argument("--price-dates", default=None)
    parser.add_argument("--data-dir", type=Path, default=default_data_dir())
    parser.add_argument("--check-only", action="store_true", help="chỉ in kiểm tra, không crawl hoặc ghi file")
    a = parser.parse_args(argv)
    date.fromisoformat(a.checkin)
    until = datetime.strptime(a.until, "%H:%M").time()
    now = datetime.now()
    end = datetime.combine(now.date(), until)
    if end <= now:
        end += timedelta(days=1)
    data = a.data_dir.resolve()
    if a.check_only:
        result = inspect(data, a.checkin)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["checks_passed"] else 2
    if os.name != "posix":
        parser.error("Script điều phối này dùng trên máy Linux; các collector vẫn có thể chạy riêng trên Windows.")
    paths = Paths(data).ensure()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.StreamHandler(), logging.FileHandler(paths.logs / "overnight.log", encoding="utf-8")])
    price_dates = a.price_dates or ",".join((now.date() + timedelta(days=n)).isoformat() for n in (30, 14, 60))
    due, tries = dict.fromkeys(SOURCES, 0.0), Counter()
    interrupted = False
    with RunLock(paths, "overnight"):
        log.info("Ngừng crawl lúc %s, sau đó xuất báo cáo. Tối đa 3 lượt mỗi nguồn; không reset số lần lỗi của URL.", end)
        try:
            while time.time() < end.timestamp():
                state = inspect(data, a.checkin)
                eligible = [s for s in SOURCES if tries[s] < 3 and needs_work(state["sources"][s])]
                ran = False
                for src in eligible:
                    if time.time() >= end.timestamp():
                        break
                    if due[src] > time.time():
                        continue
                    info = state["sources"][src]
                    # A collector marks a short discovery as done; request another search, but keep done URLs.
                    rediscover = tries[src] > 0 or bool(info["records"] and info["coverage_shortfalls"])
                    code = run_step(source_args(src, data, a.checkin, price_dates, rediscover), end.timestamp())
                    if code in (130, -signal.SIGINT):
                        raise KeyboardInterrupt
                    tries[src] += 1
                    ran = True
                    wait = 10800 if code == 75 else 1800 if code == 0 else 600
                    due[src] = time.time() + wait
                    if code == 75 and src.startswith("trip_"):
                        for other in ("trip_flights", "trip_attractions"):
                            due[other] = max(due[other], due[src])
                    log.info("%s: mã thoát %s, lượt %d/3; sẽ kiểm tra dữ liệu trước khi quyết định xong.", src, code, tries[src])
                if ran:
                    run_step([str(ROOT / "normalise.py"), "--data-dir", str(data)], time.time() + 300, 5)
                    state = report(data, a.checkin)
                    if state["checks_passed"]:
                        break
                remaining = [s for s in SOURCES if tries[s] < 3 and needs_work(state["sources"][s])]
                if not remaining:
                    log.warning("Đã hết công việc tự thử lại; các mục còn thiếu cần kiểm tra parser/nguồn.")
                    break
                wait = max(0.0, min(due[s] for s in remaining) - time.time())
                time.sleep(min(30.0, wait, max(0.0, end.timestamp() - time.time())))
        except KeyboardInterrupt:
            interrupted = True
            log.warning("Đã dừng theo yêu cầu; xuất catalog từ phần dữ liệu đã lưu.")
        finally:
            # Finish locally even at the deadline. New web requests for venues have a five-minute bound.
            venue_args = [str(ROOT / "crawl.py"), "--data-dir", str(data), "venues"]
            if interrupted or time.time() >= end.timestamp():
                venue_args.append("--offline")
            try:
                run_step(venue_args, time.time() + 300 if "--offline" in venue_args else min(end.timestamp(), time.time() + 300), 5)
                run_step([str(ROOT / "normalise.py"), "--data-dir", str(data)], time.time() + 300, 5)
            except KeyboardInterrupt:
                interrupted = True
            result = report(data, a.checkin)
    return 130 if interrupted else 0 if result["checks_passed"] else 2


if __name__ == "__main__":
    sys.exit(main())
