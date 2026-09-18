# Schema catalog du lịch V-OTA

Tài liệu tham chiếu cho `products.jsonl` · 2.216 sản phẩm · bản 16/09/2026

Bản máy đọc được, liệt kê **mọi** khoá `attributes` theo từng loại kèm độ phủ: **`template.json`** cùng thư mục
(sinh lại bằng `python make_template.py`). Tài liệu này giải thích các khoá quan trọng; `template.json` là danh
sách đầy đủ. Bản ghi thật để đọc và chạy thử: **`sample/`**.

---

## 1. Nguyên tắc

- Mỗi dòng của `products.jsonl` là **một sản phẩm**, gồm **đúng 13 trường** của CDP V-OTA theo §6 handbook.
- Mọi thông tin khác nằm trong `attributes`. Cố ý như vậy: thêm field cấp cao nhất mà CDP thật không có
  sẽ thành cái bẫy cho người tích hợp về sau.
- `products.csv` là cùng dữ liệu ở dạng bảng, chỉ để mở xem. **Khi viết code, đọc `products.jsonl`.**
- Toàn bộ văn bản là tiếng Việt; toàn bộ giá là VND; toàn bộ sản phẩm có toạ độ.

```python
import json
products = [json.loads(line) for line in open("products.jsonl", encoding="utf-8")]
```

## 2. Mười ba trường cấp cao nhất

| Trường | Kiểu | Độ phủ | Ý nghĩa |
|---|---|---|---|
| `productId` | string, UUIDv5 | 100% | Khoá chính. Sinh từ `sourceRef` nên **ổn định giữa các lần chạy lại** — dùng làm khoá ngoại được, không cần lưu bảng ánh xạ |
| `name` | string | 100% | Tên hiển thị. Hạng phòng theo mẫu `"<Khách sạn> - <Hạng phòng>"`, vé máy bay `"Vé máy bay <A> - <B>"` |
| `taxonomy` | enum | 100% | `hotel` · `flight` · `attraction` · `combo` · `golf` |
| `destination` | string | 100% | Nhãn **điểm đến du lịch**, không phải tỉnh hành chính. Tỉnh nằm ở `attributes.province` |
| `description` | string | 100% | Văn bản dùng để embedding. Không chứa điều khoản vé |
| `attributes` | object | 100% | Xem mục 3. Tập khoá thay đổi theo `taxonomy` |
| `unitPrice` | number \| null | 93,7% | Khách sạn: giá **một đêm**. `null` chỉ còn ở điểm công cộng không bán vé |
| `currency` | string | 100% | Luôn là `"VND"` |
| `available` | boolean | 100% | Nguồn có trả giá tại thời điểm crawl. **Không phải xác nhận còn chỗ** |
| `availableFrom` | date \| null | 26% | Vé Vinpearl: ngày bắt đầu bán. Vé máy bay: ngày bay sớm nhất thấy được |
| `availableTo` | date \| null | 26% | Vé Vinpearl: ngày hết hạn bán. Vé máy bay: ngày bay muộn nhất thấy được |
| `imageUrl` | URL \| null | 89,0% | Ảnh chính. Ảnh phụ ở `attributes.images`. Chỉ vé máy bay không có ảnh |
| `sourceRef` | string | 100% | `"<nguồn>:<loại>:<id>"`, ví dụ `vinpearl:tour:VW00466`. Truy ngược về bản ghi gốc |

### Ba chỗ dễ hiểu sai

1. **`available = true` không phải là còn phòng.** Nó chỉ nói nguồn có trả giá lúc crawl (15–16/09/2026).
   Luồng đặt chỗ thật phải gọi lại nguồn.
2. **`unitPrice = null` không phải là miễn phí.** 140 sản phẩm còn `null` đều là điểm công cộng không bán vé
   (`attributes.ticketed = false`) — Phố cổ Hội An, Mỹ Sơn, hòn Thơm. Với chúng, không có giá là dữ liệu đúng.
   Mọi sản phẩm có bán vé đều đã có giá.
3. **`destination` ≠ `province`.** `destination` là nhãn du lịch dùng để lọc và gợi ý (Hội An, Sa Pa);
   `attributes.province` là đơn vị hành chính (Quảng Nam, Lào Cai).

