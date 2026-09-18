# Báo cáo Tuần 1 — Nền tảng dữ liệu

Mảng Data · handbook RecSys internship v3 §3 và §11 · 16/09/2026

## 1. Kết luận

Catalog **đạt toàn bộ mốc nghiệm thu §3** và đã sẵn sàng bàn giao cho ba mảng Web, Agent, RecSys.

**2.216 sản phẩm trên 15 điểm đến.** Mọi sản phẩm đều có mô tả tiếng Việt và toạ độ. Mọi sản phẩm có bán vé
đều có giá — 140 sản phẩm còn `unitPrice = null` đều là điểm công cộng không bán vé, với chúng không có giá
là dữ liệu đúng.

Phần còn thiếu của Tuần 1 là **CDP clone** — chưa dựng schema và chưa nạp danh mục vào cơ sở dữ liệu.
Ba đội đang đọc trực tiếp từ file; cần thay bằng CDP clone trước khi Search nạp vector vào pgvector ở Tuần 2.

| Chỉ số | Giá trị |
|---|---|
| Sản phẩm | 2.216 |
| Điểm đến theo kế hoạch | 15 (thấp nhất Hạ Long 67) |
| Mô tả tiếng Việt | 100% |
| Có toạ độ | 100% |
| Có giá | 93,7% — phần còn lại là điểm công cộng không bán vé |
| Có ảnh | 89,0% — chỉ vé máy bay không có ảnh |

## 2. Đối chiếu nhiệm vụ Tuần 1 (§11, mảng Data)

| Nhiệm vụ | Trạng thái | Bằng chứng |
|---|---|---|
| Dẫn dắt thu thập theo §3 | Xong | 2.216 sản phẩm từ 4 nguồn, 15 điểm đến |
| Cache response thô trước khi parse | Xong | 42 MB HTML/JSON gốc trong `data/raw/`; sửa parser thì `reparse` đọc lại từ cache, không tải lại web |
| Xử lý rate limit và lỗi | Xong | Tự giới hạn tốc độ, kiểm tra `robots.txt`, dừng khi bị chặn và chạy tiếp sau; lỗi xử lý theo từng item |
| Chạy tiếp được khi gián đoạn | Xong | Hàng đợi URL trong `state/crawl_state.sqlite`; toàn bộ 899 URL của kế hoạch ở trạng thái `done` |
| Khử trùng lặp | Xong | 53 cặp giữa các nguồn, thêm 54 biến thể giá thành viên Vinpearl gộp về sản phẩm gốc |
| Chuẩn hoá | Xong | 13 trường CDP §6, toàn bộ VND, `productId` là UUIDv5 ổn định giữa các lần chạy |
| README dựng lại được bộ dữ liệu | Xong | `data-collection/README.md` |
| Kiểm tra hồi quy | Xong | 14 test offline, chạy không cần mạng |
| CDP clone: schema khớp CDP thật | **Chưa làm** | — |
| CDP clone: nạp danh mục và lịch sử khách hàng | **Chưa làm** | — |
| Text builder | Chưa làm | Theo kế hoạch là Tuần 2 |

## 3. Đối chiếu nghiệm thu §3

| Tiêu chí | Kết quả | Đánh giá |
|---|---|---|
| 2.000–5.000 sản phẩm | 2.216 | Đạt |
| 10–15 điểm đến, ≥20 sản phẩm mỗi nơi | 15 điểm, thấp nhất 67 | Đạt |
| Đủ hotel, flight, attraction, combo | Đủ cả bốn, thêm golf | Đạt |
| Mô tả tiếng Việt dùng được cho embedding | 2.216/2.216 — 100% | Đạt |
| Có giá | Mọi sản phẩm bán vé đều có giá | Đạt |
| vinpearl.com là nguồn chính cho tên và mô tả | Ưu tiên Vinpearl → booking → agoda | Đạt |
| Có toạ độ (§3: "nếu có") | 2.216 — 100% | Đạt |
| Khử trùng lặp đa nguồn | 53 cặp giữa 4 nguồn | Đạt |
| Chỉ dữ liệu sản phẩm, không dữ liệu cá nhân | Không có nội dung review, tên hay ảnh người đánh giá | Đạt |

