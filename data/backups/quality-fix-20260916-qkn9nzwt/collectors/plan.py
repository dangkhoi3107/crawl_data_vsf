"""Kế hoạch thu thập theo handbook §3: 2.000–5.000 sản phẩm, 10–15 điểm đến, đủ hotel/flight/attraction/combo.

Chọn điểm đến có Vinpearl trước, rồi thêm các điểm du lịch lớn. Slug/mã từng nguồn đã được kiểm tra thủ công
(15/09/2026); nếu website đổi URL, sửa ở đây.
"""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Destination:
    name: str                        # tên chuẩn, trùng với geo.py
    booking_query: str               # ô tìm kiếm booking.com
    agoda_city: str | None           # https://www.agoda.com/vi-vn/city/<slug>.html
    trip_city: str | None            # https://vn.trip.com/travel-guide/attraction/<slug>/tourist-attractions/
    airports: tuple[str, ...] = ()   # IATA – trang https://vn.trip.com/flights/airport-<iata>/
    vinpearl: bool = False


DESTINATIONS: tuple[Destination, ...] = (
    Destination("Nha Trang", "Nha Trang", "nha-trang-vn", "nha-trang-670", ("CXR",), vinpearl=True),
    Destination("Phú Quốc", "Phu Quoc", "phu-quoc-island-vn", "phu-quoc-island-24779", ("PQC",), vinpearl=True),
    Destination("Hội An", "Hoi An", "hoi-an-vn", "hoi-an-668", (), vinpearl=True),          # bay tới Đà Nẵng
    Destination("Đà Nẵng", "Da Nang", "da-nang-vn", "da-nang-669", ("DAD",)),
    Destination("Hạ Long", "Ha Long", "h-long-vn", "ha-long-city-1524623", ("VDO",), vinpearl=True),
    Destination("Hà Nội", "Hanoi", "hanoi-vn", "hanoi-181", ("HAN",), vinpearl=True),
    Destination("TP. Hồ Chí Minh", "Ho Chi Minh City", "ho-chi-minh-city-vn", "ho-chi-minh-city-434", ("SGN",)),
    Destination("Hải Phòng", "Hai Phong", "haiphong-vn", "haiphong-180", ("HPH",), vinpearl=True),
    Destination("Nghệ An", "Cua Lo", "vinh-vn", "vinh-city-24768", ("VII",), vinpearl=True),
    Destination("Hà Tĩnh", "Ha Tinh", "ha-tinh-vn", None, (), vinpearl=True),                # bay tới Vinh
    Destination("Đà Lạt", "Da Lat", "dalat-vn", "dalat-1393", ("DLI",)),
    Destination("Huế", "Hue", "hue-vn", "hue-667", ("HUI",)),
    Destination("Quy Nhơn", "Quy Nhon", "quy-nhon-binh-dinh-vn", "quy-nhon-24728", ("UIH",)),
    Destination("Sa Pa", "Sa Pa", "sapa-vn", "sapa-24736", ()),
    Destination("Phan Thiết", "Mui Ne", "phan-thiet-vn", "phan-thiet-1218", ()),
)


@dataclass(frozen=True)
class Budget:
    """Số lượng lấy MỖI điểm đến (trừ flight). Mặc định cho catalog cuối ~3.000–4.000 sản phẩm."""

    booking_hotels: int = 30          # khách sạn phổ biến nhất trên booking.com
    agoda_hotels: int = 20            # khách sạn phổ biến nhất trên agoda.com (trùng booking sẽ được gộp)
    trip_attractions: int = 25        # điểm tham quan trip.com
    ota_rooms_per_hotel: int = 3      # hạng phòng OTA giữ lại mỗi khách sạn (Vinpearl giữ hết)
    flights_per_route: int = 5        # số hiệu chuyến bay giữ lại mỗi tuyến (ngoài sản phẩm cấp tuyến)


DEFAULT_BUDGET = Budget()
TARGET_MIN, TARGET_MAX = 2000, 5000


def select_destinations(names: str | None) -> tuple[Destination, ...]:
    if not names:
        return DESTINATIONS
    from .textutil import fold

    wanted = {fold(n) for n in names.split(",") if n.strip()}
    chosen = tuple(d for d in DESTINATIONS if fold(d.name) in wanted)
    unknown = wanted - {fold(d.name) for d in chosen}
    if unknown:
        raise SystemExit(
            f"Điểm đến không có trong kế hoạch: {', '.join(sorted(unknown))}. "
            f"Có: {', '.join(d.name for d in DESTINATIONS)}"
        )
    return chosen


def budget_with(per_destination: int | None, **overrides) -> Budget:
    b = DEFAULT_BUDGET
    if per_destination:
        b = replace(b, booking_hotels=per_destination, agoda_hotels=max(1, per_destination * 2 // 3),
                    trip_attractions=per_destination)
    return replace(b, **{k: v for k, v in overrides.items() if v is not None})


def plan_destination_names() -> set[str]:
    return {d.name for d in DESTINATIONS}