## 3. `attributes` theo nhóm

Độ phủ tính trên toàn bộ 2.216 sản phẩm.

### 3.1 Định danh và liên kết

| Khoá | Kiểu | Độ phủ | Ý nghĩa |
|---|---|---|---|
| `level` | enum | 77% | `property` / `room` cho khách sạn; `route` / `flight` cho vé máy bay. Điểm tham quan, combo, golf không có |
| `parentProductId` | string | 49% | `productId` của khách sạn cha (hạng phòng) hoặc tuyến bay cha (chuyến cụ thể) |
| `url` | URL | 100% | Trang nguồn của sản phẩm |
| `fieldSources` | object | 100% | Trường nào lấy từ nguồn nào, ví dụ `{"unitPrice": "booking.com", "description": "vinpearl"}` |
| `brand` | string | 21% | Thương hiệu, chủ yếu là `Vinpearl` |

### 3.2 Vị trí

| Khoá | Kiểu | Độ phủ | Ý nghĩa |
|---|---|---|---|
| `latitude`, `longitude` | number | 100% | WGS84 |
| `locationSource` | enum | 100% | `booking.com` 1.137 · `trip.com` 413 · `agoda.com` 240 · `ourairports` 244 · `vinpearl` 86 · `manual` 53 · `osm` 52 |
| `locationPrecision` | enum | 100% | `exact` 1.683 — vị trí riêng của sản phẩm · `venue` 298 — khu vui chơi dùng vé · `airport` 244 — sân bay đến |
| `address` | string | 73% | Địa chỉ nguồn cung cấp |
| `province`, `city` | string | 73% / 61% | Đơn vị hành chính |
| `locationWarning` | string | <1% | Toạ độ xa tâm điểm đến bất thường; đã soát tay, phần lớn là đúng vì điểm đến là tỉnh |

`locationPrecision = venue` nghĩa là vé dùng chung toạ độ của khu vui chơi, không phải vị trí riêng —
đúng bản chất của vé vào cửa. 53 toạ độ `manual` được xác minh tay trên bản đồ, ghi nguồn trong
`collectors/venues.csv` và `collectors/location_overrides.csv`.

### 3.3 Mô tả

| Khoá | Kiểu | Độ phủ | Ý nghĩa |
|---|---|---|---|
| `descriptionLang` | enum | 100% | Luôn là `vi` sau chuẩn hoá. Ước lượng theo tỷ lệ ký tự có dấu, không phải kiểm tra ngôn ngữ đầy đủ |
| `descriptionSource` | string | 58% | **Có giá trị nghĩa là mô tả được tự sinh**, không phải văn bản gốc của nguồn. Xem mục 5 |
| `descriptionOriginal` | string | 1% | Văn bản gốc của nguồn khi mô tả đã được dựng lại bằng tiếng Việt (29 sản phẩm) |
| `policies` | object | 13% | Điều khoản, chính sách hoàn huỷ, hướng dẫn sử dụng — tách khỏi `description` để không làm nhiễu embedding |
| `conditions` | array of string | 36% | Điều kiện đặt phòng của hạng phòng OTA, mỗi phần tử một điều kiện |
| `highlights` | array | 12% | Điểm nổi bật do nguồn gắn |

### 3.4 Giá

| Khoá | Kiểu | Độ phủ | Ý nghĩa |
|---|---|---|---|
| `priceDate` | date | 66% | Ngày nhận phòng đã dùng để hỏi giá. **Không đồng nhất**: 1.455 sản phẩm hỏi cho 15/10/2026, 11 sản phẩm còn lại cho ngày khác (29/09, 14/11, 20/11) vì phải hỏi lại giá. Luôn đọc trường này thay vì giả định một ngày |
| `priceNights` | int | 61% | Số đêm của `unitPrice` — luôn là 1 |
| `priceAdults` | int | 25% | Số người lớn đã dùng để hỏi giá — luôn là 2 |
| `otaPrices` | object | 25% | Giá cùng sản phẩm ở các OTA khác, để so sánh |
| `vinpearlPrice` | number | — | Giá niêm yết trên vinpearl.com khi OTA thắng ở `unitPrice` |
| `memberPrices` | object | 1% | Giá theo hạng thành viên VinClub: `{"Gold": …, "Platinum": …, "Diamond": …}` (23 vé) |
| `adultOriginalPrice`, `childPrice` | number | 13% | Giá gốc người lớn trước khuyến mãi, giá trẻ em |

