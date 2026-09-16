# Bàn giao catalog du lịch V-OTA — 16/09/2026

Dữ liệu sản phẩm du lịch thật, thu thập theo §3 handbook RecSys internship v3.
Crawl ngày 15–16/09/2026. Người thu thập: mảng Data.

## 1. Gói này có gì

| File | Nội dung |
|---|---|
| `products.jsonl` | **Bản chuẩn.** 2.327 sản phẩm, mỗi dòng 1 JSON đúng 13 trường §6 |
| `products.csv` | Cùng dữ liệu, dạng bảng để mở xem bằng Excel/Sheets. Không dùng làm nguồn khi code |
| `stats.md` | Thống kê đối chiếu handbook §3, bảng điểm đến × loại, 15 mẫu đọc tay |
| `quality_review.csv` | 327 dòng cần kiểm tra: thiếu giá, thiếu toạ độ, mô tả cần đọc lại ngôn ngữ |
| `dedup_report.csv` | 53 cặp trùng đã gộp, kèm điểm khớp tên và khoảng cách toạ độ |
| `map/places.geojson` | 825 điểm có toạ độ, dùng cho bản đồ / lịch trình |
| `map/mymaps-*.csv` | Cùng dữ liệu, định dạng import Google My Maps (khách sạn / vui chơi / sân bay) |
| `map/can-kiem-tra.csv` | 34 dòng toạ độ chưa chắc chắn |

Không kèm HTML/JSON thô đã crawl (`data/raw/`, 42 MB). Chỉ người tiếp quản việc crawl cần,
liên hệ mảng Data nếu bạn phải parse lại.

## 2. Số liệu nhanh

- **2.327 sản phẩm** · 15 điểm đến theo kế hoạch (+5 điểm ngoài kế hoạch, đánh dấu trong `stats.md`)
- Theo loại: hotel 1.489 (582 khách sạn + 907 hạng phòng) · attraction 467 · flight 244 (60 tuyến + 184 chuyến) · combo 121 · golf 6
- Theo nguồn: booking.com 1.092 · vinpearl.com 508 · trip.com 461 · agoda.com 266
- 97,8% mô tả là tiếng Việt · 91,5% có giá · 96,9% có toạ độ

## 3. Schema

```json
{
  "productId": "9d5cd325-a23d-5907-90aa-7286e06d6654",
  "name": "Vinpearl Resort Nha Trang - Deluxe Giường Đôi",
  "taxonomy": "hotel",
  "destination": "Nha Trang",
  "description": "Với diện tích 32 m², Deluxe Giường Đôi là phòng khách sạn thiết kế hiện đại…",
  "attributes": { "level": "room", "starRating": 5, "maxOccupancy": 4, "roomSizeM2": 32, "parentProductId": "…" },
  "unitPrice": 2788898, "currency": "VND", "available": true,
  "availableFrom": null, "availableTo": null,
  "imageUrl": "https://booking-static.vinpearl.com/…jpg",
  "sourceRef": "vinpearl:hotel:1dc9c659-…:room:26863e0c-…"
}
```

- 13 trường trên là schema CDP §6. **Mọi thứ khác nằm trong `attributes`** để không tự thêm field CDP thật không có.
- `productId` = UUIDv5 của `sourceRef` → **ổn định giữa các lần chạy lại**, dùng làm khoá ngoại được.
- `taxonomy`: `hotel` (`attributes.level` = `property`/`room`) · `flight` (`route`/`flight`) · `attraction` · `combo` · `golf`.
- Hạng phòng liên kết về khách sạn qua `attributes.parentProductId`.

## 4. Độ phủ từng trường — đọc trước khi code

| Loại | n | có giá | `imageUrl` | mô tả ≥200 ký tự | sao/hạng | toạ độ | `openingHours` |
|---|---|---|---|---|---|---|---|
| hotel/property | 582 | 96% | 100% | 99% | 91% | 99% | – |
| hotel/room | 907 | 100% | 100% | 99% | 89% | 100% | – |
| attraction | 467 | 66% | 69% | 62% | 54% | 88% | 62% |
| flight | 244 | 100% | **0%** | 88% | – | 100% | – |
| combo | 121 | 90% | 100% | 86% | 100% | 90% | 34% |
| golf | 6 | 83% | 83% | 83% | 83% | 83% | 17% |

## 5. Giá và tình trạng còn chỗ — đọc kỹ

- Toàn bộ giá là **VND**, đã quy đổi nếu nguồn trả tiền khác.
- Giá khách sạn là **1 đêm**, ngày nhận phòng **15/10/2026** (1.481 sản phẩm). Xem `attributes.priceDate`, `priceNights`.
- `available = true` nghĩa là **có giá tại thời điểm crawl**, không phải còn phòng/vé hiện tại.
  Đừng hiển thị như xác nhận đặt được; gọi lại nguồn khi làm luồng đặt thật.