## 4. Đã loại bỏ những gì, và vì sao

Catalog cố ý **chỉ giữ sản phẩm hoàn chỉnh**. Bảng dưới là toàn bộ những gì bị loại, cũng có trong mục
"Bị loại" của `stats.md` — không loại thứ gì mà không ghi lại.

| Lý do loại | Số lượng |
|---|---|
| Không có giá và nguồn không cung cấp được | 48 |
| Đã soát tay và loại (`collectors/excluded_products.csv`) | 10 |
| Biến thể giá thành viên Vinpearl (đã gộp, giá từng hạng giữ trong `memberPrices`) | 53 |
| Khách sạn trùng giữa các nguồn (đã gộp) | 49 |
| Điểm tham quan trip.com trùng vé Vinpearl (đã gộp) | 4 |
| Hạng phòng, chuyến bay của sản phẩm bị loại | 3 |
| Tuyến bay ngoài kế hoạch, vượt hạn mức mỗi điểm đến | 2 |

**Về 48 sản phẩm không có giá.** Gồm 25 vé Vinpearl và 23 khách sạn agoda. Trước khi loại đã thử lấy lại
bằng `crawl.py retry-missing`:

- 25 vé Vinpearl: API chi tiết `booking-tour-api.vinpearl.com` trả **HTTP 500 cho cả 25 vé, trên cả hai kênh
  bán** — 50 lời gọi, thực hiện một ngày sau lượt crawl gốc. Không phải lỗi nhất thời: các bản ghi này hỏng
  ở phía nguồn. 21 trong số đó cũng không có mô tả dùng được.
- 23 khách sạn agoda: hỏi giá lại với ngày nhận phòng khác thu được thêm 3 giá, 23 cái còn lại vẫn trống.

Chúng vừa không đặt được vừa gần như không có nội dung để embedding, nên giữ lại chỉ làm demo có sản phẩm
click vào là cụt. Bản ghi gốc vẫn nằm trong `data/interim/` và `data/raw/`, chạy lại với cờ
`--keep-unsellable` là lấy lại được.

**Về 10 sản phẩm loại sau khi soát tay.** Ghi trong `collectors/excluded_products.csv` kèm lý do và bằng chứng:

- **8 bản ghi nguồn xếp nhầm danh mục.** Danh sách điểm tham quan của trip.com có lẫn văn phòng bảo hiểm
  (Hanwha Life SO Huế), trung tâm tiêm chủng (VNVC Vinh), hãng taxi (Taxi Quy Nhơn Xanh), dịch vụ cho thuê
  xe máy, công ty lữ hành (Sapa Sisters), hãng du thuyền (Bhaya Cruises), đại lý bán vé và một quán cà phê.
- **2 vé mà nguồn trả mô tả của sản phẩm khác.** API Vinpearl trả nội dung Bảo Tàng Gấu Teddy Bear cho vé
  thuyền Water Taxi, và nội dung vé vào cửa VinWonders cho vé Fastpass Water Taxi. Lỗi nằm ở dữ liệu nguồn,
  không phải ở bước parse.

Danh sách này là tệp riêng chứ không nằm trong code, nên thêm hay bớt một dòng là chạy lại `normalise.py`,
và người đọc thấy ngay catalog đã bỏ gì, vì sao.

## 5. Dữ liệu hiện có

### 5.1 Theo loại sản phẩm