### 3.5 Đặc tính sản phẩm

| Khoá | Kiểu | Độ phủ | Áp dụng cho |
|---|---|---|---|
| `starRating` | number | 51% | Khách sạn, hạng phòng. Phân bố: 5 sao 453 · 4–4,5 sao 264 · 3–3,5 sao 319 · 1–2,5 sao 104 |
| `starRatingType` | enum | 46% | `official` 897 hoặc `booking_estimate` 127 |
| `propertyType` | string | 21% | Loại hình lưu trú |
| `amenities` | array | 65% | Tiện ích, đã gộp từ nhiều nguồn nên có thể trùng ý. Trung vị 10, nhiều nhất 78 |
| `images` | array | 53% | Ảnh phụ, trung vị 5 ảnh |
| `roomName`, `hotelName` | string | 41% | Hạng phòng |
| `roomSizeM2`, `maxOccupancy` | int | 39% / 38% | Diện tích (m²) và sức chứa tối đa của hạng phòng |
| `bed` | string | 35% | Loại giường, chuỗi tự do của nguồn (`"1 giường đôi cực lớn"`) |
| `familyFriendly`, `oceanView` | bool | 43% / 16% | Suy ra từ tên, mô tả và tiện ích |
| `openingHours` | string | 13% | Giờ mở cửa |
| `durationMinutes` | int | 20% | Thời lượng tham quan đề xuất, quy về phút (`"0.5–1 ngày"` → 240). Luôn lớn hơn 0 |
| `venue` | string | 14% | Địa điểm sử dụng vé, tra trong `collectors/venues.csv` |
| `ticketed` | bool | — | `false` = điểm công cộng không bán vé |
| `audience` | array | 13% | Đối tượng phù hợp do nguồn gắn nhãn |

### 3.6 Đánh giá — không có dữ liệu cá nhân

| Khoá | Kiểu | Độ phủ | Ý nghĩa |
|---|---|---|---|
| `reviewScore` | number | 24% | Điểm trung bình, trung vị 8,7 |
| `reviewScoreScale` | number | 24% | Thang điểm, 10 hoặc 5 |
| `reviewCount` | int | 31% | Số lượt đánh giá, tổng 726.617 |

**Không có nội dung review, tên hay ảnh người đánh giá trong catalog.** Chúng bị loại khỏi HTML/JSON trước
khi ghi xuống đĩa, theo §3 handbook. Chỉ giữ chỉ số tổng hợp.

### 3.7 Vé máy bay

| Khoá | Độ phủ | Ý nghĩa |
|---|---|---|
| `originCity`, `destinationCity` | 11% | Thành phố đi và đến |
| `originDestination` | 11% | Nhãn điểm đến của đầu đi, để lọc theo cặp điểm đến |
| `destinationAirportName` | 11% | Tên sân bay đến |
| `originLatitude`, `originLongitude` | 11% | Toạ độ sân bay đi (`latitude`/`longitude` là sân bay đến) |
| `airline`, `flightNumber` | — | VietJet Air 131 · Sun PhuQuoc Airways 22 · Vietravel Airlines 16 · Vietnam Airlines 15 |
| `priceObservedAt` | 11% | Thời điểm quan sát giá vé |

## 4. Bảy biến thể sản phẩm

| Biến thể | Số lượng | `level` | Đặc điểm |
|---|---|---|---|
| `hotel/property` | 559 | `property` | Cơ sở lưu trú. 316 cái có hạng phòng đi kèm, trung bình 2,9 hạng |
| `hotel/room` | 907 | `room` | Hạng phòng, luôn có `parentProductId` |
| `attraction` | 407 | – | 199 vé Vinpearl · 69 vé trip.com bán được · 139 điểm công cộng không bán vé |
| `flight/flight` | 184 | `flight` | Chuyến bay cụ thể, có `parentProductId` trỏ về tuyến |
| `flight/route` | 60 | `route` | Tuyến bay giữa hai thành phố |
| `combo` | 93 | – | Combo nghỉ dưỡng và vé vui chơi Vinpearl |
| `golf` | 6 | – | Voucher sân golf Vinpearl |

