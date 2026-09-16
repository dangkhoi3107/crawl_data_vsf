# Bàn giao catalog du lịch V-OTA — 16/09/2026

Dữ liệu sản phẩm du lịch thật, thu thập theo §3 handbook RecSys internship v3.
Crawl ngày 15–16/09/2026. Người thu thập: mảng Data.

## 1. Đọc gì trước

| Nếu bạn định… | Đọc file này |
|---|---|
| Viết code đọc catalog | **`SCHEMA.md`** — 13 trường, toàn bộ `attributes`, ngữ nghĩa và bẫy thường gặp |
| Thử nhanh không muốn tải 12 MB | **`sample/`** — 50 sản phẩm, liên kết cha–con toàn vẹn, có README riêng |
| Tra một khoá cụ thể bằng code | **`template.json`** — bản máy đọc được, kèm độ phủ và ví dụ thật mỗi biến thể |
| Biết dữ liệu tới đâu, thiếu gì | **`bao-cao-ban-giao.md`** — báo cáo Tuần 1 |

## 2. Gói này có gì

| File | Nội dung |
|---|---|
| `products.jsonl` | **Bản chuẩn.** 2.225 sản phẩm, mỗi dòng 1 JSON đúng 13 trường §6 |
| `products.csv` | Cùng dữ liệu dạng bảng để mở xem. Không dùng làm nguồn khi code |
| `SCHEMA.md` | Tài liệu schema chi tiết |
| `template.json` | Schema dạng máy đọc + độ phủ từng khoá + 7 bản ghi thật làm ví dụ |
| `sample/products-sample.jsonl` · `.csv` · `README.md` | Bộ mẫu 50 sản phẩm để chạy thử |
| `bao-cao-ban-giao.md` | Báo cáo Tuần 1: nghiệm thu handbook, nguồn, những gì đã loại và vì sao |
| `stats.md` | Thống kê đối chiếu §3, bảng điểm đến × loại, mục "Bị loại", mẫu để đọc tay |
| `quality_review.csv` | Danh sách cần kiểm tra còn lại |
| `dedup_report.csv` | Các cặp trùng đã gộp kèm điểm khớp tên và khoảng cách |
| `map/places.geojson` · `mymaps-*.csv` · `can-kiem-tra.csv` | Bản đồ: GeoJSON và định dạng import Google My Maps |

Không kèm HTML/JSON thô đã crawl (`data/raw/`, 42 MB) — chỉ người tiếp quản việc crawl cần.

## 3. Số liệu nhanh

- **2.225 sản phẩm** · 15 điểm đến theo kế hoạch (+5 điểm ngoài kế hoạch, đánh dấu trong `stats.md`)
- Theo loại: khách sạn 559 + hạng phòng 907 · điểm tham quan 416 · vé máy bay 244 (60 tuyến + 184 chuyến) · combo 93 · golf 6
- Theo nguồn: booking.com 1.092 · trip.com 461 · vinpearl.com 429 · agoda.com 243
- **100% mô tả tiếng Việt · 100% có toạ độ** · 93,4% có giá · 89,0% có ảnh (chỉ vé máy bay là không có)

Catalog chỉ giữ sản phẩm hoàn chỉnh: 48 sản phẩm mà nguồn không cung cấp được giá đã bị loại và ghi rõ trong
mục "Bị loại" của `stats.md`. Chi tiết lý do ở mục 4 của báo cáo.

## 4. Ba điều phải biết trước khi dùng

1. **`available = true` không phải là còn phòng.** Nó chỉ nói nguồn có trả giá lúc crawl (15–16/09/2026).
   Đừng hiển thị như xác nhận đặt được; luồng đặt thật phải gọi lại nguồn.
2. **`unitPrice = null` không phải là miễn phí.** 146 sản phẩm còn `null` đều là điểm công cộng không bán vé
   (`attributes.ticketed = false`). Web cần trạng thái hiển thị riêng, không quy về 0 đồng.
3. **57,6% mô tả là tự sinh**, nhận biết qua `attributes.descriptionSource`. Điều khoản vé đã được tách khỏi
   `description` sang `attributes.policies`.

## 5. Độ phủ từng trường — đọc trước khi code