| Loại | Số lượng | Ghi chú |
|---|---|---|
| Khách sạn (cơ sở lưu trú) | 559 | 316 khách sạn có hạng phòng đi kèm, trung bình 2,9 hạng phòng mỗi khách sạn |
| Hạng phòng | 907 | Liên kết qua `attributes.parentProductId`; không có hạng phòng nào mất liên kết cha |
| Điểm tham quan, vé | 407 | 199 vé Vinpearl · 69 vé trip.com bán được · 139 điểm công cộng không bán vé |
| Vé máy bay | 244 | 60 tuyến và 184 chuyến cụ thể. VietJet Air 131, Sun PhuQuoc Airways 22, Vietravel Airlines 16, Vietnam Airlines 15 |
| Combo | 93 | Combo nghỉ dưỡng và vé vui chơi Vinpearl |
| Golf | 6 | Voucher sân golf Vinpearl |
| **Tổng** | **2.216** | |

### 5.2 Theo điểm đến

| Điểm đến | Khách sạn + phòng | Vé máy bay | Tham quan | Combo | Golf | Tổng |
|---|---|---|---|---|---|---|
| Nha Trang | 144 | 23 | 63 | 19 | 1 | 250 |
| Phú Quốc | 112 | 37 | 67 | 26 | 1 | 243 |
| Hà Nội | 87 | 33 | 68 | 13 | 0 | 201 |
| Hải Phòng | 126 | 16 | 25 | 8 | 1 | 176 |
| TP. Hồ Chí Minh | 99 | 42 | 21 | 1 | 1 | 164 |
| Đà Nẵng | 93 | 34 | 10 | 0 | 0 | 137 |
| Hội An | 101 | 0 | 23 | 8 | 1 | 133 |
| Nghệ An | 77 | 17 | 27 | 11 | 0 | 132 |
| Đà Lạt | 96 | 16 | 18 | 0 | 0 | 130 |
| Huế | 97 | 14 | 17 | 0 | 0 | 128 |
| Quy Nhơn | 90 | 12 | 16 | 0 | 0 | 118 |
| Phan Thiết | 98 | 0 | 16 | 0 | 1 | 115 |
| Sa Pa | 89 | 0 | 17 | 0 | 0 | 106 |
| Hà Tĩnh | 83 | 0 | 3 | 7 | 0 | 93 |
| Hạ Long | 51 | 0 | 16 | 0 | 0 | 67 |

Thêm 23 sản phẩm Vinpearl ở 5 điểm ngoài kế hoạch (Bắc Ninh 7, Thanh Hóa 4, Quảng Bình 4, Ninh Bình 4,
Tây Ninh 4) — sản phẩm của chính công ty nên giữ lại và đánh dấu riêng.

### 5.3 Độ phủ từng trường

| Loại | n | Có giá | Ảnh | Mô tả ≥200 ký tự | Sao/hạng | Toạ độ | Giờ mở cửa |
|---|---|---|---|---|---|---|---|
| Khách sạn | 559 | 100% | 100% | 99% | 91% | 100% | – |
| Hạng phòng | 907 | 100% | 100% | 99% | 89% | 100% | – |
| Điểm tham quan | 407 | 66% | 100% | 57% | 49% | 100% | 63% |
| Vé máy bay | 244 | 100% | 0% | 86% | – | 100% | – |
| Combo | 93 | 100% | 100% | 89% | 100% | 100% | 27% |
| Golf | 6 | 83% | 100% | 83% | 83% | 100% | 17% |

Hai chỗ còn dưới 100% đều có lý do thuộc về bản chất dữ liệu: điểm tham quan thiếu giá là các điểm công cộng
không bán vé; vé máy bay không có ảnh vì một chuyến bay không có ảnh sản phẩm. Một voucher golf thiếu giá.

### 5.4 Giá

Toàn bộ là VND. Giá khách sạn là giá **một đêm**, hai người lớn. Ngày nhận phòng chủ yếu là 15/10/2026
(1.455 sản phẩm); 11 sản phẩm hỏi cho ngày khác vì phải hỏi lại giá — luôn đọc `attributes.priceDate`
thay vì giả định một ngày.