## 5. Mô tả tự sinh — đọc trước khi làm text builder

**1.275/2.216 mô tả (57,5%) là tự sinh**, không phải văn bản gốc của nguồn. Nhận biết bằng
`attributes.descriptionSource`:

| Giá trị `descriptionSource` | Số lượng | Dựng từ gì |
|---|---|---|
| `derived: thông tin phòng + mô tả khách sạn` | 771 | Hạng phòng OTA |
| `derived: dữ liệu chuyến bay trip.com` | 244 | Chặng bay, hãng, thời gian bay, giá |
| `derived: loại hình, địa chỉ, giờ mở cửa, thời lượng` | 132 | Điểm tham quan trip.com thiếu phần giới thiệu |
| `derived: mô tả gốc quá ngắn, bổ sung từ thông tin vé` | 57 | Vé Vinpearl |
| `derived: tên vé, thời lượng, đối tượng, địa điểm, giá` | 46 | Vé Vinpearl không có phần giới thiệu |
| `derived: dựng tiếng Việt từ thuộc tính` | 29 | Nguồn chỉ có mô tả tiếng Anh; bản gốc ở `descriptionOriginal` |
| `derived: thông tin phòng (mô tả gốc quá ngắn)` | 2 | Hạng phòng Vinpearl |

Câu mô tả khách sạn và câu mô tả vé máy bay **không nên xây theo cùng một cách** — chúng có cấu trúc khác
hẳn nhau, và điều này ảnh hưởng tới chất lượng embedding nhiều hơn cả việc chọn mô hình.

Độ dài mô tả trung vị theo loại: khách sạn 921 ký tự · golf 733 · combo 513 · điểm tham quan 229 · vé máy bay 217.

## 6. Nguồn của từng trường

| Trường | Thứ tự ưu tiên | Lý do |
|---|---|---|
| `name`, `description` | vinpearl.com → booking.com (nếu tiếng Việt) → agoda.com | Mô tả Vinpearl là đầu vào embedding tốt nhất |
| `unitPrice`, `available` | booking.com → agoda.com → vinpearl.com | OTA sát thực tế hơn về giá và tình trạng còn chỗ |
| toạ độ | Nguồn chính → OpenStreetMap; sân bay từ OurAirports; 53 điểm xác minh tay | |
| hạng sao, tiện ích | Nguồn chính, thiếu thì nguồn khác bù | |

Mỗi sản phẩm mang `attributes.fieldSources` nên truy nguồn được từng giá trị.
Sản phẩm trùng giữa các nguồn đã gộp: 53 cặp, chi tiết trong `dedup_report.csv`.

Ngoài các quy tắc tự động, 10 sản phẩm bị loại sau khi soát tay, lý do ghi trong
`collectors/excluded_products.csv`: 8 bản ghi nguồn xếp nhầm vào danh mục điểm tham quan (văn phòng bảo hiểm,
trung tâm tiêm chủng, hãng taxi, công ty lữ hành…) và 2 vé mà API Vinpearl trả mô tả của sản phẩm khác.

## 7. Bắt đầu nhanh

```python
import json
from collections import Counter

products = [json.loads(l) for l in open("products.jsonl", encoding="utf-8")]

# lọc theo điểm đến và loại
hotels = [p for p in products if p["taxonomy"] == "hotel"
          and p["attributes"].get("level") == "property"
          and p["destination"] == "Nha Trang"]

# hạng phòng của một khách sạn
rooms_of = {}
for p in products:
    parent = p["attributes"].get("parentProductId")
    if parent:
        rooms_of.setdefault(parent, []).append(p)

# văn bản để embedding: bỏ qua hay giữ mô tả tự sinh là quyết định của bạn
texts = [p["description"] for p in products if not p["attributes"].get("descriptionSource")]

print(Counter(p["taxonomy"] for p in products))
```

Bộ mẫu 50 sản phẩm để chạy thử nhanh: `sample/products-sample.jsonl`, xem `sample/README.md`.

## 8. Quy đổi sang hợp đồng API