| Loại | n | có giá | ảnh | mô tả ≥200 ký tự | sao/hạng | toạ độ | giờ mở cửa |
|---|---|---|---|---|---|---|---|
| hotel/property | 559 | 100% | 100% | 99% | 91% | 100% | – |
| hotel/room | 907 | 100% | 100% | 99% | 89% | 100% | – |
| attraction | 416 | 65% | 100% | 57% | 48% | 100% | 62% |
| flight | 244 | 100% | **0%** | 86% | – | 100% | – |
| combo | 93 | 100% | 100% | 89% | 100% | 100% | 27% |
| golf | 6 | 83% | 100% | 83% | 83% | 100% | 17% |

Hai chỗ dưới 100% đều thuộc về bản chất dữ liệu: điểm tham quan thiếu giá là điểm công cộng không bán vé;
vé máy bay không có ảnh vì một chuyến bay không có ảnh sản phẩm.

## 6. Ghi chú theo đội

**Web** — `imageUrl` phủ 89,0%. Mọi khách sạn, hạng phòng, điểm tham quan, combo và golf đều có ảnh; chỉ
244 vé máy bay là không, nên chỉ cần placeholder cho loại đó. Việc còn lại là trạng thái hiển thị riêng cho
145 điểm công cộng không bán vé so với sản phẩm chưa có giá — đừng quy về 0 đồng. Ảnh phụ nằm trong
`attributes.images` (1.190 sản phẩm, trung vị 5 ảnh).

**Agent (trợ lý lịch trình)** — dùng `map/places.geojson`; mọi sản phẩm đều có toạ độ nên không phải lọc.
`openingHours` chỉ có ở 62% điểm tham quan và 27% combo, `durationMinutes` 46% điểm tham quan → chưa đủ xếp
lịch theo giờ cho mọi sản phẩm. `locationPrecision = venue` (298 sản phẩm) là vị trí khu vui chơi chứ không
phải vị trí riêng của vé. Đối chiếu 12 cảnh báo vị trí trong `quality_review.csv` trước khi tính lộ trình.

**RecSys** — 1.281 mô tả tự sinh; kiểm tra `attributes.descriptionSource` trước khi đưa vào text builder.
Câu mô tả khách sạn và câu mô tả vé máy bay không nên xây cùng một cách. Sau khi tách điều khoản, chỉ còn
4 nhóm mô tả trùng nhau (8 sản phẩm, đều là hạng phòng cùng loại khác cấu hình giường). Toàn bộ catalog là
tiếng Việt, nên `all-MiniLM-L6-v2` — mô hình chỉ hỗ trợ tiếng Anh mà mọi tutorial đều dùng — sẽ cho kết quả
gần như ngẫu nhiên; cần mô hình đa ngôn ngữ.

## 7. Pháp lý và dữ liệu cá nhân

- **Không có dữ liệu cá nhân.** Review, tên và ảnh người đánh giá bị xoá trước khi ghi đĩa. Chỉ giữ điểm
  trung bình (`attributes.reviewScore`) và số lượt (`reviewCount`).
- Điều khoản booking.com và agoda.com không cho phép thu thập tự động. **Dữ liệu chỉ dùng nội bộ cho demo
  thực tập, không phân phối lại, không đưa lên repo hay trang công khai.**
- Toạ độ OpenStreetMap theo giấy phép ODbL: khi hiển thị bản đồ phải ghi "© OpenStreetMap contributors".
  Toạ độ sân bay từ OurAirports (public domain).
- Không ghi gì vào CDP hay Insider production.

## 8. Tái tạo bộ dữ liệu

Code và hướng dẫn đầy đủ: repo `crawl_data_vsf`, đọc `README.md` (dựng lại được mà không cần đọc code).
Có bản cache `raw/` thì chạy lại không cần tải web:

```
python crawl.py --data-dir ./data reparse <nguồn>
python normalise.py --data-dir ./data      # thêm --keep-unsellable để giữ cả sản phẩm nguồn không có giá
python make_template.py
python make_sample.py
```

Kiểm tra hồi quy: `python -m unittest test_quality test_overnight` (14 test, không cần mạng).