| Loại | Có giá | Thấp nhất | Trung vị | Cao nhất |
|---|---|---|---|---|
| Khách sạn | 559 | 106.023 | 845.688 | 21.635.008 |
| Hạng phòng | 907 | 110.000 | 1.050.000 | 51.020.000 |
| Điểm tham quan | 271 | 30.000 | 400.000 | 13.600.000 |
| Vé máy bay | 244 | 376.000 | 705.000 | 2.374.000 |
| Combo | 93 | 100.000 | 670.000 | 10.000.000 |
| Golf | 5 | 1.700.000 | 1.700.000 | 1.700.000 |

Giá OTA khác giữ trong `attributes.otaPrices`, giá niêm yết Vinpearl trong `vinpearlPrice`, giá theo hạng
thành viên VinClub trong `memberPrices` (23 vé).

### 5.5 Mô tả — đầu vào chính của embedding

| Loại | Độ dài trung vị | Ngắn nhất | Mô tả tự sinh |
|---|---|---|---|
| Khách sạn và hạng phòng | 921 ký tự | 78 | 800 |
| Golf | 733 ký tự | 140 | 1 |
| Combo | 513 ký tự | 126 | 24 |
| Điểm tham quan | 229 ký tự | 72 | 212 |
| Vé máy bay | 217 ký tự | 169 | 244 |

**1.275/2.216 mô tả (57,5%) là tự sinh**, nhận biết qua `attributes.descriptionSource`. Bảng đầy đủ từng
loại nằm trong `SCHEMA.md` mục 5.

Hai điều đã xử lý ở bước chuẩn hoá và ảnh hưởng trực tiếp tới chất lượng embedding:

- **Điều khoản vé không nằm trong mô tả.** API Vinpearl trả điều khoản lẫn trong khối nội dung, kể cả khối
  mang tiêu đề "Mô tả". Chúng được lọc theo từng dòng và đẩy sang `attributes.policies` (286 sản phẩm).
  Trước bước này, 344 vé dùng chung vài đoạn điều khoản làm mô tả; sau khi tách chỉ còn **4 nhóm mô tả trùng
  nhau, 8 sản phẩm**, và cả 4 đều là hạng phòng cùng loại khác cấu hình giường trong cùng khách sạn.
- **29 sản phẩm mà nguồn chỉ có mô tả tiếng Anh** được dựng mô tả tiếng Việt từ thuộc tính có cấu trúc —
  tên, loại hình, hạng sao, địa chỉ, tiện ích, điểm đánh giá. Tiện ích của booking.com vốn đã là tiếng Việt
  nên phần lớn nội dung vẫn là chữ của nguồn. Văn bản gốc giữ ở `attributes.descriptionOriginal`.

### 5.6 Thuộc tính có cấu trúc

- **Hạng sao:** 1.140 sản phẩm. 5 sao 453 · 4–4,5 sao 264 · 3–3,5 sao 319 · 1–2,5 sao 104.
  897 là hạng sao chính thức, 127 là ước lượng của booking.com.
- **Điểm đánh giá:** 528 sản phẩm có điểm trung bình (trung vị 8,7/10), 687 có số lượt, tổng 726.617 lượt.
  Chỉ là chỉ số tổng hợp — không có nội dung review, tên hay ảnh người đánh giá.
- **Tiện ích:** 1.447 sản phẩm, trung vị 10, nhiều nhất 78.
- **Ảnh:** 1.972 có ảnh chính (mọi loại trừ vé máy bay), 1.181 có thêm ảnh phụ (trung vị 5 ảnh).

### 5.7 Toạ độ

Toàn bộ 2.216 sản phẩm đều có toạ độ.