Catalog và CDP clone giữ dữ liệu **đúng như nguồn**. `ProductSummary` của hợp đồng Backend
(`docs/spec/hop-dong-tich-hop-backend.md` §2) có vài trường dữ liệu không có sẵn ở dạng đó; tầng API quy đổi theo
các quy tắc dưới đây. Số liệu tính trên 2.216 sản phẩm thật.

### 8.1 `rating` và `reviewCount`

Hợp đồng dùng thang 0–5, một chữ số thập phân; `reviewCount` là `null` khi `rating` là `null`.

| Thứ tự | Nguồn | Có ở | Quy đổi |
|---|---|---|---|
| 1 | `reviewScore`, `reviewScoreScale` | 528 sản phẩm, đều thang 10 | `rating = round(reviewScore / reviewScoreScale × 5, 1)`, `reviewCount = reviewCount` |
| 2 | `tripAdvisorRating`, `tripAdvisorReviewCount` | 15 khách sạn Vinpearl, thang 5 | giữ nguyên |
| — | không có điểm | còn lại | `rating = null`, `reviewCount = null` — kể cả 159 sản phẩm có `reviewCount` mà không có điểm |

### 8.2 `attributes`

Hợp đồng chỉ nhận một bộ khoá cố định, giá trị là `true` hoặc vắng mặt, riêng `starRating` là số nguyên. API
**chỉ trả các khoá trong bảng này**; mọi khoá khác trong `attributes` của catalog (mảng `amenities`, `ticketed: false`,
`nonstop: false`…) không đi ra ngoài.

| Khoá hợp đồng | Lấy từ | Số sản phẩm |
|---|---|---|
| `starRating` | `starRating` làm tròn xuống (4,5 sao → 4) | 1.140 |
| `oceanView`, `familyFriendly` | cùng tên, khi là `true` | 358, 952 |
| `directFlight` | `nonstop = true` | 136 |
| `wifi` | `amenities` khớp `wi-fi`, `wifi`, `internet` | 1.093 |
| `pool` | `amenities` khớp `hồ bơi`, `bể bơi`, `pool` | 445 |
| `freeBreakfast` | `amenities` khớp `bữa sáng`, `breakfast` — **cần loại mục ghi có phí** | 330 |
| `spa` | `amenities` khớp `spa`, `massage` | 244 |
| `parking` | `amenities` khớp `chỗ đỗ xe`, `bãi đỗ xe`, `parking` | 150 |
| `shuttle` | `amenities` khớp `đưa đón`, `shuttle` | 89 |
| `nearBeach` | `amenities` khớp `gần biển`, `sát biển`, `bãi biển`, `beachfront` | 73 |
| `privateBeach` | `amenities` khớp `bãi biển riêng`, `private beach` | 50 |
| `kidsClub` | `amenities` khớp `câu lạc bộ trẻ em`, `kids club` | 9 |
| `kidsPool`, `nearCenter`, `baggage`, `indoor`, `outdoor`, `waterPark`, `show`, `buffet`, `seaside`, `caddie` | chưa có nguồn | 0 |

So khớp trên chuỗi đã bỏ dấu và viết thường. Đây là suy luận từ từ khoá, không phải dữ liệu nguồn gắn nhãn sẵn.

### 8.3 `availableFrom`, `availableTo`

Hợp đồng bắt buộc cả hai để kiểm tra `DATE_OUT_OF_RANGE`, nhưng 1.675 sản phẩm không có: **toàn bộ 1.466 khách sạn
và hạng phòng**, 208 điểm tham quan, 1 sân golf. Nguồn không công bố khoảng bán, nên không có giá trị đúng để điền.
Đề xuất cho Backend: khi `null`, dùng cửa sổ đặt chỗ cấu hình được, từ hôm nay đến hôm nay + N ngày, và ghi rõ đây
là giả định của bản demo. Vé máy bay có sẵn khoảng từ ngày bay thấy được (D12).

### 8.4 `unitPrice`

Hợp đồng ghi `unitPrice` bắt buộc là số nguyên, nhưng 140 sản phẩm có `unitPrice = null` (139 điểm tham quan,
1 sân golf), cũng là các sản phẩm `available = false`. Cần Backend chọn: cho phép `null` trong hợp đồng, hoặc không
trả các sản phẩm này ra API. Lưu ý `ticketed = false` của chúng đang được suy ra từ việc thiếu giá nên chưa chắc đúng.