- Giá đối thủ giữ trong `attributes.otaPrices`, giá gốc Vinpearl trong `attributes.vinpearlPrice`.

## 6. Nguồn của từng trường

| Trường | Thứ tự ưu tiên |
|---|---|
| `name`, `description` | **vinpearl.com** → booking.com (nếu tiếng Việt) → agoda.com |
| `unitPrice` | **booking.com → agoda.com → vinpearl.com** |
| toạ độ | nguồn chính; thiếu/nghi sai thì OpenStreetMap (Photon), sân bay từ OurAirports |
| sao, tiện ích | nguồn chính, thiếu thì nguồn khác bù |

Mỗi sản phẩm có `attributes.fieldSources` ghi trường nào lấy từ đâu. Gộp trùng: khớp tên (bỏ dấu, bỏ
"khách sạn/resort/hotel") kết hợp khoảng cách toạ độ, trong cùng điểm đến — chi tiết trong `dedup_report.csv`.

## 7. Điểm yếu đã biết

- **197 sản phẩm thiếu giá** (attraction 158, hotel 26, combo 12, golf 1)
- **72 sản phẩm thiếu toạ độ**; thêm 12 cảnh báo vị trí xa tâm điểm đến (ví dụ Hải Vân Quan gắn Huế nhưng cách tâm 66 km)
- **52 mô tả vẫn là tiếng Anh** (hotel 27, combo 16, attraction 9)
- **1.167/2.327 mô tả là tự sinh**, xem `attributes.descriptionSource`: phòng OTA 791, chuyến bay 244, điểm tham quan 132
- Vé máy bay chỉ phủ 8/15 điểm đến (Hội An, Hạ Long, Sa Pa, Phan Thiết, Hà Tĩnh không có)
- Toàn bộ danh sách cần kiểm tra nằm trong `quality_review.csv`

## 8. Ghi chú theo đội

**Web** — `imageUrl` phủ 83%: toàn bộ 244 vé máy bay không có ảnh, 145/467 điểm tham quan không ảnh,
158 điểm tham quan không giá. Cần placeholder ảnh và trạng thái "liên hệ để biết giá" ngay từ wireframe.
Ảnh phụ nằm trong `attributes.images` (có ở khách sạn và combo, không có ở hạng phòng).

**Agent (trợ lý lịch trình)** — dùng `map/places.geojson`. `openingHours` chỉ có ở 62% điểm tham quan và
34% combo, `durationMinutes` 46% điểm tham quan → chưa đủ xếp lịch theo giờ cho mọi sản phẩm.
Lọc bỏ 72 sản phẩm thiếu toạ độ và đối chiếu 12 cảnh báo vị trí trước khi tính lộ trình.

**RecSys** — 1.167 mô tả tự sinh (mục 7) có cấu trúc khác hẳn mô tả gốc; kiểm tra `attributes.descriptionSource`
trước khi đưa vào text builder. Câu mô tả khách sạn và câu mô tả vé máy bay không nên xây cùng một cách.
52 mô tả tiếng Anh nên lọc hoặc dịch trước khi so sánh mô hình embedding — `all-MiniLM-L6-v2` chỉ hỗ trợ
tiếng Anh, sẽ cho kết quả gần như ngẫu nhiên trên dữ liệu này.

## 9. Pháp lý và dữ liệu cá nhân

- **Không có dữ liệu cá nhân.** Review, tên và ảnh người đánh giá bị xoá trước khi ghi đĩa. Chỉ giữ
  điểm trung bình (`attributes.reviewScore`) và số lượt (`reviewCount`).
- Điều khoản booking.com và agoda.com không cho phép thu thập tự động. **Dữ liệu chỉ dùng nội bộ cho
  demo thực tập, không phân phối lại, không đưa lên repo/trang công khai.**
- Toạ độ OpenStreetMap theo giấy phép ODbL: khi hiển thị bản đồ phải ghi "© OpenStreetMap contributors".
  Toạ độ sân bay từ OurAirports (public domain).
- Không ghi gì vào CDP hay Insider production.

## 10. Tái tạo bộ dữ liệu

Code + hướng dẫn đầy đủ: repo `crawl_data_vsf`, đọc `README.md` (dựng lại được mà không cần đọc code).
Có bản cache `raw/` thì chạy lại không cần tải web:

```
python crawl.py --data-dir ./data reparse <nguồn> && python normalise.py --data-dir ./data
```

Kiểm tra hồi quy: `python -m unittest test_quality test_overnight` (14 test).