| Nguồn | Số lượng | | Độ chính xác | Số lượng |
|---|---|---|---|---|
| booking.com | 1.137 | | `exact` — vị trí riêng của sản phẩm | 1.683 |
| trip.com | 413 | | `venue` — khu vui chơi, sân golf dùng vé | 298 |
| OurAirports | 244 | | `airport` — sân bay đến | 244 |
| agoda.com | 240 | | | |
| vinpearl.com | 86 | | | |
| Thủ công, xác minh trên bản đồ | 53 | | | |
| OpenStreetMap (Photon) | 52 | | | |

53 toạ độ điền tay gồm 4 địa điểm Vinpearl mà tìm tự động trả về địa điểm sai tên, 3 khách sạn agoda và sân
golf Vinpearl Léman. Chúng nằm trong `collectors/venues.csv` và `collectors/location_overrides.csv` kèm nguồn
đối chiếu, và không bị máy ghi đè ở các lần chạy sau.

## 6. Nguồn dữ liệu

| Nguồn | Sản phẩm | Cung cấp gì |
|---|---|---|
| booking.com | 1.092 | Độ phủ lưu trú rộng nhất, thuộc tính có cấu trúc phong phú, giá để so sánh |
| trip.com | 453 | Vé máy bay và điểm tham quan — dữ liệu cho gợi ý chéo danh mục ở Tuần 3 |
| vinpearl.com | 428 | Sản phẩm của chính công ty. Mô tả tiếng Việt do công ty viết, chất lượng cao nhất |
| agoda.com | 243 | Bổ sung lưu trú nội địa, mạnh ở cơ sở nhỏ mà booking.com thiếu |

**Thứ tự ưu tiên từng trường** — cùng một cơ sở lưu trú xuất hiện trên nhiều trang với tên, mô tả, giá khác nhau:

| Trường | Ưu tiên | Lý do |
|---|---|---|
| `name`, `description` | vinpearl.com → booking.com (nếu tiếng Việt) → agoda.com | Mô tả Vinpearl là đầu vào embedding tốt nhất |
| `unitPrice`, `available` | booking.com → agoda.com → vinpearl.com | OTA sát thực tế hơn về giá và tình trạng còn chỗ |
| Toạ độ | Nguồn chính → OpenStreetMap; sân bay từ OurAirports | |
| Hạng sao, tiện ích | Nguồn chính, thiếu thì nguồn khác bù | |

Mỗi sản phẩm mang `attributes.fieldSources` nên truy nguồn được từng giá trị.

**Khử trùng lặp:** khớp tên (bỏ dấu, bỏ tiền tố "khách sạn / khu nghỉ dưỡng / hotel", thử cả tên tiếng Anh
trong ngoặc của agoda) kết hợp khoảng cách toạ độ, trong cùng một điểm đến. Mỗi cụm giữ tối đa một bản ghi
của mỗi nguồn. 53 cặp đã gộp, khoảng cách trung vị giữa hai bản ghi trùng là 52 m. Căn hộ và condotel cùng
toà nhà phải đạt ngưỡng giống tên như khách sạn khác — ở gần nhau không đủ để gộp.

**Pháp lý:** điều khoản booking.com và agoda.com không cho phép thu thập tự động — dữ liệu chỉ dùng nội bộ
cho demo thực tập, không phân phối lại, không đưa lên nơi công khai. Toạ độ OpenStreetMap theo giấy phép
ODbL, khi hiển thị bản đồ phải ghi "© OpenStreetMap contributors". Toạ độ sân bay từ OurAirports
(public domain). Không ghi gì vào CDP hay Insider production.

## 7. Gói bàn giao

Gói gửi cho ba đội chỉ gồm những gì cần để dùng dữ liệu:

| File | Nội dung |
|---|---|
| `products.jsonl` | **Bản chuẩn** — 2.216 dòng, mỗi dòng 13 trường CDP §6 |
| `SCHEMA.md` | Tài liệu schema chi tiết: 13 trường, toàn bộ `attributes` theo nhóm, ngữ nghĩa và bẫy thường gặp |
| `template.json` | Bản máy đọc được của schema: 97 khoá `attributes` theo từng loại kèm độ phủ thực tế |
| `sample/` | 50 sản phẩm để chạy thử nhanh, liên kết cha–con toàn vẹn, kèm README riêng |
| `BANGIAO.md` | Tổng quan gói và ghi chú riêng cho từng đội |
| `bao-cao-ban-giao.md` | Báo cáo này |

Các tệp phục vụ kiểm tra chất lượng nằm trong repo chứ không gửi kèm: `stats.md`, `quality_review.csv`
(405 dòng cần soát), `dedup_report.csv` (53 cặp đã gộp), `map/places.geojson`, `products.csv`, cùng
`data/raw/` (42 MB HTML/JSON thô), `data/interim/`, `data/state/`, `data/logs/` và `data/browser-profile/`.

## 8. Còn lại và giới hạn

**Còn lại trong catalog, không phải lỗi:**

- 140 điểm công cộng không bán vé nên không có giá (Phố cổ Hội An, Mỹ Sơn, hòn Thơm…). Giữ lại vì đây chính
  là dữ liệu trợ lý lịch trình Tuần 3 cần nhất. Web cần trạng thái hiển thị riêng, không quy về 0 đồng.
- 244 vé máy bay không có ảnh. Một chuyến bay không có ảnh sản phẩm, nên đây là giới hạn thật của loại dữ liệu.
- 34 mô tả dưới 120 ký tự, gần như toàn bộ là nhóm điểm công cộng trên — nguồn chỉ có tên và địa chỉ.
- 12 cảnh báo vị trí xa tâm điểm đến. Đã soát tay: phần lớn là đúng, do điểm đến là tỉnh chứ không phải
  thành phố (khách sạn Hà Tĩnh ở Xuân Thành, Hải Vân Quan nằm trên ranh giới Huế–Đà Nẵng).
- Vé máy bay không phủ 5/15 điểm đến. Phần lớn là cố ý: Hội An bay tới Đà Nẵng, Hà Tĩnh bay tới Vinh, Sa Pa
  và Phan Thiết không có sân bay. Riêng Hạ Long có cấu hình sân bay Vân Đồn nhưng crawl ra 0 chuyến.

**Giới hạn của phương pháp — không nên diễn giải quá:**

- Nhãn ngôn ngữ ước lượng theo tỷ lệ ký tự có dấu, không phải kiểm tra ngôn ngữ đầy đủ.
- `available` suy ra từ dữ liệu nguồn tại thời điểm crawl, không phải xác nhận đặt chỗ hiện tại.
- Giá là giá quan sát ngày 15–16/09/2026 cho một ngày nhận phòng cụ thể, không phải giá hiện hành.
- Toạ độ `venue` là vị trí khu vui chơi, không phải vị trí riêng của từng vé.

## 9. Việc tiếp theo

1. **CDP clone** — hạng mục Tuần 1 còn lại. Cho tới khi có, ba đội nên đọc catalog qua một lớp loader thay vì
   hard-code đường dẫn file, để đổi sang cơ sở dữ liệu không phải sửa code.
2. **Giờ mở cửa và thời lượng cho điểm tham quan** — mới có ở 62% và 46%. Trợ lý lịch trình Tuần 3 cần dữ
   liệu này; nên bổ sung trước khi vào tuần đó.
3. **Kiểm tra tuyến bay Hạ Long (Vân Đồn)** — điểm đến duy nhất có cấu hình sân bay mà không thu được chuyến nào.
4. **Giá sẽ cũ dần.** Muốn làm mới, chạy lại `crawl.py booking-hotels --checkin <ngày mới>` rồi `normalise.py`;
   `productId` ổn định nên dữ liệu đã nạp vào CDP clone không bị đứt liên kết.
